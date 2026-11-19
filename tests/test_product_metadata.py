"""Deterministic marketplace-preview tests with no external HTTP requests"""
import base64
from unittest.mock import Mock
import pytest

from cloud import product_metadata as pm
from server import ApiError


@pytest.mark.parametrize('url', [
    'http://www.ozon.ru/product/123', 'https://localhost/private',
    'https://127.0.0.1/admin', 'https://www.ozon.ru.evil.test/product/1',
    'https://attacker@www.ozon.ru/product/1',
    'https://www.ozon.ru:8443/product/1', 'file:///etc/passwd',
    'https://evil.yandex.ru/product/1', 'https://example.com/product/1',
    'https://www.ozon.ru@127.0.0.1/private',
])
def test_only_allowlisted_https_product_pages(url):
    with pytest.raises(ApiError) as error:
        pm._target(url, pm.SHOP_DOMAINS)
    assert error.value.status == 400


@pytest.mark.parametrize('url', [
    'https://www.ozon.ru/product/test',
    'https://www.wildberries.ru/catalog/123/detail.aspx',
    'https://www.wb.ru/catalog/123/detail.aspx',
    'https://market.yandex.ru/card/example/1',
    'https://www.bookvoed.ru/product/test',
    'https://www.chitai-gorod.ru/product/1',
    'https://www.labirint.ru/books/123',
])
def test_marketplace_domains_supported(url):
    assert pm._target(url, pm.SHOP_DOMAINS) == url


@pytest.mark.parametrize('address', [
    '127.0.0.1', '10.1.1.1', '169.254.169.254', '192.168.1.1',
    '::1', 'fc00::1', '0.0.0.0',
])
def test_dns_private_addresses_blocked(monkeypatch, address):
    monkeypatch.setattr(pm.socket, 'getaddrinfo',
                        lambda *args, **kwargs: [(None, None, None, None, (address, 443))])
    with pytest.raises(ApiError) as error:
        pm._public_ip('www.ozon.ru')
    assert error.value.status == 422


def test_dns_mixed_public_private_addresses_rejected(monkeypatch):
    monkeypatch.setattr(pm.socket, 'getaddrinfo',
                        lambda *args, **kwargs: [
                            (None, None, None, None, ('1.1.1.1', 443)),
                            (None, None, None, None, ('127.0.0.1', 443)),
                        ])
    with pytest.raises(ApiError):
        pm._public_ip('www.ozon.ru')


def test_json_ld_product_fields_and_price():
    html = '''
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@graph":[
        {"@type":"Organization","name":"Shop"},
        {"@type":"Product","name":"Книга о звёздах",
         "image":["https://img.bookvoed.ru/cover.jpg"],
         "offers":{"@type":"Offer","price":"2 490,50","priceCurrency":"RUB"}}
      ]}
      </script>
    </head></html>
    '''
    result = pm._data_from_html(html)
    assert result['title'] == 'Книга о звёздах'
    assert result['price'] == '2490.50'
    assert result['currency'] == 'RUB'
    assert result['image_url'] == 'https://img.bookvoed.ru/cover.jpg'


def test_marketplace_price_thousands_separators():
    assert pm._price('2.490') == '2490.00'
    assert pm._price('1,299.50') == '1299.50'
    assert pm._price('2490,50 ₽') == '2490.50'
    assert pm._price('0') == '0.00'


def test_open_graph_metadata_and_currency_filter():
    result = pm._data_from_html('''
      <meta property="og:title" content="Кружка с котом">
      <meta property="og:image" content="https://cdn1.ozone.ru/image.jpg">
      <meta property="product:price:amount" content="1599.99">
      <meta property="product:price:currency" content="RUB">
    ''')
    assert result['title'] == 'Кружка с котом'
    assert result['price'] == '1599.99'
    assert result['image_url'].startswith('https://cdn1.ozone.ru/')
    no_conversion = pm._data_from_html('''
      <meta property="og:title" content="Imported product">
      <meta property="product:price:amount" content="49.99">
      <meta property="product:price:currency" content="USD">
    ''')
    assert no_conversion['price'] is None


