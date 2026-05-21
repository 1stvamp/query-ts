"""Tests for the Tailscale API client."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from query_ts.api import OAuthTokenManager, TailscaleAPIError, TailscaleClient

BASE = "https://api.tailscale.com/api/v2"
TOKEN_URL = f"{BASE}/oauth/token"
TAILNET = "example.com"


@pytest.fixture
def client():
    return TailscaleClient(api_key="tskey-test-123", tailnet=TAILNET)


# ---------------------------------------------------------------------------
# TailscaleClient — API key auth
# ---------------------------------------------------------------------------


class TestTailscaleClient:
    @respx.mock
    def test_get_devices_success(self, client):
        payload = {
            "devices": [
                {"id": "1", "hostname": "web-1", "tags": ["tag:env-production"]}
            ]
        }
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json=payload)
        )
        devices = client.get_devices()
        assert len(devices) == 1
        assert devices[0]["hostname"] == "web-1"

    @respx.mock
    def test_get_devices_empty(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json={"devices": []})
        )
        assert client.get_devices() == []

    @respx.mock
    def test_get_devices_missing_key(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json={})
        )
        assert client.get_devices() == []

    @respx.mock
    def test_get_users_success(self, client):
        payload = {"users": [{"id": "u1", "loginName": "alice@example.com"}]}
        respx.get(f"{BASE}/tailnet/{TAILNET}/users").mock(
            return_value=httpx.Response(200, json=payload)
        )
        users = client.get_users()
        assert users[0]["loginName"] == "alice@example.com"

    @respx.mock
    def test_get_acl_success(self, client):
        payload = {
            "groups": {"group:admins": ["alice@example.com"]},
            "acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}],
        }
        respx.get(f"{BASE}/tailnet/{TAILNET}/acl").mock(
            return_value=httpx.Response(200, json=payload)
        )
        acl = client.get_acl()
        assert "groups" in acl

    @respx.mock
    def test_get_groups_from_acl(self, client):
        payload = {
            "groups": {
                "group:admins": ["alice@example.com"],
                "group:devs": ["bob@example.com"],
            }
        }
        respx.get(f"{BASE}/tailnet/{TAILNET}/acl").mock(
            return_value=httpx.Response(200, json=payload)
        )
        groups = client.get_groups()
        assert len(groups) == 2
        names = {g["name"] for g in groups}
        assert names == {"group:admins", "group:devs"}

    @respx.mock
    def test_get_groups_empty_acl(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/acl").mock(
            return_value=httpx.Response(200, json={})
        )
        assert client.get_groups() == []

    @respx.mock
    def test_get_services(self, client):
        payload = {
            "devices": [
                {
                    "id": "1",
                    "hostname": "web-1",
                    "services": [
                        {"proto": "tcp", "port": 80, "description": "HTTP"}
                    ],
                }
            ]
        }
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json=payload)
        )
        services = client.get_services()
        assert len(services) == 1
        assert services[0]["device"] == "web-1"
        assert services[0]["proto"] == "tcp"

    @respx.mock
    def test_get_services_no_services(self, client):
        payload = {
            "devices": [{"id": "1", "hostname": "web-1", "services": None}]
        }
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json=payload)
        )
        assert client.get_services() == []

    @respx.mock
    def test_api_error_401(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(401, json={"message": "Unauthorized"})
        )
        with pytest.raises(TailscaleAPIError) as exc_info:
            client.get_devices()
        assert exc_info.value.status_code == 401
        assert "Unauthorized" in exc_info.value.message

    @respx.mock
    def test_api_error_404(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
        with pytest.raises(TailscaleAPIError) as exc_info:
            client.get_devices()
        assert exc_info.value.status_code == 404

    @respx.mock
    def test_api_error_message_from_body(self, client):
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(403, json={"message": "Access denied"})
        )
        with pytest.raises(TailscaleAPIError) as exc_info:
            client.get_devices()
        assert "Access denied" in str(exc_info.value)

    def test_auth_header_set(self, client):
        assert client._client.headers["authorization"] == "Bearer tskey-test-123"

    def test_default_tailnet(self):
        c = TailscaleClient(api_key="key")
        assert c.tailnet == "-"

    def test_context_manager(self):
        with TailscaleClient(api_key="key") as c:
            assert c.tailnet == "-"

    def test_custom_base_url(self):
        c = TailscaleClient(api_key="key", base_url="https://custom.example.com/api/v2")
        assert c.base_url == "https://custom.example.com/api/v2"

    @respx.mock
    def test_injects_custom_client(self):
        custom = httpx.Client(
            base_url=BASE,
            headers={"Authorization": "Bearer test"},
        )
        c = TailscaleClient(api_key="test", client=custom)
        respx.get(f"{BASE}/tailnet/-/devices").mock(
            return_value=httpx.Response(200, json={"devices": []})
        )
        assert c.get_devices() == []

    def test_no_credentials_raises(self):
        with pytest.raises(ValueError, match="api_key or"):
            TailscaleClient()

    def test_both_credentials_raises(self):
        with pytest.raises(ValueError, match="not both"):
            TailscaleClient(
                api_key="key",
                oauth_client_id="id",
                oauth_client_secret="secret",
            )

    def test_partial_oauth_raises(self):
        with pytest.raises(ValueError):
            TailscaleClient(oauth_client_id="id")


# ---------------------------------------------------------------------------
# OAuthTokenManager
# ---------------------------------------------------------------------------


class TestOAuthTokenManager:
    @respx.mock
    def test_fetches_token(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "tok-abc", "expires_in": 3600}
            )
        )
        mgr = OAuthTokenManager("my-id", "my-secret", token_url=TOKEN_URL)
        token = mgr.get_token()
        assert token == "tok-abc"

    @respx.mock
    def test_caches_token(self):
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"access_token": "tok-abc", "expires_in": 3600})

        respx.post(TOKEN_URL).mock(side_effect=handler)
        mgr = OAuthTokenManager("my-id", "my-secret", token_url=TOKEN_URL)
        mgr.get_token()
        mgr.get_token()
        assert call_count == 1

    @respx.mock
    def test_refreshes_expired_token(self):
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"access_token": f"tok-{call_count}", "expires_in": 3600})

        respx.post(TOKEN_URL).mock(side_effect=handler)
        mgr = OAuthTokenManager("my-id", "my-secret", token_url=TOKEN_URL)
        mgr.get_token()
        # Force expiry
        mgr._expires_at = time.monotonic() - 1
        token2 = mgr.get_token()
        assert call_count == 2
        assert token2 == "tok-2"

    @respx.mock
    def test_token_error_raises(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                401, json={"error": "invalid_client", "error_description": "Bad credentials"}
            )
        )
        mgr = OAuthTokenManager("bad-id", "bad-secret", token_url=TOKEN_URL)
        with pytest.raises(TailscaleAPIError) as exc_info:
            mgr.get_token()
        assert exc_info.value.status_code == 401
        assert "Bad credentials" in exc_info.value.message

    @respx.mock
    def test_token_error_fallback_to_error_field(self):
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"error": "unsupported_grant_type"})
        )
        mgr = OAuthTokenManager("id", "secret", token_url=TOKEN_URL)
        with pytest.raises(TailscaleAPIError) as exc_info:
            mgr.get_token()
        assert "unsupported_grant_type" in exc_info.value.message

    def test_auth_header_format(self):
        mgr = OAuthTokenManager("id", "secret", token_url=TOKEN_URL)
        mgr._token = "my-token"
        mgr._expires_at = time.monotonic() + 3600
        assert mgr.auth_header() == "Bearer my-token"


# ---------------------------------------------------------------------------
# TailscaleClient — OAuth auth
# ---------------------------------------------------------------------------


class TestTailscaleClientOAuth:
    def _make_oauth_client(self, token="oauth-token"):
        mock_mgr = MagicMock(spec=OAuthTokenManager)
        mock_mgr.auth_header.return_value = f"Bearer {token}"
        return TailscaleClient(
            oauth_client_id="id",
            oauth_client_secret="secret",
            tailnet=TAILNET,
            _oauth_manager=mock_mgr,
        ), mock_mgr

    @respx.mock
    def test_oauth_sets_auth_header(self):
        c, mgr = self._make_oauth_client("my-oauth-tok")
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json={"devices": []})
        )
        c.get_devices()
        mgr.auth_header.assert_called()

    @respx.mock
    def test_oauth_header_sent_on_request(self):
        c, mgr = self._make_oauth_client("tok-xyz")
        sent_headers = {}

        def capture(request):
            sent_headers.update(dict(request.headers))
            return httpx.Response(200, json={"devices": []})

        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(side_effect=capture)
        c.get_devices()
        assert sent_headers.get("authorization") == "Bearer tok-xyz"

    @respx.mock
    def test_oauth_header_refreshed_per_request(self):
        c, mgr = self._make_oauth_client()
        mgr.auth_header.side_effect = ["Bearer tok-1", "Bearer tok-2"]
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json={"devices": []})
        )
        c.get_devices()
        c.get_devices()
        assert mgr.auth_header.call_count == 2

    def test_oauth_no_static_auth_header(self):
        c, _ = self._make_oauth_client()
        # The underlying httpx client should NOT have a static Authorization header
        assert "authorization" not in c._client.headers

    @respx.mock
    def test_full_oauth_flow(self):
        """Integration: real OAuthTokenManager fetches token then calls API."""
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "live-tok", "expires_in": 3600}
            )
        )
        respx.get(f"{BASE}/tailnet/{TAILNET}/devices").mock(
            return_value=httpx.Response(200, json={"devices": [{"hostname": "x"}]})
        )
        c = TailscaleClient(
            oauth_client_id="id",
            oauth_client_secret="secret",
            tailnet=TAILNET,
        )
        devices = c.get_devices()
        assert devices[0]["hostname"] == "x"
