"""
storage/ — Task File Storage module for To-Do List Bot Gen 2

Provides task attachment management via Supabase Storage (REST API).
Users can upload files through Discord slash commands or the TaskActionView button.

Public API:
    from storage.service import StorageService, storage_service
    from storage.models import TaskAttachment
    from storage.cog import setup
"""
