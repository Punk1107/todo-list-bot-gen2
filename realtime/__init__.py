"""
realtime/ — Supabase Realtime Collaboration module for To-Do List Bot Gen 2

Provides push-based task-completion notifications and live dashboard updates
via Supabase Realtime (Phoenix WebSocket / Postgres CDC).

Public API:
    from realtime.service import RealtimeService
    from realtime.dashboard_tracker import dashboard_tracker
    from realtime.service import setup as setup_realtime
"""
