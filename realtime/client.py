"""
realtime/client.py — Supabase Realtime Phoenix WebSocket Client

Implements the Phoenix protocol over WebSocket (aiohttp) to subscribe to
Supabase Realtime Postgres CDC change events.

Protocol overview:
  1. Connect to wss://<project>.supabase.co/realtime/v1/websocket
     with Authorization header (Bearer <anon/service_role key>).
  2. Send phx_join to the "realtime:*" channel to receive all table events,
     or more specific channels like "realtime:public:tasks" for a single table.
  3. Send heartbeat every N seconds to keep the WS alive.
  4. On change events, call registered callbacks with the raw payload dict.
  5. On disconnect: exponential backoff with jitter before reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable, Coroutine, Optional

import aiohttp

log = logging.getLogger(__name__)

# Type alias for an async callback receiving a change payload
ChangeCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class PhoenixWSClient:
    """
    Persistent Phoenix WebSocket client for Supabase Realtime.

    Usage:
        client = PhoenixWSClient(
            url="wss://xxx.supabase.co/realtime/v1/websocket",
            api_key="<service_role_key>",
        )
        client.on_change("public", "tasks", my_async_callback)
        asyncio.create_task(client.start())
    """

    _PHXREF_SEED = 1

    def __init__(
        self,
        url: str,
        api_key: str,
        heartbeat_sec: int = 30,
        reconnect_base_sec: float = 1.0,
        max_reconnect_attempts: int = 0,
    ) -> None:
        # Ensure ws:// scheme and correct endpoint
        if url.startswith("https://"):
            url = url.replace("https://", "wss://", 1)
        elif url.startswith("http://"):
            url = url.replace("http://", "ws://", 1)
        self._url = f"{url.rstrip('/')}/realtime/v1/websocket?vsn=1.0.0"
        self._api_key = api_key
        self._heartbeat_sec = heartbeat_sec
        self._reconnect_base = reconnect_base_sec
        self._max_reconnect = max_reconnect_attempts

        # Table -> list[ChangeCallback]
        self._subscribers: dict[str, list[ChangeCallback]] = {}
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._running = False
        self._ref = 0
        self._connected = False
        self._connect_attempts = 0
        # Metrics
        self._messages_received = 0
        self._reconnects = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def subscribe(self, schema: str, table: str, callback: ChangeCallback) -> None:
        """Register callback for CDC changes on schema.table."""
        key = f"{schema}:{table}"
        self._subscribers.setdefault(key, []).append(callback)
        log.debug("Subscribed realtime callback for %s", key)

    def unsubscribe(self, schema: str, table: str, callback: ChangeCallback) -> None:
        key = f"{schema}:{table}"
        if key in self._subscribers:
            self._subscribers[key] = [cb for cb in self._subscribers[key] if cb is not callback]

    async def start(self) -> None:
        """Main loop — connects, subscribes, and reconnects on failure."""
        self._running = True
        while self._running:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as exc:
                self._connect_attempts += 1
                if self._max_reconnect and self._connect_attempts > self._max_reconnect:
                    log.error(
                        "Realtime WS exceeded max reconnect attempts (%d). Giving up.",
                        self._max_reconnect,
                    )
                    break
                delay = self._backoff_delay()
                log.warning(
                    "Realtime WS disconnected (%s). Reconnecting in %.1fs (attempt %d)…",
                    exc, delay, self._connect_attempts,
                )
                await asyncio.sleep(delay)
        log.info("Realtime WS client stopped.")

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def metrics(self) -> dict:
        return {
            "connected": self._connected,
            "messages_received": self._messages_received,
            "reconnects": self._reconnects,
            "connect_attempts": self._connect_attempts,
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    def _backoff_delay(self) -> float:
        """Exponential backoff with ±20% jitter, capped at 60 s."""
        base = min(self._reconnect_base * (2 ** min(self._connect_attempts - 1, 6)), 60.0)
        return base * (0.8 + random.random() * 0.4)

    def _build_msg(self, topic: str, event: str, payload: dict) -> str:
        return json.dumps({
            "topic":   topic,
            "event":   event,
            "payload": payload,
            "ref":     self._next_ref(),
        })

    async def _send(self, msg: str) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(msg)

    async def _connect_and_run(self) -> None:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "apikey":        self._api_key,
        }
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                self._url,
                headers=headers,
                heartbeat=self._heartbeat_sec,
                max_msg_size=4 * 1024 * 1024,  # 4 MB
            ) as ws:
                self._ws = ws
                self._connected = True
                self._connect_attempts = 0
                self._reconnects += 1 if self._reconnects > 0 else 0
                log.info("Realtime WS connected to %s", self._url)

                # Join all-tables channel ("realtime:*") and specific table channels
                await self._join_channels()

                # Start heartbeat and message reader concurrently
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            log.warning("Realtime WS error: %s", ws.exception())
                            break
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                            log.info("Realtime WS closing (code=%s)", ws.close_code)
                            break
                finally:
                    heartbeat_task.cancel()
                    self._connected = False

    async def _join_channels(self) -> None:
        """Subscribe to Supabase Realtime channels for our tables."""
        # Wildcard channel catches all tables
        channels = {"realtime:*"}
        # Also add per-table channels for tables we have callbacks for
        for key in self._subscribers:
            schema, table = key.split(":", 1)
            channels.add(f"realtime:{schema}:{table}")

        for channel in channels:
            msg = self._build_msg(channel, "phx_join", {
                "config": {
                    "broadcast": {"self": False},
                    "presence":  {"key":  ""},
                    "postgres_changes": [
                        {"event": "*", "schema": "public"},
                    ],
                }
            })
            await self._send(msg)
            log.debug("Realtime: joined channel %s", channel)

    async def _heartbeat_loop(self) -> None:
        """Send Phoenix heartbeat every _heartbeat_sec seconds."""
        while True:
            await asyncio.sleep(self._heartbeat_sec)
            try:
                msg = self._build_msg("phoenix", "heartbeat", {})
                await self._send(msg)
                log.debug("Realtime: heartbeat sent")
            except Exception as exc:
                log.debug("Realtime heartbeat failed: %s", exc)

    async def _handle_message(self, raw: str) -> None:
        """Parse and dispatch an incoming Phoenix message."""
        self._messages_received += 1
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("Realtime: non-JSON message ignored")
            return

        event = data.get("event", "")

        # Supabase Realtime wraps Postgres changes in a "postgres_changes" event
        if event in ("postgres_changes", "INSERT", "UPDATE", "DELETE"):
            payload = data.get("payload", {})
            # New Supabase format: nested under data.payload.data
            change_data = payload.get("data", payload)
            await self._dispatch(change_data)
            return

        # Some Supabase versions use event="*" with type in payload
        if event == "*":
            payload = data.get("payload", {})
            if payload.get("type") in ("INSERT", "UPDATE", "DELETE"):
                await self._dispatch(payload)
            return

        # phx_reply (join confirmation)
        if event == "phx_reply":
            status = data.get("payload", {}).get("status", "")
            if status != "ok":
                log.warning("Realtime channel join failed: %s", data.get("payload"))
            return

        log.debug("Realtime: unhandled event '%s'", event)

    async def _dispatch(self, change: dict[str, Any]) -> None:
        """Route a CDC change payload to registered callbacks."""
        schema = change.get("schema", "public")
        table  = change.get("table", "")
        key    = f"{schema}:{table}"

        callbacks = self._subscribers.get(key, []) + self._subscribers.get("public:*", [])
        for cb in callbacks:
            try:
                await cb(change)
            except Exception as exc:
                log.error(
                    "Realtime callback error for %s: %s", key, exc, exc_info=True
                )
