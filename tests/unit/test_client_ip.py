"""Unit tests for the reverse-proxy-aware client IP extractor.

Without these helpers in front of `request.client.host`, every audit row
on Railway came from `10.156.29.246` — the proxy's internal IP — and the
proposal-view audit (the symptom that triggered this fix) couldn't tell
two devices apart.
"""

from types import SimpleNamespace

from src.core.client_ip import get_client_ip


def _make_request(headers: dict | None = None, client_host: str | None = None):
    """Minimal stub matching the bits of starlette.Request that get_client_ip uses."""
    client = SimpleNamespace(host=client_host) if client_host else None
    # Lowercase keys — starlette normalizes header names on access.
    return SimpleNamespace(headers={k.lower(): v for k, v in (headers or {}).items()}, client=client)


class TestGetClientIp:
    def test_prefers_cf_connecting_ip(self):
        req = _make_request(
            headers={
                "CF-Connecting-IP": "203.0.113.7",
                "X-Forwarded-For": "1.1.1.1",
                "X-Real-IP": "2.2.2.2",
            },
            client_host="10.0.0.1",
        )
        assert get_client_ip(req) == "203.0.113.7"

    def test_falls_back_to_x_forwarded_for_first_hop(self):
        req = _make_request(
            headers={"X-Forwarded-For": "203.0.113.7, 198.51.100.1, 10.0.0.5"},
            client_host="10.0.0.1",
        )
        assert get_client_ip(req) == "203.0.113.7"

    def test_strips_whitespace_in_xff(self):
        req = _make_request(headers={"X-Forwarded-For": "  203.0.113.7  ,  10.0.0.5  "})
        assert get_client_ip(req) == "203.0.113.7"

    def test_x_real_ip_when_xff_absent(self):
        req = _make_request(headers={"X-Real-IP": "203.0.113.9"}, client_host="10.0.0.1")
        assert get_client_ip(req) == "203.0.113.9"

    def test_falls_back_to_request_client_host(self):
        req = _make_request(client_host="198.51.100.1")
        assert get_client_ip(req) == "198.51.100.1"

    def test_returns_none_when_nothing_known(self):
        req = _make_request()
        assert get_client_ip(req) is None
