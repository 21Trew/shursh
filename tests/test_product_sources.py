"""Deterministic tests for three Russian marketplaces and consented YML sources."""
import pytest
from cloud import product_metadata as pm, product_sources as src
from server import ApiError

SAMPLES = (
    ("https://www.ozon.ru/product/lego-classic-30947723/", "ozon", "30947723"),
    ("https://www.wildberries.ru/catalog/140707460/detail.aspx", "wildberries", "140707460"),
    ("https://market.yandex.ru/card/igra/103227515458", "yandex-market", "103227515458"),
)

@pytest.mark.parametrize("url,store,identifier", SAMPLES)
def test_marketplace_ids(url,store,identifier):
    assert src.adapter_for(url) == {"store":store,"product_id":identifier}

@pytest.mark.parametrize("url", (
    "https://www.bookvoed.ru/product/literatura-8713602",
    "https://openlibrary.org/isbn/9780140328721.json",
    "https://www.ozon.ru.evil.test/product/12345678",
    "http://www.ozon.ru/product/12345678",
))
def test_non_marketplace_rejected_without_network(monkeypatch,url):
    monkeypatch.setattr(pm, "_request_public", lambda *a: pytest.fail("no HTTP expected"))
    with pytest.raises(ApiError):
        pm.fetch_product_metadata(url)

YML = """<yml_catalog><shop><offers>
<offer><url>https://www.ozon.ru/product/lego-classic-30947723/</url>
<name>LEGO Classic</name><price>1999.00</price><currencyId>RUB</currencyId>
<picture>https://cdn1.ozone.ru/lego.jpg</picture></offer>
<offer><url>https://www.wildberries.ru/catalog/140707460/detail.aspx</url>
<name>Набор</name><price>799</price><currencyId>RUR</currencyId>
<picture>https://images.wbstatic.net/item.jpg</picture></offer>
<offer><url>https://market.yandex.ru/card/igra/103227515458</url>
<name>Игра</name><price>1499</price><currencyId>RUB</currencyId>
<picture>https://avatars.mds.yandex.net/image.jpg</picture></offer>
<offer><url>https://www.bookvoed.ru/product/12345</url><name>Book</name></offer>
</offers></shop></yml_catalog>""".encode("utf-8")

def test_approved_feed_contains_all_three_marketplaces():
    rows=src.parse_approved_yml(YML)
    assert len(rows)==3
    for url,store,identifier in SAMPLES:
        record=rows[(store,identifier)]
        assert record["title"] and record["price"] and record["image_url"]

@pytest.mark.parametrize("payload", (
    b"", b"<broken", b"x"*(src.MAX_FEED_BYTES+1),
    b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>',
))
def test_reject_invalid_or_unsafe_xml(payload):
    with pytest.raises(ValueError):
        src.parse_approved_yml(payload)

def test_opted_in_feed_skips_network(monkeypatch,tmp_path):
    path=tmp_path/"approved.xml"
    path.write_bytes(YML)
    monkeypatch.setenv("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE",str(path))
    monkeypatch.setattr(pm,"_request_public",lambda *a: pytest.fail("no network"))
    monkeypatch.setattr(pm,"_image_data",lambda *a: "data:image/jpeg;base64,YWJj")
    for url,store,_ in SAMPLES:
        item=pm.fetch_product_metadata(url)
        assert item["title"] and item["price"] and item["image_data"]
        assert item["source"]=="approved_marketplace_feed"
        assert item["store"]==store

def test_feed_disabled_without_path(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE",raising=False)
    assert src.approved_marketplace_offer(SAMPLES[0][0]) is None

@pytest.mark.parametrize("url,store,_",SAMPLES)
def test_allowed_html_json_ld(monkeypatch,url,store,_):
    monkeypatch.delenv("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE",raising=False)
    page=b'<script type="application/ld+json">{"@type":"Product","name":"Gift","image":"https://cdn1.ozone.ru/cover.jpg","offers":{"price":"1250.00","priceCurrency":"RUB"}}</script>'
    monkeypatch.setattr(pm,"_request_public",lambda address,domains,limit:(address,"text/html",page))
    monkeypatch.setattr(pm,"_image_data",lambda *a:"data:image/jpeg;base64,YWJj")
    item=pm.fetch_product_metadata(url)
    assert item["title"]=="Gift" and item["price"]=="1250.00"
    assert item["image_data"] and item["store"]==store

def test_redirect_to_another_product_rejected(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE",raising=False)
    url=SAMPLES[0][0]
    monkeypatch.setattr(pm,"_request_public",lambda *a:("https://www.ozon.ru/product/12345678","text/html",b'<meta property="og:title" content="Wrong">'))
    with pytest.raises(ApiError):
        pm.fetch_product_metadata(url)

def test_no_product_id_no_network(monkeypatch):
    monkeypatch.setattr(pm,"_request_public",lambda *a:pytest.fail("No HTTP"))
    with pytest.raises(ApiError):
        pm.fetch_product_metadata("https://www.ozon.ru/")

def test_approved_catalog_price_updates_when_file_changes(monkeypatch,tmp_path):
    path=tmp_path/"refresh.xml"
    path.write_bytes(YML)
    monkeypatch.setenv("SHURSH_APPROVED_MARKETPLACE_CATALOG_FILE",str(path))
    url=SAMPLES[0][0]
    assert src.approved_marketplace_offer(url)["price"]=="1999.00"
    import os
    updated=YML.replace(b"1999.00",b"2000.00")
    path.write_bytes(updated)
    os.utime(path,ns=(path.stat().st_atime_ns,path.stat().st_mtime_ns+1000000000))
    assert src.approved_marketplace_offer(url)["price"]=="2000.00"
