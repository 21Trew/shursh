# Password strength (Auth vNext)

The UI uses the original Dropbox zxcvbn 4.4.2 (MIT), pinned to upstream
blob 0daf83098e4c90508dcbd69257c6f16ee4da3a8b:
https://github.com/dropbox/zxcvbn/tree/v4.4.2 .
The bundled license is retained; the unused source-map directive is removed.
The static asset is self-hosted and loaded by a Web Worker only after input
in a new-password field. No initial page or ordinary login bundle growth from
the library. No CDN, runtime npm install, CSP relaxation or external password
estimation service. Worker replies contain only request ID, score and a coarse reason code, never matched substrings. Nonempty invalid passwords and valid passwords with missing groups or a weak score can display up to six cryptographically generated replacements; the number visible is maximized by selecting the shortest measured tag widths that fit the available row, including spacing. Candidate length and character-class mix depend on the typed input, with all required recommendation groups represented, but literal input fragments are never copied. They are stored only in a WeakMap, masked when the input is masked, and cleared on edits. Selecting one fills both password fields without changing the current visibility.
Debounced, one in-flight estimate with latest-only queued input; obsolete
results are ignored. Empty/overlong inputs clear the meter. Worker errors
clear the estimate rather than guessing; an unresponsive worker is terminated
at 15 seconds and can be retried after a 30-second cooldown. Existing submit validation and HIBP
are unchanged. Original English/password dictionaries are not a comprehensive
Russian-language dictionary. Levels map zxcvbn scores 0/1 → Weak, 2 → Medium,
3 → Good, 4 → Strong. Score is an estimate, not authentication policy.

CI checks the exact original blob hash, compressed size and CPU times on
synthetic fixtures (Node runner, not a mobile-device benchmark), plus
Chromium/WebKit meter layout and frame-by-frame continuous fill/reversal checks. A single interpolated CSS scalar drives all four clipped tracks without per-segment timers; reduced-motion mode disables the animation. The worker isolates
computation from the UI thread. No password fixtures copied from users.

The quality estimator is displayed only for passwords that pass mandatory
local shape validation. Non-empty invalid input shows “Не подходит”, with an
explicit field error; obsolete worker responses cannot override this state.
This is distinct from a weak but policy-compliant zxcvbn score. Character classes are advisory, not mandatory; weak scores never block submit.
Mandatory shape checks still enforce eight characters and the existing bcrypt
boundary, and reject Russian letters (А–Я, а–я, Ё, ё), controls and invalid
Unicode. Existing passwords are unaffected by the new-letter restriction on login.
Advice lists only missing character classes, never claims uniqueness and hides on valid passwords with all groups unless the estimator reports a weak pattern. Mandatory length feedback reports the exact remaining character count. Mandatory errors remain visible above replacement suggestions; a short or Cyrillic password must never suppress help. No suggestions are shown for an empty input. Previously agreed HIBP
breach blocking is separate from strength advice and remains unchanged.
Email-format feedback uses matching reason-specific checks in browser and
hosted backend. The supported address format is unquoted ASCII local part
and ASCII DNS domain (including punycode); commas, Cyrillic and other
unsupported characters are rejected. The OTP, not syntax, verifies ownership.
No DNS lookup or TLD allowlist is added to form validation. A single trailing domain dot is incomplete, not an extra character; invalid domain characters take priority over missing suffixes. Consumer Gmail/Googlemail base usernames allow ASCII letters, digits and dots; plus aliases remain supported. Other providers retain the general local-part character set.

Auth email inputs preserve the raw typed address (`type=text`, `inputmode=email`,
`autocomplete=email`), preventing browser IDN normalization from hiding Cyrillic
from the app's ASCII validator. Nonempty email edits validate immediately;
empty untouched fields stay neutral. Both browser regression tests exercise
an invalid first edit while the field remains focused.
