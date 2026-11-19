"""Best-effort product preview for a small allowlist of public Russian shops

Never fetch arbitrary URLs, use browser cookies, bypass access challenges, or log
product URLs. DNS is validated and pinned to the TLS connection to avoid SSRF
through private addresses and DNS rebinding. Any missing field stays editable
by the wishlist owner.
"""
import base64
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit, urlunsplit

from server import ApiError
from cloud.product_sources import (BOOK_STORES, adapter_for, approved_book_offer,
                                   isbn_from_text, valid_isbn)
from functools import lru_cache
import time

SHOP_DOMAINS = (
    'ozon.ru', 'wildberries.ru', 'wb.ru', 'market.yandex.ru', 'bookvoed.ru',
    'chitai-gorod.ru', 'labirint.ru', 'detmir.ru', 'dns-shop.ru',
    'mvideo.ru', 'eldorado.ru', 'sportmaster.ru',
)
# Product pictures are normally served by separate CDN domains
IMAGE_DOMAINS = (
    'ozon.ru', 'ozone.ru', 'ozonusercontent.com', 'wildberries.ru', 'wb.ru',
    'wbstatic.net', 'wbbasket.ru', 'yandex.ru', 'yandex.net',
    'yastatic.net', 'bookvoed.ru', 'book24.ru', 'chitai-gorod.ru',
    'img-gorod.ru', 'labirint.ru', 'detmir.ru', 'dns-shop.ru',
    'mvideo.ru', 'eldorado.ru', 'sportmaster.ru', 'covers.openlibrary.org',
)
OPEN_LIBRARY_DOMAINS = ('openlibrary.org',)
OPEN_LIBRARY_LIMIT = 96_000
HTML_LIMIT = 500_000
IMAGE_LIMIT = 1_750_000
MAX_REDIRECTS = 2


def _domain_allowed(host, choices):
    # Wildcard subdomains are permitted only under exact, reviewed domains
    # market.yandex.ru must not grant arbitrary *.yandex.ru page fetching
    return any(host == domain or host.endswith('.' + domain) for domain in choices)


def _target(value, choices):
    if not isinstance(value, str) or not 0 < len(value) <= 2048:
        raise ApiError(400, 'Нужна короткая ссылка на товар')
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or '').lower().rstrip('.')
        if (parsed.scheme != 'https' or not host or not re.fullmatch(r'[a-z0-9.-]+', host)
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not _domain_allowed(host, choices)):
            raise ApiError(400, 'Пока поддерживаются ссылки HTTPS на выбранные магазины')
    except (ValueError, TypeError):
        raise ApiError(400, 'Проверь ссылку на товар') from None
    return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))


