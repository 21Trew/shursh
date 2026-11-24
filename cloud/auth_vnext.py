"""Staging-only native OTP onboarding/recovery. No bearer token in browser JS.

A provider access token is encrypted at rest, tied to an opaque browser cookie,
and destroyed on completion. A durable per-address generation fences in-flight
password logins across reset; no DB transaction spans a provider HTTP request.
"""
import hashlib
import hmac
import os
import re
import time
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.conninfo import conninfo_to_dict

from cloud import auth, db, password_policy
from cloud.backend import valid_auth_email, valid_signup_name
from cloud.environment import assert_staging_target, EnvironmentError
from server import ApiError, token, token_hash

COOKIE='__Host-shursh_auth'
CHALLENGE_SECONDS=600
BUSY_SECONDS=120


def enabled():
    if os.environ.get('SHURSH_AUTH_VNEXT')!='1':
        return False
    if os.environ.get('VERCEL_ENV')=='production' or (
            os.environ.get('VERCEL')=='1' and os.environ.get('SHURSH_ENV')!='staging'):
        raise EnvironmentError('vnext_not_staging', 'Auth vNext is restricted to isolated Staging')
    assert_staging_target()
    if os.environ.get('SHURSH_ENV')!='staging':
        # Never allow this experiment against a hosted DSN from a local shell.
        cfg=conninfo_to_dict(os.environ.get('SHURSH_DATABASE_URL',''))
        if (cfg.get('host') not in ('localhost','127.0.0.1')
                or cfg.get('dbname')!='shursh_ci' or cfg.get('hostaddr')
                or cfg.get('service') or cfg.get('options')):
            raise EnvironmentError('vnext_database_not_isolated', 'Auth vNext requires isolated Staging or disposable CI')
    return True


def secret():
    value=os.environ.get('SHURSH_RATE_SECRET')
    if not value:
        raise RuntimeError('Auth challenge key is not configured')
    return value.encode()


def address_key(email):
    return hmac.new(secret(),b'auth-vnext-address:'+email.encode(),hashlib.sha256).hexdigest()


def lock_address(con,key):
    value=int.from_bytes(bytes.fromhex(key[:16]),'big',signed=True)
    con.execute('SELECT pg_advisory_xact_lock(?)',(value,))


def cookie(value,age=CHALLENGE_SECONDS):
    return f'{COOKIE}={value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={age}'


def raw_challenge(handler):
    raw=handler.request.cookies.get(COOKIE,'')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',raw):
        raise ApiError(400,'Запроси новый код')
    return token_hash(raw)


def cipher():
    key=hmac.new(secret(),b'auth-vnext-proof-encryption-v1',hashlib.sha256).digest()
    return AESGCM(key)


def encrypt_proof(access,challenge_hash):
    nonce=os.urandom(12)
    return nonce+cipher().encrypt(nonce,access.encode(),challenge_hash.encode())


def decrypt_proof(value,challenge_hash):
    return cipher().decrypt(value[:12],value[12:],challenge_hash.encode()).decode()


def guard(con,key):
    row=con.execute('SELECT generation,busy_until FROM shursh_auth_private.guard WHERE email_hash=?',(key,)).fetchone()
    return (row['generation'],row['busy_until']) if row else ('',0)


def ensure_idle(con,key):
    generation,busy=guard(con,key)
    if busy>int(time.time()):
        raise ApiError(409,'Сейчас обновляются данные входа. Попробуй немного позже')
    return generation


def credential_fingerprint(con,uid):
    # The narrowly granted private function returns a second hash of the
    # provider's salted verifier, never the password or original verifier.
    row=con.execute('SELECT shursh_auth_private.credential_fingerprint(?) AS stamp',(uid,)).fetchone()
    return row['stamp'] if row else None


