# Visual baselines for PR #4

`ui-gallery-palette.png` is a deliberately narrow pixel golden, consisting
of 8 exact 96 × 24 sampled paint strips in Gallery order:
`--paper`, `--paper2`, `--ink`, `--peach`, `--lilac`, `--mint`,
`--yellow`, `--border`.

These areas contain no text, font glyphs, gradients, SVG antialiasing,
animation or platform-specific rasterization. Chromium and WebKit must match
the same screenshot exactly across all 5 viewport widths. The reference is
anchored to the palette in `DESIGN.md`, not generated from current runtime CSS.

Full-page Gallery and authenticated-flow screenshots are CI artifacts for
**human comparison**. Those are intentionally not pixel-gated until a
human-approved, OS/font-stable baseline exists. Do not auto-approve new
screenshots from the code under test: doing so hides regressions.

To update this golden after an intentional brand palette change: edit the
explicit accepted palette in the baseline generation procedure and update
the PNG in a reviewed PR with screenshot evidence.


## Component surface screenshot regression

`ui-components-flat.png` adds a fixed pixel atlas for **stable color interiors**
of 5 existing button variants, 4 card surfaces and 3 form controls. Each strip is
96 × 24 pixels, sampled from a real Playwright screenshot of the actual
production CSS selector in Chromium and WebKit at 375/390/768/1024/1440 px.

Accepted source values are from the current playful-editorial DESIGN.md and
CSS contract, NOT from a runtime screenshot automatically accepted on failure:

| Row | Component | Accepted sampled color |
|---|---|---|
| 1 | dark button | `#27272b` |
| 2 | peach button | `#f9c6ac` |
| 3 | lilac button | `#d9c9f2` |
| 4 | soft button on paper | `#f9f7ef` |
| 5 | danger button | `#fff5f3` |
| 6 | panel card | `#fffdf8` |
| 7 | wishlist card | `#ffffff` |
| 8 | Santa card | `#f7e9db` |
| 9 | input | `#ffffff` |
| 10 | textarea | `#ffffff` |
| 11 | select | `#ffffff` |

The test also validates border colors and corner radii, and saves full
component-fixture screenshots including hover/focus for human visual review.

Do **not** claim that these color-strip references approve complete button/card/
input imagery: fonts, text, SVG, native controls, borders, shadows and animations
may vary between browser engines. Full visual references require explicit human
approval before becoming strict full-component pixel goldens.

## Effective declaration lock

`ui-css-effective.sha256` hashes all final declaration winners by
at-rule context, selector, property, importance and value. It was generated
**before** removing the overridden CSS rules from the previous approved PR
head. `python tools/css_effective_check.py --check` must continue to pass.

This statically verifies that the refactor changed no final CSS declaration.
It complements (but does not replace) the Chromium/WebKit screenshot and
authenticated navigation performance checks. Do not update it to silence CI
without explicit review of intended style changes.

The Santa cards have a deliberate alternating :nth-child(even) lilac background.
Both even/odd variants are now independently pixel-gated and border-checked.