def _public_ip(host):
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ApiError(422, 'Не удалось открыть страницу магазина') from None
    ips = []
    for record in addresses:
        address = record[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise ApiError(422, 'Адрес магазина недоступен') from None
        if not ip.is_global:
            raise ApiError(422, 'Адрес магазина недоступен')
        ips.append(address)
    if not ips:
        raise ApiError(422, 'Адрес магазина недоступен')
    return next((v for v in ips if ':' not in v), ips[0])


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, ip):
        super().__init__(hostname, port=443, timeout=5, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        # Resolve/validate first, then use the verified IP for the connection
        sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _request_public(url, domains, limit):
    current = _target(url, domains)
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        host = parts.hostname
        ip = _public_ip(host)
        con = _PinnedHTTPS(host, ip)
        try:
            con.request('GET', urlunsplit(('', '', parts.path or '/', parts.query, '')),
                        headers={'Host': host, 'Accept': 'text/html,image/*;q=0.8',
                                 'Accept-Encoding': 'identity',
                                 'User-Agent': 'ShurshProductImporter/1.0',
                                 'Connection': 'close'})
            resp = con.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                target = resp.getheader('Location') or ''
                # No cross-domain redirects to unexpected hosts/private IPs
                current = _target(urljoin(current, target), domains)
                continue
            if resp.status != 200:
                raise ApiError(422, 'Магазин не предоставил данные товара')
            mime = (resp.getheader('Content-Type') or '').lower()
            body = resp.read(limit + 1)
            if len(body) > limit:
                if domains == SHOP_DOMAINS:
                    # Huge storefront pages are common. Metadata is usually
                    # near the beginning; parse only a bounded HTML prefix
                    body = body[:limit]
                else:
                    raise ApiError(422, 'Изображение слишком большое')
            return current, mime, body
        except ApiError:
            raise
        except (OSError, http.client.HTTPException, ssl.SSLError, TimeoutError):
            raise ApiError(422, 'Не удалось получить данные из магазина') from None
        finally:
            con.close()
    raise ApiError(422, 'Ссылка магазина перенаправляет слишком много раз')


class _ProductHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = {}
        self.structured = []
        self._json = False
        self._buffer = ''
        self.title = ''
        self._title = False

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == 'title':
            self._title = True
        if tag == 'meta':
            name = (props.get('property') or props.get('name') or props.get('itemprop') or '').lower()
            value = (props.get('content') or '').strip()
            if name and value and name not in self.tags:
                self.tags[name] = value[:6000]
        if tag == 'script' and (props.get('type') or '').lower() == 'application/ld+json':
            self._json = True
            self._buffer = ''

    def handle_data(self, data):
        if self._json and len(self._buffer) < 150_000:
            self._buffer += data
        if self._title and not self.title:
            self.title = data.strip()[:260]

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False
        if tag == 'script' and self._json:
            self._json = False
            try:
                self.structured.append(json.loads(self._buffer))
            except (ValueError, TypeError):
                pass
            self._buffer = ''


def _find_product(value, depth=0):
    if depth > 7:
        return None
    if isinstance(value, list):
        for item in value[:80]:
            found = _find_product(item, depth + 1)
            if found:
                return found
    if isinstance(value, dict):
        kind = value.get('@type') or value.get('type') or ''
        kinds = kind if isinstance(kind, list) else [kind]
        if any(isinstance(k, str) and k.lower().split('/')[-1] == 'product' for k in kinds):
            return value
        for child in ('@graph', 'mainEntity', 'itemListElement'):
            found = _find_product(value.get(child), depth + 1)
            if found:
                return found
    return None


def _price(value):
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = re.sub(r'[\s\u00a0\u202f₽р]', '', value.strip().lower())
        text = text.replace('уб.', '')
        if not re.fullmatch(r'\d[\d.,]*', text):
            return None
        if ',' in text and '.' in text:
            if text.rfind(',') > text.rfind('.'):
                text = text.replace('.', '').replace(',', '.')
            else:
                text = text.replace(',', '')
        elif ',' in text:
            left, right = text.rsplit(',', 1)
            text = left.replace(',', '') + ('.' + right if len(right) in (1, 2) else right)
        elif '.' in text and re.fullmatch(r'\d{1,3}(?:\.\d{3})+', text):
            text = text.replace('.', '')
    else:
        return None
    try:
        amount = Decimal(text)
        if not amount.is_finite() or not Decimal('0') <= amount <= Decimal('100000000'):
            return None
        return format(amount.quantize(Decimal('0.01')), 'f')
    except (InvalidOperation, ValueError):
        return None


def _first(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _first(value[0])
    if isinstance(value, dict):
        return _first(value.get('url') or value.get('contentUrl'))
    return None


def _data_from_html(html):
    parser = _ProductHTML()
    parser.feed(html)
    tags = parser.tags
    product = next((found for item in parser.structured
                    if (found := _find_product(item)) is not None), {})
    offers = product.get('offers') or {}
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), {})
    if not isinstance(offers, dict):
        offers = {}
    name = product.get('name') or tags.get('og:title') or tags.get('twitter:title') or parser.title
    image = _first(product.get('image')) or tags.get('og:image:secure_url') or tags.get('og:image') or tags.get('twitter:image')
    currency = (offers.get('priceCurrency') or tags.get('product:price:currency') or tags.get('pricecurrency') or 'RUB')
    raw_price = (offers.get('price') or offers.get('lowPrice') or
                 tags.get('product:price:amount') or tags.get('og:price:amount') or
                 tags.get('price') or tags.get('price:amount'))
    price = _price(raw_price) if str(currency).upper() in ('RUB', 'RUR', '₽') else None
    return {
        'title': re.sub(r'\s+', ' ', str(name or '')).strip()[:130],
        'price': price,
        'currency': 'RUB',
        'image_url': image if isinstance(image, str) else None,
    }


def _image_data(url, base):
    if not url:
        return None
    try:
        absolute = _target(urljoin(base, url), IMAGE_DOMAINS)
        _, mime, blob = _request_public(absolute, IMAGE_DOMAINS, IMAGE_LIMIT)
        if blob.startswith(b'\xff\xd8\xff'):
            kind = 'jpeg'
        elif blob.startswith(b'\x89PNG\r\n\x1a\n'):
            kind = 'png'
        elif blob.startswith(b'RIFF') and blob[8:12] == b'WEBP':
            kind = 'webp'
        else:
            return None
        if mime and not (mime.startswith('image/') or mime.startswith('application/octet-stream')):
            return None
        return f'data:image/{kind};base64,{base64.b64encode(blob).decode("ascii")}'
    except (ApiError, ValueError, TypeError):
        # A blocked CDN must not prevent importing an available title/price
        return None


