"""Manual one-shot public product-page diagnostics for Russian marketplaces only.

No credentials, cookies, bypass, or retries; does not log product URLs.
Run intentionally with PYTHONPATH=. python tools/free-source-probe.py
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic
from cloud.product_metadata import fetch_product_metadata
from server import ApiError

SAMPLES = (
    ("Ozon", "https://www.ozon.ru/product/konstruktor-lego-classic-nabor-dlya-tvorchestva-srednego-razmera-484-detali-vozrast-ot-4-10696-30947723/"),
    ("Wildberries", "https://www.wildberries.ru/catalog/140707460/detail.aspx"),
    ("YandexMarket", "https://market.yandex.ru/card/patrioticheskaya-nastolnaya-igra-sluzhu-otechestvu-dlya-vzroslykh-i-detey-ot-6-let--klevyye-igry/103227515458"),
)

def probe(name, url):
    started = monotonic()
    result = {"shop": name, "title": False, "price": False, "photo": False}
    try:
        data = fetch_product_metadata(url)
        result.update(status="parsed", title=bool(data.get("title")),
                      price=data.get("price") is not None,
                      photo=bool(data.get("image_data")))
    except ApiError as exc:
        result.update(status="rejected", code=exc.status, reason=str(exc)[:100])
    except Exception as exc:
        result.update(status="error", error=type(exc).__name__)
    result["seconds"] = round(monotonic() - started, 2)
    return result

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(probe, name, url) for name, url in SAMPLES]
        for future in as_completed(futures):
            print("RUSSIAN_MARKETPLACE_PROBE " + json.dumps(future.result(), ensure_ascii=False), flush=True)
