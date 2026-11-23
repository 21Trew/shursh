# Shursh! Production hardening review — 2026-11-23

Scope: read-only audit of Production Supabase Auth, Vercel configuration, the deployed SHA `534c2d8`, and legacy Santa capabilities. Proposed code changes are staged in Draft PR #4 only. No Production Auth settings, migrations, Production deployment or user data have been modified.

## Verified findings

1. **Auth redirect mismatch (P1):** Vercel Production `SHURSH_AUTH_REDIRECT_URL` is `https://shursh.vercel.app`, not `https://shursh.fun`. Both registration and resend in `cloud/auth.py` explicitly pass this fixed origin to Supabase as `redirect_to`. Code refuses an unset or malformed non-HTTPS value.
2. **Supabase Auth URL allowlist and Site URL are unverified:** available Supabase connection has no read/update Auth settings action. Neither value may be inferred from Vercel env or DB SQL. Confirmation templates may use `{{ .SiteURL }}` rather than `{{ .RedirectTo }}`, so changing Vercel alone may not affect emailed links.
3. **Confirmation pipeline:** `verified_user()` contacts Supabase Auth `/auth/v1/user` with the access token and requires `email_confirmed_at`. Production counts at audit time: 4 Auth identities, all 4 marked email-confirmed. This is historical account state, **not** a live test of email dispatch or current Confirm Email switch. In the observed 24-hour Auth logs, 12 events, none containing obvious `/verify`, `/signup`, `resend` or `error` markers; absence of messages does not prove delivery.
4. **Favicon (P2):** `/favicon.svg` is HTTP 200 and already linked in HTML, while `/favicon.ico` and `/favicon.png` were HTTP 404. Staged `favicon.ico` is an ICO rendition of the existing 64x64 SVG design; the fallback is linked and included in the Flask/Vercel allowlists. Optional `favicon.png` remains a future enhancement.
5. **Legacy bearer links (P1):** in Production there were 3 unclaimed legacy guest links and 3 linked guest records still retaining `access_hash`. Code already requires the matching login for a *linked* participant, but the hash remains. Prepared code sets `access_hash=NULL` atomically on successful `claim`, prevents new bearer generation for already linked participants and adds tests. The 3 unclaimed historical links must remain available until owners move them to registered accounts or explicitly approve retirement.
6. **Leaked password check (P1):** Supabase Production Security Advisor reports `auth_leaked_password_protection`: disabled (WARN). Supabase documentation says the built-in HaveIBeenPwned check requires **Supabase Pro or above**. Current project billing tier was not established. Do not upgrade the plan or mutate Production Auth without consent.
7. **Additional SEO issue:** `vercel.json` sets `X-Robots-Tag: noindex, nofollow` for every route, including the landing page. Decide whether this is intentional before changing it; it is unrelated to Auth.

## Approved safe preparation in Draft PR

- Keep SVG favicon as primary; add a 32px ICO fallback and Flask/Vercel static delivery.
- Revoke only the bearer credential when the participant voluntarily claims the game into a registered account. This does not invalidate historical *unclaimed* tokens.
- Block re-issuing bearer tokens for an already-registered participant.
- Add automated regression checks for 200 on favicon, 404 on claimed tokens, and retained access to account-owned Santa routes.
- No changes to Production Auth are made in this PR.

## Controlled Production Auth change (requires separate approval)

Precondition: examine Production Supabase Dashboard → Authentication → URL Configuration.

1. **Site URL:** proposed `https://shursh.fun/`.
2. **Redirect URLs:** explicitly allow `https://shursh.fun/` and retain `https://shursh.vercel.app/` for a transition period. Verify any callback paths used by the deployed application; do not add broad `https://**` wildcards.
3. **Email templates:** inspect Confirm Signup and Resend links. If a custom template uses `{{ .SiteURL }}`, either update the Site URL safely or use `{{ .RedirectTo }}` where appropriate. A custom link built with `{{ .TokenHash }}` must preserve its required `type` and callback path. Do not edit templates blindly.
4. **Vercel env:** only after configuring and verifying the allowlist, change Production `SHURSH_AUTH_REDIRECT_URL` from `https://shursh.vercel.app` to `https://shursh.fun`. Check deployment semantics before rollout; Vercel env changes do not rewrite old deployments.
5. **Functional verification:** create or use a controlled disposable test identity without affecting real users; register, inspect *actual* email link hostname, complete confirmation, confirm login, test resend, check expired token, check URL errors and no leaked access tokens in logs. Explicit permission required before sending real email or adding test users in Production.
6. **Rollback:** retain old redirect allowlist and old domain. Restore previous env if new confirmation flow fails, without deleting existing accounts or callbacks.

## Existing linked bearer cleanup (requires separate Production DB migration approval)

After releasing the code that revokes tokens at claim time and verifying UID access, consider the following one-time narrow DB cleanup:

```sql
BEGIN;
UPDATE public.participants
SET access_hash = NULL
WHERE user_id IS NOT NULL AND access_hash IS NOT NULL;
COMMIT;
```

This revokes legacy URLs already tied to a registered account (3 records at audit time), but preserves unclaimed links. Before execution, perform a dry-run count and confirm the affected population; afterwards verify the counts and run negative-IDOR + member-session smoke. Do not run this until authorized.

## Observability / risk

- Auth emails were not sent, and no live confirmation link was clicked during this audit.
- Site URL, allowlist, custom templates, current Supabase plan and Confirm Email switch are not directly inspectable with the connected actions; a Dashboard review is required.
- There are 3 legacy *unclaimed* links in Production at audit time. These are deliberately still bearer capabilities and can be used by anyone possessing a link. Recommend a time-limited migration campaign to registered accounts rather than silent deletion.
- No secrets, raw Auth logs, email addresses or bearer values were recorded in this report.

Official references:
- https://supabase.com/docs/guides/auth/redirect-urls
- https://supabase.com/docs/guides/auth/auth-email-templates
- https://supabase.com/docs/guides/auth/password-security
