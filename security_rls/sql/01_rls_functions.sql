"""
security_rls/sql/01_rls_functions.sql — RLS Identity Resolution & Permission Helpers

Defines database functions used across all Row Level Security (RLS) policies.
Designed to work seamlessly with:
  1. Supabase PostgREST / Edge Functions (auth.uid() and request.jwt.claims)
  2. Direct asyncpg Bot connections (via SET LOCAL app.current_user_id = '...')
"""

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Identity Resolution Helper
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION current_app_user()
RETURNS TEXT AS $$
DECLARE
    jwt_claims TEXT;
    sub_claim TEXT;
    app_uid TEXT;
BEGIN
    -- Priority 1: Check session setting set by bot connection (SET LOCAL app.current_user_id)
    app_uid := NULLIF(current_setting('app.current_user_id', true), '');
    IF app_uid IS NOT NULL THEN
        RETURN app_uid;
    END IF;

    -- Priority 2: Check standard Supabase JWT claim (used by Edge Functions / PostgREST)
    sub_claim := NULLIF(current_setting('request.jwt.claim.sub', true), '');
    IF sub_claim IS NOT NULL THEN
        RETURN sub_claim;
    END IF;

    jwt_claims := NULLIF(current_setting('request.jwt.claims', true), '');
    IF jwt_claims IS NOT NULL THEN
        BEGIN
            RETURN (jwt_claims::jsonb ->> 'sub');
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END IF;

    -- Priority 3: Standard Supabase auth.uid() if Supabase Auth schema is present
    BEGIN
        RETURN auth.uid()::text;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Project Membership & Role Helpers
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION is_project_member(p_project_id INTEGER, p_user_id TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    IF p_project_id IS NULL OR p_user_id IS NULL THEN
        RETURN FALSE;
    END IF;

    RETURN EXISTS (
        SELECT 1
        FROM project_members
        WHERE project_id = p_project_id
          AND user_id = p_user_id
    ) OR EXISTS (
        SELECT 1
        FROM projects
        WHERE project_id = p_project_id
          AND owner_id = p_user_id
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;


CREATE OR REPLACE FUNCTION get_project_role(p_project_id INTEGER, p_user_id TEXT)
RETURNS TEXT AS $$
DECLARE
    v_role TEXT;
    v_owner_id TEXT;
BEGIN
    IF p_project_id IS NULL OR p_user_id IS NULL THEN
        RETURN NULL;
    END IF;

    -- Project owner always has lead privileges
    SELECT owner_id INTO v_owner_id FROM projects WHERE project_id = p_project_id;
    IF v_owner_id = p_user_id THEN
        RETURN 'lead';
    END IF;

    SELECT role INTO v_role
    FROM project_members
    WHERE project_id = p_project_id
      AND user_id = p_user_id;

    RETURN v_role;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;


CREATE OR REPLACE FUNCTION can_manage_project_tasks(p_project_id INTEGER, p_user_id TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    v_role TEXT;
BEGIN
    v_role := get_project_role(p_project_id, p_user_id);
    RETURN v_role IN ('lead', 'member');
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