def test_image_safely_imported_to_existing_upload_format(monkeypatch):
    image = b'\x89PNG\r\n\x1a\n' + b'safe-image-bytes'
    page = '''<meta property="og:title" content="Настольная игра">
      <meta property="og:image" content="https://cdn1.ozone.ru/image.png">
      <meta property="product:price:amount" content="890">'''.encode('utf-8')
    def fake_request(url, domains, limit):
        if url.endswith('.png'):
            return url, 'image/png', image
        return 'https://www.ozon.ru/product/123', 'text/html; charset=utf-8', page
    monkeypatch.setattr(pm, '_request_public', fake_request)
    result = pm.fetch_product_metadata('https://www.ozon.ru/product/123')
    assert result['title'] == 'Настольная игра'
    assert result['price'] == '890.00'
    assert result['shop_url'] == 'https://www.ozon.ru/product/123'
    assert base64.b64decode(result['image_data'].split(',', 1)[1]) == image


def test_image_from_untrusted_domain_is_not_fetched(monkeypatch):
    calls = []
    def fake_request(url, domains, limit):
        calls.append(url)
        return url, 'text/html', '''<meta property="og:title" content="Подарок">
          <meta property="og:image" content="https://127.0.0.1/secret.png">'''.encode('utf-8')
    monkeypatch.setattr(pm, '_request_public', fake_request)
    result = pm.fetch_product_metadata('https://www.ozon.ru/product/123')
    assert result['title'] == 'Подарок'
    assert result['image_data'] is None
    assert len(calls) == 1


def test_blocked_store_returns_useful_error(monkeypatch):
    def blocked(*args):
        raise ApiError(422, 'Магазин не предоставил данные товара')
    monkeypatch.setattr(pm, '_request_public', blocked)
    with pytest.raises(ApiError) as error:
        pm.fetch_product_metadata('https://www.wildberries.ru/catalog/123/detail.aspx')
    assert error.value.status == 422


@pytest.mark.parametrize('challenge', [
    'Just a moment...', 'Access Denied', 'Captcha',
    'Проверка безопасности', 'Подтвердите, что вы не робот',
])
def test_antibot_challenge_never_becomes_wishlist_title(monkeypatch, challenge):
    def fake_request(url, domains, limit):
        page = ('<html><head><title>' + challenge + '</title></head></html>').encode('utf-8')
        return url, 'text/html', page
    monkeypatch.setattr(pm, '_request_public', fake_request)
    with pytest.raises(ApiError) as error:
        pm.fetch_product_metadata('https://www.ozon.ru/product/123')
    assert error.value.status == 422


def test_legitimate_product_title_not_marked_as_challenge():
    assert pm._looks_like_challenge('Кот в сапогах. Подарочное издание') is False
    assert pm._looks_like_challenge('  JUST A   MOMENT  ') is True


@pytest.mark.parametrize('title', [
    'Яндекс', 'Яндекс Маркет', 'Ozon', 'Wildberries', 'Буквоед',
])
def test_store_landing_page_is_not_a_product(monkeypatch, title):
    calls = []
    def fake_request(url, domains, limit):
        calls.append(url)
        html = ('<head><title>' + title + '</title>'
                '<meta property="og:image" content="https://avatars.yandex.net/logo.png"></head>')
        return url, 'text/html', html.encode('utf-8')
    monkeypatch.setattr(pm, '_request_public', fake_request)
    with pytest.raises(ApiError) as error:
        pm.fetch_product_metadata('https://market.yandex.ru/card/123')
    assert error.value.status == 422
    # Store's logo must not be added to a new wish
    assert len(calls) == 1


def test_normal_product_title_survives_generic_store_filter():
    assert not pm._generic_store_title('Яндекс Станция Мини с Алисой')
    assert not pm._generic_store_title('LEGO Classic 10696')
    assert pm._generic_store_title('  ЯНДЕКС   МАРКЕТ  ')
