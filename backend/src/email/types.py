"""Provider-agnostic email types shared across the send pipeline."""

from typing import TypedDict


class EmailAttachment(TypedDict):
    """In-memory attachment passed to build_rfc822 / Resend.

    ``content`` is raw bytes (not base64) — the sender encodes per its
    own wire format.
    """

    filename: str
    content: bytes
    content_type: str