def login(handler):
    email=valid_auth_email(handler.body().get('email'))
    key=address_key(email)
    def snapshot():
        with db.transaction() as con:
            return ensure_idle(con,key)
    prepared,generation=handler.prepare_auth('/api/login',before_upstream=snapshot)
    uid,_,verified_email=prepared
    if verified_email.casefold()!=email:
        raise ApiError(401,'Неверная почта или пароль')
    with db.transaction(write=True,rate_limit=True) as con:
        lock_address(con,key)
        if ensure_idle(con,key)!=generation:
            raise ApiError(409,'Данные входа изменились. Введи пароль ещё раз')
        # Never let an unconfirmed/legacy provider identity materialize a
        # Shursh profile merely by logging in after someone verified its email.
        if not con.execute('SELECT id FROM profiles WHERE id=?',(uid,)).fetchone():
            raise ApiError(403,'Подтверди почту, чтобы завершить создание аккаунта')
        approved=con.execute('SELECT stamp FROM shursh_auth_private.credential_stamp WHERE user_id=?',(uid,)).fetchone()
        current=credential_fingerprint(con,uid)
        if not approved or current is None or not hmac.compare_digest(approved['stamp'],current):
            raise ApiError(403,'Для безопасного входа восстанови пароль по почте')
        return handler.finish_auth(con,prepared)


def start(handler):
    data=handler.body()
    email=valid_auth_email(data.get('email'))
    key=address_key(email)
    handler.throttled('otp-send-ip',8,600)
    handler.throttled('otp-send-email',3,600,identity=email)
    purpose=data.get('purpose','recover')
    if purpose not in ('register','recover'):
        raise ApiError(400,'Неизвестный способ подтверждения')
    if purpose=='register':
        # Validate before sending mail. Never persist a proposed password or
        # assign it to the provider until the same browser verifies the OTP.
        valid_signup_name(data.get('name'))
        if data.get('password')!=data.get('confirm_password'):
            raise ApiError(400,'Пароли не совпадают')
        db.close_request_connection()
        password_policy.screen_new_password(data.get('password'))
    raw=token()
    digest=token_hash(raw)
    now=int(time.time())
    with db.transaction(write=True,rate_limit=True) as con:
        lock_address(con,key)
        # Limit resend independently of provider behavior and IP rotation.
        old=con.execute('SELECT sent_at,state,expires_at FROM shursh_auth_private.challenge WHERE email_hash=?',(key,)).fetchone()
        if old and (now-old['sent_at']<60 or (old['state'] in ('sending','verifying') and old['expires_at']>now)):
            raise ApiError(429,'Запроси новый код немного позже')
        ensure_idle(con,key)
        con.execute("""INSERT INTO shursh_auth_private.challenge(email_hash,challenge_hash,state,sent_at,expires_at,attempts)
          VALUES(?,?,'sending',?,?,0) ON CONFLICT(email_hash) DO UPDATE SET
          challenge_hash=excluded.challenge_hash,state='sending',sent_at=excluded.sent_at,
          expires_at=excluded.expires_at,attempts=0,user_id=NULL,proof=NULL,existing=NULL""",
          (key,digest,now,now+CHALLENGE_SECONDS))
        # Expired rows contain no usable capability; bounded cleanup per send.
        con.execute("""DELETE FROM shursh_auth_private.challenge WHERE email_hash IN
          (SELECT email_hash FROM shursh_auth_private.challenge WHERE expires_at<?
           LIMIT 50 FOR UPDATE SKIP LOCKED)""",(now,))
    db.close_request_connection()
    try:
        # Recovery must never provision a provider identity. A registration
        # may create a provisional identity but never an app profile.
        auth.auth_request('otp',email=email,create_user=(purpose=='register'))
    except ApiError:
        with db.transaction(write=True,rate_limit=True) as con:
            con.execute("UPDATE shursh_auth_private.challenge SET state='consumed' WHERE challenge_hash=? AND state='sending'",(digest,))
        raise
    with db.transaction(write=True,rate_limit=True) as con:
        changed=con.execute("UPDATE shursh_auth_private.challenge SET state='pending' WHERE challenge_hash=? AND state='sending' RETURNING challenge_hash",(digest,)).fetchone()
        if not changed:
            raise ApiError(400,'Запроси новый код')
    return 202,{'ok':True,'retry_after':60,'expires_in':CHALLENGE_SECONDS},cookie(raw)


