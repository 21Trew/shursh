-- Activate only after guarded cleanup function and its regression suite pass.
-- Hosted Supabase has pg_cron; disposable CI intentionally does not.
DO $$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
   PERFORM cron.schedule('shursh-expired-signups','*/15 * * * *',
     'SELECT shursh_auth_private.cleanup_expired_signups(false)');
 END IF;
END;
$$;
