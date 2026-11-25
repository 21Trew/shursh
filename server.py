#!/usr/bin/env python3
"""Шурш! - self-contained local web MVP. Python 3.10+, no dependencies."""
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
from datetime import datetime, timezone, timedelta
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
 cancelled_at TEXT, reserved_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_reservation ON reservations(wish_id) WHERE cancelled_at IS NULL;
CREATE TABLE IF NOT EXISTS santa_memories (event_id INTEGER PRIMARY KEY REFERENCES santa_events(id) ON DELETE CASCADE,image_data TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS santa_events (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', exchange_date TEXT,
 budget_cents INTEGER, currency TEXT NOT NULL DEFAULT 'RUB', rules TEXT NOT NULL DEFAULT '',
 invite_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','drawn','finished')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS santa_personal_invites (
 token_hash TEXT PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, claimed_by TEXT, claimed_at TEXT
);
CREATE INDEX IF NOT EXISTS santa_personal_invites_event_idx ON santa_personal_invites(event_id);
CREATE TABLE IF NOT EXISTS participants (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
 name TEXT NOT NULL, access_hash TEXT UNIQUE, created_at TEXT NOT NULL,
 wanted TEXT NOT NULL DEFAULT '', unwanted TEXT NOT NULL DEFAULT '',
 UNIQUE(event_id, user_id)
);
CREATE TABLE IF NOT EXISTS participant_wishes (
 id INTEGER PRIMARY KEY, participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 title TEXT NOT NULL, created_at TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', wanted TEXT NOT NULL DEFAULT '',
 unwanted TEXT NOT NULL DEFAULT '', price_cents INTEGER,
 currency TEXT NOT NULL DEFAULT 'RUB', shop_url TEXT, image_data TEXT
);
CREATE TABLE IF NOT EXISTS santa_messages (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES santa_events(id) ON DELETE CASCADE,
 sender_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
 room TEXT NOT NULL CHECK (room IN ('general','pair')),
 pair_giver_id INTEGER REFERENCES participants(id) ON DELETE CASCADE,
 message TEXT NOT NULL CHECK(length(message) BETWEEN 1 AND 500),
 created_at TEXT NOT NULL,
 CHECK ((room='general' AND pair_giver_id IS NULL) OR
        (room='pair' AND pair_giver_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS santa_messages_room_idx ON santa_messages(event_id,room,pair_giver_id,id);
CREATE TABLE IF NOT EXISTS developer_feedback (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
 topic TEXT NOT NULL, message TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','resolved')),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS developer_feedback_created_idx ON developer_feedback(id DESC);
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
            existing={row['name'] for row in con.execute('PRAGMA table_info(participant_wishes)')}
            for name,definition in (
                ('description',"TEXT NOT NULL DEFAULT ''"),
                ('wanted',"TEXT NOT NULL DEFAULT ''"),
                ('unwanted',"TEXT NOT NULL DEFAULT ''"),
                ('price_cents','INTEGER'),
                ('currency',"TEXT NOT NULL DEFAULT 'RUB'"),
                ('shop_url','TEXT'),
                ('image_data','TEXT')
            ):
                if name not in existing:
                    con.execute('ALTER TABLE participant_wishes ADD COLUMN '+name+' '+definition)
            old_participant_cols={row['name'] for row in con.execute('PRAGMA table_info(participants)')}
            for preference in ('wanted','unwanted'):
                if preference not in old_participant_cols:
                    con.execute("ALTER TABLE participants ADD COLUMN "+preference+" TEXT NOT NULL DEFAULT ''")
                    # One-time backfill; old gift-specific notes remain untouched.
                    con.execute("""UPDATE participants SET """+preference+"""=COALESCE((
                        SELECT substr(group_concat(NULLIF(trim("""+preference+"""),''),char(10)),1,2000)
                        FROM participant_wishes WHERE participant_id=participants.id
                    ),'')""")
            if DEMO_MODE and not con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                seed_demo(con)


def seed_demo(con):
    con.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES (?,?,?,?)',
                ('Саша', 'demo@shursh.local', password_hash('demo12345'), now()))
    uid = con.execute('SELECT id FROM users WHERE email=?', ('demo@shursh.local',)).fetchone()['id']
    lists = [
        ('День рождения, ура!', 'Собрала здесь то, чему буду очень рада. Но сюрпризы тоже люблю ♡', 'День рождения', 'peach'),
        ('Маленькие радости', 'На случай, если захочется сделать мой день чуть теплее', 'Просто так', 'lilac')
    ]
    list_ids = []
    for title, description, occasion, theme in lists:
        con.execute('INSERT INTO wishlists(owner_id,title,description,occasion,theme,visibility,share_key,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    (uid,title,description,occasion,theme,'link',token(),now()))
        list_ids.append(con.execute('SELECT last_insert_rowid()').fetchone()[0])
    samples = [
        (list_ids[0], 'Плёночный фотоаппарат', 'Хочется снимать неловкие, живые моменты', 890000, 'RUB', 'love', 'item', None),
        (list_ids[0], 'Керамическая чашка ручной работы', 'Большая, с характером. Можно необычной формы', 250000, 'RUB', 'nice', 'item', None),
        (list_ids[0], 'Билеты на спектакль', 'Буду рада любому необычному театру', 500000, 'RUB', 'love', 'experience', None),
        (list_ids[0], 'Красивое издание любимой книги', 'С иллюстрациями и плотной бумагой', 180000, 'RUB', 'nice', 'item', None),
        (list_ids[1], 'Вечер настолок', 'С печеньем и классной компанией', None, 'RUB', 'nice', 'experience', None),
        (list_ids[1], 'Набор цветных карандашей', 'Для спонтанных зарисовок', 190000, 'RUB', 'nice', 'item', None)
    ]
    for rec in samples:
        con.execute('''INSERT INTO wishes(list_id,title,description,price_cents,currency,priority,kind,shop_url,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?)''', (*rec, now()))
    con.execute('''INSERT INTO santa_events(owner_id,title,description,exchange_date,budget_cents,currency,rules,invite_key,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (uid,'Санта на нашей кухне','Чай, печенье и маленькие сюрпризы','2026-12-25',250000,'RUB',
                 'Главное - внимание, а не цена. Упаковываем подарки красиво!',token(),now()))
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
        raise ApiError(409, 'С такими исключениями жеребьёвка невозможна. Уберите часть ограничений')
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
                raise ApiError(429,'Слишком много попыток. Попробуйте немного позже')
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


    def santa_schema_ready(self,con):
        """Read-only feature detection: shared hosted DB may not be migrated."""
        if isinstance(con,sqlite3.Connection):
            return True
        ready=getattr(self,'_santa_feature_ready',None)
        if ready is None:
            row=con.execute("""SELECT (
                EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='participant_wishes'
                  AND column_name='wanted')
                AND to_regclass('public.santa_messages') IS NOT NULL
              ) AS ready""").fetchone()
            ready=bool(row['ready'])
            self._santa_feature_ready=ready
        return ready

    @staticmethod
    def santa_roster(con, eid):
        """Member-visible projection. Never include contact info or draw pairs."""
        return [dict(r) for r in con.execute('''SELECT p.id,p.name,p.user_id,
            count(pw.id) AS wish_count,
            CASE WHEN p.user_id=e.owner_id THEN 1 ELSE 0 END AS is_organizer
            FROM participants p JOIN santa_events e ON e.id=p.event_id
            LEFT JOIN participant_wishes pw ON pw.participant_id=p.id
            WHERE p.event_id=?
            GROUP BY p.id,p.name,p.user_id,e.owner_id ORDER BY p.id''',(eid,))]

    @staticmethod
    def participant_preferences(con,pid):
        row=con.execute('SELECT wanted,unwanted FROM participants WHERE id=?',(pid,)).fetchone()
        if not row: raise ApiError(404,'Участник не найден')
        return {'wanted':row['wanted'] or '', 'unwanted':row['unwanted'] or ''}

    def edit_participant_preferences(self,con,pid):
        data=self.body()
        wanted=optional(data.get('wanted'),'Что хотелось бы',2000)
        unwanted=optional(data.get('unwanted'),'Чего не хотелось бы',2000)
        con.execute('UPDATE participants SET wanted=?,unwanted=? WHERE id=?',(wanted,unwanted,pid))
        return 200,{'preferences':{'wanted':wanted,'unwanted':unwanted}},None

    def game_wishes(self,con,participant_id):
        if not self.santa_schema_ready(con):
            return [dict(r)|{'description':'','wanted':'','unwanted':'','price_cents':None,
                    'currency':'RUB','shop_url':None,'image_data':None}
                    for r in con.execute('''SELECT id,title FROM participant_wishes
                        WHERE participant_id=? ORDER BY id DESC''',(participant_id,))]
        return [dict(r) for r in con.execute('''SELECT id,title,description,wanted,unwanted,
            price_cents,currency,shop_url,image_data FROM participant_wishes
            WHERE participant_id=? ORDER BY id DESC''',(participant_id,))]

    @staticmethod
    def game_wish_payload(data):
        title=req(data.get('title'),'Название подарка',130)
        description=optional(data.get('description'),'Описание',800)
        wanted=optional(data.get('wanted'),'Что хотелось бы',500)
        unwanted=optional(data.get('unwanted'),'Чего не хотелось бы',500)
        price=amount(data.get('price'))
        currency=enum(data.get('currency') or 'RUB',('RUB','EUR','USD'),'Валюта')
        url=shop_url(data.get('shop_url'))
        picture=data.get('image_data')
        if picture:
            decoded=decode_image(picture)
            if len(decoded[0])>250_000:
                raise ApiError(413,'Фото для игры должно быть не больше 250 КБ')
        else:
            picture=None
        return (title,description,wanted,unwanted,price,currency,url,picture)

    def add_game_wish(self,con,participant_id,data):
        if not self.santa_schema_ready(con):
            title=req(data.get('title'),'Желание',130)
            rec=con.execute('''INSERT INTO participant_wishes(participant_id,title,created_at)
                           VALUES(?,?,?) RETURNING id''',(participant_id,title,now())).fetchone()
            return {'id':rec['id']}
        if con.execute('SELECT count(*) AS n FROM participant_wishes WHERE participant_id=?',
                       (participant_id,)).fetchone()['n']>=40:
            raise ApiError(409,'Максимум 40 подарков для участника')
        values=self.game_wish_payload(data)
        rec=con.execute('''INSERT INTO participant_wishes(
              participant_id,title,description,wanted,unwanted,price_cents,currency,
              shop_url,image_data,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id''',
              (participant_id,*values,now())).fetchone()
        return {'id':rec['id']}

    def game_wish_from_library(self,con,row,list_id):
        """Small authorized image snapshots; no external image URL fetching."""
        image=None
        if row.get('image_path'):
            if isinstance(con, sqlite3.Connection):
                source=(ROOT/row['image_path'].lstrip('/')).resolve()
                directory=(ROOT/'uploads').resolve()
                if source.is_relative_to(directory) and source.is_file() and source.stat().st_size<=250_000:
                    import mimetypes
                    mime=mimetypes.guess_type(source)[0]
                    if mime in ('image/png','image/jpeg','image/webp'):
                        import base64
                        image='data:'+mime+';base64,'+base64.b64encode(source.read_bytes()).decode()
            else:
                image_rec=con.execute('SELECT mime,content FROM wish_images WHERE path=? AND list_id=?',
                                      (row['image_path'],list_id)).fetchone()
                if image_rec and len(image_rec['content'])<=250_000:
                    import base64
                    image='data:'+image_rec['mime']+';base64,'+base64.b64encode(bytes(image_rec['content'])).decode()
        return image

    def import_wishlist_wishes(self, con, user, participant_id, data):
        """Snapshot only this account owner's selected wishlist gifts."""
        try:
            list_id=int(data.get('list_id'))
        except (TypeError,ValueError,OverflowError):
            raise ApiError(400,'Выбери свой вишлист') from None
        lst=con.execute('SELECT id FROM wishlists WHERE id=? AND owner_id=?',
                        (list_id,user['id'])).fetchone()
        if not lst: raise ApiError(404,'Вишлист не найден')
        rows=[dict(r) for r in con.execute('''SELECT id,title,description,price_cents,
                currency,shop_url,image_path FROM wishes WHERE list_id=? ORDER BY id''',(list_id,))]
        selected=data.get('wish_ids')
        if selected is not None:
            if not isinstance(selected,list) or len(selected)>40:
                raise ApiError(400,'Выбери до 40 подарков')
            try:
                ids=[int(value) for value in selected]
            except (TypeError,ValueError,OverflowError):
                raise ApiError(400,'Неверный список подарков') from None
            if len(ids)!=len(set(ids)) or any(i<=0 for i in ids):
                raise ApiError(400,'Неверный список подарков')
            allowed={r['id']:r for r in rows}
            if any(i not in allowed for i in ids):
                raise ApiError(400,'Подарок не принадлежит выбранному вишлисту')
            rows=[allowed[i] for i in ids]
        if len(rows)>40: raise ApiError(400,'Можно добавить не больше 40 подарков за раз')
        existing={r['title'].strip().casefold() for r in con.execute(
            'SELECT title FROM participant_wishes WHERE participant_id=?',(participant_id,))}
        if len(rows)+len(existing)>80:
            raise ApiError(409,'Слишком много подарков')
        compatible=not self.santa_schema_ready(con)
        added=0
        for row in rows:
            title=row['title'].strip()
            if title.casefold() in existing: continue
            if len(existing)>=40: break
            if compatible:
                con.execute('INSERT INTO participant_wishes(participant_id,title,created_at) VALUES(?,?,?)',
                            (participant_id,title,now()))
            else:
                image=self.game_wish_from_library(con,row,list_id)
                con.execute('''INSERT INTO participant_wishes(
                     participant_id,title,description,wanted,unwanted,price_cents,
                     currency,shop_url,image_data,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                     (participant_id,title,row['description'] or '','','',row['price_cents'],
                      row['currency'],row['shop_url'],image,now()))
            existing.add(title.casefold());added+=1
        return {'added':added,'skipped':len(rows)-added,'snapshot':True}

    def mutate_game_wish(self,con,pid,wid,method):
        if not self.santa_schema_ready(con):
            raise ApiError(409,'Карточки подарков пока недоступны')
        wish=con.execute('SELECT id,image_data,wanted,unwanted FROM participant_wishes WHERE participant_id=? AND id=?',
                         (pid,wid)).fetchone()
        if not wish: raise ApiError(404,'Подарок не найден')
        if method=='DELETE':
            con.execute('DELETE FROM participant_wishes WHERE id=? AND participant_id=?',(wid,pid))
            return 200,{'ok':True},None
        data=self.body()
        values=list(self.game_wish_payload(data))
        # Preserve legacy gift-specific notes hidden by the new participant-level UI.
        for position,key in ((2,'wanted'),(3,'unwanted')):
            if key not in data: values[position]=wish[key]
        # Editing text should not upload the unchanged photo again.
        if 'image_data' not in data:
            values[-1]=wish['image_data']
        con.execute('''UPDATE participant_wishes SET title=?,description=?,wanted=?,unwanted=?,
                     price_cents=?,currency=?,shop_url=?,image_data=?
                     WHERE id=? AND participant_id=?''',(*values,wid,pid))
        return 200,{'ok':True},None

    @staticmethod
    def chat_pair(con,eid,pid,room):
        if room=='general':
            return None
        if room not in ('to-recipient','from-santa'):
            raise ApiError(404,'Чат не найден')
        column='giver_id' if room=='to-recipient' else 'receiver_id'
        pair=con.execute('SELECT giver_id,receiver_id FROM assignments WHERE event_id=? AND '+
                         column+'=?',(eid,pid)).fetchone()
        if not pair: raise ApiError(409,'Парные чаты откроются после жеребьёвки')
        return pair['giver_id']

    def chat_messages(self,con,eid,pid,room,method):
        if not self.santa_schema_ready(con):
            raise ApiError(409,'Чаты появятся после обновления игры')
        # Every route resolves its authenticated owner or private participant
        # capability BEFORE reaching this function. Admin is not a moderator
        # with unlimited access to other pairs.
        pair=self.chat_pair(con,eid,pid,room)
        topic='general' if pair is None else 'pair'
        condition='m.pair_giver_id=?' if pair is not None else 'm.pair_giver_id IS NULL'
        args=(eid,topic,pair) if pair is not None else (eid,topic)
        if method=='POST':
            if not getattr(self,'_chat_rate_checked',False): self.throttled('chat',20)
            payload=self.body()
            message=req(payload.get('message'),'Сообщение',500)
            count=con.execute('SELECT count(*) AS n FROM santa_messages m WHERE m.event_id=? AND m.room=? AND '+
                              condition,args).fetchone()['n']
            if count>=2500: raise ApiError(409,'Чат заполнен')
            created=now()
            sent=con.execute('''INSERT INTO santa_messages(event_id,sender_id,room,pair_giver_id,message,created_at)
                       VALUES(?,?,?,?,?,?) RETURNING id''',(eid,pid,topic,pair,message,created)).fetchone()
            return 201,{'ok':True,'room':room,
                        'message':{'id':sent['id'],'message':message,'author':'Ты',
                                   'mine':True,'created_at':created}},None
        if method=='GET':
            rows=con.execute('''SELECT m.id,m.sender_id,m.message,m.created_at,p.name
                 FROM santa_messages m JOIN participants p ON p.id=m.sender_id
                 WHERE m.event_id=? AND m.room=? AND '''+condition+
                 ' ORDER BY m.id DESC LIMIT 60',args)
            items=[]
            for row in reversed([dict(r) for r in rows]):
                mine=row['sender_id']==pid
                if topic=='general':
                    author=row['name']
                elif row['sender_id']==pair:
                    author='Тайный даритель'
                else:
                    author='Получатель'
                items.append({'id':row['id'],'message':row['message'],
                              'created_at':row['created_at'],'mine':mine,
                              'author':'Ты' if mine else author})
            return 200,{'messages':items,'room':room},None
        raise ApiError(405,'Метод не поддерживается')

    def santa_memory(self,con,event_id,method,personal_link=False,member=False):
        event=con.execute('SELECT owner_id,status FROM santa_events WHERE id=?',(event_id,)).fetchone()
        if not event: raise ApiError(404,'Игра не найдена')
        user=None if personal_link else (self.auth(con) if method=='PUT' else self.user(con))
        owner=bool(user and user['id']==event['owner_id'])
        belongs=bool(user and con.execute(
            'SELECT 1 FROM participants WHERE event_id=? AND user_id=?',
            (event_id,user['id'])).fetchone())
        if not (owner or belongs or personal_link):
            raise ApiError(404,'Игра недоступна')
        if event['status']!='finished':
            raise ApiError(409,'Общее фото доступно после завершения игры')
        if method=='GET':
            item=con.execute('SELECT image_data,updated_at FROM santa_memories WHERE event_id=?',(event_id,)).fetchone()
            return 200,{'memory':dict(item) if item else None,'can_edit':owner},None
        if method!='PUT' or not owner:
            raise ApiError(403,'Загрузить общее фото может только организатор')
        data=self.body()
        image=data.get('image_data')
        if not isinstance(image,str) or not image:
            raise ApiError(400,'Выбери фотографию')
        decoded=decode_image(image)
        if not decoded or len(decoded[0])>900_000:
            raise ApiError(413,'Общее фото должно быть не больше 900 КБ')
        con.execute('''INSERT INTO santa_memories(event_id,image_data,updated_at) VALUES(?,?,?)
                       ON CONFLICT(event_id) DO UPDATE SET
                       image_data=excluded.image_data,updated_at=excluded.updated_at''',
                    (event_id,image,now()))
        return 200,{'ok':True},None

    def is_site_admin(self,con):
        user=self.auth(con)
        allowed={email.strip().casefold() for email in
                 os.getenv('SHURSH_ADMIN_EMAILS','').split(',') if email.strip()}
        if not allowed or (user['email'] or '').casefold() not in allowed:
            raise ApiError(403,'Недостаточно прав')
        return user

    def handle_api(self,method,path,con):
        if path=='/api/feedback' and method=='POST':
            if not getattr(self,'_feedback_rate_checked',False):
                self.throttled('feedback',5,600)
            data=self.body()
            name=req(data.get('name'),'Имя',80)
            email=req(data.get('email'),'Почта',200).lower()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                raise ApiError(400,'Укажи корректную почту')
            topic=enum(data.get('topic'),('idea','bug','question','other'),'Тема')
            message=req(data.get('message'),'Сообщение',3000,5)
            con.execute('''INSERT INTO developer_feedback(name,email,topic,message,status,created_at)
                         VALUES(?,?,?,?,'new',?)''',(name,email,topic,message,now()))
            return 201,{'ok':True},None
        if path=='/api/admin/feedback' and method=='GET':
            self.is_site_admin(con)
            items=[dict(r) for r in con.execute('''SELECT id,name,email,topic,message,status,created_at
                       FROM developer_feedback ORDER BY id DESC LIMIT 100''')]
            return 200,{'items':items},None
        match=re.fullmatch(r'/api/admin/feedback/(\d+)',path)
        if match and method=='PATCH':
            self.is_site_admin(con)
            status=enum(self.body().get('status'),('new','resolved'),'Статус')
            updated=con.execute('''UPDATE developer_feedback SET status=? WHERE id=?
                            RETURNING id''',(status,int(match.group(1)))).fetchone()
            if not updated: raise ApiError(404,'Обращение не найдено')
            return 200,{'ok':True},None
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
            if owner_view:
                # Never query reservation metadata for the list owner.
                wishes=[dict(rec) for rec in con.execute('SELECT * FROM wishes WHERE list_id=? ORDER BY id DESC',(item['id'],))]
            else:
                # One joined read instead of one reservation query per gift.
                for rec in con.execute('''SELECT w.*,r.id AS active_reservation_id,r.reserved_by AS active_reserved_by
                         FROM wishes w LEFT JOIN reservations r ON r.wish_id=w.id AND r.cancelled_at IS NULL
                         WHERE w.list_id=? ORDER BY w.id DESC''',(item['id'],)):
                    wish=dict(rec)
                    reserved=wish.pop('active_reservation_id') is not None
                    reserved_by=wish.pop('active_reserved_by')
                    wish['reserved']=reserved
                    wish['reserved_by_me']=bool(user and reserved and reserved_by==user['id'])
                    wishes.append(wish)
            return 200, {'list':output,'wishes':wishes,'owner_view':owner_view},None
        match=re.fullmatch(r'/api/public/([A-Za-z0-9_\-]+)/reserve/(\d+)',path)
        if match and method in ('POST','DELETE'):
            # Enforce identity on the server, not only through a disabled button.
            user=self.auth(con)
            key,wid=match.group(1),int(match.group(2))
            item=con.execute('''SELECT wishes.id,wishlists.owner_id FROM wishes JOIN wishlists
                         ON wishes.list_id=wishlists.id WHERE wishes.id=? AND wishlists.share_key=? AND wishlists.visibility='link' ''',
                         (wid,key)).fetchone()
            if not item: raise ApiError(404,'Подарок не найден')
            if user['id']==item['owner_id']:
                raise ApiError(403,'Нельзя бронировать собственный подарок')
            if method=='DELETE':
                removed=con.execute('''UPDATE reservations SET cancelled_at=? WHERE
                      wish_id=? AND reserved_by=? AND cancelled_at IS NULL RETURNING id''',
                      (now(),wid,user['id'])).fetchone()
                if not removed: raise ApiError(409,'Нет активной брони этого подарка в твоём аккаунте')
                return 200,{'ok':True},None
            if not getattr(self,'_reserve_rate_checked',False): self.throttled('reserve',20)
            self.body()
            con.execute('BEGIN IMMEDIATE')
            try:
                # Keep the legacy hash opaque for old management-link compatibility;
                # authenticated bookings never receive a management token.
                con.execute('''INSERT INTO reservations(wish_id,guest_name,manage_hash,created_at,reserved_by)
                               VALUES(?,?,?,?,?)''',(wid,'Анонимный даритель',token_hash(token()),now(),user['id']))
            except sqlite3.IntegrityError:
                raise ApiError(409,'Этот подарок уже забронировали. Выбери другой')
            con.execute('COMMIT')
            return 201,{'ok':True},None
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
        if method=='GET' and path=='/api/santa/library':
            # One small response replaces sequential full-wishlist/image requests.
            user=self.auth(con)
            rows=con.execute('''SELECT l.id AS list_id,l.title AS list_title,
                   w.id AS wish_id,w.title AS wish_title
                   FROM wishlists l LEFT JOIN wishes w ON w.list_id=l.id
                   WHERE l.owner_id=? ORDER BY l.id DESC,w.id DESC''',
                   (user['id'],))
            lists=[]
            by_id={}
            for r in rows:
                lid=r['list_id']
                if lid not in by_id:
                    item={'id':lid,'title':r['list_title'],'wishes':[]}
                    by_id[lid]=item
                    lists.append(item)
                if r['wish_id'] is not None:
                    by_id[lid]['wishes'].append({'id':r['wish_id'],'title':r['wish_title']})
            return 200,{'lists':lists},None
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
        match=re.fullmatch(r'/api/santas/(\d+)/memory',path)
        if match and method in ('GET','PUT'):
            return self.santa_memory(con,int(match.group(1)),method)
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_-]+)/memory',path)
        if match and method=='GET':
            part=con.execute('SELECT event_id FROM participants WHERE access_hash=?',
                             (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            return self.santa_memory(con,part['event_id'],method,personal_link=True)
        match=re.fullmatch(r'/api/santas/(\d+)/roster',path)
        if match and method=='GET':
            user=self.auth(con);eid=int(match.group(1))
            game=con.execute('SELECT status FROM santa_events WHERE id=? AND owner_id=?',
                             (eid,user['id'])).fetchone()
            if not game: raise ApiError(404,'Игра не найдена')
            return 200,{'participants':self.santa_roster(con,eid),
                        'status':game['status']},None
        match=re.fullmatch(r'/api/santas/(\d+)',path)
        if match and method=='DELETE':
            user=self.auth(con);eid=int(match.group(1))
            event=con.execute('SELECT id FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            # All game-related FK rows cascade; never delete another organizer's game.
            con.execute('DELETE FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id']))
            return 200,{'ok':True},None
        if match and method=='PATCH':
            user=self.auth(con);eid=int(match.group(1));data=self.body()
            event=con.execute('SELECT * FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            updates={}
            if 'exchange_date' in data:
                value=data['exchange_date']
                if value in ('',None):
                    updates['exchange_date']=None
                elif isinstance(value,str):
                    try:
                        parsed=datetime.strptime(value,'%Y-%m-%d').date()
                        if parsed.isoformat()!=value: raise ValueError()
                    except ValueError:
                        raise ApiError(400,'Неверная дата') from None
                    updates['exchange_date']=value
                else:
                    raise ApiError(400,'Неверная дата')
            if 'budget' in data:
                updates['budget_cents']=amount(data['budget'])
            if 'title' in data:
                updates['title']=req(data['title'],'Название игры',90)
            if 'description' in data:
                updates['description']=optional(data['description'],'Описание игры',500)
            if not updates: raise ApiError(400,'Нет изменений')
            con.execute('UPDATE santa_events SET '+', '.join(k+'=?' for k in updates)+
                        ' WHERE id=?',(*updates.values(),eid))
            return 200,{'ok':True},None
        match=re.fullmatch(r'/api/santas/(\d+)/personal-invites',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1))
            # Expired, unused invitation tokens must never remain valid.
            cutoff=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='seconds')
            con.execute('DELETE FROM santa_personal_invites WHERE claimed_at IS NULL AND created_at <= ?', (cutoff,))
            event=con.execute('SELECT status FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']!='open':
                raise ApiError(409,'После жеребьёвки новые приглашения недоступны')
            value=token()
            con.execute('INSERT INTO santa_personal_invites(token_hash,event_id,created_at) VALUES(?,?,?)',
                        (token_hash(value),eid,now()))
            return 201,{'invite_token':value},None
        match=re.fullmatch(r'/api/santas/(\d+)/participants',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1));data=self.body()
            name=req(data.get('name'),'Имя участника',50)
            event=con.execute('SELECT status FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            if event['status']!='open': raise ApiError(409,'Состав игры уже заморожен')
            current=[dict(r) for r in con.execute(
                'SELECT name FROM participants WHERE event_id=?',(eid,))]
            if len(current)>=12: raise ApiError(409,'В игре уже 12 участников - максимум')
            if any(p['name'].strip().casefold()==name.casefold() for p in current):
                raise ApiError(409,'Участник с таким именем уже в игре')
            value=token()
            result=con.execute('''INSERT INTO participants(event_id,name,access_hash,created_at)
                     VALUES(?,?,?,?) RETURNING id''',
                     (eid,name,token_hash(value),now()))
            return 201,{'id':result.fetchone()['id'],'participant_token':value},None
        match=re.fullmatch(r'/api/santas/(\d+)/participants/(\d+)/new-link',path)
        if match and method=='POST':
            user=self.auth(con);eid,pid=map(int,match.groups())
            event=con.execute('SELECT status FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            part=con.execute('SELECT user_id FROM participants WHERE event_id=? AND id=?',
                             (eid,pid)).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            if part['user_id'] is not None:
                raise ApiError(409,'Участник уже привязан к аккаунту. Новая гостевая ссылка не нужна')
            if event['status']!='open':
                raise ApiError(409,'После жеребьёвки ссылки не меняются')
            value=token()
            con.execute('UPDATE participants SET access_hash=? WHERE id=? AND event_id=?',
                        (token_hash(value),pid,eid))
            return 200,{'participant_token':value},None
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes/import',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1));data=self.body()
            participant=con.execute('''SELECT p.id FROM participants p
                JOIN santa_events e ON e.id=p.event_id
                WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',
                (eid,user['id'],user['id'])).fetchone()
            if not participant: raise ApiError(404,'Место участника не найдено')
            return 200,self.import_wishlist_wishes(con,user,participant['id'],data),None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/wishes/import',path)
        if match and method=='POST':
            user=self.auth(con);data=self.body()
            participant=con.execute('SELECT id FROM participants WHERE access_hash=?',
                                    (token_hash(match.group(1)),)).fetchone()
            if not participant: raise ApiError(404,'Личная ссылка недействительна')
            return 200,self.import_wishlist_wishes(con,user,participant['id'],data),None
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
            if my_part and event['status'] in ('drawn','finished'):
                mine=self.assignment_view(con,eid,my_part['id'])
            my_wishes=self.game_wishes(con,my_part['id']) if my_part else []
            return 200,{'event':dict(event),'participants':participants,'exclusions':excluded,
                        'my_assignment':mine,'my_wishes':my_wishes,
                        'my_preferences':self.participant_preferences(con,my_part['id']) if my_part else {'wanted':'','unwanted':''},
                        'rich_enabled':self.santa_schema_ready(con)},None
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes',path)
        if match and method=='GET':
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('''SELECT p.id FROM participants p JOIN santa_events e ON p.event_id=e.id
                             WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',
                             (eid,user['id'],user['id'])).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            return 200,{'wishes':self.game_wishes(con,part['id'])},None
        match=re.fullmatch(r'/api/santas/(\d+)/preferences',path)
        if match and method=='PATCH':
            user=self.auth(con)
            part=con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',
                             (int(match.group(1)),user['id'])).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            return self.edit_participant_preferences(con,part['id'])
        # Organizer may only read/write their own three chat rooms.
        match=re.fullmatch(r'/api/santas/(\d+)/messages/(general|to-recipient|from-santa)',path)
        if match and method in ('GET','POST'):
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('''SELECT p.id FROM participants p
                JOIN santa_events e ON e.id=p.event_id
                WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',
                (eid,user['id'],user['id'])).fetchone()
            if not part: raise ApiError(404,'Чат не найден')
            return self.chat_messages(con,eid,part['id'],match.group(2),method)
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/messages/(general|to-recipient|from-santa)',path)
        if match and method in ('GET','POST'):
            part=con.execute('''SELECT id,event_id FROM participants WHERE access_hash=?''',
                             (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Чат не найден')
            return self.chat_messages(con,part['event_id'],part['id'],match.group(2),method)
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
            if event['status']=='finished': raise ApiError(409,'Завершённую игру нельзя разыграть снова')
            ids=[r['id'] for r in con.execute('SELECT id FROM participants WHERE event_id=? ORDER BY id',(eid,))]
            blocked=[(r['giver_id'],r['receiver_id']) for r in con.execute('SELECT giver_id,receiver_id FROM exclusions WHERE event_id=?',(eid,))]
            pairs=matching(ids,blocked)
            for a,b in pairs:
                con.execute('INSERT INTO assignments(event_id,giver_id,receiver_id) VALUES(?,?,?)',(eid,a,b))
            con.execute("UPDATE santa_events SET status='drawn' WHERE id=?",(eid,))
            con.execute('COMMIT')
            return 200,{'ok':True,'already_drawn':False},None
        match=re.fullmatch(r'/api/santas/(\d+)/finish',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1))
            event=con.execute('SELECT status FROM santa_events WHERE id=? AND owner_id=?',
                              (eid,user['id'])).fetchone()
            if not event: raise ApiError(404,'Игра не найдена')
            data=self.body()
            photo=data.get('image_data')
            if photo is not None:
                if not isinstance(photo,str) or not photo.startswith('data:image/webp;base64,'):
                    raise ApiError(400,'Фотография должна быть в формате WebP')
                decoded=decode_image(photo)
                if not decoded or decoded[1]!='webp' or len(decoded[0])>900_000:
                    raise ApiError(413,'Фото должно быть не больше 900 КБ')
            if event['status']=='finished':
                if photo: raise ApiError(409,'Игра уже завершена. Измени фото на странице игры')
                return 200,{'ok':True,'already_finished':True},None
            # An unplayed event may be archived without creating assignments.
            if event['status'] not in ('open','drawn'):
                raise ApiError(409,'Нельзя завершить игру')
            con.execute("UPDATE santa_events SET status='finished' WHERE id=? AND status IN ('open','drawn')",(eid,))
            if photo:
                con.execute('INSERT INTO santa_memories(event_id,image_data,updated_at) VALUES(?,?,?)',(eid,photo,now()))
            return 200,{'ok':True,'already_finished':False},None
        match=re.fullmatch(r'/api/santas/(\d+)/reveal',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('''SELECT p.id FROM participants p JOIN santa_events e ON e.id=p.event_id
                         WHERE e.id=? AND e.owner_id=? AND p.user_id=?''',(eid,user['id'],user['id'])).fetchone()
            if not part: raise ApiError(404,'Место участника не найдено')
            return 200,{'assignment':self.reveal(con,eid,part['id'])},None
        match=re.fullmatch(r'/api/personal-invites/([A-Za-z0-9_-]{43})',path)
        if match and method=='GET':
            row=con.execute('''SELECT e.id,e.title,e.description,e.exchange_date,e.budget_cents,
                              e.currency,e.rules,e.status,i.claimed_at
                              FROM santa_personal_invites i JOIN santa_events e ON e.id=i.event_id
                              WHERE i.token_hash=? AND i.created_at > ?''',
                              (token_hash(match.group(1)),(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='seconds'))).fetchone()
            if not row: raise ApiError(404,'Приглашение не найдено')
            data=dict(row);used=bool(data.pop('claimed_at'))
            user=self.user(con)
            joined=bool(user and con.execute(
                'SELECT 1 FROM participants WHERE event_id=? AND user_id=?',
                (row['id'],user['id'])).fetchone())
            eid=data.pop('id')
            return 200,{'event':data,'event_id':eid,'used':used,'already_joined':joined},None
        match=re.fullmatch(r'/api/personal-invites/([A-Za-z0-9_-]{43})/join',path)
        if match and method=='POST':
            self.throttled('join',20)
            user=self.auth(con)
            name=req(self.body().get('name'),'Имя участника',50)
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('''SELECT i.event_id,i.claimed_at,e.status
                     FROM santa_personal_invites i JOIN santa_events e ON e.id=i.event_id
                     WHERE i.token_hash=? AND i.created_at > ?''',
                     (token_hash(match.group(1)),(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='seconds'))).fetchone()
            if not row: raise ApiError(404,'Приглашение не найдено')
            if row['claimed_at']: raise ApiError(409,'Эта личная ссылка уже использована')
            if row['status']!='open':
                raise ApiError(409,'Приём участников завершён')
            eid=row['event_id']
            if con.execute('SELECT 1 FROM participants WHERE event_id=? AND user_id=?',
                           (eid,user['id'])).fetchone():
                raise ApiError(409,'Ты уже участвуешь в этой игре')
            people=con.execute('SELECT name FROM participants WHERE event_id=?',(eid,)).fetchall()
            if len(people)>=12: raise ApiError(409,'В игре уже 12 участников - максимум')
            if any(p['name'].strip().casefold()==name.casefold() for p in people):
                raise ApiError(409,'Такое имя уже занято в игре')
            con.execute('''INSERT INTO participants(event_id,user_id,name,created_at)
                           VALUES(?,?,?,?)''',(eid,user['id'],name,now()))
            updated=con.execute('''UPDATE santa_personal_invites SET claimed_by=?,claimed_at=?
                        WHERE token_hash=? AND claimed_at IS NULL RETURNING token_hash''',
                        (user['id'],now(),token_hash(match.group(1)))).fetchone()
            if not updated: raise ApiError(409,'Эта личная ссылка уже использована')
            con.execute('COMMIT')
            return 201,{'event_id':eid},None
        match=re.fullmatch(r'/api/invites/([A-Za-z0-9_\-]+)',path)
        if match and method=='GET':
            event=con.execute('''SELECT title,description,exchange_date,budget_cents,currency,rules,status,
                        (SELECT count(*) FROM participants WHERE event_id=e.id) AS participant_count
                        FROM santa_events e WHERE invite_key=?''',(match.group(1),)).fetchone()
            if not event: raise ApiError(404,'Приглашение не найдено')
            logged=self.user(con)
            joined=bool(logged and con.execute(
                'SELECT 1 FROM participants WHERE event_id=(SELECT id FROM santa_events WHERE invite_key=?) AND user_id=?',
                (match.group(1),logged['id'])).fetchone())
            return 200,{'event':dict(event),'already_joined':joined},None
        match=re.fullmatch(r'/api/invites/([A-Za-z0-9_\-]+)/join',path)
        if match and method=='POST':
            self.throttled('join',20)
            user=self.auth(con)
            data=self.body(); name=req(data.get('name'),'Имя участника',50)
            con.execute('BEGIN IMMEDIATE')
            event=con.execute('SELECT * FROM santa_events WHERE invite_key=?',(match.group(1),)).fetchone()
            if not event: raise ApiError(404,'Приглашение не найдено')
            if event['status']!='open': raise ApiError(409,'Жеребьёвка уже прошла. Присоединиться нельзя')
            signed_in=user
            participants=[dict(r) for r in con.execute(
                'SELECT name,user_id FROM participants WHERE event_id=?',(event['id'],))]
            if len(participants)>=12: raise ApiError(409,'В игре уже 12 участников - максимум для MVP')
            if signed_in and any(p['user_id']==signed_in['id'] for p in participants):
                raise ApiError(409,'Ты уже участвуешь в этой игре')
            if any(p['name'].strip().casefold()==name.casefold() for p in participants):
                raise ApiError(409,'Участник с таким именем уже в игре')
            # Registered joins must not mint an anonymous bearer credential.
            # The existing session and UID are the only authority for this member.
            con.execute('INSERT INTO participants(event_id,user_id,name,created_at) VALUES(?,?,?,?)',
                        (event['id'],signed_in['id'],name,now()))
            con.execute('COMMIT')
            return 201,{'event_id':event['id']},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/roster',path)
        if match and method=='GET':
            member=con.execute('''SELECT p.event_id,e.status FROM participants p
                JOIN santa_events e ON e.id=p.event_id WHERE p.access_hash=?''',
                (token_hash(match.group(1)),)).fetchone()
            if not member: raise ApiError(404,'Личная ссылка недействительна')
            return 200,{'participants':self.santa_roster(con,member['event_id']),
                        'status':member['status']},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)',path)
        if match and method=='GET':
            # A personal bearer link grants membership view, not organizer powers.
            part=con.execute('''SELECT p.id,p.name,p.event_id,p.user_id, e.title,e.description,e.exchange_date,e.budget_cents,
                        e.currency,e.rules,e.status FROM participants p
                        JOIN santa_events e ON e.id=p.event_id WHERE p.access_hash=?''',
                        (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            event=con.execute('''SELECT id,title,description,exchange_date,budget_cents,currency,rules,status,invite_key
                            FROM santa_events WHERE id=?''',(part['event_id'],)).fetchone()
            # A safe roster projection: never expose emails, user IDs, personal
            # access tokens, exclusions, draw pairings or another person's wishes.
            participants=[dict(r) for r in con.execute('''SELECT p.id,p.name,count(pw.id) AS wish_count,
                         CASE WHEN p.user_id=e.owner_id THEN 1 ELSE 0 END AS is_organizer
                         FROM participants p JOIN santa_events e ON e.id=p.event_id
                         LEFT JOIN participant_wishes pw ON pw.participant_id=p.id
                         WHERE p.event_id=? GROUP BY p.id,p.name,p.user_id,e.owner_id
                         ORDER BY p.id''',(part['event_id'],))]
            public_event=dict(event)
            if public_event['status']!='open':
                public_event.pop('invite_key')
            wishes=self.game_wishes(con,part['id'])
            receiver=self.assignment_view(con,part['event_id'],part['id']) if part['status'] in ('drawn','finished') else None
            return 200,{'participant':dict(part),'event':public_event,
                        'participants':participants,'wishes':wishes,'assignment':receiver,
                        'preferences':self.participant_preferences(con,part['id']),
                        'rich_enabled':self.santa_schema_ready(con)},None
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/preferences',path)
        if match and method=='PATCH':
            part=con.execute('SELECT id FROM participants WHERE access_hash=?',
                             (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            return self.edit_participant_preferences(con,part['id'])
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/wishes',path)
        if match and method in ('GET','POST'):
            part=con.execute('SELECT id FROM participants WHERE access_hash=?',
                             (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            if method=='GET':
                return 200,{'wishes':self.game_wishes(con,part['id'])},None
            return 201,self.add_game_wish(con,part['id'],self.body()),None
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes',path)
        if match and method=='POST':
            user=self.auth(con);eid=int(match.group(1))
            part=con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',
                             (eid,user['id'])).fetchone()
            if not part: raise ApiError(404,'Участник не найден')
            return 201,self.add_game_wish(con,part['id'],self.body()),None
        # Only the owner of a Santa wishlist may update or remove its cards.
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/wishes/(\d+)',path)
        if match and method in ('PATCH','DELETE'):
            part=con.execute('SELECT id FROM participants WHERE access_hash=?',
                             (token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Подарок не найден')
            return self.mutate_game_wish(con,part['id'],int(match.group(2)),method)
        match=re.fullmatch(r'/api/santas/(\d+)/my-wishes/(\d+)',path)
        if match and method in ('PATCH','DELETE'):
            user=self.auth(con);eid,wid=map(int,match.groups())
            part=con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',
                             (eid,user['id'])).fetchone()
            if not part: raise ApiError(404,'Подарок не найден')
            return self.mutate_game_wish(con,part['id'],wid,method)
        match=re.fullmatch(r'/api/participant/([A-Za-z0-9_\-]+)/reveal',path)
        if match and method=='POST':
            part=con.execute('SELECT id,event_id FROM participants WHERE access_hash=?',(token_hash(match.group(1)),)).fetchone()
            if not part: raise ApiError(404,'Личная ссылка недействительна')
            return 200,{'assignment':self.reveal(con,part['event_id'],part['id'])},None
        raise ApiError(404,'Такой страницы или действия нет')

    def assignment_view(self,con,eid,pid):
        item=con.execute('''SELECT a.revealed_at, p.id AS receiver_id,p.name AS receiver_name,p.user_id AS receiver_user_id
                 FROM assignments a JOIN participants p ON p.id=a.receiver_id
                 WHERE a.event_id=? AND a.giver_id=?''',(eid,pid)).fetchone()
        if not item:
            return None
        if not item['revealed_at']:
            return {'revealed':False}
        cards=self.game_wishes(con,item['receiver_id'])
        return {'revealed':True,'receiver_name':item['receiver_name'],'receiver_user_id':item['receiver_user_id'],
                'preferences':self.participant_preferences(con,item['receiver_id']),
                'wishes':[w['title'] for w in cards],'wish_cards':cards}

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
                filepath=ROOT/'templates'/'index.html'
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
            return self.json(409,{'error':'Конфликт данных. Обновите страницу и повторите'})
        except Exception as exc:
            print('Internal server error:',type(exc).__name__,str(exc))
            return self.json(500,{'error':'Ошибка сервера. Попробуйте ещё раз'})

    def do_GET(self): self.route('GET')
    def do_POST(self): self.route('POST')
    def do_PATCH(self): self.route('PATCH')
    def do_DELETE(self): self.route('DELETE')


if __name__=='__main__':
    init_db()
    print(f'Шурш! готов: http://localhost:{PORT}  (demo mode: {DEMO_MODE})')
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