def verify(handler):
    data=handler.body()
    email=valid_auth_email(data.get('email'))
    code=data.get('code')
    if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):
        raise ApiError(400,'Введи шесть цифр из письма')
    digest=raw_challenge(handler)
    key=address_key(email)
    handler.throttled('otp-verify-ip',30,600)
    handler.throttled('otp-verify-email',10,600,identity=email)
    now=int(time.time())
    with db.transaction(write=True,rate_limit=True) as con:
        row=con.execute("""UPDATE shursh_auth_private.challenge SET attempts=attempts+1,state='verifying'
          WHERE email_hash=? AND challenge_hash=? AND state='pending' AND expires_at>? AND attempts<5
          RETURNING attempts""",(key,digest,now)).fetchone()
        if not row:
            raise ApiError(400,'Код истёк или исчерпаны попытки. Запроси новый')
    db.close_request_connection()
    try:
        result=auth.auth_request('otp_verify',email=email,token=code,type='email')
        provider=result.get('user') or {}
        access=result.get('access_token')
        if (not isinstance(access,str) or not 1<=len(access)<=8192
                or not provider.get('email_confirmed_at')
                or str(provider.get('email','')).casefold()!=email):
            raise ApiError(400,'Не удалось подтвердить почту. Запроси новый код')
        try:
            uid=UUID(provider['id'])
        except (KeyError,ValueError,TypeError):
            raise ApiError(503,'Сервис входа временно недоступен') from None
        proof=encrypt_proof(access,digest)
    except ApiError:
        with db.transaction(write=True,rate_limit=True) as con:
            con.execute("UPDATE shursh_auth_private.challenge SET state='pending' WHERE challenge_hash=? AND state='verifying'",(digest,))
        raise
    with db.transaction(write=True,rate_limit=True) as con:
        lock_address(con,key)
        existing=bool(con.execute('SELECT id FROM profiles WHERE id=?',(uid,)).fetchone())
        changed=con.execute("""UPDATE shursh_auth_private.challenge SET state='verified',user_id=?,proof=?,existing=?
          WHERE challenge_hash=? AND state='verifying' AND expires_at>? RETURNING challenge_hash""",
          (uid,proof,existing,digest,int(time.time()))).fetchone()
        if not changed:
            raise ApiError(400,'Код истёк. Запроси новый')
    return 200,{'next':'existing' if existing else 'setup'},None


