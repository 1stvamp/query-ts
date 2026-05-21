from __future__ import annotations

from typing import Any

import httpx


class TailscaleAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class TailscaleClient:
    BASE_URL = "https://api.tailscale.com/api/v2"

    def __init__(
        self,
        api_key: str,
        tailnet: str = "-",
        base_url: str = BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.tailnet = tailnet
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
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
