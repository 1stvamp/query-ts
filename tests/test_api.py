"""Tests for the Tailscale API client."""

import json

import httpx
import pytest
import respx

from query_ts.api import TailscaleAPIError, TailscaleClient

BASE = "https://api.tailscale.com/api/v2"
TAILNET = "example.com"


@pytest.fixture
def client():
    return TailscaleClient(api_key="tskey-test-123", tailnet=TAILNET)


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
        # API might return without the wrapping key
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
            return_value=httpx.Response(
                401, json={"message": "Unauthorized"}
            )
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
            return_value=httpx.Response(
                403, json={"message": "Access denied"}
            )
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
