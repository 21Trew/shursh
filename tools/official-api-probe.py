"""One-shot public availability check of official seller and bibliographic APIs.

Run only on explicit diagnostics. No API keys, cookies, bypasses, retries,
user-provided URLs, or response bodies printed. HTTP statuses describe the
unauthenticated request from the runner, not general API availability.
"""
import json
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINTS = (
    ("ozon_seller", "https://api-seller.ozon.ru/v1/seller/info", "seller"),
    ("wildberries_seller", "https://common-api.wildberries.ru/api/v1/seller-info", "seller"),
    ("yandex_market_partner", "https://api.partner.market.yandex.ru/v2/campaigns", "seller"),
    ("open_library_isbn", "https://openlibrary.org/isbn/9780140328721.json", "book"),
    ("google_books_isbn", "https://www.googleapis.com/books/v1/volumes?q=isbn%3A9780140328721&maxResults=1", "google"),
)

def probe(name, address, kind):
    started = monotonic()
    result = {"source": name, "title": False, "price": False, "photo": False}
    try:
        request = Request(address, headers={
            "User-Agent": "ShurshProductImporter/1.0",
            "Accept": "application/json",
        })
        with urlopen(request, timeout=8) as response:
            result["http"] = response.status
            raw = response.read(120001)
        if len(raw) > 120000:
            result["result"] = "oversized_response"
        elif kind == "book":
            entry = json.loads(raw)
            covers = entry.get("covers") if isinstance(entry, dict) else None
            verified_photo = False
            if isinstance(covers, list) and covers and type(covers[0]) is int:
                cover_url = ("https://covers.openlibrary.org/b/id/" +
                             str(covers[0]) + "-M.jpg?default=false")
                image_req = Request(cover_url, headers={
                    "User-Agent": "ShurshWishlist/0.1 (lvs.codelab@yandex.ru)"})
                try:
                    with urlopen(image_req, timeout=8) as image:
                        verified_photo = (image.status == 200 and
                                          image.headers.get("Content-Type", "").startswith("image/") and
                                          image.read(3) == b"\\xff\\xd8\\xff")
                except (HTTPError, URLError, OSError, TimeoutError):
                    verified_photo = False
            result.update(title=bool(entry.get("title")), photo=verified_photo,
                          result="book_metadata_only")
        elif kind == "google":
            entry = json.loads(raw)
            volumes = entry.get("items") or []
            info = volumes[0].get("volumeInfo", {}) if volumes else {}
            result.update(title=bool(info.get("title")),
                          photo=bool(info.get("imageLinks")),
                          result="book_metadata_only")
        else:
            result["result"] = "unexpected_public_response"
    except HTTPError as exc:
        result.update(http=exc.code, result="http_rejected")
    except (URLError, OSError, TimeoutError, ValueError, TypeError) as exc:
        result.update(result="transport_or_parse_failure", error=type(exc).__name__)
    result["seconds"] = round(monotonic() - started, 2)
    return result

if __name__ == "__main__":
    for name, url, kind in ENDPOINTS:
        print("OFFICIAL_API_PROBE " + json.dumps(probe(name, url, kind),
                                                   ensure_ascii=False), flush=True)
