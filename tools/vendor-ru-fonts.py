#!/usr/bin/env python3
"""Fetch verified Fontsource WOFF2 subsets once into git, not at runtime.

Only 6 approved Open Font License files, pinned to one upstream Git commit.
No downloaded code is executed. Output licenses are tracked separately.
"""
import hashlib
import urllib.request
from pathlib import Path

UPSTREAM_COMMIT = "5a72889057f592bb0659629e38337359f94d53b2"
FILES = {
    "onest-cyrillic-ext-wght-normal.woff2": ("302e231fa03029b2b54cb97ec126d0a5c6eb32bb", 10540),
    "onest-cyrillic-wght-normal.woff2": ("7a139b02364f0570cfab1165ffca91f6a6e4dff8", 15860),
    "onest-latin-wght-normal.woff2": ("bd5ac33465262fc8a62437e2417948574cdbf53b", 33760),
    "unbounded-cyrillic-ext-wght-normal.woff2": ("b0c60540f19957dd076920db99dd430afc140007", 1840),
    "unbounded-cyrillic-wght-normal.woff2": ("102b4544462df67852ac719f97301a83c9b9de5f", 31424),
    "unbounded-latin-wght-normal.woff2": ("3260a1939eb5a3020b48235c1a52852080f929b6", 50904),
}
folder = Path(__file__).resolve().parents[1] / "public" / "fonts"
folder.mkdir(parents=True, exist_ok=True)

for filename, (blob_sha, expected_bytes) in FILES.items():
    family = filename.split("-")[0]
    url = (f"https://raw.githubusercontent.com/fontsource/font-files/"
           f"{UPSTREAM_COMMIT}/fonts/variable/{family}/files/{filename}")
    with urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent":"Shursh-Font-Vendor/1.0"}), timeout=25) as response:
        data = response.read(expected_bytes + 1)
    actual_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()
    if len(data) != expected_bytes or actual_sha != blob_sha or data[:4] != b"wOF2":
        raise RuntimeError(f"Invalid source content: {filename}")
    (folder / filename).write_bytes(data)
    print(f"Verified {filename}: {len(data)} bytes, Git blob {actual_sha}", flush=True)
print(f"Total {sum(size for _, size in FILES.values())} bytes, ready", flush=True)
