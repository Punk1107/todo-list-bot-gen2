-- ─────────────────────────────────────────────────────────────────────────────
-- security_rls/sql/03_rls_projects_and_members.sql — RLS for Projects & Members
--
-- Enforces multi-tenancy and role-based permissions:
--   - Non-members cannot view project details or member lists
--   - Only project owner or lead can edit project details or manage members
--   - Members can leave the project voluntarily
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;

-- ── 1. Projects Policies ─────────────────────────────────────────────────────

DROP POLICY IF EXISTS projects_select ON projects;
CREATE POLICY projects_select ON projects
    FOR SELECT
    USING (
        owner_id = current_app_user()
        OR is_project_member(project_id, current_app_user())
    );

DROP POLICY IF EXISTS projects_insert ON projects;
CREATE POLICY projects_insert ON projects
    FOR INSERT
    WITH CHECK (
        owner_id = current_app_user()
    );

DROP POLICY IF EXISTS projects_update ON projects;
CREATE POLICY projects_update ON projects
    FOR UPDATE
    USING (
        owner_id = current_app_user()
        OR get_project_role(project_id, current_app_user()) = 'lead'
    )
    WITH CHECK (
        owner_id = current_app_user()
        OR get_project_role(project_id, current_app_user()) = 'lead'
    );

DROP POLICY IF EXISTS projects_delete ON projects;
CREATE POLICY projects_delete ON projects
    FOR DELETE
    USING (
        owner_id = current_app_user()
    );


-- ── 2. Project Members Policies ──────────────────────────────────────────────

DROP POLICY IF EXISTS project_members_select ON project_members;
CREATE POLICY project_members_select ON project_members
    FOR SELECT
    USING (
        is_project_member(project_id, current_app_user())
    );

DROP POLICY IF EXISTS project_members_insert ON project_members;
CREATE POLICY project_members_insert ON project_members
    FOR INSERT
    WITH CHECK (
        get_project_role(project_id, current_app_user()) = 'lead'
    );

DROP POLICY IF EXISTS project_members_update ON project_members;
CREATE POLICY project_members_update ON project_members
    FOR UPDATE
    USING (
        get_project_role(project_id, current_app_user()) = 'lead'
    )
    WITH CHECK (
        get_project_role(project_id, current_app_user()) = 'lead'
    );

DROP POLICY IF EXISTS project_members_delete ON project_members;
CREATE POLICY project_members_delete ON project_members
    FOR DELETE
    USING (
        get_project_role(project_id, current_app_user()) = 'lead'
        OR user_id = current_app_user() -- member can leave
    );
