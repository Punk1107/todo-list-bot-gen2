-- ─────────────────────────────────────────────────────────────────────────────
-- security_rls/sql/04_rls_categories_attachments.sql — RLS for Auxiliary Tables
--
-- Covers:
--   1. categories (Private user categories)
--   2. task_attachments (Files attached to personal or project tasks)
--   3. project_activity_log (Audit trail for project actions)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_activity_log ENABLE ROW LEVEL SECURITY;

-- ── 1. Categories Policies ───────────────────────────────────────────────────

DROP POLICY IF EXISTS categories_select ON categories;
CREATE POLICY categories_select ON categories
    FOR SELECT
    USING (
        owner_id = current_app_user()
        OR owner_id = 'system'
    );

DROP POLICY IF EXISTS categories_insert ON categories;
CREATE POLICY categories_insert ON categories
    FOR INSERT
    WITH CHECK (
        owner_id = current_app_user()
    );

DROP POLICY IF EXISTS categories_update ON categories;
CREATE POLICY categories_update ON categories
    FOR UPDATE
    USING (
        owner_id = current_app_user()
    )
    WITH CHECK (
        owner_id = current_app_user()
    );

DROP POLICY IF EXISTS categories_delete ON categories;
CREATE POLICY categories_delete ON categories
    FOR DELETE
    USING (
        owner_id = current_app_user()
    );


-- ── 2. Task Attachments Policies ─────────────────────────────────────────────

DROP POLICY IF EXISTS attachments_select ON task_attachments;
CREATE POLICY attachments_select ON task_attachments
    FOR SELECT
    USING (
        -- Accessible if user has access to parent task
        EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_attachments.task_id
              AND (
                  (t.project_id IS NULL AND (t.owner_id = current_app_user() OR task_attachments.uploader_id = current_app_user()))
                  OR
                  (t.project_id IS NOT NULL AND is_project_member(t.project_id, current_app_user()))
              )
        )
    );

DROP POLICY IF EXISTS attachments_insert ON task_attachments;
CREATE POLICY attachments_insert ON task_attachments
    FOR INSERT
    WITH CHECK (
        uploader_id = current_app_user()
        AND EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_attachments.task_id
              AND (
                  (t.project_id IS NULL AND t.owner_id = current_app_user())
                  OR
                  (t.project_id IS NOT NULL AND can_manage_project_tasks(t.project_id, current_app_user()))
              )
        )
    );

DROP POLICY IF EXISTS attachments_delete ON task_attachments;
CREATE POLICY attachments_delete ON task_attachments
    FOR DELETE
    USING (
        uploader_id = current_app_user()
        OR EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_attachments.task_id
              AND (
                  (t.project_id IS NULL AND t.owner_id = current_app_user())
                  OR
                  (t.project_id IS NOT NULL AND get_project_role(t.project_id, current_app_user()) = 'lead')
              )
        )
    );


-- ── 3. Project Activity Log Policies ─────────────────────────────────────────

DROP POLICY IF EXISTS activity_log_select ON project_activity_log;
CREATE POLICY activity_log_select ON project_activity_log
    FOR SELECT
    USING (
        is_project_member(project_id, current_app_user())
    );

DROP POLICY IF EXISTS activity_log_insert ON project_activity_log;
CREATE POLICY activity_log_insert ON project_activity_log
    FOR INSERT
    WITH CHECK (
        user_id = current_app_user()
        AND is_project_member(project_id, current_app_user())
    );
