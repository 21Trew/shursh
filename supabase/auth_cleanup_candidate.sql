-- Owner-only cleanup. No service-role key, no public RPC.
-- Run with READ COMMITTED (cron default); the row lock prevents an already
-- started confirmation/foreign-key insert from being silently cascaded away.
CREATE OR REPLACE FUNCTION shursh_auth_private.cleanup_expired_signups(dry_run boolean DEFAULT true)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE
 candidate record;
 dependency record;
 linked boolean;
 removed integer:=0;
 cutoff timestamptz:=clock_timestamp()-interval '24 hours';
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
   RAISE EXCEPTION 'Signup cleanup requires read committed';
 END IF;
 IF NOT pg_try_advisory_xact_lock(58310974031082413) THEN RETURN 0; END IF;
 -- An unexpected custom trigger may have side effects we cannot audit.
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
   WHERE tgrelid='auth.users'::regclass AND NOT tgisinternal) THEN
   RAISE EXCEPTION 'Review Auth triggers before signup cleanup';
 END IF;
 FOR candidate IN
   SELECT u.id FROM auth.users u
   WHERE u.created_at<=cutoff
     AND greatest(u.updated_at,u.confirmation_sent_at,u.recovery_sent_at,
                  u.email_change_sent_at,u.reauthentication_sent_at,u.created_at)<=cutoff
     AND u.email_confirmed_at IS NULL AND u.confirmed_at IS NULL
     AND u.phone_confirmed_at IS NULL AND u.last_sign_in_at IS NULL
     AND u.invited_at IS NULL AND u.deleted_at IS NULL AND u.banned_until IS NULL
     AND coalesce(u.is_anonymous,false)=false AND coalesce(u.is_sso_user,false)=false
     AND coalesce(u.is_super_admin,false)=false
     AND coalesce(u.phone,'')='' AND coalesce(u.email_change,'')=''
     AND coalesce(u.email,'')<>'' AND u.raw_app_meta_data->>'provider'='email'
     AND coalesce(u.raw_app_meta_data->'providers','["email"]'::jsonb)='["email"]'::jsonb
   ORDER BY u.created_at,u.id LIMIT 200 FOR UPDATE OF u SKIP LOCKED
 LOOP
   -- Native email identity and stale verification tokens are the ONLY
   -- cascade dependents that may be removed. All other FKs are inspected,
   -- including future tables, invitations, sessions, and SET NULL references.
   IF EXISTS(SELECT 1 FROM auth.identities i WHERE i.user_id=candidate.id
     AND (i.provider<>'email' OR coalesce(i.identity_data->>'email_verified','false')='true'
          OR coalesce(i.identity_data->>'phone_verified','false')='true'
          OR greatest(i.created_at,i.updated_at)>cutoff))
     OR (SELECT count(*) FROM auth.identities i WHERE i.user_id=candidate.id)>1
     OR EXISTS(SELECT 1 FROM auth.one_time_tokens t WHERE t.user_id=candidate.id
          AND greatest(t.created_at,t.updated_at)>cutoff)
   THEN CONTINUE; END IF;
   linked:=false;
   FOR dependency IN
     SELECT f.conkey,f.confkey,n.nspname AS schema_name,c.relname AS table_name,
            a.attname AS column_name
     FROM pg_catalog.pg_constraint f
     JOIN pg_catalog.pg_class c ON c.oid=f.conrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid=f.conrelid AND a.attnum=f.conkey[1]
     WHERE f.contype='f' AND f.confrelid='auth.users'::regclass
       AND f.conrelid NOT IN ('auth.identities'::regclass,'auth.one_time_tokens'::regclass)
   LOOP
     -- Unexpected composite or non-id FK: fail closed, do not guess.
     IF cardinality(dependency.conkey)<>1 OR cardinality(dependency.confkey)<>1
        OR dependency.confkey[1]<>(SELECT attnum FROM pg_catalog.pg_attribute
             WHERE attrelid='auth.users'::regclass AND attname='id')
        OR dependency.column_name IS NULL
     THEN linked:=true; EXIT; END IF;
     EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE %I=$1)',
       dependency.schema_name,dependency.table_name,dependency.column_name)
       INTO linked USING candidate.id;
     IF linked THEN EXIT; END IF;
   END LOOP;
   IF linked THEN CONTINUE; END IF;
   -- Known non-FK references in Auth/Storage; never delete owned objects,
   -- refresh tokens or flow state. Check every relevant ownership column.
   FOR dependency IN
     SELECT table_schema,table_name,column_name
     FROM information_schema.columns
     WHERE (table_schema='storage' AND column_name IN ('owner','owner_id'))
        OR (table_schema='auth' AND table_name IN ('refresh_tokens','flow_state')
             AND column_name='user_id')
   LOOP
     EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE %I::text=$1)',
       dependency.table_schema,dependency.table_name,dependency.column_name)
       INTO linked USING candidate.id::text;
     IF linked THEN EXIT; END IF;
   END LOOP;
   IF linked THEN CONTINUE; END IF;
   IF NOT dry_run THEN
     DELETE FROM auth.users WHERE id=candidate.id AND email_confirmed_at IS NULL
        AND confirmed_at IS NULL AND last_sign_in_at IS NULL;
     IF NOT FOUND THEN CONTINUE; END IF;
   END IF;
   removed:=removed+1;
   EXIT WHEN removed>=50;
 END LOOP;
 -- Expired capabilities, including encrypted proof, are not business data.
 IF NOT dry_run THEN
   DELETE FROM shursh_auth_private.challenge WHERE email_hash IN
     (SELECT email_hash FROM shursh_auth_private.challenge
      WHERE expires_at<extract(epoch FROM clock_timestamp())::bigint
      ORDER BY expires_at LIMIT 200 FOR UPDATE SKIP LOCKED);
 END IF;
 RETURN removed;
END;
$$;
REVOKE ALL ON FUNCTION shursh_auth_private.cleanup_expired_signups(boolean) FROM PUBLIC,anon,authenticated,shursh_backend;
-- Activate separately after tests/hosted dry run. pg_cron already exists on
-- Staging; do not install an extension or schedule a job in disposable CI.
