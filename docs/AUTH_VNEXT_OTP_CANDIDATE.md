# Auth vNext OTP candidate — isolated Staging only

Implemented native email OTP start/verify/finish, a per-address opaque
HttpOnly browser challenge, five attempts and 10-minute lifetime, resend
cooldown, encrypted short-lived provider access proof, server-side profile
existence check only after proof, and durable per-address generation fencing.
No general provider-token exchange or legacy signup in vNext. Existing profiles
are not renamed/recreated; password login stays a single HTTP request to the
app and does not call HIBP. New signup automatically enters the app after
password setup and provider global logout. Recovery revokes old app cookies
and returns to pre-filled normal login. This follows OWASP reset guidance.

Feature flag SHURSH_AUTH_VNEXT=1 is explicitly denied in Vercel Production.
Staging guard remains mandatory for hosted testing. Candidate SQL is not
automatically deployed: supabase/auth_vnext_candidate.sql, private schema with
RLS and backend-only grants. CI fixture applies it solely to disposable DB.
Generate a tracked migration with CLI and verify Staging role grants before
enabling Staging. No existing account IDs or business tables are changed.

## Open release gates

- Both signup and magic-link templates must use {{ .Token }} on Staging;
  real email delivery, provider response/error mapping and OTP lifetime need
  dedicated verified mailbox. No hosted settings have been changed.
- Verify actual legacy unconfirmed user/password race against real Auth.
  The app refuses missing profiles until screened password setup, proof of
  the newly accepted password, global logout and credential-stamp recording.
  A private read-only fingerprint of the provider's salted password verifier
  detects later out-of-band changes at app login. Existing profiles are
  seeded at migration; no prior password history or raw verifier is stored.
  The backend role has no direct read permission on auth.users. The function
  grants only the fingerprint to the backend, with empty search_path.
  Direct provider password updates remain possible at the provider; the
  application refuses to mint a session from an unapproved credential.
  This depends on the managed encrypted_password column: validate provider
  upgrades/hash rehash behavior and real OTP/session semantics in Staging.
  Existing app cookies remain valid after out-of-band provider changes until
  expiry or an app recovery. Do not claim provider-wide enforcement.
- Recovery explicitly disables provider user creation; unknown recovery addresses receive the neutral response without an Auth record. Registration alone permits provisional identities; no Shursh profile or session until proof and a screened password.
- Same response/status for valid new/existing start; timing and provider
  throttles not yet empirically equalized. Test real enumeration resistance.
- Password change through old app endpoint disabled in vNext; use OTP.
  Synthetic CI covers concurrent in-flight old-password login, ambiguous
  mutation failure, expiry, same-password retry, unapproved provider
  credential changes and private function grants. Real provider behavior,
  cross-address email changes and rate-limit DoS remain live-test gates.
  A failed remote mutation consumes proof and conservatively revokes app
  sessions; bounded busy fence remains.
- Global logout revokes refresh tokens, not necessarily outstanding access
  JWTs. Never accept those via old generic exchange in vNext.
- No Production merge/deploy, paid plans or hosted DB/Auth edits.

References:
https://supabase.com/docs/guides/auth/auth-email-passwordless
https://supabase.com/docs/reference/javascript/auth-verifyotp
https://supabase.com/docs/reference/javascript/auth-signout
https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

## Registration UX revision

Registration collects email, name and matching password fields before requesting the native email OTP. The proposed password is validated and screened before mail is sent, remains only in the live modal closure, and is screened again at the authoritative finish step. No proposed password is stored in the challenge, browser storage or provider before verification. An existing profile is offered login or explicit recovery after proof; the registration form never automatically overwrites its password. Recovery remains email → OTP → new password. Closing/reloading the form discards the proposed password. Hosted OTP templates and real delivery are still release gates.

Recovery defaults to `create_user=false`, including omitted purpose; only explicit, fully validated registration enables provider user creation. Unknown recovery addresses retain the same neutral response. Stale signup cleanup is an independent database-owner-only cron candidate; no service-role key in the application.

## Guarded signup retention

Staging migrations `20261124095352_guarded_expired_signup_cleanup` and `20261124095444_schedule_guarded_signup_cleanup` install an invoker-rights, owner-only cleanup function and schedule it every 15 minutes with pg_cron. No new services or application privileges. The function requires at least 24 hours since creation and last recorded auth activity; it skips confirmed/previously signed-in/invited/phone/SSO/anonymous identities, live tokens, locked rows, all actual foreign-key dependents except native unverified email identity and expired verification tokens, and known non-FK Auth/Storage references. Unknown composite/non-id FKs, custom triggers, or foreign keys to the allowed cascade children fail closed. An unexpected dependency can defer cleanup indefinitely by design. Dry run is the default. Never schedule on Production before release approval and migration/role checks. Rollback: `SELECT cron.unschedule('shursh-expired-signups');` in the target database; do not restore deleted expired provisional identities. Staging dry run found zero eligible records; the job was configured active as postgres; a scheduled invocation has not yet been observed. HIBP is screened at the application boundary; the provider's paid native leaked-password protection remains off.
