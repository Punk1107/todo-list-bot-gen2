-- ─────────────────────────────────────────────────────────────────────────────
-- security_rls/sql/02_rls_tasks.sql — RLS Policies for Tasks & Assignments
--
-- Enforces absolute isolation between Personal Tasks and Group/Project Tasks:
--   1. Personal tasks (project_id IS NULL):
--      Only visible/modifiable by task owner or explicitly assigned user.
--   2. Group tasks (project_id IS NOT NULL):
--      Visible by all project members. Modifiable by lead/member.
--      Viewers strictly read-only.
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable RLS
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_assignments ENABLE ROW LEVEL SECURITY;

-- ── 1. Tasks: Personal Scope Policies ────────────────────────────────────────

DROP POLICY IF EXISTS tasks_personal_select ON tasks;
CREATE POLICY tasks_personal_select ON tasks
    FOR SELECT
    USING (
        project_id IS NULL
        AND (
            owner_id = current_app_user()
            OR EXISTS (
                SELECT 1 FROM task_assignments ta
                WHERE ta.task_id = tasks.task_id
                  AND ta.user_id = current_app_user()
            )
        )
    );

DROP POLICY IF EXISTS tasks_personal_insert ON tasks;
CREATE POLICY tasks_personal_insert ON tasks
    FOR INSERT
    WITH CHECK (
        project_id IS NULL
        AND owner_id = current_app_user()
    );

DROP POLICY IF EXISTS tasks_personal_update ON tasks;
CREATE POLICY tasks_personal_update ON tasks
    FOR UPDATE
    USING (
        project_id IS NULL
        AND (
            owner_id = current_app_user()
            OR EXISTS (
                SELECT 1 FROM task_assignments ta
                WHERE ta.task_id = tasks.task_id
                  AND ta.user_id = current_app_user()
            )
        )
    )
    WITH CHECK (
        project_id IS NULL
        AND (
            owner_id = current_app_user()
            OR EXISTS (
                SELECT 1 FROM task_assignments ta
                WHERE ta.task_id = tasks.task_id
                  AND ta.user_id = current_app_user()
            )
        )
    );

DROP POLICY IF EXISTS tasks_personal_delete ON tasks;
CREATE POLICY tasks_personal_delete ON tasks
    FOR DELETE
    USING (
        project_id IS NULL
        AND owner_id = current_app_user()
    );


-- ── 2. Tasks: Group/Project Scope Policies ───────────────────────────────────

DROP POLICY IF EXISTS tasks_group_select ON tasks;
CREATE POLICY tasks_group_select ON tasks
    FOR SELECT
    USING (
        project_id IS NOT NULL
        AND is_project_member(project_id, current_app_user())
    );

DROP POLICY IF EXISTS tasks_group_insert ON tasks;
CREATE POLICY tasks_group_insert ON tasks
    FOR INSERT
    WITH CHECK (
        project_id IS NOT NULL
        AND can_manage_project_tasks(project_id, current_app_user())
    );

DROP POLICY IF EXISTS tasks_group_update ON tasks;
CREATE POLICY tasks_group_update ON tasks
    FOR UPDATE
    USING (
        project_id IS NOT NULL
        AND can_manage_project_tasks(project_id, current_app_user())
    )
    WITH CHECK (
        project_id IS NOT NULL
        AND can_manage_project_tasks(project_id, current_app_user())
    );

DROP POLICY IF EXISTS tasks_group_delete ON tasks;
CREATE POLICY tasks_group_delete ON tasks
    FOR DELETE
    USING (
        project_id IS NOT NULL
        AND (
            get_project_role(project_id, current_app_user()) = 'lead'
            OR owner_id = current_app_user()
        )
    );


-- ── 3. Task Assignments Policies ─────────────────────────────────────────────

DROP POLICY IF EXISTS task_assignments_select ON task_assignments;
CREATE POLICY task_assignments_select ON task_assignments
    FOR SELECT
    USING (
        -- Can view assignment if can view the task
        EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_assignments.task_id
              AND (
                  (t.project_id IS NULL AND (t.owner_id = current_app_user() OR task_assignments.user_id = current_app_user()))
                  OR
                  (t.project_id IS NOT NULL AND is_project_member(t.project_id, current_app_user()))
              )
        )
    );

DROP POLICY IF EXISTS task_assignments_insert ON task_assignments;
CREATE POLICY task_assignments_insert ON task_assignments
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_assignments.task_id
              AND (
                  (t.project_id IS NULL AND t.owner_id = current_app_user())
                  OR
                  (t.project_id IS NOT NULL AND can_manage_project_tasks(t.project_id, current_app_user()))
              )
        )
    );

DROP POLICY IF EXISTS task_assignments_delete ON task_assignments;
CREATE POLICY task_assignments_delete ON task_assignments
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.task_id = task_assignments.task_id
              AND (
                  (t.project_id IS NULL AND t.owner_id = current_app_user())
                  OR
                  (t.project_id IS NOT NULL AND can_manage_project_tasks(t.project_id, current_app_user()))
              )
        )
    );
