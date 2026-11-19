"""Manual anonymous reachability checks: official Russian seller/partner APIs.

These APIs are for authorized sellers. 401/403 show access restrictions;
405 may indicate the wrong HTTP method. No credentials, retries, bypass or
personal contacts. Results are network-specific, not a claim of free public API.
"""
import json
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINTS = (
    ("Ozon Seller", "https://api-seller.ozon.ru/v3/product/info/list", "POST"),
    ("Wildberries Seller", "https://common-api.wildberries.ru/api/v1/seller-info", "GET"),
    ("Yandex Market Partner", "https://api.partner.market.yandex.ru/v2/campaigns", "GET"),
)

def probe(name, url, method):
    started=monotonic()
    result={"api":name, "title":False, "price":False, "photo":False}
    try:
        req=Request(url,method=method,data=b"{}" if method=="POST" else None,
                    headers={"User-Agent":"ShurshProductImporter/1.0",
                             "Accept":"application/json",
                             "Content-Type":"application/json"})
        with urlopen(req,timeout=8) as response:
            result.update(http=response.status,status="anonymous_response")
            response.read(2048)
    except HTTPError as exc:
        result.update(http=exc.code,status="rejected")
    except (URLError,OSError,TimeoutError,ValueError) as exc:
        result.update(status="network_error",error=type(exc).__name__)
    result["seconds"]=round(monotonic()-started,2)
    return result

if __name__=="__main__":
    for name,url,method in ENDPOINTS:
        print("OFFICIAL_API_PROBE "+json.dumps(probe(name,url,method),ensure_ascii=False),flush=True)
