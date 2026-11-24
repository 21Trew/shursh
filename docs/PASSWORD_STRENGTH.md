# Password strength (Auth vNext)

The UI uses the original Dropbox zxcvbn 4.4.2 (MIT), pinned to upstream
blob 0daf83098e4c90508dcbd69257c6f16ee4da3a8b:
https://github.com/dropbox/zxcvbn/tree/v4.4.2 .
The bundled license is retained; the unused source-map directive is removed.
The static asset is self-hosted and loaded by a Web Worker only after input
in a new-password field. No initial page or ordinary login bundle growth from
the library. No CDN, runtime npm install, CSP relaxation or external password
estimation service. Worker replies contain only request ID and score.
Debounced, one in-flight estimate with latest-only queued input; obsolete
results are ignored. Empty/overlong inputs clear the meter. Worker errors
clear the estimate rather than guessing. Existing submit validation and HIBP
are unchanged. Original English/password dictionaries are not a comprehensive
Russian-language dictionary. Levels map zxcvbn scores 0/1 → Weak, 2 → Medium,
3 → Good, 4 → Strong. Score is an estimate, not authentication policy.

CI checks the exact original blob hash, compressed size and CPU times on
synthetic fixtures (Node runner, not a mobile-device benchmark), plus
Chromium/WebKit meter layout and sequential animations. The worker isolates
computation from the UI thread. No password fixtures copied from users.
