from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Server
from app.services.notifier import notify_admins

log = logging.getLogger(__name__)


async def check_server(session: AsyncSession, server: Server) -> tuple[bool, float | None]:
    url = server.health_check_url or f"https://{server.host}:{server.port}/"
    start = time.perf_counter()
    ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            r = await client.get(url)
            ok = r.status_code < 500
    except Exception as e:
        log.debug("health %s: %s", url, e)
        ok = False
    latency = (time.perf_counter() - start) * 1000.0
    server.last_latency_ms = latency
    server.last_online = ok
    server.last_checked_at = datetime.now(timezone.utc)
    await session.commit()
    return ok, latency


async def check_all_servers(session: AsyncSession, notify_on_failure: bool = False) -> dict[int, bool]:
    servers = list((await session.scalars(select(Server))).all())
    results: dict[int, bool] = {}
    for s in servers:
        ok, _ = await check_server(session, s)
        results[s.id] = ok
        if notify_on_failure and not ok and s.is_active:
            await notify_admins(
                f"⚠️ Server unreachable\n{s.name} ({s.country})\n{s.host}:{s.port}"
            )
    return results
