import unittest
from core.database import SCHEMA_VERSION, _split_sql_statements, MIGRATIONS


class TestSqlSplit(unittest.TestCase):
    def test_basic_split(self):
        sql = "SELECT 1; SELECT 2;"
        stmts = _split_sql_statements(sql)
        self.assertEqual(stmts, ["SELECT 1", "SELECT 2"])

    def test_single_quoted_semicolon(self):
        sql = "CREATE TABLE t (val TEXT DEFAULT 'hello;world'); SELECT 1;"
        stmts = _split_sql_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertIn("'hello;world'", stmts[0])
        self.assertEqual(stmts[1], "SELECT 1")

    def test_dollar_quoted_block(self):
        sql = """
        DO $rt$
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $rt$;
        ALTER TABLE tasks REPLICA IDENTITY FULL;
        """
        stmts = _split_sql_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertTrue(stmts[0].startswith("DO $rt$"))
        self.assertTrue(stmts[0].endswith("END $rt$"))
        self.assertEqual(stmts[1], "ALTER TABLE tasks REPLICA IDENTITY FULL")

    def test_anonymous_dollar_quoted_block(self):
        sql = """
        DO $$
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
        SELECT 1;
        """
        stmts = _split_sql_statements(sql)
        self.assertEqual(len(stmts), 2)
        self.assertTrue(stmts[0].startswith("DO $$"))
        self.assertTrue(stmts[0].endswith("END $$"))

    def test_migration_v14_statements(self):
        v14 = next(sql for v, sql in MIGRATIONS if v == 14)
        stmts = _split_sql_statements(v14)
        # Verify no unterminated dollar-quote in any statement
        for idx, stmt in enumerate(stmts):
            if "DO $" in stmt:
                self.assertIn("END $", stmt, f"Statement {idx} has unclosed DO block: {stmt}")

    def test_migration_v18_focus_and_recurrence_schema(self):
        v18 = next(sql for version, sql in MIGRATIONS if version == 18)
        statements = _split_sql_statements(v18)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("recurrence_rule JSONB" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS focus_sessions" in stmt for stmt in statements))
        self.assertTrue(any("idx_focus_sessions_one_active_per_user" in stmt for stmt in statements))

    def test_migration_v20_adds_discord_native_references(self):
        v20 = next(sql for version, sql in MIGRATIONS if version == 20)
        statements = _split_sql_statements(v20)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("source_message_url" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_task_threads" in stmt for stmt in statements))
        self.assertTrue(any("thread_id" in stmt and "BIGINT UNIQUE" in stmt for stmt in statements))

    def test_migration_v22_enables_nullable_deadlines_and_calendar_tokens(self):
        v22 = next(sql for version, sql in MIGRATIONS if version == 22)
        statements = _split_sql_statements(v22)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("deadline DROP NOT NULL" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS calendar_feed_tokens" in stmt for stmt in statements))

    def test_migration_v23_adds_templates_checklists_and_routine_rules(self):
        v23 = next(sql for version, sql in MIGRATIONS if version == 23)
        statements = _split_sql_statements(v23)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_templates" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_checklists" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS routine_event_rules" in stmt for stmt in statements))

    def test_migration_v24_adds_soft_delete_and_permissions(self):
        v24 = next(sql for version, sql in MIGRATIONS if version == 24)
        statements = _split_sql_statements(v24)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("is_deleted BOOLEAN" in stmt for stmt in statements))
        self.assertTrue(any("is_private BOOLEAN" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_role_permissions" in stmt for stmt in statements))

    def test_migration_v25_adds_saved_filters(self):
        v25 = next(sql for version, sql in MIGRATIONS if version == 25)
        statements = _split_sql_statements(v25)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS saved_filters" in stmt for stmt in statements))
        self.assertTrue(any("uq_user_filter_name" in stmt for stmt in statements))
        self.assertTrue(any("idx_saved_filters_owner" in stmt for stmt in statements))

    def test_migration_v26_adds_audit_index_and_retrospective(self):
        v26 = next(sql for version, sql in MIGRATIONS if version == 26)
        statements = _split_sql_statements(v26)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("idx_audit_target_created" in stmt for stmt in statements))
        self.assertTrue(any("weekly_retrospective" in stmt for stmt in statements))

    def test_migration_v27_adds_performance_indexes(self):
        v27 = next(sql for version, sql in MIGRATIONS if version == 27)
        statements = _split_sql_statements(v27)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("idx_tasks_recurring_due" in stmt for stmt in statements))
        self.assertTrue(any("idx_tasks_deadline_dm_pending" in stmt for stmt in statements))
        self.assertTrue(any("idx_tasks_pending_reminders" in stmt for stmt in statements))
        self.assertTrue(any("idx_focus_sessions_active_lookup" in stmt for stmt in statements))

    def test_migration_v28_adds_user_and_active_task_indexes(self):
        v28 = next(sql for version, sql in MIGRATIONS if version == 28)
        statements = _split_sql_statements(v28)
        self.assertGreaterEqual(SCHEMA_VERSION, 36)
        self.assertTrue(any("idx_users_daily_digest" in stmt for stmt in statements))
        self.assertTrue(any("idx_users_weekly_retrospective" in stmt for stmt in statements))
        self.assertTrue(any("idx_users_streak_reminder" in stmt for stmt in statements))
        self.assertTrue(any("idx_tasks_user_active_root" in stmt for stmt in statements))

    def test_migration_v29_to_v36_gen5_schema(self):
        """Verify Gen 5.0 database schema migrations (v29-v36) parse and contain required definitions."""
        self.assertGreaterEqual(SCHEMA_VERSION, 36)

        # v29: Sprints & story points
        v29_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 29))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS sprints" in s for s in v29_stmts))
        self.assertTrue(any("sprint_id INTEGER" in s for s in v29_stmts))
        self.assertTrue(any("story_points INTEGER" in s for s in v29_stmts))

        # v30: Time logs & estimated hours
        v30_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 30))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_time_logs" in s for s in v30_stmts))
        self.assertTrue(any("estimated_hours NUMERIC" in s for s in v30_stmts))

        # v31: Automation rules
        v31_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 31))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS automation_rules" in s for s in v31_stmts))

        # v32: RPG profiles & co-op quests
        v32_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 32))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS user_rpg_profiles" in s for s in v32_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS coop_quests" in s for s in v32_stmts))

        # v33: Documents & revisions
        v33_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 33))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_documents" in s for s in v33_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_revisions" in s for s in v33_stmts))

        # v34: Checklist templates & custom fields GIN index
        v34_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 34))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS checklist_templates" in s for s in v34_stmts))
        self.assertTrue(any("custom_fields JSONB" in s for s in v34_stmts))
        self.assertTrue(any("idx_tasks_custom_fields" in s and "GIN" in s for s in v34_stmts))

        # v35: Federation & assignees
        v35_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 35))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_federation_guilds" in s for s in v35_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_assignees" in s for s in v35_stmts))

        # v36: Milestones, retros, and archive
        v36_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 36))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_milestones" in s for s in v36_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS sprint_retros" in s for s in v36_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS tasks_archive" in s for s in v36_stmts))

    def test_migration_v37_discord_native_ecosystem(self):
        """Verify Gen 5.0 Pillar 3 database schema migration (v37) parses and contains required definitions."""
        self.assertGreaterEqual(SCHEMA_VERSION, 37)
        v37_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 37))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS voice_focus_rooms" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS user_chime_settings" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_scheduled_events" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_forum_configs" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_forum_posts" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS standup_configs" in s for s in v37_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS daily_standups" in s for s in v37_stmts))

    def test_migration_v38_time_tracking_engine(self):
        """Verify Gen 5.0 Pillar 4 database schema migration (v38) parses and contains required definitions."""
        self.assertGreaterEqual(SCHEMA_VERSION, 38)
        v38_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 38))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS active_time_timers" in s for s in v38_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS user_workload_capacities" in s for s in v38_stmts))
        self.assertTrue(any("budget NUMERIC" in s for s in v38_stmts))
        self.assertTrue(any("currency TEXT" in s for s in v38_stmts))
        self.assertTrue(any("hourly_rate NUMERIC" in s for s in v38_stmts))

    def test_migration_v39_automations_sla(self):
        """Verify Gen 5.0 Pillar 5 database schema migration (v39) parses and contains required definitions."""
        self.assertEqual(SCHEMA_VERSION, 39)
        v39_stmts = _split_sql_statements(next(sql for v, sql in MIGRATIONS if v == 39))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_escalations" in s for s in v39_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_sla_policies" in s for s in v39_stmts))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_sla_tracking" in s for s in v39_stmts))
        self.assertTrue(any("early_warning_sent BOOLEAN" in s for s in v39_stmts))
        self.assertTrue(any("breached BOOLEAN" in s for s in v39_stmts))


if __name__ == "__main__":
    unittest.main()
