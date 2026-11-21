-- Authenticated anonymous gifting, persistent site-admin identities,
-- and one private group photo per completed Santa game.
ALTER TABLE public.reservations ADD COLUMN reserved_by uuid REFERENCES auth.users(id) ON DELETE SET NULL;
CREATE INDEX reservations_active_booker_idx ON public.reservations(reserved_by)
 WHERE cancelled_at IS NULL AND reserved_by IS NOT NULL;

CREATE TABLE public.site_admins (
 user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
 granted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.santa_memories (
 event_id bigint PRIMARY KEY REFERENCES public.santa_events(id) ON DELETE CASCADE,
 image_data text NOT NULL CHECK (char_length(image_data) BETWEEN 100 AND 1400000),
 updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['site_admins','santa_memories'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.%I TO shursh_backend',t);
  EXECUTE format('CREATE POLICY shursh_backend_only ON public.%I FOR ALL TO shursh_backend USING (true) WITH CHECK (true)',t);
 END LOOP;
END $$;
-- Never grant admins by user-supplied metadata or permit direct browser writes.
