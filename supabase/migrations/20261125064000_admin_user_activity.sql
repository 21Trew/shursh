-- One latest visit per account; no device history or raw browser identifiers.
CREATE TABLE IF NOT EXISTS public.admin_user_activity (
    user_id uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    last_seen_at timestamptz NOT NULL,
    last_platform text NOT NULL CHECK (last_platform IN ('windows','macos','linux','android','ios','unknown'))
);
ALTER TABLE public.admin_user_activity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.admin_user_activity FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.admin_user_activity TO shursh_backend;
DROP POLICY IF EXISTS backend_admin_activity ON public.admin_user_activity;
CREATE POLICY backend_admin_activity ON public.admin_user_activity FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