_BLOCKED_PAGE_TITLES = (
    'access denied', 'access to this page has been denied',
    'just a moment', 'attention required', 'captcha',
    'robot check', 'are you a human', 'service unavailable',
    'доступ запрещен', 'доступ запрещён', 'проверка браузера',
    'проверка безопасности', 'подтвердите, что вы не робот',
    'подтвердите, что вы человек',
)


def _looks_like_challenge(title):
    # A generic HTML <title> from a challenge must never become a wish name
    normalized = re.sub(r'\s+', ' ', title).strip().lower()
    return any(normalized == phrase or
               (normalized.startswith(phrase) and
                normalized[len(phrase):len(phrase) + 1] in (' ', '.', ':', '-', '|', '!', '?'))
               for phrase in _BLOCKED_PAGE_TITLES)


_GENERIC_STORE_TITLES = frozenset((
    'яндекс', 'яндекс маркет', 'yandex market',
    'ozon', 'ozon.ru', 'wildberries', 'wildberries.ru',
    'библиотека буквоед', 'буквоед',
))


def _generic_store_title(title):
    # Some storefronts return a landing page with the site logo, not a product
    return re.sub(r'\s+', ' ', title).strip().lower() in _GENERIC_STORE_TITLES


@lru_cache(maxsize=256)
def _book_edition(isbn, epoch_day):
    """Official public book metadata API. No merchant prices, no scraping"""
    if not valid_isbn(isbn):
        return None
    try:
        address = 'https://openlibrary.org/isbn/' + isbn + '.json'
        _, mime, body = _request_public(address, OPEN_LIBRARY_DOMAINS, OPEN_LIBRARY_LIMIT)
        if mime and 'json' not in mime:
            return None
        entry = json.loads(body)
        if not isinstance(entry, dict) or not isinstance(entry.get('title'), str):
            return None
        covers = entry.get('covers')
        cover_id = covers[0] if isinstance(covers, list) and covers else None
        image = ('https://covers.openlibrary.org/b/id/' + str(cover_id) +
                 '-M.jpg?default=false') if type(cover_id) is int and 0 < cover_id < 1_000_000_000 else None
        return {"title": re.sub(r'\s+', ' ', entry['title']).strip()[:130],
                "image_url": image, "price": None, "currency": "RUB"}
    except (ApiError, ValueError, TypeError, OSError):
        return None


def _finish_preview(data, final_url, store, source):
    picture = _image_data(data.pop('image_url', None), final_url)
    if not data.get('title'):
        raise ApiError(422, 'Не удалось получить название товара')
    return {'title': data['title'], 'price': data.get('price'),
            'currency': 'RUB', 'image_data': picture, 'shop_url': final_url,
            'source': source, 'store': store}


def fetch_product_metadata(value):
    """Store-specific ID adapter, optional licensed feed, then public metadata

    Never invent a price; an ISBN may yield edition information but not store stock
    """
    url = _target(value, SHOP_DOMAINS)
    adapter = adapter_for(url)
    store = adapter['store']
    if store in BOOK_STORES:
        approved = approved_book_offer(url)
        if approved:
            data = dict(approved)
            isbn = data.pop('isbn', None)
            if not data.get('image_url') and isbn:
                edition = _book_edition(isbn, int(time.time()) // 86400)
                if edition:
                    data['image_url'] = edition.get('image_url')
            return _finish_preview(data, url, store, 'approved_partner_feed')

    # No unofficial marketplace JSON endpoints. If the public product page
    # rejects requests, preserve a clear error and require manual data entry
    final_url, mime, body = _request_public(url, SHOP_DOMAINS, HTML_LIMIT)
    if mime and 'text/html' not in mime and 'application/xhtml+xml' not in mime:
        raise ApiError(422, 'По ссылке не нашлась страница товара')
    encoding = 'cp1251' if 'windows-1251' in mime else 'utf-8'
    page = body.decode(encoding, errors='replace')
    preview = _data_from_html(page)
    if _looks_like_challenge(preview['title']):
        raise ApiError(422, 'Магазин ограничил доступ к странице товара. Заполни данные вручную')
    if _generic_store_title(preview['title']):
        raise ApiError(422, 'По ссылке открылась главная страница магазина, а не товар. Заполни данные вручную')

    source = 'public_product_page'
    if store in BOOK_STORES and (not preview['title'] or not preview['image_url']):
        isbn = isbn_from_text(page) or isbn_from_text(final_url)
        if isbn:
            edition = _book_edition(isbn, int(time.time()) // 86400)
            if edition:
                if not preview['title']:
                    preview['title'] = edition['title']
                    source = 'open_library'
                if not preview['image_url']:
                    preview['image_url'] = edition['image_url']
    if not preview['title']:
        raise ApiError(422, 'Магазин не передал название товара')
    return _finish_preview(preview, final_url, store, source)
