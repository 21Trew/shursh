# UI CSS rule registry (generated)

Source of truth: `public/styles.css` at the current checkout. Regenerate:
`python tools/ui_audit.py` (`--check` in CI).

A repeat is not automatically a defect: responsive and state-specific overrides are expected.
A **conflict** here means the same selector, CSS property and at-rule context
have different declarations in source order. The last declaration is not
necessarily the winner if specificity, importance or cascading conditions differ.

- Qualified rule blocks: **890**
- Unique selectors: **618**
- Selectors in multiple blocks: **182**
- Differing declarations in the same context: **0**
- At-rule contexts: **16**

## Same-context differing declarations

| Selector | Context | Property | Earlier → later | Source lines |
|---|---|---|---|---|

## Selectors declared in multiple blocks

| Selector | Blocks | Contexts / source lines |
|---|---:|---|
| `.nav` | 8 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2, base > @media (min-width:761px) and (max-width:920px)@5, base@149, base > @media (max-width:760px)@219, base > @med…` |
| `.game-gifts-track` | 7 | `base@122, base > @media (prefers-reduced-motion:reduce)@144, base@188, base@253, base > @media (max-width:760px)@266, base@345, base > @media (max-width:520px)@349` |
| `.game-gifts-track .game-gift-card` | 6 | `base@124, base > @media (max-width:520px)@139, base > @media (max-width:760px)@267, base > @media (max-width:440px)@277, base@347, base > @media (max-width:520px)@350` |
| `.hero` | 5 | `base@2, base > @media (min-width:1450px)@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.hero h1` | 5 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.hero-visual` | 5 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.container` | 4 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@441, base > @media (max-width:400px)@485` |
| `.dashboard-welcome` | 4 | `base@26, base > @media (max-width:760px)@46, base > @media (max-width:760px)@479, base > @media (max-width:400px)@498` |
| `.dashboard-welcome h1` | 4 | `base@27, base@368, base > @media (max-width:760px)@480, base > @media (max-width:400px)@499` |
| `.game-chat-form` | 4 | `base@111, base > @media (max-width:580px)@115, base@396, base > @media (max-width:760px)@470` |
| `.game-chat-messages` | 4 | `base@106, base > @media (max-width:580px)@115, base@394, base > @media (max-width:760px)@468` |
| `.game-chat-panel` | 4 | `base@103, base > @media (max-width:580px)@115, base > @media (max-width:760px)@466, base > @media (max-width:400px)@491` |
| `.game-gifts-track .game-gift-card .wish-image` | 4 | `base@125, base > @media (max-width:760px)@268, base > @media (max-width:440px)@278, base > @media (max-width:520px)@351` |
| `.header-actions` | 4 | `base@2, base > @media (max-width:760px)@2, base@359, base > @media (max-width:760px)@446` |
| `.hero-visual:before` | 4 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.nav a` | 4 | `base@2, base > @media (max-width:420px)@2, base@150, base > @media (max-width:760px)@220` |
| `.secret-card.revealed` | 4 | `base@2, base@169, base@385, base > @media (max-width:760px)@461` |
| `.site-header .nav` | 4 | `base@312, base > @media (max-width:760px)@315, base@363, base > @media (max-width:760px)@444` |
| `.topbar` | 4 | `base@2, base > @media (max-width:760px)@2, base > @media (min-width:761px) and (max-width:920px)@5, base > @media (max-width:760px)@442` |
| `.wishlist-grid` | 4 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.bubble-heart` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.cards-grid` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.chat-message` | 3 | `base@107, base@395, base > @media (max-width:760px)@469` |
| `.dashboard-santa-grid` | 3 | `base@39, base > @media (max-width:760px)@46, base > @media (min-width:761px) and (max-width:1100px)@47` |
| `.detail-top` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.detail-top .detail-art svg` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.detail-top h1` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.emoji-grid` | 3 | `base@436, base > @media (max-width:760px)@478, base > @media (max-width:400px)@497` |
| `.game-chat-form button` | 3 | `base > @media (max-width:580px)@115, base > @media (max-width:760px)@471, base > @media (max-width:400px)@492` |
| `.game-chat-tabs` | 3 | `base@104, base@392, base > @media (max-width:760px)@467` |
| `.game-gifts-track .game-gift-card .wish-content` | 3 | `base@127, base > @media (max-width:760px)@270, base > @media (max-width:520px)@352` |
| `.game-gifts-track .game-gift-card .wish-desc` | 3 | `base@129, base > @media (max-width:760px)@271, base > @media (max-width:520px)@353` |
| `.header-actions .btn-ghost` | 3 | `base > @media (max-width:760px)@2, base > @media (max-width:920px)@89, base > @media (max-width:760px)@449` |
| `.header-bell` | 3 | `base@360, base > @media (max-width:760px)@448, base@503` |
| `.list-cover` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.list-info h3` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.logo` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (min-width:761px) and (max-width:920px)@5` |
| `.modal` | 3 | `base@2, base@181, base > @media (max-width:760px)@221` |
| `.modal-backdrop .modal` | 3 | `base > @media (max-width:760px)@519, base > @media (prefers-reduced-motion:reduce)@526, base > @media (max-width:760px)@534` |
| `.modal-scroll-area` | 3 | `base@182, base > @media (max-width:760px)@222, base > @media (max-width:440px)@227` |
| `.page` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:760px)@450` |
| `.page-hero` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:760px)@451` |
| `.santa-detail-layout` | 3 | `base@2, base > @media (max-width:760px)@265, base > @media (max-width:760px)@452` |
| `.secret-card.revealed .recipient-summary` | 3 | `base@170, base@386, base > @media (max-width:760px)@462` |
| `.secret-card.revealed .recipient-wishes` | 3 | `base@174, base@387, base > @media (max-width:760px)@464` |
| `.showcase` | 3 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2` |
| `.showcase-mock` | 3 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2` |
| `.site-header .nav a` | 3 | `base > @media (max-width:760px)@316, base@364, base > @media (max-width:760px)@445` |
| `.social-profile-identity` | 3 | `base@407, base > @media (max-width:760px)@473, base > @media (max-width:400px)@493` |
| `.social-profile-identity .profile-emoji` | 3 | `base@411, base > @media (max-width:760px)@474, base > @media (max-width:400px)@494` |
| `.social-search` | 3 | `base@286, base@431, base > @media (max-width:760px)@472` |
| `.social-stat-grid` | 3 | `base@300, base > @media (max-width:760px)@318, base > @media (max-width:440px)@322` |
| `.step` | 3 | `base@2, base > @media (max-width:1100px)@2, base > @media (max-width:760px)@2` |
| `.wish-content h3` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.wish-edit-modal .modal-scroll-area` | 3 | `base@254, base@328, base > @media (max-width:760px)@336` |
| `.wish-edit-modal .modal-scroll-area .form-actions` | 3 | `base@258, base > @media (max-width:760px)@274, base > @media (max-width:440px)@280` |
| `.wish-image` | 3 | `base@2, base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `html` | 3 | `base@2, base > @media (prefers-reduced-motion:reduce)@2, base@180` |
| `.auth-confirm-card` | 2 | `base@16, base > @media (max-width:480px)@24` |
| `.auth-confirm-card p` | 2 | `base@21, base > @media (max-width:480px)@24` |
| `.auth-confirm-card strong` | 2 | `base@20, base > @media (max-width:480px)@24` |
| `.auth-confirm-symbol` | 2 | `base@17, base > @media (max-width:480px)@24` |
| `.auth-confirm-symbol .icon` | 2 | `base@18, base > @media (max-width:480px)@24` |
| `.btn-row` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.bubble-gift` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.dashboard-empty` | 2 | `base@35, base > @media (max-width:760px)@46` |
| `.dashboard-empty-art` | 2 | `base@36, base > @media (max-width:760px)@46` |
| `.dashboard-metrics` | 2 | `base@30, base > @media (max-width:760px)@46` |
| `.dashboard-metrics>div` | 2 | `base@31, base > @media (max-width:760px)@46` |
| `.dashboard-page` | 2 | `base@26, base > @media (max-width:760px)@46` |
| `.dashboard-section` | 2 | `base@33, base > @media (max-width:760px)@46` |
| `.dashboard-section-head` | 2 | `base@33, base > @media (max-width:760px)@46` |
| `.dashboard-welcome .btn-row` | 2 | `base@370, base > @media (max-width:760px)@481` |
| `.dashboard-welcome-art` | 2 | `base@29, base > @media (max-width:760px)@46` |
| `.detail-actions` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.final-cta` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.final-cta h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.footer` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.footer-credit` | 2 | `base@211, base > @media (max-width:760px)@223` |
| `.form-actions` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.form-grid` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.game-chat-refresh` | 2 | `base@113, base@398` |
| `.game-gifts-arrows` | 2 | `base@120, base@164` |
| `.game-gifts-arrows .btn` | 2 | `base@121, base > @media (max-width:520px)@142` |
| `.game-gifts-carousel` | 2 | `base@118, base@252` |
| `.game-gifts-toolbar` | 2 | `base@119, base@163` |
| `.game-gifts-track .game-gift-card .wish-content h3` | 2 | `base@128, base > @media (max-width:520px)@354` |
| `.game-gifts-track .game-gift-card .wish-image svg` | 2 | `base@126, base > @media (max-width:760px)@269` |
| `.game-gifts-track .game-gift-card .wish-price` | 2 | `base@130, base > @media (max-width:520px)@355` |
| `.header-actions .btn-small` | 2 | `base > @media (max-width:760px)@2, base > @media (max-width:420px)@2` |
| `.header-bell:hover,.header-bell.active` | 2 | `base@361, base@504` |
| `.hero-copy` | 2 | `base@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.hero-description` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.hero-visual>svg` | 2 | `base@2, base > @media (min-width:761px) and (max-width:980px)@6` |
| `.invite-card` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.invite-info` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.list-bottom` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.list-card,.dashboard-santa-card,.santa-list-card,.wish-card` | 2 | `base@66, base > @media (prefers-reduced-motion:reduce)@73` |
| `.list-info` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.list-info p` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.logo-dot` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.marquee-inner` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.mock-art` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.mock-item .mock-copy` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.mock-item strong` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.modal h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.modal-backdrop` | 2 | `base@2, base > @media (max-width:760px)@518` |
| `.modal-close` | 2 | `base@2, base@183` |
| `.my-wishes-list` | 2 | `base@2, base@161` |
| `.nav a::before` | 2 | `base@151, base > @media (prefers-reduced-motion:reduce)@230` |
| `.occasion-chip` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.occasions` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.page-hero h1` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.panel-heading-actions` | 2 | `base@74, base > @media (max-width:520px)@85` |
| `.participant-preferences` | 2 | `base@233, base@381` |
| `.privacy-illustration` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.privacy-strip` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.privacy-strip h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.profile-actions` | 2 | `base@416, base > @media (max-width:760px)@476` |
| `.profile-actions .btn` | 2 | `base@417, base > @media (max-width:760px)@477` |
| `.recipient-wishes` | 2 | `base@2, base@134` |
| `.santa-art` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.santa-copy` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.santa-copy h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.santa-detail-layout .panel` | 2 | `base > @media (max-width:760px)@453, base > @media (max-width:400px)@486` |
| `.santa-detail-layout .person-row` | 2 | `base > @media (max-width:760px)@457, base > @media (max-width:400px)@488` |
| `.santa-detail-layout .person-row .avatar` | 2 | `base > @media (max-width:760px)@458, base > @media (max-width:400px)@487` |
| `.santa-detail-layout .person-topline` | 2 | `base@402, base > @media (max-width:400px)@489` |
| `.santa-feature` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.santa-grid` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.santa-list-card .sparkle-deco` | 2 | `base@2, base@507` |
| `.secret-card` | 2 | `base@2, base@166` |
| `.secret-card .envelope-svg` | 2 | `base@2, base@168` |
| `.secret-card h2` | 2 | `base@2, base@167` |
| `.secret-card.revealed .recipient` | 2 | `base@173, base@391` |
| `.secret-card.revealed .recipient-summary>.icon` | 2 | `base@171, base > @media (max-width:760px)@463` |
| `.secret-card.revealed .recipient-wishes .participant-preferences-summary` | 2 | `base@388, base > @media (max-width:760px)@465` |
| `.secret-card.revealed .recipient-wishes>strong` | 2 | `base@175, base@390` |
| `.section` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.section-intro` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.section-intro h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.section-intro p` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.share-field` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.shop-import-row` | 2 | `base@56, base > @media (max-width:480px)@62` |
| `.shop-import-status` | 2 | `base@58, base > @media (max-width:480px)@62` |
| `.showcase-copy h2` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.site-header .topbar` | 2 | `base > @media (max-width:760px)@2, base > @media (max-width:920px)@90` |
| `.skeleton-bar,.skeleton-card` | 2 | `base@509, base > @media (prefers-reduced-motion:reduce)@516` |
| `.skeleton-card` | 2 | `base@514, base > @media (max-width:760px)@522` |
| `.skeleton-cards` | 2 | `base@513, base > @media (max-width:760px)@521` |
| `.skeleton-title` | 2 | `base@511, base > @media (max-width:760px)@523` |
| `.social-page` | 2 | `base@283, base > @media (max-width:760px)@319` |
| `.social-person` | 2 | `base@290, base > @media (max-width:760px)@320` |
| `.social-person-name` | 2 | `base@294, base@428` |
| `.social-profile-hero` | 2 | `base@295, base > @media (max-width:760px)@317` |
| `.social-profile-hero>.avatar` | 2 | `base@296, base > @media (max-width:440px)@322` |
| `.social-search .share-field` | 2 | `base@433, base > @media (max-width:400px)@495` |
| `.social-search .share-field .btn` | 2 | `base@434, base > @media (max-width:400px)@496` |
| `.step h3` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.step p` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.step-art` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.step-art svg` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.step-number` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.steps` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.ui-select-menu` | 2 | `base@205, base@263` |
| `.ui-select-menu [role="option"]` | 2 | `base@206, base > @media (max-width:440px)@228` |
| `.ui-select-trigger` | 2 | `base@200, base > @media (prefers-reduced-motion:reduce)@230` |
| `.user-name` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.wish-action` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.wish-content` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.wish-controls` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.wish-controls .btn` | 2 | `base@2, base > @media (max-width:420px)@2` |
| `.wish-desc` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.wish-detail-image,.wish-detail-art` | 2 | `base@81, base > @media (max-width:520px)@85` |
| `.wish-edit-modal .modal-close` | 2 | `base@259, base@332` |
| `.wish-edit-modal .modal-fixed-footer` | 2 | `base@330, base > @media (max-width:760px)@337` |
| `.wish-edit-modal .modal-fixed-footer .form-actions` | 2 | `base@331, base > @media (max-width:440px)@340` |
| `.wish-edit-modal .modal-fixed-header` | 2 | `base@326, base > @media (max-width:760px)@335` |
| `.wish-edit-modal .modal-scroll-area>.modal-subtitle` | 2 | `base@256, base@333` |
| `.wish-edit-modal .modal-scroll-area>h2` | 2 | `base@255, base > @media (max-width:760px)@273` |
| `.wish-price` | 2 | `base@2, base > @media (max-width:760px)@2` |
| `.wishlist-grid .wish-image` | 2 | `base > @media (max-width:760px)@272, base > @media (max-width:440px)@279` |

## Context inventory

| Context | Declaration count |
|---|---:|
| `base` | 2250 |
| `base > @media (max-width:760px)` | 300 |
| `base > @media (max-width:420px)` | 30 |
| `base > @media (max-width:400px)` | 23 |
| `base > @media (max-width:440px)` | 18 |
| `base > @media (max-width:520px)` | 17 |
| `base > @media (max-width:480px)` | 14 |
| `base > @media (max-width:1100px)` | 13 |
| `base > @media (min-width:761px) and (max-width:980px)` | 12 |
| `base > @media (prefers-reduced-motion:reduce)` | 10 |
| `base > @media (min-width:761px) and (max-width:920px)` | 5 |
| `base > @media (max-width:920px)` | 5 |
| `base > @media (max-width:580px)` | 4 |
| `base > @media (max-width:1130px)` | 4 |
| `base > @media (min-width:1450px)` | 1 |
| `base > @media (min-width:761px) and (max-width:1100px)` | 1 |
