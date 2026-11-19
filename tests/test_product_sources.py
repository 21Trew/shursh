"""Deterministic tests for free, approved and isolated product adapters"""
import json
import pytest
from cloud import product_metadata as pm
from cloud import product_sources as src
from server import ApiError


@pytest.mark.parametrize("url,store,identifier", [
    ("https://www.ozon.ru/product/lego-classic-30947723/", "ozon", "30947723"),
    ("https://www.wildberries.ru/catalog/140707460/detail.aspx", "wildberries", "140707460"),
    ("https://market.yandex.ru/card/example/103227515458", "yandex-market", "103227515458"),
    ("https://www.bookvoed.ru/product/literatura-8713602", "bookvoed", "8713602"),
    ("https://www.chitai-gorod.ru/product/literatura-3109366", "chitai-gorod", "3109366"),
    ("https://www.labirint.ru/books/731281/", "labirint", "731281"),
])
def test_url_identifiers(url, store, identifier):
    assert src.adapter_for(url) == {"store": store, "product_id": identifier}


@pytest.mark.parametrize("invalid", [
    "9780140328722", "9785042061876", "0000000000000",
    "1234567890", "978-123", "none", "12345678901234",
])
def test_invalid_isbn_rejected(invalid):
    assert src.valid_isbn(invalid) is False


def test_isbn_checksum_and_marked_extraction_only():
    assert src.valid_isbn("978-5-04-206187-5")
    assert src.valid_isbn("9780140328721")
    assert src.isbn_from_text("ISBN | 978-5-04-206187-5") == "9785042061875"
    assert src.isbn_from_text('<meta itemprop="isbn" content="9780140328721">') == "9780140328721"
    assert src.isbn_from_text("Артикул 9785042061875") is None
    assert src.isbn_from_text("ISBN: 9785042061876") is None


YML = """<?xml version="1.0" encoding="utf-8"?>
<yml_catalog date="2026-11-19"><shop><offers>
<offer id="a"><url>https://www.bookvoed.ru/product/literatura-8713602</url>
<name>Литература</name><price>599.00</price><currencyId>RUR</currencyId>
<isbn>9785042061875</isbn>
<picture>https://img.bookvoed.ru/book.jpg</picture></offer>
<offer id="b"><url>https://www.chitai-gorod.ru/product/literatura-3109366</url>
<name>Книга</name><price>799</price><currencyId>RUB</currencyId></offer>
<offer id="evil"><url>https://localhost/private</url><name>Private</name><price>123</price></offer>
</offers></shop></yml_catalog>""".encode("utf-8")


def test_approved_xml_parses_only_store_items_with_verified_prices():
    offers = src.parse_approved_yml(YML)
    assert len(offers) == 2
    first = offers[("bookvoed", "8713602")]
    assert first["title"] == "Литература"
    assert first["price"] == "599.00"
    assert first["isbn"] == "9785042061875"
    assert offers[("chitai-gorod", "3109366")]["price"] == "799"


@pytest.mark.parametrize("payload", [
    b'<!DOCTYPE shop [<!ENTITY x SYSTEM "file:///etc/passwd">]><shop>&x;</shop>',
    b"", b"<broken", b"x" * (src.MAX_FEED_BYTES + 1),
])
def test_approved_feed_malformed_or_unsafe_xml_rejected(payload):
    with pytest.raises(ValueError):
        src.parse_approved_yml(payload)


def test_disabled_approved_catalog_never_reads_a_file(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_BOOK_CATALOG_FILE", raising=False)
    assert src.approved_book_offer("https://www.bookvoed.ru/product/literatura-8713602") is None


def test_opted_in_partner_feed_skips_blocked_store_and_preserves_price(monkeypatch, tmp_path):
    path = tmp_path / "approved.xml"
    path.write_bytes(YML)
    monkeypatch.setenv("SHURSH_APPROVED_BOOK_CATALOG_FILE", str(path))
    calls = []
    def fake_request(*args):
        calls.append(args)
        raise AssertionError("No network required for approved feed metadata")
    monkeypatch.setattr(pm, "_request_public", fake_request)
    monkeypatch.setattr(pm, "_image_data", lambda value, base: "data:image/jpeg;base64,YWJj")
    result = pm.fetch_product_metadata("https://www.bookvoed.ru/product/literatura-8713602")
    assert result["source"] == "approved_partner_feed"
    assert result["price"] == "599.00"
    assert result["title"] == "Литература"
    assert result["image_data"].startswith("data:image/")
    assert calls == []


def test_bookstore_with_missing_image_uses_official_openlibrary(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_BOOK_CATALOG_FILE", raising=False)
    requests = []
    def fake_request(url, domains, limit):
        requests.append(url)
        if url.startswith("https://openlibrary.org/isbn/"):
            assert domains == pm.OPEN_LIBRARY_DOMAINS
            return url, "application/json", json.dumps({
                "title": "Литература", "covers": [1234567]
            }).encode("utf-8")
        return url, "text/html; charset=utf-8", (
            '<html><head><meta property="og:title" content="Литература">'
            '<meta name="isbn" content="9785042061875"></head></html>'
        ).encode("utf-8")
    monkeypatch.setattr(pm, "_request_public", fake_request)
    fetched_pictures = []
    def image(url, base):
        fetched_pictures.append(url)
        return "data:image/jpeg;base64,YWJj"
    monkeypatch.setattr(pm, "_image_data", image)
    pm._book_edition.cache_clear()
    data = pm.fetch_product_metadata("https://www.bookvoed.ru/product/literatura-8713602")
    assert data["title"] == "Литература"
    assert data["price"] is None
    assert data["source"] == "public_product_page"
    assert fetched_pictures == ["https://covers.openlibrary.org/b/id/1234567-M.jpg?default=false"]
    assert any(x.startswith("https://openlibrary.org/isbn/") for x in requests)


def test_openlibrary_can_restore_missing_title_and_image(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_BOOK_CATALOG_FILE", raising=False)
    pm._book_edition.cache_clear()
    def fake_request(url, domains, limit):
        if "openlibrary.org/isbn/" in url:
            return url, "application/json", b'{"title":"Book title","covers":[140]}'
        return url, "text/html", b"<html><head><meta name='isbn' content='9780140328721'></head></html>"
    monkeypatch.setattr(pm, "_request_public", fake_request)
    monkeypatch.setattr(pm, "_image_data", lambda url, base: "data:image/jpeg;base64,YWJj")
    data = pm.fetch_product_metadata("https://www.bookvoed.ru/product/book-12345")
    assert data["title"] == "Book title"
    assert data["source"] == "open_library"
    assert data["price"] is None


def test_ozon_cannot_be_replaced_by_unrelated_openlibrary_metadata(monkeypatch):
    monkeypatch.delenv("SHURSH_APPROVED_BOOK_CATALOG_FILE", raising=False)
    def blocked(url, domains, limit):
        raise ApiError(422, "Магазин отказал")
    monkeypatch.setattr(pm, "_request_public", blocked)
    with pytest.raises(ApiError) as error:
        pm.fetch_product_metadata("https://www.ozon.ru/product/12345678")
    assert error.value.status == 422
