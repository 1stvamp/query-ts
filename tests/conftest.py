"""Shared fixtures for query-ts tests."""

import pytest


@pytest.fixture(autouse=True)
def clear_tailscale_env(monkeypatch):
    """Isolate tests from any TAILSCALE_* credentials in the real environment."""
    for var in (
        "TAILSCALE_API_KEY",
        "TAILSCALE_OAUTH_CLIENT_ID",
        "TAILSCALE_OAUTH_CLIENT_SECRET",
        "TAILSCALE_TAILNET",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def devices():
    return [
        {
            "id": "1",
            "hostname": "web-prod-1",
            "name": "web-prod-1.tail1234.ts.net",
            "os": "linux",
            "user": "alice@example.com",
            "tags": ["tag:env-production", "tag:role-web"],
            "addresses": ["100.64.0.1"],
            "online": True,
            "lastSeen": "2024-01-15T10:30:00Z",
        },
        {
            "id": "2",
            "hostname": "web-prod-2",
            "name": "web-prod-2.tail1234.ts.net",
            "os": "linux",
            "user": "bob@example.com",
            "tags": ["tag:env-production", "tag:role-web"],
            "addresses": ["100.64.0.2"],
            "online": True,
            "lastSeen": "2024-01-15T11:00:00Z",
        },
        {
            "id": "3",
            "hostname": "api-staging-1",
            "name": "api-staging-1.tail1234.ts.net",
            "os": "linux",
            "user": "alice@example.com",
            "tags": ["tag:env-staging", "tag:role-api"],
            "addresses": ["100.64.0.3"],
            "online": False,
            "lastSeen": "2024-01-10T08:00:00Z",
        },
        {
            "id": "4",
            "hostname": "db-prod-1",
            "name": "db-prod-1.tail1234.ts.net",
            "os": "linux",
            "user": "carol@example.com",
            "tags": ["tag:env-production", "tag:role-db"],
            "addresses": ["100.64.0.4"],
            "online": True,
            "lastSeen": "2024-01-15T09:45:00Z",
        },
        {
            "id": "5",
            "hostname": "laptop-alice",
            "name": "laptop-alice.tail1234.ts.net",
            "os": "macos",
            "user": "alice@example.com",
            "tags": None,
            "addresses": ["100.64.0.5"],
            "online": False,
            "lastSeen": "2024-01-14T20:00:00Z",
        },
    ]


@pytest.fixture
def users():
    return [
        {
            "id": "u1",
            "loginName": "alice@example.com",
            "displayName": "Alice Admin",
            "role": "admin",
            "status": "active",
            "created": "2023-01-01T00:00:00Z",
        },
        {
            "id": "u2",
            "loginName": "bob@example.com",
            "displayName": "Bob Dev",
            "role": "member",
            "status": "active",
            "created": "2023-06-01T00:00:00Z",
        },
        {
            "id": "u3",
            "loginName": "carol@example.com",
            "displayName": "Carol Ops",
            "role": "member",
            "status": "suspended",
            "created": "2023-03-01T00:00:00Z",
        },
    ]


@pytest.fixture
def groups():
    return [
        {"name": "group:admins", "members": ["alice@example.com"]},
        {"name": "group:devs", "members": ["bob@example.com", "alice@example.com"]},
        {"name": "group:ops", "members": ["carol@example.com"]},
    ]


@pytest.fixture
def services():
    return [
        {
            "name": "svc:web",
            "addrs": ["100.93.49.180", "fd7a:115c:a1e0::3456:3cb4"],
            "comment": "Public web service",
            "ports": ["tcp:80", "tcp:443"],
            "tags": ["tag:env-production"],
        },
        {
            "name": "svc:api",
            "addrs": ["100.93.49.181"],
            "comment": "Internal API",
            "ports": ["tcp:8080"],
            "tags": ["tag:env-staging"],
        },
    ]
