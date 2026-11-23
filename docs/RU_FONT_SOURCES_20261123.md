# Local font assets for Shursh

Source: [Fontsource font-files](https://github.com/fontsource/font-files/tree/5a72889057f592bb0659629e38337359f94d53b2/fonts/variable), commit `5a72889057f592bb0659629e38337359f94d53b2`, variable weight WOFF2.

| Family | Subsets | Total |
|---|---|---|
| Onest | cyrillic-ext, cyrillic, latin | 60,160 bytes |
| Unbounded | cyrillic-ext, cyrillic, latin | 84,168 bytes |
| **Total** | 6 assets | **144,328 bytes** |

License: SIL Open Font License 1.1. Text: `licenses/Onest-OFL.txt` and `licenses/Unbounded-OFL.txt`.

Files are verified against exact upstream Git blob SHA-1 before vendoring by `tools/vendor-ru-fonts.py`. All six weights are variable; the original Google Fonts dependency can be removed without changing the declared font family/weight. Languages outside the included Latin/Cyrillic subsets fall back to the browser/system font. No font downloads occur at build or runtime once assets are committed.

This eliminates the external Google Fonts CSS request and gives the application a first-party font origin. It does not cure ISP/TCP reachability issues connecting to the primary Vercel address.
