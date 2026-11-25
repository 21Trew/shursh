-- Additive: optional full names and revocable invitations. No browser grants.
ALTER TABLE public.profiles
 ADD COLUMN last_name text NOT NULL DEFAULT '' CHECK (char_length(last_name)<=60),
 ADD COLUMN patronymic text NOT NULL DEFAULT '' CHECK (char_length(patronymic)<=60),
 ADD COLUMN show_full_name boolean NOT NULL DEFAULT false,
 ADD COLUMN allow_friend_invites boolean NOT NULL DEFAULT false;

CREATE TABLE public.user_invites (
 code text PRIMARY KEY CHECK (code ~ '^[A-Za-z0-9_-]{24}$'),
 owner_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(),
 revoked_at timestamptz,
 UNIQUE (code,owner_id)
);
CREATE UNIQUE INDEX user_invites_active_owner_idx ON public.user_invites(owner_id) WHERE revoked_at IS NULL;
CREATE TABLE public.referral_pending (
 provider_id uuid PRIMARY KEY,
 invite_code text NOT NULL REFERENCES public.user_invites(code) ON DELETE CASCADE,
 signup_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL CHECK (expires_at>signup_at)
);
CREATE INDEX referral_pending_expiry_idx ON public.referral_pending(expires_at);
CREATE INDEX referral_pending_invite_idx ON public.referral_pending(invite_code);
CREATE TABLE public.referral_attributions (
 referred_id uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
 referrer_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
 invite_code text NOT NULL,
 confirmed_at timestamptz NOT NULL DEFAULT now(),
 CHECK (referrer_id<>referred_id),
 FOREIGN KEY (invite_code,referrer_id) REFERENCES public.user_invites(code,owner_id) ON DELETE CASCADE
);
CREATE INDEX referral_attributions_referrer_idx ON public.referral_attributions(referrer_id);
CREATE INDEX referral_attributions_invite_idx ON public.referral_attributions(invite_code,referrer_id);
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['user_invites','referral_pending','referral_attributions'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated',t);
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO shursh_backend',t);
  EXECUTE format('CREATE POLICY shursh_backend_only ON public.%I FOR ALL TO shursh_backend USING (true) WITH CHECK (true)',t);
 END LOOP;
END $$;
