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
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("recurrence_rule JSONB" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS focus_sessions" in stmt for stmt in statements))
        self.assertTrue(any("idx_focus_sessions_one_active_per_user" in stmt for stmt in statements))

    def test_migration_v20_adds_discord_native_references(self):
        v20 = next(sql for version, sql in MIGRATIONS if version == 20)
        statements = _split_sql_statements(v20)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("source_message_url" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_task_threads" in stmt for stmt in statements))
        self.assertTrue(any("thread_id" in stmt and "BIGINT UNIQUE" in stmt for stmt in statements))

    def test_migration_v22_enables_nullable_deadlines_and_calendar_tokens(self):
        v22 = next(sql for version, sql in MIGRATIONS if version == 22)
        statements = _split_sql_statements(v22)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("deadline DROP NOT NULL" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS calendar_feed_tokens" in stmt for stmt in statements))

    def test_migration_v23_adds_templates_checklists_and_routine_rules(self):
        v23 = next(sql for version, sql in MIGRATIONS if version == 23)
        statements = _split_sql_statements(v23)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_templates" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS task_checklists" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS routine_event_rules" in stmt for stmt in statements))

    def test_migration_v24_adds_soft_delete_and_permissions(self):
        v24 = next(sql for version, sql in MIGRATIONS if version == 24)
        statements = _split_sql_statements(v24)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("is_deleted BOOLEAN" in stmt for stmt in statements))
        self.assertTrue(any("is_private BOOLEAN" in stmt for stmt in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS project_role_permissions" in stmt for stmt in statements))

    def test_migration_v25_adds_saved_filters(self):
        v25 = next(sql for version, sql in MIGRATIONS if version == 25)
        statements = _split_sql_statements(v25)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS saved_filters" in stmt for stmt in statements))
        self.assertTrue(any("uq_user_filter_name" in stmt for stmt in statements))
        self.assertTrue(any("idx_saved_filters_owner" in stmt for stmt in statements))

    def test_migration_v26_adds_audit_index_and_retrospective(self):
        v26 = next(sql for version, sql in MIGRATIONS if version == 26)
        statements = _split_sql_statements(v26)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("idx_audit_target_created" in stmt for stmt in statements))
        self.assertTrue(any("weekly_retrospective" in stmt for stmt in statements))

    def test_migration_v27_adds_performance_indexes(self):
        v27 = next(sql for version, sql in MIGRATIONS if version == 27)
        statements = _split_sql_statements(v27)
        self.assertEqual(SCHEMA_VERSION, 27)
        self.assertTrue(any("idx_tasks_recurring_due" in stmt for stmt in statements))
        self.assertTrue(any("idx_tasks_deadline_dm_pending" in stmt for stmt in statements))
        self.assertTrue(any("idx_tasks_pending_reminders" in stmt for stmt in statements))
        self.assertTrue(any("idx_focus_sessions_active_lookup" in stmt for stmt in statements))


if __name__ == "__main__":
    unittest.main()
