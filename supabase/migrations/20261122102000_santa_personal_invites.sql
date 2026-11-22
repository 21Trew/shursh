-- One-time personal Santa invitations: a person becomes a participant only after authenticated acceptance.
CREATE TABLE public.santa_personal_invites (
  token_hash text PRIMARY KEY,
  event_id bigint NOT NULL REFERENCES public.santa_events(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  claimed_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  claimed_at timestamptz
);
CREATE INDEX santa_personal_invites_event_idx ON public.santa_personal_invites(event_id);
ALTER TABLE public.santa_personal_invites ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.santa_personal_invites FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.santa_personal_invites TO shursh_backend;
CREATE POLICY shursh_backend_only ON public.santa_personal_invites
  FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
