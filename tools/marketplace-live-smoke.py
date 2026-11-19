"""Optional live marketplace diagnostics against real public product pages

No credentials, bypass tools, private URLs or writes
Results describe access observed from the GitHub runner, not browser availability
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic
from cloud.product_metadata import fetch_product_metadata
from server import ApiError

SAMPLES = (
    ("Ozon", "https://www.ozon.ru/product/konstruktor-lego-classic-nabor-dlya-tvorchestva-srednego-razmera-484-detali-vozrast-ot-4-10696-30947723/"),
    ("Wildberries", "https://www.wildberries.ru/catalog/140707460/detail.aspx"),
    ("YandexMarket", "https://market.yandex.ru/card/patrioticheskaya-nastolnaya-igra-sluzhu-otechestvu-dlya-vzroslykh-i-detey-ot-6-let--klevyye-igry/103227515458"),
    ("Bookvoed", "https://www.bookvoed.ru/product/literatura-8713602"),
)

def probe(name, url):
    started = monotonic()
    try:
        data = fetch_product_metadata(url)
        result = {
            "shop": name,
            "outcome": "parsed",
            "title": bool(data.get("title")),
            "sample_title": str(data.get("title") or "")[:90],
            "price": data.get("price") is not None,
            "image": bool(data.get("image_data")),
        }
    except ApiError as exc:
        result = {"shop": name, "outcome": "unavailable", "status": exc.status,
                  "reason": str(exc)[:120]}
    except Exception as exc:
        result = {"shop": name, "outcome": "unexpected_error", "type": type(exc).__name__}
    result["elapsed_s"] = round(monotonic() - started, 2)
    return result

def trace_ozon_redirects():
    """Inspect only HTTP status and host of the same allowlisted public URL"""
    from urllib.parse import urljoin, urlsplit, urlunsplit
    from cloud import product_metadata as pm
    current = next(url for shop, url in SAMPLES if shop == "Ozon")
    hops = []
    for _ in range(7):
        target = pm._target(current, pm.SHOP_DOMAINS)
        parts = urlsplit(target)
        ip = pm._public_ip(parts.hostname)
        con = pm._PinnedHTTPS(parts.hostname, ip)
        try:
            con.request("GET", urlunsplit(("", "", parts.path or "/", parts.query, "")),
                        headers={"Host": parts.hostname,
                                 "Accept": "text/html,image/*;q=0.8",
                                 "Accept-Encoding": "identity",
                                 "User-Agent": "ShurshWishlistPreview/1.0",
                                 "Connection": "close"})
            response = con.getresponse()
            hops.append({"status": response.status, "host": parts.hostname})
            if response.status not in (301, 302, 303, 307, 308):
                break
            destination = response.getheader("Location") or ""
            next_url = pm._target(urljoin(target, destination), pm.SHOP_DOMAINS)
            if next_url == current:
                hops.append({"status": "redirect_self_loop"})
                break
            current = next_url
        finally:
            con.close()
    return hops


def main():
    import json
    try:
        print("OZON_REDIRECT_DIAGNOSTICS " + json.dumps(trace_ozon_redirects()), flush=True)
    except Exception as exc:
        print("OZON_REDIRECT_DIAGNOSTICS " + json.dumps({"error": type(exc).__name__}), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(probe, name, url): name for name, url in SAMPLES}
        for future in as_completed(futures):
            print("MARKETPLACE_LIVE " + json.dumps(future.result(), ensure_ascii=False), flush=True)
    print("Live diagnostics completed. Individual blocking is not a CI regression", flush=True)

if __name__ == "__main__":
    main()
