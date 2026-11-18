#!/usr/bin/env python3
"""Шурш! — self-contained local web MVP. Python 3.10+, no dependencies."""
from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('SHURSH_DB', str(ROOT / 'data' / 'shursh.sqlite3')))
DEMO_MODE = os.getenv('SHURSH_DEMO', '1') == '1'
PORT = int(os.getenv('PORT', '8787'))
SESSION_AGE = 60 * 60 * 24 * 30
LIMIT_BYTES = 4_000_000
RATE_BUCKETS: dict[str, list[float]] = {}
RATE_LOCK = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def token():
    return secrets.token_urlsafe(32)


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(passphrase, salt=None):
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(passphrase.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f'{salt.hex()}${derived.hex()}'


def check_password(value, saved):
    try:
        salt, expected = saved.split('$', 1)
        return hmac.compare_digest(password_hash(value, bytes.fromhex(salt)).split('$', 1)[1], expected)
    except (ValueError, TypeError):
        return False


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), isolation_level=None, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS wishlists (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', occasion TEXT NOT NULL DEFAULT 'Просто так',
 theme TEXT NOT NULL DEFAULT 'peach', visibility TEXT NOT NULL DEFAULT 'link' CHECK (visibility IN ('link','private')),
 share_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wishes (
 id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL REFERENCES wishlists(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', price_cents INTEGER,
 currency TEXT NOT NULL DEFAULT 'RUB', priority TEXT NOT NULL DEFAULT 'nice',
 kind TEXT NOT NULL DEFAULT 'item', shop_url TEXT, image_path TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
 id INTEGER PRIMARY KEY, wish_id INTEGER NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
 guest_name TEXT NOT NULL, manage_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
 cancelled_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_reservation ON reservations(wish_id) WHERE cancelled_at IS NULL;
CREATE TABLE IF NOT EXISTS santa_events (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', exchange_date TEXT,
 budget_cents INTEGER, currency TEXT NOT NULL DEFAULT 'RUB', rules TEXT NOT NULL DEFAULT '',
 invite_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','drawn')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS participants (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
 name TEXT NOT NULL, access_hash TEXT UNIQUE, created_at TEXT NOT NULL,
 UNIQUE(event_id, user_id)
);
CREATE TABLE IF NOT EXISTS participant_wishes (
 id INTEGER PRIMARY KEY, participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 title TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exclusions (
 event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 giver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 receiver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 PRIMARY KEY (event_id, giver_id, receiver_id), CHECK (giver_id != receiver_id)
);
CREATE TABLE IF NOT EXISTS assignments (
 event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 giver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 receiver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 revealed_at TEXT, PRIMARY KEY (event_id, giver_id), UNIQUE(event_id, receiver_id),
 CHECK (giver_id != receiver_id)
);
CREATE INDEX IF NOT EXISTS wishes_by_list ON wishes(list_id);
CREATE INDEX IF NOT EXISTS participants_by_event ON participants(event_id);
CREATE INDEX IF NOT EXISTS events_by_owner ON santa_events(owner_id);
'''


def init_db():
    with closing(connect()) as con:
        with con:
            con.executescript(SCHEMA)
            if DEMO_MODE and not con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                seed_demo(con)


def seed_demo(con):
    con.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES (?,?,?,?)',
                ('Саша', 'demo@shursh.local', password_hash('demo12345'), now()))
    uid = con.execute('SELECT id FROM users WHERE email=?', ('demo@shursh.local',)).fetchone()['id']
    lists = [
        ('День рождения, ура!', 'Собрала здесь то, чему буду очень рада. Но сюрпризы тоже люблю ♡', 'День рождения', 'peach'),
        ('Маленькие радости', 'На случай, если захочется сделать мой день чуть теплее.', 'Просто так', 'lilac')
    ]
    list_ids = []
    for title, description, occasion, theme in lists:
        con.execute('INSERT INTO wishlists(owner_id,title,description,occasion,theme,visibility,share_key,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    (uid,title,description,occasion,theme,'link',token(),now()))
        list_ids.append(con.execute('SELECT last_insert_rowid()').fetchone()[0])
    samples = [
        (list_ids[0], 'Плёночный фотоаппарат', 'Хочется снимать неловкие, живые моменты.', 890000, 'RUB', 'love', 'item', None),
        (list_ids[0], 'Керамическая чашка ручной работы', 'Большая, с характером. Можно необычной формы.', 250000, 'RUB', 'nice', 'item', None),
        (list_ids[0], 'Билеты на спектакль', 'Буду рада любому необычному театру.', 500000, 'RUB', 'love', 'experience', None),
        (list_ids[0], 'Красивое издание любимой книги', 'С иллюстрациями и плотной бумагой.', 180000, 'RUB', 'nice', 'item', None),
        (list_ids[1], 'Вечер настолок', 'С печеньем и классной компанией.', None, 'RUB', 'nice', 'experience', None),
        (list_ids[1], 'Набор цветных карандашей', 'Для спонтанных зарисовок.', 190000, 'RUB', 'nice', 'item', None)
    ]
    for rec in samples:
        con.execute('''INSERT INTO wishes(list_id,title,description,price_cents,currency,priority,kind,shop_url,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?)''', (*rec, now()))
    con.execute('''INSERT INTO santa_events(owner_id,title,description,exchange_date,budget_cents,currency,rules,invite_key,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (uid,'Санта на нашей кухне','Чай, печенье и маленькие сюрпризы','2026-12-25',250000,'RUB',
                 'Главное — внимание, а не цена. Упаковываем подарки красиво!',token(),now()))
    eid = con.execute('SELECT last_insert_rowid()').fetchone()[0]
    for name, user_id in [('Саша',uid),('Маша',None),('Дима',None),('Настя',None)]:
        con.execute('INSERT INTO participants(event_id,user_id,name,created_at) VALUES(?,?,?,?)',(eid,user_id,name,now()))
    for name, title in [('Саша','Виниловая пластинка'),('Маша','Кофе в зёрнах'),('Маша','Пазл на 500 деталей'),
                        ('Дима','Настольная игра'),('Настя','Набор для рисования')]:
        pid = con.execute('SELECT id FROM participants WHERE event_id=? AND name=?',(eid,name)).fetchone()['id']
        con.execute('INSERT INTO participant_wishes(participant_id,title,created_at) VALUES (?,?,?)',(pid,title,now()))


class ApiError(Exception):
    def __init__(self, status, message, detail=None):
        super().__init__(message)
        self.status, self.message, self.detail = status, message, detail


def req(value, name, maximum=140, minimum=1):
    if not isinstance(value, str):
        raise ApiError(400, f'Поле «{name}» заполнено неверно')
    if '\x00' in value or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ApiError(400, f'Поле «{name}» содержит недопустимые символы')
    value = value.strip()
    if len(value) < minimum or len(value) > maximum:
        raise ApiError(400, f'Поле «{name}»: от {minimum} до {maximum} символов')
    return value


def optional(value, name, max_length=1000):
    return req('' if value is None else value, name, max_length, 0)


def enum(value, allowed, field):
    if value not in allowed:
        raise ApiError(400, f'Недопустимое значение «{field}»')
    return value


def amount(value):
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ApiError(400, 'Некорректная сумма')
    try:
        cent = int(round(float(value) * 100))
    except (ValueError, TypeError, OverflowError):
        raise ApiError(400, 'Некорректная сумма')
    if not 0 <= cent <= 100_000_000_00:
        raise ApiError(400, 'Сумма вне допустимого диапазона')
    return cent


def shop_url(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, 'Некорректная ссылка на магазин')
    value = req(value, 'Ссылка', 2000, 0)
    if not value:
        return None
    if len(value) > 2000 or not value.startswith(('https://', 'http://')):
        raise ApiError(400, 'Ссылка должна начинаться с https:// или http://')
    try:
        parts = urlparse(value)
        _ = parts.port
    except ValueError:
        raise ApiError(400, 'Неверная ссылка на магазин') from None
    if not parts.hostname or parts.username or parts.password or '\\' in value or any(c.isspace() for c in value):
        raise ApiError(400, 'Неверная ссылка на магазин')
    return value


def decode_image(data):
    if not data:
        return None
    if not isinstance(data, str) or len(data) > 3_500_000 or not data.startswith('data:image/'):
        raise ApiError(400, 'Изображение слишком большое или неверного формата')
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([a-zA-Z0-9+/=]+)',data)
    if not match:
        raise ApiError(400, 'Допустимы только JPG, PNG, WEBP')
    try:
        raw = base64.b64decode(match.group(2),validate=True)
    except Exception:
        raise ApiError(400, 'Повреждённое изображение')
    if len(raw)>2_000_000 or len(raw)<8:
        raise ApiError(400, 'Изображение должно быть не больше 2 МБ')
    typ = match.group(1)
    valid = (typ=='png' and raw.startswith(b'\x89PNG\r\n\x1a\n') or
             typ=='jpeg' and raw.startswith(b'\xff\xd8\xff') or
             typ=='webp' and raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')
    if not valid:
        raise ApiError(400, 'Формат изображения не совпадает с содержимым')
    ext = {'jpeg':'jpg','png':'png','webp':'webp'}[typ]
    return raw, ext


def image_store(data):
    decoded = decode_image(data)
    if not decoded:
        return None
    raw, ext = decoded
    (ROOT/'uploads').mkdir(exist_ok=True)
    filename = f'{secrets.token_hex(20)}.{ext}'
    (ROOT/'uploads'/filename).write_bytes(raw)
    return '/uploads/'+filename


def row_dict(row):
    return dict(row) if row is not None else None


def matching(participant_ids, excluded):
    """Sample uniformly among all permitted perfect matchings using DP counts."""
    ids = list(participant_ids)
    n = len(ids)
    if n < 3:
        raise ApiError(409, 'Для жеребьёвки нужно минимум 3 участника')
    if n > 12:
        raise ApiError(409, 'В локальной версии поддерживается до 12 участников')
    from functools import lru_cache
    blocked = set(excluded)
    allowed = [[i != j and (giver, receiver) not in blocked
                for j, receiver in enumerate(ids)] for i, giver in enumerate(ids)]

    @lru_cache(None)
    def count(mask):
        i = mask.bit_count()
        if i == n:
            return 1
        return sum(count(mask | (1 << j)) for j in range(n)
                   if not (mask & (1 << j)) and allowed[i][j])

    total = count(0)
    if total == 0:
        raise ApiError(409, 'С такими исключениями жеребьёвка невозможна. Уберите часть ограничений.')
    mask, results = 0, []
    for i in range(n):
        options = []
        for j in range(n):
            if not (mask & (1 << j)) and allowed[i][j]:
                possibilities = count(mask | (1 << j))
                if possibilities:
                    options.append((j,possibilities))
        choice = secrets.randbelow(sum(weight for _, weight in options))
        for j, weight in options:
            if choice < weight:
                results.append((ids[i], ids[j]))
                mask |= 1 << j
                break
            choice -= weight
    return results


class Handler(BaseHTTPRequestHandler):
    server_version = 'ShurshMVP/0.1'

    def log_message(self, format, *args):
        # Do not log URL paths: they may contain private bearer tokens.
        print(f'{self.address_string()} [{self.log_date_time_string()}] {self.command} status={args[1] if len(args)>1 else "?"}')

    def json(self, status, data, cookie=None):
        raw = json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.secure_headers()
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)

    def secure_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'")

    def send_cookie(self,value,max_age=SESSION_AGE):
        secure = '; Secure' if os.getenv('SHURSH_HTTPS','0') == '1' else ''
        return f'shursh_sid={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}'

    def user(self,conn):
        cookie = self.headers.get('Cookie','')
        match = re.search(r'(?:^|;\s*)shursh_sid=([A-Za-z0-9_\-]+)',cookie)
        if not match:
            return None
        result = conn.execute('''SELECT users.id, users.name, users.email FROM sessions
                              JOIN users ON sessions.user_id=users.id
                              WHERE sessions.token_hash=? AND sessions.expires_at>?''',
                              (token_hash(match.group(1)),int(time.time()))).fetchone()
        return row_dict(result)

    def auth(self,conn):
        user = self.user(conn)
        if not user:
            raise ApiError(401,'Войдите, чтобы продолжить')
        return user

    def throttled(self, action, limit=25, window=60):
        key = f'{self.client_address[0]}:{action}'
        with RATE_LOCK:
            samples = RATE_BUCKETS.get(key,[])
            t = time.monotonic()
            samples = [x for x in samples if t-x < window]
            if len(samples)>=limit:
                raise ApiError(429,'Слишком много попыток. Попробуйте немного позже.')
            samples.append(t)
            RATE_BUCKETS[key]=samples

    def body(self):
        if 'application/json' not in self.headers.get('Content-Type',''):
            raise ApiError(415,'Ожидается JSON')
        size = int(self.headers.get('Content-Length',0))
        if not 0 < size <= LIMIT_BYTES:
            raise ApiError(413,'Слишком большой запрос или пустые данные')
        try:
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError()
            return data
        except (ValueError,UnicodeError):
            raise ApiError(400,'Неверный формат JSON')

    owner_profile_table = 'users'

    def store_image(self, con, list_id, data):
        return image_store(data)

    def handle_api(self,method,path,con):
        user = self.user(con)
        if method == 'GET' and path == '/api/me':
            return 200, {'user':user, 'demo':DEMO_MODE}, None
        if method == 'POST' and path in ('/api/register','/api/login'):
            self.throttled('auth',15)
            data=self.body()
            email=req(data.get('email'),'Почта',200).lower()
            if email == 'demo@shursh.local' and (not DEMO_MODE or path.endswith('register')):
                raise ApiError(401,'Этот адрес зарезервирован для локального демо')
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                raise ApiError(400,'Укажите корректную почту')
            password=req(data.get('password'),'Пароль',200,8)
            if path.endswith('register'):
                name=req(data.get('name'),'Имя',40)
                try:
                    con.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)',
                                (name,email,password_hash(password),now()))
                except sqlite3.IntegrityError:
                    raise ApiError(409,'Такой аккаунт уже есть')
            rec=con.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not rec or not check_password(password,rec['password_hash']):
                raise ApiError(401,'Неверная почта или пароль')
            value=token()
            con.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(value),rec['id'],int(time.time())+SESSION_AGE))
            return 200, {'user':dict(id=rec['id'],name=rec['name'],email=rec['email'])}, self.send_cookie(value)
        if method == 'POST' and path == '/api/demo-login':
            if not DEMO_MODE:
                raise ApiError(404,'Режим демо выключен')
            rec=con.execute('SELECT * FROM users WHERE email=?',('demo@shursh.local',)).fetchone()
            if not rec:
                raise ApiError(404,'Демо-аккаунт не найден')
            value=token()
            con.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(value),rec['id'],int(time.time())+SESSION_AGE))
            return 200, {'user':dict(id=rec['id'],name=rec['name'],email=rec['email'])}, self.send_cookie(value)
        if method == 'POST' and path == '/api/logout':
            match=re.search(r'(?:^|;\s*)shursh_sid=([A-Za-z0-9_\-]+)',self.headers.get('Cookie',''))
            if match:
                con.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(match.group(1)),))
            return 200, {'ok':True}, self.send_cookie('',0)
        if method == 'GET' and path == '/api/lists':
            user=self.auth(con)
            return 200, {'lists':[dict(r) for r in con.execute('''SELECT wishlists.*,count(wishes.id) AS wish_count
                      FROM wishlists LEFT JOIN wishes ON wishes.list_id=wishlists.id
                      WHERE wishlists.owner_id=? GROUP BY wishlists.id ORDER BY wishlists.id DESC''',(user['id'],))]},None
        if method == 'POST' and path == '/api/lists':
            user=self.auth(con); data=self.body()
            title=req(data.get('title'),'Название',90)
            desc=optional(data.get('description'),'Описание',450)
            occasion=req(data.get('occasion') or 'Просто так','Повод',50)
            theme=enum(data.get('theme') or 'peach',('peach','lilac','mint','yellow'),'Оформление')
            visibility=enum(data.get('visibility') or 'link',('link','private'),'Доступ')
            key=token()
            inserted=con.execute('''INSERT INTO wishlists(owner_id,title,description,occasion,theme,visibility,share_key,created_at)
                           VALUES(?,?,?,?,?,?,?,?) RETURNING id''',(user['id'],title,desc,occasion,theme,visibility,key,now()))
            return 201, {'id':inserted.fetchone()['id']},None
        match=re.fullmatch(r'/api/lists/(\d+)',path)
        if match:
            user=self.auth(con); lid=int(match.group(1))
            item=con.execute('SELECT * FROM wishlists WHERE id=? AND owner_id=?',(lid,user['id'])).fetchone()
            if not item: raise ApiError(404,'Список не найден')
            if method=='GET':
                wishes=[dict(r) for r in con.execute('SELECT * FROM wishes WHERE list_id=? ORDER BY id DESC',(lid,))]
                # no reservations queried or returned for list owners
                return 200, {'list':dict(item),'wishes':wishes},None
            if method=='PATCH':
                data=self.body()
                fields={'title':lambda x:req(x,'Название',90), 'description':lambda x:optional(x,'Описание',450),
                        'occasion':lambda x:req(x,'Повод',50), 'theme':lambda x:enum(x,('peach','lilac','mint','yellow'),'Оформление'),
                        'visibility':lambda x:enum(x,('private','link'),'Доступ')}
                updates={k:f(data[k]) for k,f in fields.items() if k in data}
                if not updates: raise ApiError(400,'Нет изменений')
                con.execute(f'''UPDATE wishlists SET {', '.join(k+'=?' for k in updates)} WHERE id=?''',(*updates.values(),lid))
                return 200, {'ok':True},None
            if method=='DELETE':
                con.execute('DELETE FROM wishlists WHERE id=?',(lid,))
                return 200,{'ok':True},None
        match=re.fullmatch(r'/api/lists/(\d+)/wishes',path)
        if method=='POST' and match:
            user=self.auth(con); lid=int(match.group(1)); data=self.body()
            if not con.execute('SELECT 1 FROM wishlists WHERE id=? AND owner_id=?',(lid,user['id'])).fetchone():
                raise ApiError(404,'Список не найден')
            title=req(data.get('title'),'Название подарка',130)
            desc=optional(data.get('description'),'Комментарий',500)
            price=amount(data.get('price'))
            currency=enum(data.get('currency') or 'RUB',('RUB','EUR','USD'),'Валюта')
            priority=enum(data.get('priority') or 'nice',('nice','love'),'Приоритет')
            kind=enum(data.get('kind') or 'item',('item','experience'),'Тип подарка')
            url=shop_url(data.get('shop_url'))
            image_path=self.store_image(con,lid,data.get('image_data'))
            inserted=con.execute('''INSERT INTO wishes(list_id,title,description,price_cents,currency,priority,kind,shop_url,image_path,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id''', (lid,title,desc,price,currency,priority,kind,url,image_path,now()))
            return 201,{'id':inserted.fetchone()['id']},None
        match=re.fullmatch(r'/api/wishes/(\d+)',path)
        if match and method in ('PATCH','DELETE'):
            user=self.auth(con); wid=int(match.group(1))
            rec=con.execute('''SELECT wishes.* FROM wishes JOIN wishlists ON wishlists.id=wishes.list_id
                               WHERE wishes.id=? AND wishlists.owner_id=?''',(wid,user['id'])).fetchone()
            if not rec: raise ApiError(404,'Пожелание не найдено')
            if method=='DELETE':
                con.execute('DELETE FROM wishes WHERE id=?',(wid,))
                return 200,{'ok':True},None
            data=self.body()
            fields={'title':lambda x:req(x,'Название',130),'description':lambda x:optional(x,'Комментарий',500),
                    'price_cents':lambda x:amount(x),'currency':lambda x:enum(x,('RUB','EUR','USD'),'Валюта'),
                    'priority':lambda x:enum(x,('nice','love'),'Приоритет'),
                    'kind':lambda x:enum(x,('item','experience'),'Тип'),'shop_url':shop_url}
            updates={k:f(data['price'] if k=='price_cents' else data[k]) for k,f in fields.items()
                     if ('price' if k=='price_cents' else k) in data}
            if data.get('image_data'):
                updates['image_path']=self.store_image(con,rec['list_id'],data['image_data'])
            if not updates: raise ApiError(400,'Нет изменений')
            con.execute(f'''UPDATE wishes SET {', '.join(k+'=?' for k in updates)} WHERE id=?''',(*updates.values(),wid))
            return 200,{'ok':True},None
        match=re.fullmatch(r'/api/public/([A-Za-z0-9_\-]+)',path)
        if match and method=='GET':
            item=con.execute(f'''SELECT w.*,p.name AS owner_name FROM wishlists w
                                 JOIN {self.owner_profile_table} p ON p.id=w.owner_id WHERE w.share_key=?''',(match.group(1),)).fetchone()
            if not item or item['visibility']!='link': raise ApiError(404,'Этот список сейчас недоступен')
            owner_view=bool(user and user['id']==item['owner_id'])
            output={k:v for k,v in dict(item).items() if k not in ('owner_id','share_key')}
            wishes=[]
            for rec in con.execute('SELECT * FROM wishes WHERE list_id=? ORDER BY id DESC',(item['id'],)):
                wish=dict(rec)
                if not owner_view:
                    reserved=con.execute('SELECT 1 FROM reservations WHERE wish_id=? AND cancelled_at IS NULL',(rec['id'],)).fetchone()
                    wish['reserved']=bool(reserved)
                wishes.append(wish)
            return 200, {'list':output,'wishes':wishes,'owner_view':owner_view},None
        match=re.fullmatch(r'/api/public/([A-Za-z0-9_\-]+)/reserve/(\d+)',path)
        if match and method=='POST':
            self.throttled('reserve',20)
            key,wid=match.group(1),int(match.group(2));data=self.body()
            guest=req(data.get('guest_name'),'Имя дарителя',50)
            con.execute('BEGIN IMMEDIATE')
            item=con.execute('''SELECT wishes.id,wishlists.owner_id FROM wishes JOIN wishlists
                         ON wishes.list_id=wishlists.id WHERE wishes.id=? AND wishlists.share_key=? AND wishlists.visibility='link' ''',
                         (wid,key)).fetchone()
            if not item: raise ApiError(404,'Подарок не найден')
            if user and user['id']==item['owner_id']:
                raise ApiError(403,'Нельзя резервировать подарок из собственного списка')
            value=token()
            try:
                con.execute('INSERT INTO reservations(wish_id,guest_name,manage_hash,created_at) VALUES(?,?,?,?)',
                            (wid,guest,token_hash(value),now()))
            except sqlite3.IntegrityError:
                raise ApiError(409,'Этот подарок уже забронировали. Выберите другой.')
            con.execute('COMMIT')
            return 201,{'manage_token':value},None
        match=re.fullmatch(r'/api/reservations/([A-Za-z0-9_\-]+)',path)
        if match:
            rec=con.execute('''SELECT r.id,r.guest_name,r.cancelled_at,w.title AS wish_title,
                         wl.title AS list_title FROM reservations r
                         JOIN wishes w ON w.id=r.wish_id
                         JOIN wishlists wl ON wl.id=w.list_id
                         WHERE r.manage_hash=?''',(token_hash(match.group(1)),)).fetchone()
            if not rec: raise ApiError(404,'Бронь не найдена или ссылка недействительна')
            if method=='GET':
                return 200,{'reservation':dict(rec)},None
            if method=='DELETE':
                if rec['cancelled_at']: raise ApiError(409,'Бронь уже отменена')
                con.execute('UPDATE reservations SET cancelled_at=? WHERE id=?',(now(),rec['id']))
                return 200,{'ok':True},None
        if method=='GET' and path=='/api/santas':
            user=self.auth(con)
            return 200,{'events':[dict(r) for r in con.execute('''SELECT e.*,count(p.id) AS participant_count
                           FROM santa_events e LEFT JOIN participants p ON p.event_id=e.id
                           WHERE e.owner_id=? GROUP BY e.id ORDER BY e.id DESC''',(user['id'],))]},None
        if method=='POST' and path=='/api/santas':
            user=self.auth(con);data=self.body()
            title=req(data.get('title'),'Название',100)
            description=optional(data.get('description'),'Описание',500)
            date=optional(data.get('exchange_date'),'Дата',10)
            if date:
                try: datetime.strptime(date,'%Y-%m-%d')
                except ValueError: raise ApiError(400,'Неверная дата')
            budget=amount(data.get('budget'))
            currency=enum(data.get('currency') or 'RUB',('RUB','EUR','USD'),'Валюта')
            rules=optional(data.get('rules'),'Правила',1000)
            inserted=con.execute('''INSERT INTO santa_events(owner_id,title,description,exchange_date,budget_cents,currency,rules,invite_key,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?) RETURNING id''',
                        (user['id'],title,description,date or None,budget,currency,rules,token(),now()))
            eid=inserted.fetchone()['id']
            con.execute('INSERT INTO participants(event_id,user_id,name,created_at) VALUES(?,?,?,?)',
                        (eid,user['id'],user['name'],now()))
            return 201,{'id':eid},None
        match=re.fullmatch(r'/api/santas/(\d+)',path)
        if match and method=='GET':
            user=self.auth(con);eid=int(match.group(1))
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            participants=[dict(r) for r in con.execute('''SELECT p.id,p.name,p.user_id,count(pw.id) wish_count
                               FROM participants p LEFT JOIN participant_wishes pw ON pw.participant_id=p.id
                               WHERE p.event_id=? GROUP BY p.id ORDER BY p.id''',(eid,))]
            excluded=[dict(r) for r in con.execute('SELECT giver_id,receiver_id FROM exclusions WHERE event_id=?',(eid,))]
            my_part=con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',(eid,user['id'])).fetchone()
            mine=None
            if my_part and event['status']=='drawn':
                mine=self.assignment_view(con,eid,my_part['id'])
            my_wishes=[dict(r) for r in con.execute(
                'SELECT id,title FROM participant_wishes WHERE participant_id=? ORDER BY id DESC',
                (my_part['id'],))] if my_part else []
            return 200,{'event':dict(event),'participants':participants,'exclusions':excluded,
                        'my_assignment':mine,'my_wishes':my_wishes},None
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes',path)
        if match and method=='GET':
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('''SELECT p.id FROM participants p JOIN santa_events e ON p.event_id=e.id
                             WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',
                             (eid,user['id'],user['id'])).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            return 200,{'wishes':[dict(r) for r in con.execute(
                'SELECT id,title FROM participant_wishes WHERE participant_id=? ORDER BY id DESC',(part['id'],))]},None
        match=re.fullmatch(r'/api/santas/(\d+)/participants/(\d+)',path)
        if match and method=='DELETE':
            user=self.auth(con);eid,pid=map(int,match.groups())
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']!='open': raise ApiError(409,'После жеребьёвки состав не меняется')
            p=con.execute('SELECT * FROM participants WHERE id=? AND event_id=?',(pid,eid)).fetchone()
            if not p: raise ApiError(404,'Участник не найден')
            if p['user_id']==user['id']:
                raise ApiError(409,'Организатора нельзя удалить из игры')
            con.execute('DELETE FROM participants WHERE id=?',(pid,))
            return 200,{'ok':True},None
        match=re.fullmatch(r'/api/santas/(\d+)/exclusions',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1));data=self.body()
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']!='open': raise ApiError(409,'Правила уже заморожены')
            try: a,b=int(data.get('giver_id')),int(data.get('receiver_id'))
            except (ValueError,TypeError,OverflowError): raise ApiError(400,'Выберите двух участников')
            if a==b: raise ApiError(400,'Самому себе и так нельзя дарить')
            if con.execute('SELECT count(*) n FROM participants WHERE event_id=? AND id IN (?,?)',(eid,a,b)).fetchone()['n']!=2:
                raise ApiError(400,'Участник не найден')
            con.execute('INSERT INTO exclusions VALUES(?,?,?) ON CONFLICT DO NOTHING',(eid,a,b))
            return 201,{'ok':True},None
        match=re.fullmatch(r'/api/santas/(\d+)/exclusions/(\d+)/(\d+)',path)
        if match and method=='DELETE':
            user=self.auth(con);eid,a,b=map(int,match.groups())
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']!='open': raise ApiError(409,'Правила уже заморожены')
            con.execute('DELETE FROM exclusions WHERE event_id=? AND giver_id=? AND receiver_id=?',(eid,a,b))
            return 200,{'ok':True},None
        match=re.fullmatch(r'/api/santas/(\d+)/draw',path)
        if match and method=='POST':
            self.throttled('draw',15)
            user=self.auth(con);eid=int(match.group(1))
            con.execute('BEGIN IMMEDIATE')
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']=='drawn':
                return 200, {'ok':True,'already_drawn':True},None
            ids=[r['id'] for r in con.execute('SELECT id FROM participants WHERE event_id=? ORDER BY id',(eid,))]
            blocked=[(r['giver_id'],r['receiver_id']) for r in con.execute('SELECT giver_id,receiver_id FROM exclusions WHERE event_id=?',(eid,))]
            pairs=matching(ids,blocked)
            for a,b in pairs:
                con.execute('INSERT INTO assignments(event_id,giver_id,receiver_id) VALUES(?,?,?)',(eid,a,b))
            con.execute("UPDATE santa_events SET status='drawn' WHERE id=?",(eid,))
            con.execute('COMMIT')
            return 200,{'ok':True,'already_drawn':False},None
        match=re.fullmatch(r'/api/santas/(\d+)/reveal',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('''SELECT p.id FROM participants p JOIN santa_events e ON e.id=p.event_id
                         WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',(eid,user['id'],user['id'])).fetchone()
            if not part: raise ApiError(404,'Место участника не найдено')
            return 200,{'assignment':self.reveal(con,eid,part['id'])},None
        match=re.fullmatch(r'/api/invites/([A-Za-z0-9_\-]+)',path)
        if match and method=='GET':
            event=con.execute('''SELECT title,description,exchange_date,budget_cents,currency,rules,status,
                        (SELECT count(*) FROM participants WHERE event_id=e.id) AS participant_count
                        FROM santa_events e WHERE invite_key=?''',(match.group(1),)).fetchone()
            if not event: raise ApiError(404,'Приглашение не найдено')
            return 200,{'event':dict(event)},None
        match=re.fullmatch(r'/api/invites/([A-Za-z0-9_\-]+)/join',path)
        if match and method=='POST':
            self.throttled('join',20)
            data=self.body(); name=req(data.get('name'),'Имя участника',50)
            con.execute('BEGIN IMMEDIATE')
            event=con.execute('SELECT * FROM santa_events WHERE invite_key=?',(match.group(1),)).fetchone()
            if not event: raise ApiError(404,'Приглашение не найдено')
            if event['status']!='open': raise ApiError(409,'Жеребьёвка уже прошла. Присоединиться нельзя.')
            count=con.execute('SELECT count(*) n FROM participants WHERE event_id=?',(event['id'],)).fetchone()['n']
            if count>=12: raise ApiError(409,'В игре уже 12 участников — максимум для MVP')
            value=token()
            con.execute('INSERT INTO participants(event_id,name,access_hash,created_at) VALUES(?,?,?,?)',
                        (event['id'],name,token_hash(value),now()))
            con.execute('COMMIT')
            return 201,{'participant_token':value},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)',path)
        if match and method=='GET':
            part=con.execute('''SELECT p.id,p.name,p.event_id, e.title,e.description,e.exchange_date,e.budget_cents,
                        e.currency,e.rules,e.status FROM participants p
                        JOIN santa_events e ON e.id=p.event_id WHERE p.access_hash=?''',
                        (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            wishes=[dict(r) for r in con.execute('SELECT id,title FROM participant_wishes WHERE participant_id=? ORDER BY id DESC',(part['id'],))]
            receiver=self.assignment_view(con,part['event_id'],part['id']) if part['status']=='drawn' else None
            return 200,{'participant':dict(part),'wishes':wishes,'assignment':receiver},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/wishes',path)
        if match and method=='POST':
            data=self.body();title=req(data.get('title'),'Желание',130)
            part=con.execute('SELECT id FROM participants WHERE access_hash=?',(token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            con.execute('INSERT INTO participant_wishes(participant_id,title,created_at) VALUES(?,?,?)',(part['id'],title,now()))
            return 201,{'ok':True},None
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1));data=self.body();title=req(data.get('title'),'Желание',130)
            part=con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',(eid,user['id'])).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            con.execute('INSERT INTO participant_wishes(participant_id,title,created_at) VALUES(?,?,?)',(part['id'],title,now()))
            return 201,{'ok':True},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/reveal',path)
        if match and method=='POST':
            part=con.execute('SELECT id,event_id FROM participants WHERE access_hash=?',(token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            return 200,{'assignment':self.reveal(con,part['event_id'],part['id'])},None
        raise ApiError(404,'Такой страницы или действия нет')

    def assignment_view(self,con,eid,pid):
        item=con.execute('''SELECT a.revealed_at, p.id AS receiver_id,p.name AS receiver_name
                 FROM assignments a JOIN participants p ON p.id=a.receiver_id
                 WHERE a.event_id=? AND a.giver_id=?''',(eid,pid)).fetchone()
        if not item or not item['revealed_at']:
            return {'revealed':False}
        wishes=[r['title'] for r in con.execute('SELECT title FROM participant_wishes WHERE participant_id=?',(item['receiver_id'],))]
        return {'revealed':True,'receiver_name':item['receiver_name'],'wishes':wishes}

    def reveal(self,con,eid,pid):
        con.execute('UPDATE assignments SET revealed_at=COALESCE(revealed_at,?) WHERE event_id=? AND giver_id=?',
                    (now(),eid,pid))
        item=self.assignment_view(con,eid,pid)
        if not item or not item.get('revealed'):
            raise ApiError(409,'Жеребьёвка ещё не состоялась')
        return item

    def route(self,method):
        path=unquote(urlparse(self.path).path)
        if method != 'GET':
            origin=self.headers.get('Origin')
            if origin:
                allowed=f'http://{self.headers.get("Host", "")}'
                allowed_secure=f'https://{self.headers.get("Host", "")}'
                if origin not in (allowed, allowed_secure):
                    return self.json(403,{'error':'Запрос из другого источника отклонён'})
        try:
            if path.startswith('/api/'):
                with closing(connect()) as con:
                    with con:
                        result=self.handle_api(method,path,con)
                        self.json(*result)
                return
            if method!='GET':
                raise ApiError(405,'Метод не поддерживается')
            if path.startswith('/uploads/'):
                filename=Path(path).name
                if not re.fullmatch(r'[a-f0-9]{40}\.(jpg|png|webp)',filename):
                    raise ApiError(404,'Файл не найден')
                filepath=ROOT/'uploads'/filename
            elif path in ('/','/index.html') or not Path(path).suffix:
                filepath=ROOT/'public'/'index.html'
            else:
                filepath=(ROOT/'public'/path.lstrip('/')).resolve()
                if not filepath.is_relative_to((ROOT/'public').resolve()):
                    raise ApiError(403,'Доступ запрещён')
            if not filepath.is_file():
                raise ApiError(404,'Файл не найден')
            data=filepath.read_bytes()
            self.send_response(200)
            mime=mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
            if mime.startswith('text/') or mime in ('application/javascript','application/json'):
                mime += '; charset=utf-8'
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length',str(len(data)))
            self.secure_headers()
            self.end_headers()
            self.wfile.write(data)
        except ApiError as exc:
            return self.json(exc.status,{'error':exc.message, **({'detail':exc.detail} if exc.detail else {})})
        except sqlite3.IntegrityError:
            return self.json(409,{'error':'Конфликт данных. Обновите страницу и повторите.'})
        except Exception as exc:
            print('Internal server error:',type(exc).__name__,str(exc))
            return self.json(500,{'error':'Ошибка сервера. Попробуйте ещё раз.'})

    def do_GET(self): self.route('GET')
    def do_POST(self): self.route('POST')
    def do_PATCH(self): self.route('PATCH')
    def do_DELETE(self): self.route('DELETE')


if __name__=='__main__':
    init_db()
    print(f'Шурш! готов: http://localhost:{PORT}  (demo mode: {DEMO_MODE})')
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
