# Auth vNext phase 1 (Draft; not ready for production)

The three-password history requirement was retired. This commit implements
new-password screening in the existing signup and authenticated password change
routes, normalized-address rate limits, rotation/revocation of app sessions
after successful password change, and inline change-password feedback.
Existing password login never calls HIBP or enforces the new length policy.
HIBP uses only a padded five-character SHA-1 range prefix, a bounded response,
a four-second timeout and fails closed on new-password screening errors.
No real credentials, OTPs or provider tokens are used in tests.

Remaining release gates: email-first OTP signup/recovery, proof-bound challenge
and replay protection, legacy unconfirmed account takeover protection, concurrent
login/reset and provider/DB failure handling, provider-side session revocation,
direct Supabase API bypass evaluation (free tier cannot natively enforce HIBP),
and real Staging OTP email verification. The current legacy registration flow
is deliberately retained until the new flow is safe. Do not deploy this partial
implementation to Production. No schema/production setting changes in phase 1.

Reference: https://haveibeenpwned.com/API/v3#PwnedPasswords
