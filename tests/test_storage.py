"""
tests/test_storage.py — Unit Tests for Storage Module

Tests:
  - TaskAttachment model properties
  - StorageService validation logic (file size, extension)
  - SupabaseStorageClient URL construction
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO


# ─────────────────────────────────────────────────────────────────────────────
# TaskAttachment model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskAttachmentModel:
    def _make(self, file_name="report.pdf", file_size=1024 * 512):
        from storage.models import TaskAttachment
        return TaskAttachment(
            attachment_id=1,
            task_id=10,
            project_id=5,
            file_name=file_name,
            file_size=file_size,
            file_type="application/pdf",
            storage_path="tasks/10/report.pdf",
            public_url="https://supabase.co/storage/v1/public/task-attachments/tasks/10/report.pdf",
            uploader_id="123456",
            created_at=datetime.now(timezone.utc),
        )

    def test_extension_pdf(self):
        att = self._make("report.pdf")
        assert att.extension == "pdf"

    def test_extension_no_dot(self):
        att = self._make("readme")
        assert att.extension == ""

    def test_is_document_pdf(self):
        att = self._make("report.pdf")
        assert att.is_document
        assert not att.is_image

    def test_is_image_png(self):
        from storage.models import TaskAttachment
        att = TaskAttachment(
            attachment_id=2, task_id=1, project_id=None,
            file_name="screenshot.png", file_size=204800,
            file_type="image/png", storage_path="tasks/1/s.png",
            public_url="https://x.co/s.png", uploader_id="1",
            created_at=datetime.now(timezone.utc),
        )
        assert att.is_image
        assert att.icon_emoji == "🖼️"

    def test_size_human_bytes(self):
        att = self._make(file_size=500)
        assert att.size_human == "500 B"

    def test_size_human_kb(self):
        att = self._make(file_size=2048)
        assert "KB" in att.size_human

    def test_size_human_mb(self):
        att = self._make(file_size=2 * 1024 * 1024)
        assert "MB" in att.size_human

    def test_display_name_truncation(self):
        long_name = "a" * 60 + ".pdf"
        att = self._make(file_name=long_name)
        assert len(att.display_name) <= 53  # 50 chars + "…"
        assert att.display_name.endswith("…")

    def test_display_name_short(self):
        att = self._make("short.txt")
        assert att.display_name == "short.txt"

    def test_icon_emoji_archive(self):
        from storage.models import TaskAttachment
        att = TaskAttachment(
            attachment_id=3, task_id=1, project_id=None,
            file_name="data.zip", file_size=1024,
            file_type="application/zip", storage_path="tasks/1/d.zip",
            public_url="https://x.co/d.zip", uploader_id="1",
            created_at=datetime.now(timezone.utc),
        )
        assert att.icon_emoji == "📦"


# ─────────────────────────────────────────────────────────────────────────────
# Storage service validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageServiceValidation:
    """Tests that don't touch external services — validate only guard clauses."""

    def test_sanitise_filename_removes_special_chars(self):
        from storage.service import _sanitise_filename
        assert _sanitise_filename("my file <script>.pdf") == "my_file__script_.pdf"

    def test_sanitise_filename_truncates(self):
        from storage.service import _sanitise_filename
        long = "a" * 200 + ".pdf"
        assert len(_sanitise_filename(long)) <= 120

    def test_build_object_path_personal_task(self):
        from storage.service import _build_object_path
        path = _build_object_path(task_id=5, file_name="test.png", project_id=None)
        assert path.startswith("tasks/5/")
        assert "test.png" in path

    def test_build_object_path_project_task(self):
        from storage.service import _build_object_path
        path = _build_object_path(task_id=5, file_name="test.png", project_id=10)
        assert path.startswith("projects/10/tasks/5/")

    def test_guess_content_type_png(self):
        from storage.service import _guess_content_type
        assert _guess_content_type("screenshot.png") == "image/png"

    def test_guess_content_type_pdf(self):
        from storage.service import _guess_content_type
        assert _guess_content_type("report.PDF") == "application/pdf"

    def test_guess_content_type_unknown(self):
        from storage.service import _guess_content_type
        assert _guess_content_type("mystery.xyz") == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_raises_storage_disabled(self):
        from storage.service import StorageDisabledError, upload_attachment

        mock_att = MagicMock()
        mock_att.size = 1024
        mock_att.filename = "test.png"
        mock_att.url = "https://cdn.discordapp.com/attachments/test.png"

        with patch("storage.service.config") as mock_config:
            mock_config.storage.enabled = False
            with pytest.raises(StorageDisabledError):
                await upload_attachment(
                    task_id=1,
                    discord_attachment=mock_att,
                    uploader_id="123",
                )

    @pytest.mark.asyncio
    async def test_upload_raises_file_too_large(self):
        from storage.service import FileTooLargeError, upload_attachment

        mock_att = MagicMock()
        mock_att.size = 100 * 1024 * 1024  # 100 MB
        mock_att.filename = "large.zip"
        mock_att.url = "https://cdn.discordapp.com/attachments/large.zip"

        with patch("storage.service.config") as mock_config:
            mock_config.storage.enabled = True
            mock_config.storage.max_file_size_mb = 15
            mock_config.storage.allowed_extensions = ("zip",)
            with pytest.raises(FileTooLargeError) as exc_info:
                await upload_attachment(
                    task_id=1,
                    discord_attachment=mock_att,
                    uploader_id="123",
                )
            assert exc_info.value.max_mb == 15

    @pytest.mark.asyncio
    async def test_upload_raises_invalid_extension(self):
        from storage.service import InvalidFileTypeError, upload_attachment

        mock_att = MagicMock()
        mock_att.size = 1024
        mock_att.filename = "malware.exe"
        mock_att.url = "https://cdn.discordapp.com/attachments/malware.exe"

        with patch("storage.service.config") as mock_config:
            mock_config.storage.enabled = True
            mock_config.storage.max_file_size_mb = 15
            mock_config.storage.allowed_extensions = ("png", "pdf")
            with pytest.raises(InvalidFileTypeError) as exc_info:
                await upload_attachment(
                    task_id=1,
                    discord_attachment=mock_att,
                    uploader_id="123",
                )
            assert exc_info.value.extension == "exe"


# ─────────────────────────────────────────────────────────────────────────────
# SupabaseStorageClient URL tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSupabaseStorageClient:
    def make_client(self):
        from storage.client import SupabaseStorageClient
        return SupabaseStorageClient(
            project_url="https://test.supabase.co",
            api_key="test_key",
            bucket="task-attachments",
        )

    def test_get_public_url(self):
        client = self.make_client()
        url = client.get_public_url("tasks/1/file.png")
        assert url == "https://test.supabase.co/storage/v1/object/public/task-attachments/tasks/1/file.png"

    def test_trailing_slash_stripped(self):
        from storage.client import SupabaseStorageClient
        client = SupabaseStorageClient(
            project_url="https://test.supabase.co/",
            api_key="k",
            bucket="b",
        )
        url = client.get_public_url("x/y.png")
        assert "supabase.co//" not in url
