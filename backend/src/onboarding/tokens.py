"""Token + bearer-session + verify-throttle primitives for packets.

Three concerns, all stateless except the verify throttle:

  * **Access / download tokens** — high-entropy ``secrets.token_urlsafe(32)``
    raw values; only their SHA-256 hash is persisted. Lookup is by hash with
    a constant-time compare, so a leaked DB row never reveals a usable link.
  * **Bearer session** — after the recipient passes the e-mail gate we hand
    them a short-lived HMAC-signed token (``payload.signature``) carried in
    the ``X-Onboarding-Session`` header. Stateless: no DB session table. The
    HMAC key is the app ``SECRET_KEY`` (same secret as the JWT auth tokens).
  * **Verify throttle** — an in-memory ``(token_hash, client_ip)`` counter
    that backs off brute-force e-mail guessing. Per-process only; fine for a
    single instance. Multi-instance scaling would need a shared store (Redis)
    — call that out before relying on this across replicas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from src.config import settings

# --------------------------------------------------------------------------
# Raw tokens + hashes
# --------------------------------------------------------------------------


def mint_token() -> str:
    """Return a fresh high-entropy raw token (never persisted as-is)."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """SHA-256 hex of a raw token — the at-rest representation."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_hash(raw: str, stored_hash: str | None) -> bool:
    """Constant-time check that ``raw`` hashes to ``stored_hash``."""
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_token(raw), stored_hash)


# --------------------------------------------------------------------------
# Bearer session (HMAC, stateless)
# --------------------------------------------------------------------------

SESSION_TTL_SECONDS = 45 * 60  # signer has 45 min after passing the e-mail gate


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url(sig)


def sign_session(*, packet_id: int, token_hash: str, signer_email: str) -> str:
    """Mint a signed bearer-session token bound to this packet + signer."""
    payload = {
        "packet_id": packet_id,
        "token_hash": token_hash,
        "signer_email": signer_email,
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_session(token: str | None) -> dict | None:
    """Return the session payload if the token is valid + unexpired, else None.

    Verifies the HMAC in constant time and rejects an expired or malformed
    token. Caller must additionally confirm ``packet_id`` / ``token_hash``
    match the packet looked up from the URL.
    """
    if not token or "." not in token:
        return None
    payload_b64, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    return payload


# --------------------------------------------------------------------------
# In-memory verify throttle (token_hash, client_ip)
# --------------------------------------------------------------------------

# NOTE: per-process state. Single-instance only; a multi-replica deployment
# would need a shared store (e.g. Redis) to enforce this globally.
_VERIFY_MAX_ATTEMPTS = 5
_VERIFY_LOCKOUT_SECONDS = 15 * 60
# A high per-token ceiling so one attacker IP can't lock out the real signer:
# the per-(hash, ip) lockout is the primary control; this only caps absurd
# distributed guessing on a single token.
_verify_state: dict[tuple[str, str | None], tuple[int, float]] = {}


def verify_throttle_blocked(token_hash: str, client_ip: str | None) -> bool:
    """True if this (token, ip) is currently locked out."""
    attempts, locked_until = _verify_state.get((token_hash, client_ip), (0, 0.0))
    return attempts >= _VERIFY_MAX_ATTEMPTS and locked_until > time.time()


def verify_throttle_record_failure(token_hash: str, client_ip: str | None) -> None:
    """Record a failed verify attempt and (re)arm the lockout window."""
    key = (token_hash, client_ip)
    attempts, _ = _verify_state.get(key, (0, 0.0))
    attempts += 1
    _verify_state[key] = (attempts, time.time() + _VERIFY_LOCKOUT_SECONDS)


def reset_throttle(token_hash: str, client_ip: str | None = None) -> None:
    """Clear throttle state for a token (success / staff resend / revoke).

    With ``client_ip`` clears just that IP's counter; without it clears every
    IP recorded against the token (used by staff resend/revoke).
    """
    if client_ip is not None:
        _verify_state.pop((token_hash, client_ip), None)
        return
    for key in [k for k in _verify_state if k[0] == token_hash]:
        _verify_state.pop(key, None)


def _clear_all_throttle() -> None:
    """Test hook — drop all throttle state."""
    _verify_state.clear()
