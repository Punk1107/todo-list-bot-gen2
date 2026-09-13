"""
analytics/client.py — Async HTTP Bridge to Supabase Edge Function

Invokes the 'weekly-analytics' Edge Function via HTTPS and returns parsed
WeeklyMetrics. This keeps all heavy computation (SQL aggregation, QuickChart
calls, Discord DM delivery) on the serverless Edge, leaving the bot lightweight.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

from analytics.models import WeeklyMetrics

log = logging.getLogger(__name__)

# Edge Function endpoint is built from SUPABASE_URL
# e.g. https://<ref>.supabase.co/functions/v1/weekly-analytics
_EDGE_FUNCTION_NAME = "weekly-analytics"


class AnalyticsClient:
    """
    Async client that calls the Supabase Edge Function for analytics.

    Args:
        supabase_url: Your Supabase project URL (e.g. https://xyz.supabase.co)
        service_key:  Supabase service_role key (used as Bearer token to invoke the function)
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_key: Optional[str]  = None,
    ) -> None:
        # Use provided value if not None; only fall back to env when argument is None
        self._url = (os.getenv("SUPABASE_URL", "") if supabase_url is None else supabase_url).rstrip("/")
        self._key = (
            (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
            if service_key is None
            else service_key
        )
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def endpoint(self) -> str:
        return f"{self._url}/functions/v1/{_EDGE_FUNCTION_NAME}"

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type":  "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def request_snapshot(
        self,
        user_id: str,
        lang: str = "en",
        send_dm: bool = True,
    ) -> tuple[Optional[WeeklyMetrics], Optional[str]]:
        """
        Triggers an on-demand snapshot for user_id.

        Returns:
            (WeeklyMetrics, chart_url) on success.
            (None, error_message) on failure.
        """
        if not self._url or not self._key:
            return None, "SUPABASE_URL or SUPABASE_KEY not configured — Analytics is disabled"

        payload = {
            "userId": user_id,
            "lang":   lang,
            "sendDm": send_dm,
        }
        session = self._get_session()
        try:
            async with session.post(self.endpoint, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.error("[analytics] Edge Function returned HTTP %d: %s", resp.status, text)
                    return None, f"Edge Function error: HTTP {resp.status}"

                data = await resp.json()
                if not data.get("success"):
                    err = data.get("error", "Unknown error")
                    log.error("[analytics] Edge Function returned success=false: %s", err)
                    return None, err

                metrics_data = data.get("metrics")
                if metrics_data is None:
                    return None, "No metrics returned by Edge Function"

                metrics = WeeklyMetrics.from_dict(metrics_data)
                chart_url: str = data.get("chartUrl", "")
                return metrics, chart_url

        except aiohttp.ClientError as exc:
            log.error("[analytics] HTTP client error calling Edge Function: %s", exc)
            return None, f"Network error: {exc}"

    async def trigger_cron_batch(self) -> tuple[int, int]:
        """
        Triggers the cron batch mode on the Edge Function (processes all users).
        Returns (processed, failed) counts.
        """
        session = self._get_session()
        try:
            async with session.get(
                self.endpoint,
                headers={"X-Cron-Trigger": "true"},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Cron batch failed: HTTP {resp.status} — {text}")
                data = await resp.json()
                return data.get("processed", 0), data.get("failed", 0)
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"Network error triggering cron batch: {exc}") from exc
