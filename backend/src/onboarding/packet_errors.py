"""Phase-2 packet service exceptions, mapped to HTTP by validation.py.

Mirrors the Phase-1 convention (``service.py``): each class is deliberately
NOT a ``ValueError`` subclass unless a 400 is genuinely wanted, so a stray
``value_error_as_400`` can't silently downgrade a 409/422/503 into a 400.
"""


class PacketRaceError(Exception):
    """Optimistic-lock / claim-race / wrong-status conflict → HTTP 409.

    Raised when a version drifts (``base_version`` / ``base_signature_version``
    mismatch), the completion claim loses the race, or a mutation targets a
    packet whose status no longer permits it (e.g. ``completing``). NOT a
    ``ValueError``.
    """


class PacketValidationError(Exception):
    """Recipient-supplied data failed validation / overflow → HTTP 422.

    Deliberately NOT a ``ValueError`` so it can never be downgraded to a 400,
    and the route never truncates the offending payload — it rejects whole.
    """


class PacketInfraError(Exception):
    """Storage / stamping / infrastructure failure → HTTP 503. NOT a ValueError."""


class PacketGoneError(Exception):
    """Packet is in a terminal-dead state (expired/revoked/abandoned) → HTTP 410."""


class PacketNotFoundError(Exception):
    """Token not found, or expired before terminal handling → HTTP 404."""
