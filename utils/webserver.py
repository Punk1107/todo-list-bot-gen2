"""
utils/webserver.py — High-performance async keep-alive server v2
Changes over v1 (Flask):
  - Replaced synchronous Flask/WSGI with aiohttp (pure async, same event loop)
  - No dedicated daemon thread needed — runs as a coroutine on the bot's loop
  - Supports concurrent HTTP connections without blocking the bot
  - Added /metrics endpoint exposing DB pool, cache, and BulkWriter stats
  - Added /ready endpoint for liveness probes (Render, Railway, fly.io)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from aiohttp import web

from core.config import config

log = logging.getLogger(__name__)

_start_time = time.monotonic()

# ─────────────────────────────────────────────────────────────────────────────
# Route handlers
# ─────────────────────────────────────────────────────────────────────────────

async def _index(request: web.Request) -> web.Response:
    return web.json_response({
        "status":  "online",
        "service": "To-Do List Bot Gen 2",
        "uptime_s": round(time.monotonic() - _start_time, 1),
    })


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"}, status=200)


async def _ready(request: web.Request) -> web.Response:
    """Kubernetes/Render readiness probe — returns 200 only when DB is reachable."""
    try:
        from core.database import db
        # Quick synchronous ping — pool connection already open
        with db._pool.get() as conn:
            conn.execute("SELECT 1")
        return web.json_response({"ready": True}, status=200)
    except Exception as exc:
        log.warning("Readiness probe failed: %s", exc)
        return web.json_response({"ready": False, "error": str(exc)}, status=503)


async def _metrics(request: web.Request) -> web.Response:
    """Expose internal metrics: DB pool, caches, BulkWriter."""
    try:
        from core.database import db
        return web.json_response({
            "uptime_s": round(time.monotonic() - _start_time, 1),
            "database": db.metrics,
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# App factory & start
# ─────────────────────────────────────────────────────────────────────────────

def _build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/",       _index)
    app.router.add_get("/health", _health)
    app.router.add_get("/ready",  _ready)
    app.router.add_get("/metrics", _metrics)
    return app


async def start_async() -> Optional[web.AppRunner]:
    """
    Start the aiohttp server as a coroutine on the existing event loop.
    Call this from setup_hook or on_ready — never before the loop is running.
    Returns the AppRunner so the caller can keep a reference for graceful shutdown.
    """
    if not config.webserver.enabled:
        log.info("Webserver disabled — skipping")
        return None

    app    = _build_app()
    runner = web.AppRunner(app, access_log=None)  # suppress per-request logs
    await runner.setup()
    site = web.TCPSite(
        runner,
        config.webserver.host,
        config.webserver.port,
        reuse_address=True,
        reuse_port=True,
    )
    await site.start()
    log.info(
        "Async webserver started on %s:%d (endpoints: / /health /ready /metrics)",
        config.webserver.host,
        config.webserver.port,
    )
    return runner


def start() -> None:
    """
    Backward-compatible synchronous shim.
    Schedules start_async() on the running event loop.
    Called from main.py before bot.start().
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(start_async(), name="webserver")
    except RuntimeError:
        # If no loop is running yet, fall back to scheduling via ensure_future
        asyncio.ensure_future(start_async())
