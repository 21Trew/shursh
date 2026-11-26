-- Server-only audit metadata; no request payloads, emails, tokens or secrets.
CREATE TABLE public.admin_audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 audience text NOT NULL CHECK (audience IN ('admins','users')),
 actor_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
 target_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
 event text NOT NULL CHECK (char_length(event) BETWEEN 1 AND 64),
 object_id bigint,
 category text CHECK (category IS NULL OR category IN ('wishlists','gifts','referrals','organized','joined','discoverable')),
 before_visible boolean,
 after_visible boolean,
 success boolean NOT NULL DEFAULT true
);
CREATE INDEX admin_audit_events_audience_id_idx ON public.admin_audit_events(audience,id DESC);
CREATE INDEX admin_audit_events_created_at_idx ON public.admin_audit_events(created_at);
ALTER TABLE public.admin_audit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.admin_audit_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.admin_audit_events_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON public.admin_audit_events TO shursh_backend;
GRANT USAGE, SELECT ON SEQUENCE public.admin_audit_events_id_seq TO shursh_backend;
CREATE POLICY shursh_backend_only ON public.admin_audit_events FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
