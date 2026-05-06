"""Gmail history sync worker — polls Gmail API and writes EmailQueue / InboundEmail rows."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.client import GmailAuthError, GmailClient
from src.integrations.gmail.models import GmailBackfillState, GmailConnection, GmailSyncState

# Backfill loop is deliberately sequential (per-message awaits in a for-
# loop) so we don't bombard Gmail's per-account rate limits. Removed a
# module-level Semaphore that was process-wide and shared across users —
# under the sequential loop it never throttled anything, but if anyone
# ever switches to asyncio.gather() it would silently serialize across
# tenants. If concurrency comes back, instantiate the Semaphore inside
# `backfill()` so the limit is per-invocation.

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

        except GmailAuthError as exc:
            # Google revoked / invalidated the credential. Flip the
            # connection to revoked so (a) the scheduler stops retrying it
            # forever and (b) the Settings + Emails-tab UI can surface a
            # "Reconnect Gmail" prompt instead of pretending all is well.
            state.failure_count += 1
            state.last_error = f"GmailAuthError: {exc}"
            connection.revoked_at = datetime.now(UTC)
            db.add(state)
            db.add(connection)
            await db.commit()
            raise
        except Exception as exc:
            state.failure_count += 1
            state.last_error = str(exc)[:500]
            db.add(state)
            await db.commit()
            raise

    @staticmethod
    async def backfill(connection: GmailConnection, db: AsyncSession, days: int = 365) -> None:
        """Backfill historical Gmail messages for a connection.

        Walks messages.list since (now - days), calls _process_message for each
        so thread-linking, contact matching, and entity resolution behave
        identically to the forward-going sync. Idempotent: skips messages
        whose gmail_message_id is already stored (checked via _is_duplicate on
        the RFC Message-ID header after fetching the full message).

        Throttled to at most 10 concurrent get_message calls. A small sleep
        between pages avoids bursting the Gmail API quota.
        """
        days = min(days, 3650)
        start_date = datetime.now(UTC) - timedelta(days=days)

        state = await _get_or_create_backfill_state(connection.user_id, db)
        state.status = "running"
        state.started_at = datetime.now(UTC)
        state.finished_at = None
        state.error = None
        state.processed_count = 0
        state.total_count = 0
        db.add(state)
        await db.commit()

        try:
            async with GmailClient(connection, db) as client:
                msg_ids = await client.list_messages_since(start_date)
                state.total_count = len(msg_ids)
                db.add(state)
                await db.commit()

                async def _fetch_one(msg_id: str) -> None:
                    try:
                        await _process_message(msg_id, connection, client, db)
                    except GmailAuthError:
                        raise
                    except IntegrityError:
                        # A racing forward-sync (or rerun) already wrote
                        # this message under the unique constraint on
                        # InboundEmail.resend_email_id ('gmail:<id>').
                        # Treat as idempotent: rollback the failed insert
                        # and move on so progress count stays accurate.
                        await db.rollback()
                        logger.debug(
                            "[gmail_backfill] user_id=%s message_id=%s already stored (race), skipping",
                            connection.user_id, msg_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[gmail_backfill] user_id=%s message_id=%s error: %s",
                            connection.user_id, msg_id, exc,
                        )

                for i, msg_id in enumerate(msg_ids):
                    await _fetch_one(msg_id)
                    state.processed_count = i + 1
                    # Flush progress to DB every 50 messages so the UI stays live.
                    if (i + 1) % 50 == 0:
                        db.add(state)
                        await db.commit()
                    # Yield to event loop briefly between pages of 500
                    if (i + 1) % 500 == 0:
                        await asyncio.sleep(0.1)

            state.status = "complete"
            state.finished_at = datetime.now(UTC)
            db.add(state)
            await db.commit()

        except GmailAuthError as exc:
            state.status = "failed"
            state.error = f"GmailAuthError: {exc}"
            state.finished_at = datetime.now(UTC)
            connection.revoked_at = datetime.now(UTC)
            db.add(state)
            db.add(connection)
            await db.commit()
            raise
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)[:500]
            state.finished_at = datetime.now(UTC)
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

async def _get_or_create_backfill_state(
    user_id: int, db: AsyncSession
) -> GmailBackfillState:
    result = await db.execute(
        select(GmailBackfillState).where(GmailBackfillState.user_id == user_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = GmailBackfillState(user_id=user_id)
        db.add(state)
        await db.flush()
    return state


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
    from src.email.models import EmailQueue

    to_addr = msg["to"]
    recipients = _collect_recipients(msg)

    entity_type, entity_id = await _resolve_contact_by_addresses(recipients, db)

    if entity_id is None:
        entity_type, entity_id = await _resolve_entity_from_thread(
            msg.get("thread_id"), connection, db
        )

    row = EmailQueue(
        status="sent",
        sent_at=received_at,
        from_email=connection.email,
        to_email=to_addr,
        cc=_join_recipients(msg.get("cc_list") or []) or msg.get("cc") or None,
        bcc=_join_recipients(msg.get("bcc_list") or []) or msg.get("bcc") or None,
        subject=msg["subject"] or "",
        body=msg["body_text"] or msg["body_html"] or "",
        message_id=msg["message_id"],
        thread_id=msg["thread_id"],
        sent_via="gmail",
        sent_by_id=connection.user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        participant_emails=recipients,
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
    from src.email.models import InboundEmail

    from_addr = msg["from"]
    recipients = _collect_recipients(msg)

    entity_type, entity_id = await _resolve_contact_by_addresses(recipients, db)

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
        bcc=msg.get("bcc") or None,
        subject=msg["subject"] or "",
        body_text=msg["body_text"],
        body_html=msg["body_html"],
        message_id=msg["message_id"],
        in_reply_to=msg.get("in_reply_to") or None,
        thread_id=msg.get("thread_id") or None,
        received_at=received_at,
        entity_type=entity_type,
        entity_id=entity_id,
        participant_emails=recipients,
    )
    db.add(row)
    await db.flush()


def _collect_recipients(msg: dict) -> list[str]:
    """Aggregate every address on a parsed Gmail message for contact match.

    Includes from + every entry of To/CC/BCC. We dedupe case-insensitively
    while preserving order so the first match wins (matters when two
    different contacts both appear on the same thread — the sender's
    contact takes precedence).
    """
    seen: set[str] = set()
    out: list[str] = []
    candidates: list[str] = []
    if msg.get("from"):
        candidates.append(msg["from"])
    candidates.extend(msg.get("to_list") or [])
    candidates.extend(msg.get("cc_list") or [])
    candidates.extend(msg.get("bcc_list") or [])
    for addr in candidates:
        key = (addr or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _join_recipients(addrs: list[str]) -> str:
    """Comma-join a list of addresses for the cc/bcc text columns."""
    return ", ".join(a for a in addrs if a)


async def _resolve_contact_by_addresses(
    addresses: list[str], db: AsyncSession
) -> tuple[str | None, int | None]:
    """Return ('contacts', id) for the first contact matching any of `addresses`.

    Used by the inbound + sent ingestion path so a CRM contact in CC or
    position 2+ of the To: header still links the row to that contact
    instead of leaving entity_id NULL.

    Delegates to `find_contact_id_by_any_email` which checks both the primary
    email column AND `contact_email_aliases`, preserves caller-supplied
    priority ordering (from > to-list > cc-list > bcc-list), and skips
    soft-deleted contacts.
    """
    from src.contacts.alias_match import find_contact_id_by_any_email
    return await find_contact_id_by_any_email(addresses, db)
