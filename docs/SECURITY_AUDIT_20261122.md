# Шурш! - security review of games, gifts and profiles
Date: 2026-11-22
Scope: application source at PR #4, Supabase Staging metadata and the disposable CI database. Production has not been updated by this review.

## Trust boundaries

- Authentication: opaque random `shursh_sid` session cookie issued by the application, validated server-side by a hashed session token and expiry. Registration/login use Supabase Auth upstream.
- Authorization: Flask/Python enforces ownership and game membership on every primary resource route. `shursh_backend` has broad table access *inside the trusted backend*. RLS is defense against direct Data API access, not a substitute for API authorization.
- Capabilities: share keys expose intentionally link-shared wishlists; old `/p/<token>` links expose an unclaimed participant's game context. A copied capability is still a risk while unclaimed.
- Admin access: a verified application session and server-side `is_site_admin` permission are required. The browser's `is_admin` flag controls navigation only.

## Confirmed issues and remediation in this Draft PR

1. **High / registered Santa join generated a bearer capability.** Previously a registered participant joining via the common invite received a reusable `participant_token` even though a UID-based membership already existed. The token could bypass login if disclosed. **Fix:** join now creates the participant with the verified UID and no `access_hash`, returning only the event ID.
2. **High / claimed guest bearer link remained anonymously usable.** After an old guest seat was linked to an account, anyone possessing the original URL could still call its game, chat, wishes, assignment and photo endpoints. **Fix:** centralized guard checks `participants.user_id` against the authenticated session across all legacy `/api/participant/<token>` routes. Claimed links are unusable from other sessions; historical unclaimed guest seats remain available for compatibility.
3. **Moderate / membership page displayed a fake personal link.** A UID-based `/api/member/<id>` fallback rendered `/p/null` with an irrelevant claim action. **Fix:** render the legacy block only when an actual unclaimed participant token is present.
4. **Moderate / new user directory privacy.** An administrative directory would become an unnecessary data-exfiltration surface if it returned entire profile/session rows. **Fix:** explicit projection (ID, name, handle, avatar, registration time, discoverability, aggregate counts), maximum 25 users/page, bounded offset and query, and mandatory server-side admin check. No email, sessions, reservations, private gift details or draw mappings are returned.

## Authorization and data flows reviewed

| Surface | Intended right | Review / regression |
|---|---|---|
| Owned wishlists and wishes | Owner by UID | Other users receive 404 on GET, PATCH and DELETE |
| Shared wishlists | Possession of unguessable share key, only when visibility=link | Private list returns 404 even with key |
| Gift booking | Signed-in non-owner, valid public wishlist | Cannot reserve an owner's or private gift; cancellation scoped to reserver |
| Santa owner routes | Event owner UID | Outsiders receive 404 for roster, details, draw, CRUD and private wishes |
| Santa member routes | Exact participant UID for event | Outsiders receive 401/404 for wishes, roster and chats |
| Santa assignments | Giver-specific record, after reveal | Pair identity not returned before reveal |
| Legacy /p capability | Unclaimed seat or exact linked user | Linked seat now requires matching UID on every read/mutation |
| Social profile | Discoverable or allowed relationship | Public view omits email and unrelated games |
| Admin directory | Verified site-admin session | 401/403 for unauthenticated/non-admin, bounded result |
| Uploaded wishlist images | List owner or share-visible list | Private upload not served to strangers |

## Staging Postgres evidence

- RLS enabled and direct SELECT privileges absent for roles `anon` and `authenticated` on 11 sensitive public tables inspected: profiles, wishlists, wishes, reservations, santa_events, participants, participant_wishes, assignments, santa_messages, santa_memories and santa_personal_invites.
- Supabase Security Advisors reported `lints=[]` at review time.
- Staging checks are independent from the Production metadata verification below; deployed application code and authentication flows must still be smoke-tested separately.

## Production Supabase metadata (read-only verification)

- Ten existing sensitive public tables (profiles, wishlists, wishes, reservations, santa_events, participants, participant_wishes, assignments, santa_messages, santa_memories) have RLS enabled. Neither `anon` nor `authenticated` has direct SELECT.
- `santa_personal_invites` is absent from Production at this time; its migration was applied only in Staging.
- Production Supabase Security Advisors reports one **WARN: Leaked Password Protection Disabled**. The Supabase Auth leaked-password check should be enabled, subject to account feature availability and explicit Production-setting approval. Reference: https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection
- Verification used only metadata and advisor read APIs; no live user records, emails or session secrets were retrieved.

## Existing mitigations reviewed

- Read/write SQL uses bound parameters except static trusted column names and explicit whitelists.
- HTTP session cookie uses `HttpOnly; Secure; SameSite=Lax` in the cloud.
- Mutating API rejects cross-site requests; responses use `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, restrictive CSP and `nosniff`.
- UI output escapes untrusted labels. Product images are restricted to accepted image formats; shop links use URL validation.
- Private chat responses use pseudonyms rather than revealing the secret sender.

## Regression tests added

- `test_cross_user_wishlist_santa_and_capability_isolation`
- `test_claimed_guest_capability_requires_same_registered_identity`
- `test_admin_user_directory_is_paginated_and_only_for_site_admin`
- `test_social_meta_profile_and_legacy_link_ux_static`
- `test_browser_ux_fixes_avatar_gift_placeholder_and_admin_directory`
- Existing registered join tests updated to assert the absence of an anonymous participant token.

## Residual risk and release gates

1. **Unclaimed historical /p links are bearer credentials.** Anyone who receives one may access that unclaimed guest seat. Keep them private, rotate exposed links and encourage migration to registered membership. A later compatibility-breaking migration could revoke all unclaimed links.
2. **Backend is a privileged trust boundary.** An API-level BOLA bug could expose information even while direct Supabase Data API access is blocked. Keep per-endpoint owner/member checks and negative-case security tests.
3. **No external penetration test was performed.** This is source review, disposable-database test coverage and Staging RLS verification, not a guarantee of zero vulnerabilities.
4. **Preview runtime database configuration remains incomplete** from prior inspection; authenticated Preview HTTP smoke requires separately restoring the approved Staging-only connection.
5. **Production has not been updated.** Do not claim production security fixes until migrations/deployment and post-deploy smoke have actually been completed.

Release sequence: green full CI -> Staging-authenticated Preview smoke -> explicit approval -> Production publish -> fresh unauthorized/authorized HTTP smoke and account-flow checks.
