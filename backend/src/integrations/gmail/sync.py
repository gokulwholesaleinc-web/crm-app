"""Gmail history sync worker — polls Gmail API and writes EmailQueue / InboundEmail rows."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.client import GmailAuthError, GmailClient
from src.integrations.gmail.models import GmailConnection, GmailSyncState

logger = logging.getLogger(__name__)


class GmailSyncWorker:

    @staticmethod
    async def sync_account(connection: GmailConnection, db: AsyncSession) -> None:
        """Sync one Gmail account forward from its last known historyId."""
        state = await _get_or_create_state(connection, db)
        client = GmailClient(connection, db)

        try:
            if state.last_history_id is None:
                # First run: seed the cursor and return — no messages processed.
                profile = await client.get_profile()
                state.last_history_id = str(profile["historyId"])
                state.last_synced_at = datetime.now(UTC)
                state.failure_count = 0
                state.last_error = None
                db.add(state)
                await db.commit()
                return

            history_records = await client.list_history_since(state.last_history_id)
            max_history_id = state.last_history_id

            for record in history_records:
                record_id = str(record.get("id", ""))
                if record_id and record_id > max_history_id:
                    max_history_id = record_id

                for added in record.get("messagesAdded", []):
                    msg_meta = added.get("message", {})
                    msg_id = msg_meta.get("id")
                    if not msg_id:
                        continue
                    try:
                        await _process_message(msg_id, connection, client, db)
                    except Exception as exc:
                        logger.error(
                            "[gmail_sync] user_id=%s message_id=%s error: %s",
                            connection.user_id, msg_id, exc,
                        )

            state.last_history_id = max_history_id
            state.last_synced_at = datetime.now(UTC)
            state.failure_count = 0
            state.last_error = None
            db.add(state)
            await db.commit()

        except GmailAuthError:
            state.failure_count += 1
            state.last_error = "GmailAuthError: access revoked or token invalid"
            db.add(state)
            await db.commit()
            raise
        except Exception as exc:
            state.failure_count += 1
            state.last_error = str(exc)[:500]
            db.add(state)
            await db.commit()
            raise

    @staticmethod
    async def sync_all_active() -> None:
        """Iterate all non-revoked GmailConnections and sync each."""
        import src.database as db_module

        async with db_module.async_session_maker() as db:
            result = await db.execute(
                select(GmailConnection).where(GmailConnection.revoked_at.is_(None))
            )
            connections = result.scalars().all()

        for conn in connections:
            try:
                async with db_module.async_session_maker() as db:
                    await GmailSyncWorker.sync_account(conn, db)
            except Exception as exc:
                logger.error(
                    "[gmail_sync_all] user_id=%s error: %s", conn.user_id, exc
                )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _get_or_create_state(
    connection: GmailConnection, db: AsyncSession
) -> GmailSyncState:
    result = await db.execute(
        select(GmailSyncState).where(GmailSyncState.user_id == connection.user_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = GmailSyncState(user_id=connection.user_id, failure_count=0)
        db.add(state)
        await db.flush()
    return state


async def _is_duplicate(message_id: str, db: AsyncSession) -> bool:
    """Return True if message_id already exists in email_queue or inbound_emails."""
    from src.email.models import EmailQueue, InboundEmail

    eq = await db.execute(
        select(EmailQueue.id).where(EmailQueue.message_id == message_id).limit(1)
    )
    if eq.scalar_one_or_none() is not None:
        return True

    ib = await db.execute(
        select(InboundEmail.id).where(InboundEmail.message_id == message_id).limit(1)
    )
    return ib.scalar_one_or_none() is not None


async def _process_message(
    msg_id: str,
    connection: GmailConnection,
    client: GmailClient,
    db: AsyncSession,
) -> None:
    msg = await client.get_message(msg_id)
    rfc_message_id = msg["message_id"]

    if rfc_message_id and await _is_duplicate(rfc_message_id, db):
        return

    from_addr = msg["from"]
    received_at: datetime = msg["date"] or datetime.now(UTC)

    if from_addr.lower() == connection.email.lower():
        await _store_sent(msg, connection, db, received_at)
    else:
        await _store_inbound(msg, connection, db, received_at)


async def _resolve_entity_from_thread(
    thread_id: str | None,
    connection: GmailConnection,
    db: AsyncSession,
) -> tuple[str | None, int | None]:
    # Replies sent/received from outside CRM (Gmail web, phone) keep the same
    # Gmail threadId but may use addresses that don't match any contact, so
    # direct email-match misses them. Fall back to any prior row on the thread,
    # scoped to this connection's user so thread_id collisions across tenants
    # can't attach an email to someone else's contact.
    from src.email.models import EmailQueue, InboundEmail

    if not thread_id:
        return None, None

    eq = await db.execute(
        select(EmailQueue.entity_type, EmailQueue.entity_id)
        .where(
            EmailQueue.thread_id == thread_id,
            EmailQueue.sent_by_id == connection.user_id,
            EmailQueue.entity_type.is_not(None),
            EmailQueue.entity_id.is_not(None),
        )
        .limit(1)
    )
    row = eq.first()
    if row is not None:
        return row.entity_type, row.entity_id

    # InboundEmail has no owner column; scope via the receiving mailbox instead.
    ib = await db.execute(
        select(InboundEmail.entity_type, InboundEmail.entity_id)
        .where(
            InboundEmail.thread_id == thread_id,
            InboundEmail.to_email == connection.email,
            InboundEmail.entity_type.is_not(None),
            InboundEmail.entity_id.is_not(None),
        )
        .limit(1)
    )
    row = ib.first()
    if row is not None:
        return row.entity_type, row.entity_id

    return None, None


async def _store_sent(
    msg: dict,
    connection: GmailConnection,
    db: AsyncSession,
    received_at: datetime,
) -> None:
    """Insert an EmailQueue row for an email sent from the user's phone/other client."""
    from src.contacts.models import Contact
    from src.email.models import EmailQueue

    to_addr = msg["to"]

    entity_type: str | None = None
    entity_id: int | None = None
    if to_addr:
        result = await db.execute(
            select(Contact).where(func.lower(Contact.email) == to_addr.lower())
        )
        contact = result.scalar_one_or_none()
        if contact:
            entity_type = "contacts"
            entity_id = contact.id

    if entity_id is None:
        entity_type, entity_id = await _resolve_entity_from_thread(
            msg.get("thread_id"), connection, db
        )

    row = EmailQueue(
        status="sent",
        sent_at=received_at,
        from_email=connection.email,
        to_email=to_addr,
        subject=msg["subject"] or "",
        body=msg["body_text"] or msg["body_html"] or "",
        message_id=msg["message_id"],
        thread_id=msg["thread_id"],
        sent_via="gmail",
        sent_by_id=connection.user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(row)
    await db.flush()


async def _store_inbound(
    msg: dict,
    connection: GmailConnection,
    db: AsyncSession,
    received_at: datetime,
) -> None:
    """Insert an InboundEmail row for a message received by this account."""
    from src.contacts.models import Contact
    from src.email.models import InboundEmail

    from_addr = msg["from"]

    entity_type: str | None = None
    entity_id: int | None = None
    if from_addr:
        result = await db.execute(
            select(Contact).where(func.lower(Contact.email) == from_addr.lower())
        )
        contact = result.scalar_one_or_none()
        if contact:
            entity_type = "contacts"
            entity_id = contact.id

    if entity_id is None:
        entity_type, entity_id = await _resolve_entity_from_thread(
            msg.get("thread_id"), connection, db
        )

    # resend_email_id is required by the model's unique constraint; use Gmail message id
    row = InboundEmail(
        resend_email_id=f"gmail:{msg['raw_payload'].get('id', msg['message_id'])}",
        from_email=from_addr,
        to_email=msg["to"],
        cc=msg.get("cc") or None,
        subject=msg["subject"] or "",
        body_text=msg["body_text"],
        body_html=msg["body_html"],
        message_id=msg["message_id"],
        in_reply_to=msg.get("in_reply_to") or None,
        thread_id=msg.get("thread_id") or None,
        received_at=received_at,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(row)
    await db.flush()
