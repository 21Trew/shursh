"""One-shot live availability checks for permitted public product and book sources.

Run explicitly only for diagnostics: PYTHONPATH=. python tools/free-source-probe.py
Never sends credentials, bypasses a challenge, logs product URLs, or writes data
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from cloud.product_metadata import fetch_product_metadata
from server import ApiError

SAMPLES = (
    ("Ozon", "https://www.ozon.ru/product/konstruktor-lego-classic-nabor-dlya-tvorchestva-srednego-razmera-484-detali-vozrast-ot-4-10696-30947723/"),
    ("Wildberries", "https://www.wildberries.ru/catalog/140707460/detail.aspx"),
    ("YandexMarket", "https://market.yandex.ru/card/patrioticheskaya-nastolnaya-igra-sluzhu-otechestvu-dlya-vzroslykh-i-detey-ot-6-let--klevyye-igry/103227515458"),
    ("Bookvoed", "https://www.bookvoed.ru/product/literatura-8713602"),
    ("ChitaiGorod", "https://www.chitai-gorod.ru/product/literatura-3109366"),
)

def probe_page(name, url):
    started = monotonic()
    try:
        data = fetch_product_metadata(url)
        answer = {"name": name, "status": "parsed",
                  "title": bool(data.get("title")), "price": data.get("price") is not None,
                  "image": bool(data.get("image_data"))}
    except ApiError as exc:
        answer = {"name": name, "status": "rejected", "code": exc.status, "reason": str(exc)[:100],
                  "title": False, "price": False, "image": False}
    except Exception as exc:
        answer = {"name": name, "status": "error", "error": type(exc).__name__,
                  "title": False, "price": False, "image": False}
    answer["elapsed_s"] = round(monotonic() - started, 2)
    return answer

def probe_api(name, url, kind):
    started = monotonic()
    try:
        request = Request(url, headers={"User-Agent": "ShurshProductImporter/1.0",
                                         "Accept": "application/json"})
        with urlopen(request, timeout=7) as response:
            if response.status != 200 or len(raw := response.read(160000)) > 159999:
                raise ValueError("unavailable")
        data = json.loads(raw)
        if kind == "openlibrary":
            answer = {"name": name, "status": "parsed", "title": bool(data.get("title")),
                      "price": False, "image": bool(data.get("covers")),
                      "source": "OpenLibrary edition JSON"}
        else:
            volumes = data.get("items") or []
            metadata = volumes[0].get("volumeInfo", {}) if volumes else {}
            answer = {"name": name, "status": "parsed", "title": bool(metadata.get("title")),
                      "price": False, "image": bool(metadata.get("imageLinks")),
                      "source": "Google Books volumes search"}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        answer = {"name": name, "status": "unavailable", "reason": type(exc).__name__,
                  "title": False, "price": False, "image": False}
    answer["elapsed_s"] = round(monotonic() - started, 2)
    return answer

def main():
    tasks = [(probe_page, (name, url)) for name, url in SAMPLES]
    tasks.extend([
        (probe_api, ("OpenLibrary", "https://openlibrary.org/isbn/9780140328721.json", "openlibrary")),
        (probe_api, ("GoogleBooks", "https://www.googleapis.com/books/v1/volumes?q=isbn%3A9780140328721&maxResults=1", "google")),
    ])
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fn, *args) for fn, args in tasks]
        for f in as_completed(futures):
            print("FREE_SOURCE_PROBE " + json.dumps(f.result(), ensure_ascii=False), flush=True)
    print("Partner XML feeds require explicit approved partner access and were not fetched", flush=True)

if __name__ == "__main__":
    main()
