from __future__ import annotations

from typing import Any

import httpx

from bot.config import API_SECRET, BACKEND_URL


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_SECRET, "Content-Type": "application/json"}


class BackendClient:
    def __init__(self) -> None:
        # trust_env=False prevents system HTTP(S)_PROXY from intercepting localhost with 502
        self._client = httpx.AsyncClient(
            base_url=BACKEND_URL,
            headers=_headers(),
            timeout=60.0,
            trust_env=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def user_create(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        referrer_telegram_id: int | None = None,
    ) -> dict[str, Any]:
        r = await self._client.post(
            "/user/create",
            json={
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "referrer_telegram_id": referrer_telegram_id,
            },
        )
        r.raise_for_status()
        return r.json()

    async def user_by_telegram(self, telegram_id: int) -> dict[str, Any]:
        r = await self._client.get(f"/user/telegram/{telegram_id}")
        r.raise_for_status()
        return r.json()

    async def vpn_keys(self, user_id: int) -> list[dict[str, Any]]:
        r = await self._client.get(f"/vpn/keys/{user_id}")
        r.raise_for_status()
        return r.json()

    async def create_trial(self, user_id: int) -> dict[str, Any]:
        r = await self._client.post("/vpn/create_trial", json={"user_id": user_id})
        r.raise_for_status()
        return r.json()

    async def sync_pool(self, user_id: int) -> list[dict[str, Any]]:
        r = await self._client.post("/vpn/sync_pool", json={"user_id": user_id})
        r.raise_for_status()
        return r.json()

    async def vless_export(self, user_id: int) -> dict[str, Any]:
        r = await self._client.post("/vpn/vless_export", json={"user_id": user_id})
        r.raise_for_status()
        return r.json()

    async def catalog(self) -> dict[str, Any]:
        r = await self._client.get("/catalog")
        r.raise_for_status()
        return r.json()

    async def create_invoice(self, user_id: int, plan_days: int, amount: str, currency: str = "USDT") -> dict[str, Any]:
        r = await self._client.post(
            "/payment/create_invoice",
            json={"user_id": user_id, "plan_days": plan_days, "amount": amount, "currency": currency},
        )
        r.raise_for_status()
        return r.json()

    def get_sub_url(self, base_url: str, sub_token: str) -> str:
        return f"{base_url.rstrip('/')}/vpn/sub/{sub_token}"
