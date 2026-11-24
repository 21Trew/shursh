-- Auth vNext candidate; do not apply to Production. CI applies to disposable DB.
-- Generate a tracked migration with Supabase CLI before hosted rollout.
CREATE SCHEMA IF NOT EXISTS shursh_auth_private;
REVOKE ALL ON SCHEMA shursh_auth_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA shursh_auth_private TO shursh_backend;
CREATE TABLE shursh_auth_private.challenge (
 email_hash text PRIMARY KEY CHECK (email_hash ~ '^[0-9a-f]{64}$'),
 challenge_hash text UNIQUE NOT NULL CHECK (challenge_hash ~ '^[0-9a-f]{64}$'),
 state text NOT NULL CHECK (state IN ('sending','pending','verifying','verified','consumed')),
 sent_at bigint NOT NULL,
 expires_at bigint NOT NULL,
 attempts integer NOT NULL CHECK (attempts BETWEEN 0 AND 5),
 user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
 existing boolean,
 proof bytea CHECK (octet_length(proof) <= 8220)
);
CREATE INDEX auth_challenge_expiry ON shursh_auth_private.challenge(expires_at);
CREATE TABLE shursh_auth_private.guard (
 email_hash text PRIMARY KEY CHECK (email_hash ~ '^[0-9a-f]{64}$'),
 generation text NOT NULL CHECK (generation ~ '^[0-9a-f]{64}$'),
 busy_until bigint NOT NULL
);
ALTER TABLE shursh_auth_private.challenge ENABLE ROW LEVEL SECURITY;
ALTER TABLE shursh_auth_private.guard ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA shursh_auth_private FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shursh_auth_private TO shursh_backend;
CREATE POLICY backend_only ON shursh_auth_private.challenge FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
CREATE POLICY backend_only ON shursh_auth_private.guard FOR ALL TO shursh_backend USING (true) WITH CHECK (true);

-- Credential version gate: no historical or raw provider hashes are stored.
-- A tightly scoped read-only SECURITY DEFINER is required because the backend
-- role deliberately has no SELECT privilege on auth.users.
CREATE TABLE shursh_auth_private.credential_stamp (
 user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
 stamp bytea NOT NULL CHECK (octet_length(stamp)=32)
);
ALTER TABLE shursh_auth_private.credential_stamp ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON shursh_auth_private.credential_stamp FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON shursh_auth_private.credential_stamp TO shursh_backend;
CREATE POLICY backend_only ON shursh_auth_private.credential_stamp FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
CREATE FUNCTION shursh_auth_private.credential_fingerprint(target uuid) RETURNS bytea
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT pg_catalog.sha256(pg_catalog.convert_to(u.encrypted_password,'UTF8'))
 FROM auth.users u WHERE u.id=target AND u.email_confirmed_at IS NOT NULL
 AND u.encrypted_password IS NOT NULL AND u.encrypted_password<>''
$$;
REVOKE ALL ON FUNCTION shursh_auth_private.credential_fingerprint(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION shursh_auth_private.credential_fingerprint(uuid) TO shursh_backend;
-- Preserve already confirmed profiles at activation. No reset or rewrite of
-- auth.users, existing UUIDs, profile data, or business records.
INSERT INTO shursh_auth_private.credential_stamp(user_id,stamp)
 SELECT p.id,shursh_auth_private.credential_fingerprint(p.id) FROM public.profiles p
 WHERE shursh_auth_private.credential_fingerprint(p.id) IS NOT NULL;