def finish(handler):
    data=handler.body()
    email=valid_auth_email(data.get('email'))
    key=address_key(email)
    digest=raw_challenge(handler)
    handler.throttled('otp-finish-ip',12,600)
    handler.throttled('otp-finish-email',8,600,identity=email)
    now=int(time.time())
    with db.transaction() as con:
        row=con.execute("""SELECT user_id,existing FROM shursh_auth_private.challenge
           WHERE email_hash=? AND challenge_hash=? AND state='verified' AND expires_at>?""",
           (key,digest,now)).fetchone()
    if not row:
        raise ApiError(400,'Подтверди почту заново')
    password=data.get('password')
    name=None if row['existing'] else valid_signup_name(data.get('name'))
    db.close_request_connection()
    password_policy.screen_new_password(password)
    generation=token_hash(token())
    # Commit revocation and consume the proof BEFORE the remote mutation.
    # A crash cannot restore an old Shursh session or replay the proof.
    with db.transaction(write=True,rate_limit=True) as con:
        lock_address(con,key)
        ensure_idle(con,key)
        row=con.execute("""SELECT user_id,existing,proof FROM shursh_auth_private.challenge
            WHERE email_hash=? AND challenge_hash=? AND state='verified' AND expires_at>? FOR UPDATE""",
            (key,digest,int(time.time()))).fetchone()
        if not row:
            raise ApiError(400,'Подтверди почту заново')
        uid=row['user_id']
        actual=con.execute('SELECT id,name FROM profiles WHERE id=?',(uid,)).fetchone()
        if bool(actual)!=row['existing']:
            raise ApiError(409,'Данные аккаунта изменились. Запроси новый код')
        access=decrypt_proof(row['proof'],digest)
        con.execute("UPDATE shursh_auth_private.challenge SET state='consumed',proof=NULL WHERE challenge_hash=?",(digest,))
        con.execute("""INSERT INTO shursh_auth_private.guard(email_hash,generation,busy_until)
            VALUES(?,?,?) ON CONFLICT(email_hash) DO UPDATE SET
            generation=excluded.generation,busy_until=excluded.busy_until""",
            (key,generation,int(time.time())+BUSY_SECONDS))
        con.execute('DELETE FROM app_sessions WHERE user_id=?',(uid,))
    db.close_request_connection()
    try:
        auth.set_password_from_otp(access,uid,email,password)
    except ApiError as error:
        # A typed same-password rejection is not an ambiguous mutation.
        # Restore the verified challenge only for that explicit rejection.
        # All sessions were conservatively revoked; no old cookie is restored.
        if error.status==400 and error.message=='Новый пароль должен отличаться от текущего':
            with db.transaction(write=True,rate_limit=True) as con:
                lock_address(con,key)
                current,busy=guard(con,key)
                if current==generation and busy>int(time.time()):
                    con.execute('UPDATE shursh_auth_private.guard SET busy_until=0 WHERE email_hash=? AND generation=?',(key,generation))
                    con.execute("""UPDATE shursh_auth_private.challenge SET state='verified',proof=?
                       WHERE challenge_hash=? AND state='consumed' AND expires_at>?""",
                       (encrypt_proof(access,digest),digest,int(time.time())))
        raise
    # Establish that the provider accepts the exact newly screened candidate.
    # Snapshot before proof; compare again before accepting the credential.
    # A direct provider password mutation must not be blessed by the app.
    with db.transaction() as con:
        stamp=credential_fingerprint(con,uid)
    db.close_request_connection()
    if stamp is None:
        raise ApiError(503,'Не удалось подтвердить новый пароль. Запроси новый код')
    confirmed=auth.auth_request('login',email=email,password=password)
    identity=confirmed.get('user') or {}
    fresh=confirmed.get('access_token')
    if (not isinstance(fresh,str) or not fresh or str(identity.get('id'))!=str(uid)
            or str(identity.get('email','')).casefold()!=email or not identity.get('email_confirmed_at')):
        raise ApiError(503,'Не удалось подтвердить новый пароль. Запроси новый код')
    auth.revoke_provider_sessions(fresh)
    with db.transaction(write=True,rate_limit=True) as con:
        lock_address(con,key)
        current,busy=guard(con,key)
        if current!=generation or busy<=int(time.time()):
            raise ApiError(409,'Данные входа изменились. Запроси новый код')
        live_stamp=credential_fingerprint(con,uid)
        if live_stamp is None or not hmac.compare_digest(stamp,live_stamp):
            raise ApiError(409,'Данные входа изменились. Запроси новый код')
        con.execute("""INSERT INTO shursh_auth_private.credential_stamp(user_id,stamp) VALUES(?,?)
            ON CONFLICT(user_id) DO UPDATE SET stamp=excluded.stamp""",(uid,stamp))
        con.execute('DELETE FROM app_sessions WHERE user_id=?',(uid,))
        con.execute('UPDATE shursh_auth_private.guard SET busy_until=0 WHERE email_hash=? AND generation=?',(key,generation))
        if not row['existing']:
            status,data,session_cookie=handler.finish_auth(con,(uid,name,email))
            return status,data,[session_cookie,cookie('',0)]
        # OWASP recovery guidance: return to pre-filled normal login, not an
        # implicit session after password reset. Existing profile untouched.
        return 200,{'login_required':True},[handler.send_cookie('',0),cookie('',0)]
