"""Cloud-specific request adapter, auth, rate limiting and private images."""
from datetime import date, datetime
from hashlib import sha256
import hmac
import os
import re
import sqlite3
import time
from uuid import UUID

from server import Handler, ApiError, req, token, token_hash, decode_image, LIMIT_BYTES
from cloud import auth, db

SESSION_SECONDS = 24 * 60 * 60
IMAGE_USER_LIMIT = 12_000_000
IMAGE_TOTAL_LIMIT = 100_000_000


def serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError('Unsupported response value')


class CloudRequest(Handler):
    owner_profile_table = 'profiles'

    def __init__(self, request):
        # The WSGI framework owns the HTTP transport. Only business methods of
        # Handler are reused, never its BaseHTTPRequestHandler lifecycle.
        self.request = request
        self.headers = request.headers
        self._user_loaded = False
        self._user = None

    def body(self):
        if not self.request.is_json:
            raise ApiError(415, 'Ожидается JSON')
        data = self.request.get_data(cache=True)
        if not 0 < len(data) <= LIMIT_BYTES:
            raise ApiError(413, 'Слишком большой запрос или пустые данные')
        parsed = self.request.get_json(silent=True)
        if not isinstance(parsed, dict):
            raise ApiError(400, 'Неверный формат JSON')
        return parsed

    def send_cookie(self, value, max_age=SESSION_SECONDS):
        return f'shursh_sid={value}; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age={max_age}'

    def user(self, con):
        if not self._user_loaded:
            self._user_loaded = True
            raw = self.request.cookies.get('shursh_sid', '')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}', raw):
                self._user = con.execute('''SELECT p.id,p.name,s.email FROM app_sessions s
                    JOIN profiles p ON p.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''',
                    (token_hash(raw), int(time.time()))).fetchone()
        return self._user

    def throttled(self, action, limit=25, window=60):
        # Vercel sets this header itself; outside Vercel trust only the peer.
        source = self.request.remote_addr or 'unknown'
        if os.environ.get('VERCEL') == '1':
            source = (self.headers.get('x-vercel-forwarded-for') or source).split(',')[0].strip()
        secret = os.environ.get('SHURSH_RATE_SECRET') or os.environ.get('SHURSH_DATABASE_URL')
        if not secret:
            raise RuntimeError('Rate limiting is not configured')
        key = hmac.new(secret.encode(), f'{source}:{action}'.encode(), sha256).hexdigest()
        bucket = int(time.time()) // window
        # Independent transaction so failed API requests also count.
        with db.transaction(write=True, rate_limit=True) as con:
            row = con.execute('''INSERT INTO app_rate_limits(key_hash,bucket,hits) VALUES(?,?,1)
                ON CONFLICT(key_hash) DO UPDATE SET hits=CASE WHEN app_rate_limits.bucket=excluded.bucket
                THEN app_rate_limits.hits+1 ELSE 1 END,bucket=excluded.bucket RETURNING hits''', (key,bucket)).fetchone()
            # Do not acquire other request keys while holding this key's row lock.
            # Expired buckets can be pruned by a separate maintenance job.
        if row['hits'] > limit:
            raise ApiError(429, 'Слишком много попыток. Попробуй немного позже.')

    def handle_api(self, method, path, con):
        if method == 'GET' and path == '/api/me':
            return 200, {'user': self.user(con), 'demo': False}, None
        if method == 'POST' and path in ('/api/register', '/api/login'):
            self.throttled('auth', 15)
            data = self.body()
            email = req(data.get('email'), 'Почта', 200).lower()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or email == 'demo@shursh.local':
                raise ApiError(400, 'Укажи корректную почту')
            password = req(data.get('password'), 'Пароль', 200, 8)
            action = 'register' if path.endswith('register') else 'login'
            payload = {'email': email, 'password': password}
            if action == 'register':
                payload['data'] = {'name': req(data.get('name'), 'Имя', 40)}
            result = auth.auth_request(action, **payload)
            # A confirmation-required signup deliberately never establishes a session.
            if action == 'register' and not result.get('access_token'):
                return 202, {'user': None, 'pending_confirmation': True}, None
            provider = result.get('user') or {}
            if not result.get('access_token') or not provider.get('email_confirmed_at'):
                raise ApiError(401, 'Подтверди адрес электронной почты')
            try:
                uid = UUID(provider['id'])
            except (ValueError, TypeError, KeyError):
                raise ApiError(503, 'Сервис входа временно недоступен') from None
            # Metadata is for display ONLY; authorization uses the provider's user ID.
            display = (provider.get('user_metadata') or {}).get('name')
            name = display.strip()[:40] if isinstance(display, str) and display.strip() else 'Друг'
            con.execute('INSERT INTO profiles(id,name) VALUES(?,?) ON CONFLICT(id) DO NOTHING', (uid,name))
            value = token()
            now = int(time.time())
            con.execute('DELETE FROM app_sessions WHERE expires_at<=?', (now,))
            previous = self.request.cookies.get('shursh_sid','')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}',previous):
                con.execute('DELETE FROM app_sessions WHERE token_hash=?',(token_hash(previous),))
            con.execute('INSERT INTO app_sessions(token_hash,user_id,email,expires_at) VALUES(?,?,?,?)',
                        (token_hash(value),uid,provider.get('email') or email,now+SESSION_SECONDS))
            rec = con.execute('SELECT id,name FROM profiles WHERE id=?',(uid,)).fetchone()
            return 200, {'user': {**rec,'email':provider.get('email') or email}}, self.send_cookie(value)
        if method == 'POST' and path == '/api/logout':
            raw = self.request.cookies.get('shursh_sid','')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}',raw):
                con.execute('DELETE FROM app_sessions WHERE token_hash=?',(token_hash(raw),))
            return 200, {'ok':True}, self.send_cookie('',0)
        if path == '/api/demo-login':
            raise ApiError(404,'Демо-аккаунт отключён')
        # All original wishlist, reservation and random matching routes.
        return super().handle_api(method,path,con)

    def store_image(self, con, list_id, data):
        decoded = decode_image(data)
        if not decoded:
            return None
        raw, ext = decoded
        owner = self.auth(con)
        used = con.execute('''SELECT coalesce(sum(octet_length(i.content)),0) AS total FROM wish_images i
            JOIN wishlists w ON w.id=i.list_id WHERE w.owner_id=?''',(owner['id'],)).fetchone()['total']
        total = con.execute('SELECT coalesce(sum(octet_length(content)),0) AS total FROM wish_images').fetchone()['total']
        if used+len(raw)>IMAGE_USER_LIMIT or total+len(raw)>IMAGE_TOTAL_LIMIT:
            raise ApiError(413, 'Лимит изображений достигнут. Удали лишние фотографии.')
        import secrets
        path = '/uploads/'+secrets.token_hex(20)+'.'+ext
        mime = {'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[ext]
        con.execute('INSERT INTO wish_images(path,list_id,mime,content) VALUES(?,?,?,?)',(path,list_id,mime,raw))
        return path

    def image(self, con, path):
        raw = self.user(con)
        item = con.execute('''SELECT i.content,i.mime,w.visibility,w.owner_id FROM wish_images i
            JOIN wishlists w ON w.id=i.list_id WHERE i.path=?''',(path,)).fetchone()
        if not item or (item['visibility']!='link' and (not raw or raw['id']!=item['owner_id'])):
            raise ApiError(404,'Файл не найден')
        return bytes(item['content']), item['mime']
