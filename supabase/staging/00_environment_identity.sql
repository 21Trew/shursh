-- Staging-only environment marker.
-- Apply ONLY through the Supabase project-scoped management API with:
-- project_id = vwhzhbsaspbelkvnjjho (Shursh Staging).
-- Never include this file in a Production migration or automated db push.
CREATE SCHEMA IF NOT EXISTS shursh_env;
REVOKE ALL ON SCHEMA shursh_env FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS shursh_env.environment_identity (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 environment text NOT NULL CHECK (environment = 'staging'),
 project_ref text NOT NULL CHECK (project_ref = 'vwhzhbsaspbelkvnjjho')
);
REVOKE ALL ON shursh_env.environment_identity FROM PUBLIC, anon, authenticated;
INSERT INTO shursh_env.environment_identity(singleton,environment,project_ref)
VALUES(true,'staging','vwhzhbsaspbelkvnjjho')
ON CONFLICT(singleton) DO NOTHING;
DO $$
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM shursh_env.environment_identity
   WHERE singleton = true AND environment = 'staging'
     AND project_ref = 'vwhzhbsaspbelkvnjjho'
 ) THEN
   RAISE EXCEPTION 'Staging identity marker mismatch';
 END IF;
END $$;
