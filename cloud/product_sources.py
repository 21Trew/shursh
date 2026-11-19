"""Store URL adapters, ISBN checks, and offline approved partner YML catalog

The catalog adapter reads only a local file deliberately installed by the owner
with permission from the feed provider. No feed is downloaded from a user URL
Do not use undocumented marketplace endpoints or browser challenge bypasses
"""
from functools import lru_cache
from pathlib import Path
import os
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

BOOK_STORES = frozenset(("bookvoed", "chitai-gorod", "labirint"))
MARKETPLACE_STORES = frozenset(("ozon", "wildberries", "yandex-market"))
MAX_FEED_BYTES = 4_000_000

# These adapters recognize stable customer-facing item identifiers.
# They do not assert that a public catalog API exists for the platform
_STORE_PATTERNS = (
    ("ozon", re.compile(r"(?:[a-z0-9-]+\.)*ozon\.ru$", re.I), re.compile(r"/product/(?:[^/?]*?-)?(\d{5,})(?:/|$)", re.I)),
    ("wildberries", re.compile(r"(?:[a-z0-9-]+\.)*wildberries\.ru$|(?:[a-z0-9-]+\.)*wb\.ru$", re.I), re.compile(r"/catalog/(\d{4,})/detail\.aspx", re.I)),
    ("yandex-market", re.compile(r"^market\.yandex\.ru$", re.I), re.compile(r"/(?:card|product--[^/]+|product)/[^?#]*/(\d{5,})(?:/|$)", re.I)),
    ("bookvoed", re.compile(r"(?:[a-z0-9-]+\.)*bookvoed\.ru$", re.I), re.compile(r"/product/(?:[^/?]*?-)?(\d{3,})(?:/|$)", re.I)),
    ("chitai-gorod", re.compile(r"(?:[a-z0-9-]+\.)*chitai-gorod\.ru$", re.I), re.compile(r"/product/(?:[^/?]*?-)?(\d{3,})(?:/|$)", re.I)),
    ("labirint", re.compile(r"(?:[a-z0-9-]+\.)*labirint\.ru$", re.I), re.compile(r"/books/(\d{3,})(?:/|$)", re.I)),
)


def adapter_for(url):
    """Return safe store/merchant product ID metadata without network access"""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    for name, domain, item in _STORE_PATTERNS:
        if domain.fullmatch(host):
            match = item.search(parts.path)
            return {"store": name, "product_id": match.group(1) if match else None}
    return {"store": "other", "product_id": None}


def valid_isbn(value):
    digits = re.sub(r"[\s\-]", "", str(value)).upper()
    if len(digits) == 13 and digits.isdigit():
        return digits.startswith(("978", "979")) and (
            sum((1 if i % 2 == 0 else 3) * int(v) for i, v in enumerate(digits)) % 10 == 0
        )
    if len(digits) == 10 and re.fullmatch(r"\d{9}[\dX]", digits):
        return sum((10 - i) * (10 if v == "X" else int(v)) for i, v in enumerate(digits)) % 11 == 0
    return False


def isbn_from_text(value):
    """Only accept validated ISBN explicitly marked in HTML/metadata text"""
    if not isinstance(value, str) or not value:
        return None
    # Bounded scan, no general 13-digit SKUs silently treated as ISBNs
    for match in re.finditer(r"(?i)\bisbn(?:-1[03])?\b[^0-9]{0,60}([0-9Xx\- \u00a0]{10,26})", value[:300000]):
        raw = re.sub(r"[\s\-]", "", match.group(1)).upper()
        for size in (13, 10):
            candidate = raw[:size]
            if valid_isbn(candidate):
                return candidate
    return None


def _tag_value(element, name):
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == name:
            return (child.text or "").strip()
    return ""


def parse_approved_yml(blob):
    """Parse a SMALL, legally supplied Yandex Market Language feed (no network)

    Returns URL-keyed records, never credentials, HTML or external XML entities
    Full feeds must be prefiltered offline to a compact authorized subset
    """
    if not isinstance(blob, bytes) or not 0 < len(blob) <= MAX_FEED_BYTES:
        raise ValueError("Approved catalog size outside limits")
    lowered = blob.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("Document type and entity declarations are not allowed")
    try:
        root = ElementTree.fromstring(blob)
    except ElementTree.ParseError:
        raise ValueError("Invalid approved XML catalog") from None
    entries = {}
    for offer in root.iter():
        if offer.tag.rsplit("}", 1)[-1] != "offer":
            continue
        address = _tag_value(offer, "url")
        parts = urlsplit(address)
        if (parts.scheme != "https" or not parts.hostname or parts.username or
                parts.password or parts.port not in (None, 443)):
            continue
        adapter = adapter_for(address)
        if adapter["store"] not in BOOK_STORES | MARKETPLACE_STORES or not adapter["product_id"]:
            continue
        name = (_tag_value(offer, "name") or _tag_value(offer, "model"))[:130]
        if not name:
            continue
        currency = _tag_value(offer, "currencyId").upper()
        raw_price = _tag_value(offer, "price")
        price = raw_price if currency in ("RUB", "RUR") and re.fullmatch(r"\d{1,8}(?:\.\d{1,2})?", raw_price) else None
        identifier = _tag_value(offer, "isbn")
        image = _tag_value(offer, "picture")
        entries[(adapter["store"], adapter["product_id"])] = {
            "title": name, "price": price, "currency": "RUB",
            "image_url": image or None,
            "isbn": identifier if valid_isbn(identifier) else None,
        }
    return entries


@lru_cache(maxsize=2)
def _approved_catalog(path):
    # Operator-provided local path only. Do not accept file paths in user requests
    file = Path(path)
    if not file.is_file() or file.stat().st_size > MAX_FEED_BYTES:
        return {}
    return parse_approved_yml(file.read_bytes())


def approved_book_offer(url):
    """Optional, disabled until an approved catalog is installed in deployment"""
    path = os.environ.get("SHURSH_APPROVED_BOOK_CATALOG_FILE", "").strip()
    if not path:
        return None
    adapter = adapter_for(url)
    if adapter["store"] not in BOOK_STORES or not adapter["product_id"]:
        return None
    try:
        return _approved_catalog(path).get((adapter["store"], adapter["product_id"]))
    except (OSError, ValueError):
        return None

def approved_marketplace_offer(url):
    """Use only a local XML/YML catalog supplied with explicit reuse rights.

    Disabled by default: no remote feed request or seller credential used.
    """
    path = os.environ.get("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE", "").strip()
    item = adapter_for(url)
    if not path or item["store"] not in MARKETPLACE_STORES or not item["product_id"]:
        return None
    try:
        return _approved_catalog(path).get((item["store"], item["product_id"]))
    except (OSError, ValueError):
        return None
