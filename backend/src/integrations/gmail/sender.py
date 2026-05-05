"""Gmail send helpers."""

from email.message import EmailMessage
from email.utils import make_msgid

from src.email.types import EmailAttachment

__all__ = ["build_rfc822", "EmailAttachment", "make_rfc_message_id"]


def make_rfc_message_id(from_email: str) -> str:
    """Generate a fresh RFC 5322 Message-ID for an outgoing message.

    Lifted out so the sender path can capture the same id it sets on
    the RFC-822 envelope and persist it to ``EmailQueue.message_id``.
    Without this, the Gmail sync worker re-ingests every outbound CRM
    send as a fresh row when polling history, because its dedup key
    (the RFC Message-ID header) doesn't match the Gmail internal id
    that we used to store on EmailQueue.
    """
    domain = from_email.split("@")[-1] if "@" in from_email else "localhost"
    return make_msgid(domain=domain)


def build_rfc822(
    to: str,
    subject: str,
    body_html: str,
    body_text: str,
    from_email: str,
    from_name: str,
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: list[EmailAttachment] | None = None,
    message_id: str | None = None,
) -> bytes:
    """Build a multipart/alternative RFC 822 message ready for Gmail API.

    Returns raw bytes; Gmail expects the entire message base64url-encoded.
    Attachments are appended as additional MIME parts after the HTML body.

    ``message_id`` lets the caller pre-generate the RFC Message-ID so
    the same value can be persisted to the EmailQueue row. When
    omitted, a fresh one is generated (used by callers that don't
    need to dedup against history later).
    """
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["Message-ID"] = message_id or make_rfc_message_id(from_email)

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    msg.set_content(body_text, subtype="plain")
    msg.add_alternative(body_html, subtype="html")

    for att in attachments or []:
        maintype, _, subtype = att["content_type"].partition("/")
        msg.add_attachment(
            att["content"],
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att["filename"],
        )

    return bytes(msg)
