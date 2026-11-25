"""Cloud-specific request adapter, auth, rate limiting and private images."""
from datetime import date, datetime
from hashlib import sha256
import hmac
import os
import re
import sqlite3
import time
from uuid import UUID
from flask import g

from server import Handler, ApiError, req, token, token_hash, decode_image, LIMIT_BYTES
from cloud import auth, db, social, password_policy

SESSION_SECONDS = 24 * 60 * 60
REMEMBER_SESSION_SECONDS = 30 * SESSION_SECONDS
IMAGE_USER_LIMIT = 12_000_000
IMAGE_TOTAL_LIMIT = 100_000_000

# Input-shape checks; Supabase owns password policy and authentication.
AUTH_DOMAIN_LABEL = re.compile(r'[a-z0-9-]+', re.I | re.ASCII)
AUTH_DOMAIN_END = re.compile(r'(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})', re.I | re.ASCII)
AUTH_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+")

def valid_auth_email(raw):
    email = raw.strip() if isinstance(raw,str) else ''
    def reject(message):
        raise ApiError(400,message)
    if not email: reject('Укажи почту')
    if len(email)>200: reject('Адрес почты слишком длинный')
    if any(ch.isspace() for ch in email): reject('Убери пробелы из адреса')
    if any(ord(ch)<32 or ord(ch)==127 for ch in email): reject('Убери управляющие символы из адреса')
    if ',' in email: reject('Убери запятую из адреса')
    if '"' in email: reject('Убери двойные кавычки из адреса')
    if any(ch in '()[]<>' for ch in email): reject('Убери скобки из адреса')
    if ':' in email: reject('Убери двоеточие из адреса')
    if ';' in email: reject('Убери точку с запятой из адреса')
    if '\\' in email: reject('Убери обратную косую черту из адреса')
    parts=email.split('@')
    if len(parts)>2: reject('В адресе должен быть только один знак @')
    local=parts[0]
    if not local: reject('Укажи имя почты перед @')
    if any(not 33<=ord(ch)<=126 for ch in local): reject('Перед @ используй латинские буквы, цифры и допустимые знаки')
    if len(local)>64: reject('Часть почты перед @ слишком длинная')
    if local.startswith('.') or '..' in local or (len(parts)==2 and local.endswith('.')):
        reject('Исправь точки в части почты перед @')
    if not AUTH_LOCAL.fullmatch(local): reject('Проверь символы в части почты перед @')
    if len(parts)==1: reject('Добавь знак @')
    domain=parts[1]
    if not domain: reject('Укажи домен после @')
    if any(not 33<=ord(ch)<=126 for ch in domain): reject('Используй латинские буквы после @')
    if '_' in domain: reject('Убери нижнее подчёркивание из домена')
    bad_domain=re.search(r'[^a-z0-9.-]',domain,re.I|re.ASCII)
    if bad_domain: reject(f'Убери символ {bad_domain.group()} из домена')
    if domain.startswith('.') or '..' in domain: reject('Убери лишние точки в домене')
    labels=domain.split('.')
    if any(label.startswith('-') or label.endswith('-') for label in labels):
        reject('Домен не должен начинаться или заканчиваться дефисом')
    if any(len(label)>63 for label in labels): reject('Часть домена между точками слишком длинная')
    if domain.endswith('.'): reject('Допиши окончание домена, например ru или com')
    if '.' not in domain: reject('Укажи домен с точкой, например example.com')
    if not AUTH_DOMAIN_END.fullmatch(labels[-1]): reject('Проверь окончание домена, например .ru или .com')
    if domain.lower() in ('gmail.com','googlemail.com'):
        base=local.split('+',1)[0]
        if not base: reject('Укажи имя почты Gmail перед +')
        bad=re.search(r'[^a-z0-9.]',base,re.I|re.ASCII)
        if bad: reject(f'Убери символ {bad.group()} из имени почты Gmail')
    if email.lower()=='demo@shursh.local': reject('Этот адрес недоступен для входа')
    return email.lower()


