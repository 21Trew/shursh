-- Remove expired, never-claimed, one-person Santa invitations.
-- Authorization: scheduled by postgres; table remains private to shursh_backend.
-- A claim holds the same row lock, so DELETE rechecks the claim predicate after waiting.
-- A minute granularity avoids long retention beyond the 24-hour validity window.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;

SELECT cron.schedule(
  'shursh-unused-personal-invites-cleanup',
  '* * * * *',
  $cleanup$
    DELETE FROM public.santa_personal_invites
    WHERE claimed_at IS NULL
      AND claimed_by IS NULL
      AND created_at <= now() - interval '24 hours';
  $cleanup$
);
