"""Gmail send helpers."""

from email.message import EmailMessage
from email.utils import make_msgid


def build_rfc822(
    to: str,
    subject: str,
    body_html: str,
    body_text: str,
    from_email: str,
    from_name: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> bytes:
    """Build a multipart/alternative RFC 822 message ready for Gmail API.

    Returns raw bytes; Gmail expects the entire message base64url-encoded.
    """
    domain = from_email.split("@")[-1] if "@" in from_email else "localhost"

    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["Message-ID"] = make_msgid(domain=domain)

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    msg.set_content(body_text, subtype="plain")
    msg.add_alternative(body_html, subtype="html")

    return bytes(msg)
