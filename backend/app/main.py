from __future__ import annotations

import asyncio
import logging
import sys
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import SessionLocal, engine, init_db
from app.routers import catalog, payment, ref, user, vpn
from app.services import settings_store

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from bot.locale import t  # noqa: E402
from app.services.server_health import check_all_servers
from app.services.subscription_notify import run_subscription_notifications

log = logging.getLogger(__name__)


async def _server_monitor_loop():
    settings = get_settings()
    while True:
        await asyncio.sleep(max(30, settings.server_monitor_interval_sec))
        try:
            async with SessionLocal() as s:
                await check_all_servers(s, notify_on_failure=True)
        except Exception as e:
            log.warning("server monitor: %s", e)


async def _subscription_notify_loop():
    while True:
        try:
            async with SessionLocal() as s:
                await run_subscription_notifications(s)
        except Exception as e:
            log.warning("subscription notify: %s", e)
        await asyncio.sleep(max(60, get_settings().subscription_notify_interval_sec))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pathlib.Path("data").mkdir(parents=True, exist_ok=True)
    await init_db()
    async with SessionLocal() as s:
        await settings_store.ensure_defaults(s)
    monitor_task = None
    if get_settings().server_monitor_interval_sec > 0:
        monitor_task = asyncio.create_task(_server_monitor_loop())
    notify_task = None
    if get_settings().subscription_notify_interval_sec > 0:
        notify_task = asyncio.create_task(_subscription_notify_loop())
    yield
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    if notify_task:
        notify_task.cancel()
        try:
            await notify_task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


settings = get_settings()
app = FastAPI(title="VPN Telegram Backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")

app.include_router(user.router)
app.include_router(catalog.router)
app.include_router(vpn.router)
app.include_router(ref.router)
app.include_router(payment.router)

from app import admin_routes  # noqa: E402

app.include_router(admin_routes.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/paid", response_class=HTMLResponse)
async def paid_landing():
    msg = t("paid.landing")
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;padding:2rem'>{msg}</body></html>"
    )
