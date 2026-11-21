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
