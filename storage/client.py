"""
storage/client.py — Supabase Storage REST Client

Async REST client for the Supabase Storage API using aiohttp.
Streams file bytes directly without writing to disk.

Supabase Storage REST API endpoints:
  Upload:  POST   <url>/storage/v1/object/<bucket>/<path>
  Delete:  DELETE <url>/storage/v1/object/<bucket>  (body: {"prefixes": [path]})
  Public URL:
    <url>/storage/v1/object/public/<bucket>/<path>   (public bucket)
  Signed URL:
    POST <url>/storage/v1/object/sign/<bucket>/<path>
         body: {"expiresIn": <seconds>}
"""
from __future__ import annotations

import logging
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_STORAGE_PREFIX = "/storage/v1"


class SupabaseStorageClient:
    """
    Async Supabase Storage REST client.

    Args:
        project_url: e.g. "https://ggjdxvzbmytyuijjsbfv.supabase.co"
        api_key:     service_role or anon key
        bucket:      name of the storage bucket
    """

    def __init__(self, project_url: str, api_key: str, bucket: str) -> None:
        self._base = project_url.rstrip("/")
        self._key  = api_key
        self._bucket = bucket
        self._session: Optional[aiohttp.ClientSession] = None

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "apikey":        self._key,
                }
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Bucket management ──────────────────────────────────────────────────────

    async def ensure_bucket(self) -> None:
        """
        Idempotent: create the bucket if it doesn't exist.
        Uses the Supabase Management API (service_role key required).
        """
        session = self._get_session()
        # Check if bucket exists
        list_url = f"{self._base}{_STORAGE_PREFIX}/bucket"
        async with session.get(list_url) as resp:
            if resp.status == 200:
                buckets = await resp.json()
                if any(b.get("id") == self._bucket for b in buckets):
                    log.info("Storage bucket '%s' already exists.", self._bucket)
                    return

        # Create bucket (public so Discord can render image embeds)
        create_url = f"{self._base}{_STORAGE_PREFIX}/bucket"
        async with session.post(create_url, json={
            "id":     self._bucket,
            "name":   self._bucket,
            "public": True,
        }) as resp:
            body = await resp.text()
            if resp.status in (200, 201):
                log.info("Storage bucket '%s' created (public=True).", self._bucket)
            elif resp.status == 409:
                log.info("Storage bucket '%s' already exists (409).", self._bucket)
            else:
                log.error(
                    "Failed to create storage bucket '%s': HTTP %d — %s",
                    self._bucket, resp.status, body,
                )

    # ── Upload ─────────────────────────────────────────────────────────────────

    async def upload_file(
        self,
        object_path: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload bytes to Supabase Storage at object_path.

        Returns:
            Public URL for the uploaded object.

        Raises:
            RuntimeError if upload fails.
        """
        url = f"{self._base}{_STORAGE_PREFIX}/object/{self._bucket}/{object_path}"
        session = self._get_session()
        async with session.post(
            url,
            data=data,
            headers={"Content-Type": content_type},
        ) as resp:
            body = await resp.text()
            if resp.status not in (200, 201):
                raise RuntimeError(
                    f"Supabase Storage upload failed: HTTP {resp.status} — {body[:200]}"
                )
        return self.get_public_url(object_path)

    # ── Delete ─────────────────────────────────────────────────────────────────

    async def delete_file(self, object_path: str) -> None:
        """
        Delete an object from Supabase Storage.

        Raises:
            RuntimeError if deletion fails.
        """
        url = f"{self._base}{_STORAGE_PREFIX}/object/{self._bucket}"
        session = self._get_session()
        async with session.delete(
            url,
            json={"prefixes": [object_path]},
        ) as resp:
            body = await resp.text()
            if resp.status not in (200, 204):
                raise RuntimeError(
                    f"Supabase Storage delete failed: HTTP {resp.status} — {body[:200]}"
                )
        log.info("Deleted storage object: %s/%s", self._bucket, object_path)

    # ── URL helpers ────────────────────────────────────────────────────────────

    def get_public_url(self, object_path: str) -> str:
        """Return the CDN URL for a public-bucket object."""
        return f"{self._base}{_STORAGE_PREFIX}/object/public/{self._bucket}/{object_path}"

    async def get_signed_url(self, object_path: str, expires_in: int = 3600) -> str:
        """
        Generate a time-limited signed URL (for private buckets).

        Returns:
            Signed URL string.

        Raises:
            RuntimeError if signing fails.
        """
        url = f"{self._base}{_STORAGE_PREFIX}/object/sign/{self._bucket}/{object_path}"
        session = self._get_session()
        async with session.post(url, json={"expiresIn": expires_in}) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Supabase Storage sign failed: HTTP {resp.status} — {body[:200]}"
                )
            data = await resp.json()
        signed_path = data.get("signedURL") or data.get("signedUrl", "")
        # signedURL may be a relative path; make it absolute
        if signed_path.startswith("/"):
            return f"{self._base}{signed_path}"
        return signed_path

    # ── List ───────────────────────────────────────────────────────────────────

    async def list_objects(self, prefix: str = "") -> list[dict]:
        """List objects under a path prefix (for debugging/management)."""
        url = f"{self._base}{_STORAGE_PREFIX}/object/list/{self._bucket}"
        session = self._get_session()
        async with session.post(url, json={
            "prefix": prefix,
            "limit":  1000,
            "offset": 0,
        }) as resp:
            if resp.status != 200:
                return []
            return await resp.json()
