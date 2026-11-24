# Auth vNext: password-history feasibility gate (2026-11-24)

Status: BLOCKED for activation. This PR contains a reproducible security probe,
not an implemented or enabled Auth module. Base: 066b135c7a337eae677b7a76e2f2bc388547faf8.

## Observed in isolated hosted Staging

Read-only metadata and a synthetic SELECT were executed against the verified
Shursh Staging project (ACTIVE_HEALTHY, eu-central-1). No actual account rows,
emails, passwords, hashes, tokens or secrets were read, and no settings/schema
or user data were changed.

- auth.users.encrypted_password exists; pgcrypto is installed in extensions.
- Inspection role has TRIGGER privilege; supabase_auth_admin has UPDATE.
- No custom non-internal triggers on auth.users were reported.
- public.app_sessions exists.
- All six synthetic checks returned true: two independent salts produce
  different hashes for the same random candidate; that candidate verifies
  against both hashes; three historical candidates match their own hashes;
  a fourth random candidate matches none.

The CI probe reproduces the cryptographic experiment on disposable PostgreSQL.
It never accesses Auth user rows. It rolls back extension/schema creation.

## Security conclusion

Hosted Supabase Auth does not natively retain password history. The password
verification hook runs on sign-in, with user ID and verification result, not
the new password. The provider's normal password update checks the current
password, not the two earlier passwords. Current upstream admin update source
uses plaintext password and generates a new salted hash; the documented
password_hash import path for creating users is not proof of an equivalent
supported update path. A database trigger comparing old and new bcrypt hashes
cannot enforce reuse detection. A Flask-only check is insufficient if direct
Auth API writes remain available. Live bypass testing on a dedicated Staging
identity is still required; no such test has been performed.

References:
- https://github.com/supabase/auth/security
- https://supabase.com/docs/guides/auth/auth-hooks
- https://supabase.com/docs/guides/auth/auth-hooks/password-verification-hook
- https://supabase.com/docs/guides/auth/password-security
- https://github.com/supabase/auth/blob/master/internal/api/user.go
- https://github.com/supabase/auth/blob/master/internal/api/admin.go
- https://supabase.com/docs/guides/getting-started/api-keys

## Required architecture gate before implementation

Evaluate a server-only Auth gateway: block all untrusted access to password
mutation/registration at the provider boundary, not merely the Shursh UI.
Hosted key rotation/revocation and gateway behavior must be proven with a
dedicated test identity; a publishable key is not a secret or a security
boundary. Do not add a service-role key to frontend, store plaintext or
reversibly encrypted passwords, modify managed Auth internals directly,
or rely on a hash-equality trigger. If the gateway cannot enforce the
boundary, explicitly choose a supported alternative (relax history policy,
or private Auth service with a reviewed credential policy and migration).
No production configuration changes are authorized by this document.

## Target UX and contracts (not yet implemented)

- Ordinary password login stays one request, with generic invalid credentials.
- Registration/recovery first proves possession via native email OTP. Before
  proof, use identical status/body and avoid timing/existence disclosures.
- Only after verification, resolve existing identity by provider UUID and
  trusted server-side onboarding state, not editable user metadata.
- Existing user: login or password recovery; do not create a duplicate profile.
  New user: name + password, then create profile and issue app session.
- Prevent pre-account takeover, including pre-existing unconfirmed identities
  with an attacker-chosen password; do not promote them to normal sessions
  without the reviewed credential setup flow.
- Challenge is scoped to purpose, email/UUID, expiry and browser session;
  limited attempts, one-use completion and safe retries/concurrency.
- Reject current and previous two passwords via a candidate-based check with
  private salted verifiers. Legacy history starts at rollout; unknown older
  passwords cannot be reconstructed. Never return candidate/hash data.
- Account reset and password change must be serialized per user, handle
  provider/DB partial failures safely and revoke previous app sessions before
  issuing a fresh session. Account confirmation endpoints must not accept
  arbitrary old provider tokens as recovery proof.
- Preserve UUIDs, profiles, wishlists, games and invitation claims. No forced
  password reset or destructive account migration.
- Rate limits per IP and normalized address, generic failure before proof,
  no-store responses, same-origin mutations, HttpOnly Secure cookies.
- Existing UI kit, inline persistent warnings, password autofill and OTP paste,
  no network request per keystroke; preserve mobile modal geometry.

## Acceptance gates

1. Dedicated isolated Staging identity: prove direct provider signup/password
   changes cannot bypass policy; test legacy key paths and authorization.
2. New/existing/unconfirmed account OTP paths; wrong/expired/replayed code,
   send/verify throttles and account enumeration (body, status, timing).
3. Reject all three known historical passwords in change and reset, allow a
   fresh one, exercise parallel requests and injected partial failure.
4. Revoke old app sessions; validate recovery token scope/replay and new
   session; preserve all existing business data and invitation claims.
5. Chromium and WebKit 375/390px; network, validation, retry, keyboard,
   accessibility and layout; password login latency compared to baseline.
6. Full CI, real Staging email delivery and live provider tests; separate
   approval for any Production DB/Auth changes and Production deployment.

No runtime behavior is changed by this feasibility PR.