def valid_auth_password(raw):
    if (not isinstance(raw, str) or not 8 <= len(raw) <= 200
            or '\x00' in raw or any(0xD800 <= ord(ch) <= 0xDFFF for ch in raw)):
        raise ApiError(400, 'Пароль должен содержать от 8 до 200 символов')
    return raw


def valid_signup_name(raw):
    value = req(raw, 'Имя', 40)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ApiError(400, 'Убери недопустимые символы из имени')
    return value


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
                self._user = con.execute('''SELECT p.id,p.name,p.avatar_emoji,p.handle,s.email,(a.user_id IS NOT NULL) AS admin_granted FROM app_sessions s
                    JOIN profiles p ON p.id=s.user_id LEFT JOIN site_admins a ON a.user_id=p.id WHERE s.token_hash=? AND s.expires_at>?''',
                    (token_hash(raw), int(time.time()))).fetchone()
                if self._user:
                    self._user=dict(self._user)
                    admins={a.strip().casefold() for a in os.getenv('SHURSH_ADMIN_EMAILS','').split(',') if a.strip()}
                    self._user['is_admin']=bool(self._user.pop('admin_granted',False) or (admins and self._user['email'].casefold() in admins))
        return self._user

    def is_site_admin(self,con):
        user=self.auth(con)
        if not user.get('is_admin'):
            raise ApiError(403,'Недостаточно прав')
        return user

    def throttled(self, action, limit=25, window=60):
        # Vercel sets this header itself; outside Vercel trust only the peer.
        source = self.request.remote_addr or 'unknown'
        if os.environ.get('VERCEL') == '1':
            source = (self.headers.get('x-vercel-forwarded-for') or source).split(',')[0].strip()
        secret = os.environ.get('SHURSH_RATE_SECRET')
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
            raise ApiError(429, 'Слишком много попыток. Попробуй немного позже')

    def resend_confirmation(self):
        # Fixed per-IP limit, independent of the generic API quota. Avoid
        # exposing whether the email exists or has already been verified.
        data = self.body()
        email = valid_auth_email(data.get('email'))
        self.throttled('auth-resend', 3, 600)
        db.close_request_connection()
        started_auth = time.perf_counter()
        try:
            auth.auth_request('resend', type='signup', email=email)
        finally:
            g.shursh_auth_ms = (time.perf_counter() - started_auth) * 1000
        return 202, {'ok':True}, None

    def prepare_confirmation(self):
        # The browser removes tokens from the fragment before transmitting.
        # Validate with Supabase Auth; never decode JWT claims as authority.
        self.throttled('auth-confirm', 10, 600)
        db.close_request_connection()
        payload = self.body()
        token_value = payload.get('access_token')
        if (not isinstance(token_value,str) or len(token_value)>4096 or
                not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token_value)):
            raise ApiError(400, 'Недействительная ссылка подтверждения')
        started_auth = time.perf_counter()
        try:
            provider = auth.verified_user(token_value)
        finally:
            g.shursh_auth_ms = (time.perf_counter() - started_auth) * 1000
        try:
            uid = UUID(provider['id'])
        except (ValueError,TypeError,KeyError):
            raise ApiError(503, 'Сервис входа временно недоступен') from None
        display = (provider.get('user_metadata') or {}).get('name')
        name = display.strip()[:40] if isinstance(display,str) and display.strip() else 'Друг'
        return (uid,name,provider['email'])

    def prepare_auth(self, path, form_data=None):
        self.throttled('auth', 15)
        # Release the completed rate-limit transaction before waiting on HTTPS
        # so slow Supabase Auth does not reserve a PostgreSQL connection.
        db.close_request_connection()
        data = form_data if form_data is not None else self.body()
        email = valid_auth_email(data.get('email'))
        action = 'register' if path.endswith('register') else 'login'
        password = data.get('password') if action == 'register' else valid_auth_password(data.get('password'))
        if action == 'register':
            password_policy.validate_new_password(password)
        payload = {'email': email, 'password': password}
        if action == 'register':
            payload['data'] = {'name': valid_signup_name(data.get('name'))}
        started_auth = time.perf_counter()
        try:
            result = auth.auth_request(action, **payload)
        finally:
            # Duration only. Never log provider response, email or tokens.
            g.shursh_auth_ms = (time.perf_counter() - started_auth) * 1000
        # A confirmation-required signup deliberately never establishes a session.
        if action == 'register' and not result.get('access_token'):
            return None
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
        return (uid, name, provider.get('email') or email)

    def finish_auth(self, con, prepared, remember=False):
        uid,name,verified_email = prepared
        con.execute('INSERT INTO profiles(id,name) VALUES(?,?) ON CONFLICT(id) DO NOTHING', (uid,name))
        value = token()
        now = int(time.time())
        con.execute('DELETE FROM app_sessions WHERE expires_at<=?', (now,))
        previous = self.request.cookies.get('shursh_sid','')
        if re.fullmatch(r'[A-Za-z0-9_-]{43}',previous):
            con.execute('DELETE FROM app_sessions WHERE token_hash=?',(token_hash(previous),))
        rec = con.execute('''SELECT p.id,p.name,p.avatar_emoji,p.handle,
                        (a.user_id IS NOT NULL) AS admin_granted
                        FROM profiles p LEFT JOIN site_admins a ON a.user_id=p.id
                        WHERE p.id=?''',(uid,)).fetchone()
        admins={a.strip().casefold() for a in os.getenv('SHURSH_ADMIN_EMAILS','').split(',') if a.strip()}
        granted=dict(rec)
        is_admin=bool(granted.pop('admin_granted',False) or
                      (admins and verified_email.casefold() in admins))
        ttl=REMEMBER_SESSION_SECONDS if remember and not is_admin else SESSION_SECONDS
        con.execute('INSERT INTO app_sessions(token_hash,user_id,email,expires_at) VALUES(?,?,?,?)',
                    (token_hash(value),uid,verified_email,now+ttl))
        return 200, {'user': {**granted,'email':verified_email,
                 'is_admin':is_admin}}, self.send_cookie(value,ttl)

    def handle_api(self, method, path, con):
        if method == 'GET' and path == '/api/me':
            return 200, {'user': self.user(con), 'demo': False}, None
        if method == 'GET' and path == '/api/dashboard':
            # Two owner-scoped collections, fetched in one transaction.
            # A guest never receives another user's data.
            user = self.user(con)
            if user is None:
                return 200, {'user': None, 'demo': False, 'lists': [], 'events': []}, None
            lists = super().handle_api('GET', '/api/lists', con)[1]['lists']
            santa = social.handle(self, 'GET', '/api/santas', con)[1]
            return 200, {'user': user, 'demo': False, 'lists': lists,
                         'events': santa['events'], 'invitations': santa['invitations']}, None
        if method == 'POST' and path == '/api/logout':
            raw = self.request.cookies.get('shursh_sid','')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}',raw):
                con.execute('DELETE FROM app_sessions WHERE token_hash=?',(token_hash(raw),))
            return 200, {'ok':True}, self.send_cookie('',0)
        if path == '/api/demo-login':
            raise ApiError(404,'Демо-аккаунт отключён')
        # Social routes are authenticated and scoped to the current UID.
        # They are intentionally absent from the local demo handler.
        special=social.handle(self,method,path,con)
        if special is not None:
            return special
        # Legacy bearer links can be retained for unclaimed guests, but once a
        # player is bound to an account, possession of a copied link is not enough.
        # Covers ALL /api/participant/<token> reads and mutations, including
        # wishes, chat, private assignments, roster and completed-game photos.
        capability=re.fullmatch(r'/api/participant/([A-Za-z0-9_-]{43})(?:/.*)?',path)
        if capability:
            participant=con.execute('SELECT user_id FROM participants WHERE access_hash=?',
                                    (token_hash(capability.group(1)),)).fetchone()
            if participant and participant['user_id'] is not None:
                viewer=self.user(con)
                if not viewer or viewer['id']!=participant['user_id']:
                    raise ApiError(404,'Личная ссылка недействительна')
        # Original wishlist, reservation and random matching routes.
        result=super().handle_api(method,path,con)
        social.after_mutation(self,method,path,con,result)
        return result

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
            raise ApiError(413, 'Лимит изображений достигнут. Удали лишние фотографии')
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
