from __future__ import annotations

import time
from typing import Any

import httpx


class TailscaleAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class OAuthTokenManager:
    """Fetches and caches an OAuth2 client-credentials access token."""

    TOKEN_URL = "https://api.tailscale.com/api/v2/oauth/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str = TOKEN_URL,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token

        response = httpx.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if not response.is_success:
            try:
                body = response.json()
                message = body.get("error_description") or body.get("error") or response.text
            except Exception:
                message = response.text
            raise TailscaleAPIError(response.status_code, message)

        data = response.json()
        self._token = data["access_token"]
        self._expires_at = time.monotonic() + data.get("expires_in", 3600)
        return self._token

    def auth_header(self) -> str:
        return f"Bearer {self.get_token()}"


class TailscaleClient:
    BASE_URL = "https://api.tailscale.com/api/v2"

    def __init__(
        self,
        api_key: str | None = None,
        oauth_client_id: str | None = None,
        oauth_client_secret: str | None = None,
        tailnet: str = "-",
        base_url: str = BASE_URL,
        client: httpx.Client | None = None,
        # Internal: allow injecting a pre-built OAuthTokenManager for testing
        _oauth_manager: OAuthTokenManager | None = None,
    ) -> None:
        if not api_key and not (oauth_client_id and oauth_client_secret):
            raise ValueError(
                "Provide either api_key or both oauth_client_id and oauth_client_secret."
            )
        if api_key and (oauth_client_id or oauth_client_secret):
            raise ValueError("Provide api_key or OAuth credentials, not both.")

        self.tailnet = tailnet
        self.base_url = base_url.rstrip("/")

        if api_key:
            self._oauth: OAuthTokenManager | None = None
            self._client = client or httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
        else:
            self._oauth = _oauth_manager or OAuthTokenManager(
                client_id=oauth_client_id,  # type: ignore[arg-type]
                client_secret=oauth_client_secret,  # type: ignore[arg-type]
            )
            self._client = client or httpx.Client(
                base_url=self.base_url,
                headers={"Accept": "application/json"},
            )

    def _auth_headers(self) -> dict[str, str]:
        if self._oauth:
            return {"Authorization": self._oauth.auth_header()}
        return {}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._oauth:
            existing = kwargs.pop("headers", {})
            kwargs["headers"] = {**self._auth_headers(), **existing}
        response = self._client.request(method, path, **kwargs)
        if not response.is_success:
            try:
                data = response.json()
                message = data.get("message", response.text)
            except Exception:
                message = response.text
            raise TailscaleAPIError(response.status_code, message)
        if not response.content:
            return {}
        return response.json()

    def get_devices(self) -> list[dict]:
        data = self._request("GET", f"/tailnet/{self.tailnet}/devices")
        return data.get("devices", [])

    def get_users(self) -> list[dict]:
        data = self._request("GET", f"/tailnet/{self.tailnet}/users")
        return data.get("users", [])

    def get_acl(self) -> dict:
        return self._request(
            "GET",
            f"/tailnet/{self.tailnet}/acl",
            headers={"Accept": "application/json"},
        )

    def get_groups(self) -> list[dict]:
        acl = self.get_acl()
        groups = acl.get("groups", {})
        return [{"name": k, "members": v} for k, v in groups.items()]

    def get_services(self) -> list[dict]:
        devices = self.get_devices()
        services: list[dict] = []
        for device in devices:
            for svc in device.get("services", []) or []:
                services.append(
                    {
                        "device": device.get("hostname", device.get("name", "")),
                        "device_id": device.get("id", ""),
                        **svc,
                    }
                )
        return services

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TailscaleClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
