"""Unit tests for the MailchimpClient transport layer.

Uses httpx.MockTransport so we exercise the real client code (auth
header, URL composition, JSON decoding, error mapping) without making
network calls.
"""

import hashlib

import httpx
import pytest

from src.integrations.mailchimp.client import (
    MailchimpClient,
    MailchimpError,
    split_api_key,
    subscriber_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _route(handlers: dict[tuple[str, str], httpx.Response | dict | tuple]) -> httpx.MockTransport:
    """Build a MockTransport that dispatches by (method, path) match.

    A handler value of dict → 200 JSON body.
    A handler value of (status, dict) → that status with that JSON body.
    A handler value of httpx.Response → returned verbatim.
    Unmatched routes return 599 so missed expectations are loud.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), request.url.path)
        spec = handlers.get(key)
        if spec is None:
            return httpx.Response(599, json={"detail": f"unmocked {key}"})
        if isinstance(spec, httpx.Response):
            return spec
        if isinstance(spec, tuple):
            status, body = spec
            return httpx.Response(status, json=body)
        return httpx.Response(200, json=spec)

    return httpx.MockTransport(handler)


def _client(transport: httpx.MockTransport, server_prefix: str = "us19") -> MailchimpClient:
    return MailchimpClient("apikey-us19", server_prefix, transport=transport)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestApiKeyHelpers:
    def test_split_api_key_returns_full_key_and_dc(self):
        key, dc = split_api_key("abc123-us19")
        assert key == "abc123-us19"
        assert dc == "us19"

    def test_split_api_key_rejects_keys_without_dc(self):
        with pytest.raises(ValueError):
            split_api_key("nodatacenter")

    def test_split_api_key_rejects_empty_dc(self):
        with pytest.raises(ValueError):
            split_api_key("abc-")

    def test_subscriber_hash_is_md5_lowercased(self):
        expected = hashlib.md5(b"foo@example.com").hexdigest()
        assert subscriber_hash("FOO@Example.COM") == expected
        assert subscriber_hash("  foo@example.com  ") == expected


# ---------------------------------------------------------------------------
# Transport behaviour
# ---------------------------------------------------------------------------


class TestPing:
    @pytest.mark.asyncio
    async def test_ping_decodes_health_status(self):
        transport = _route({("GET", "/3.0/ping"): {"health_status": "Everything's Chimpy!"}})
        async with _client(transport) as mc:
            data = await mc.ping()
        assert data["health_status"] == "Everything's Chimpy!"

    @pytest.mark.asyncio
    async def test_ping_raises_mailchimp_error_on_401(self):
        transport = _route({("GET", "/3.0/ping"): (401, {"detail": "Bad credentials"})})
        async with _client(transport) as mc:
            with pytest.raises(MailchimpError) as ei:
                await mc.ping()
        assert ei.value.status_code == 401
        assert "Bad credentials" in str(ei.value)


class TestAudiences:
    @pytest.mark.asyncio
    async def test_list_audiences_returns_lists_array(self):
        transport = _route({
            ("GET", "/3.0/lists"): {
                "lists": [
                    {"id": "abc", "name": "Newsletter", "stats": {"member_count": 42}},
                    {"id": "def", "name": "VIPs", "stats": {"member_count": 7}},
                ]
            }
        })
        async with _client(transport) as mc:
            data = await mc.list_audiences()
        ids = [lst["id"] for lst in data["lists"]]
        assert ids == ["abc", "def"]


class TestMembers:
    @pytest.mark.asyncio
    async def test_upsert_member_uses_md5_subscriber_hash(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = request.read().decode()
            return httpx.Response(200, json={"id": "fakehash", "email_address": "a@b.com"})

        transport = httpx.MockTransport(handler)
        async with _client(transport) as mc:
            await mc.upsert_member(
                "list1",
                "A@B.com",
                merge_fields={"FNAME": "Ada"},
                tags=["beta"],
            )
        expected_hash = hashlib.md5(b"a@b.com").hexdigest()
        assert captured["method"] == "PUT"
        assert captured["path"] == f"/3.0/lists/list1/members/{expected_hash}"
        assert "status_if_new" in captured["body"]


class TestCampaigns:
    @pytest.mark.asyncio
    async def test_create_regular_campaign_posts_recipients_and_settings(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            captured["body"] = _json.loads(request.read())
            return httpx.Response(200, json={"id": "campaign-1"})

        transport = httpx.MockTransport(handler)
        async with _client(transport) as mc:
            data = await mc.create_regular_campaign(
                list_id="L1",
                subject="Hello",
                from_name="CRM",
                reply_to="me@example.com",
                title="Hello — step 1",
            )
        assert data["id"] == "campaign-1"
        body = captured["body"]
        assert body["type"] == "regular"
        assert body["recipients"] == {"list_id": "L1"}
        assert body["settings"]["subject_line"] == "Hello"
        assert body["settings"]["title"] == "Hello — step 1"

    @pytest.mark.asyncio
    async def test_send_campaign_sends_action(self):
        transport = _route({
            ("POST", "/3.0/campaigns/c1/actions/send"): httpx.Response(204),
        })
        async with _client(transport) as mc:
            data = await mc.send_campaign("c1")
        assert data == {}


class TestUrlComposition:
    @pytest.mark.asyncio
    async def test_uses_server_prefix_subdomain(self):
        captured_url = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_url["host"] = request.url.host
            return httpx.Response(200, json={"health_status": "ok"})

        transport = httpx.MockTransport(handler)
        async with MailchimpClient(
            "key-us99", "us99", transport=transport
        ) as mc:
            await mc.ping()
        assert captured_url["host"] == "us99.api.mailchimp.com"
