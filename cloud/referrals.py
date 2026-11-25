"""Revocable friend invitations and server-bound signup attribution.

No auth tokens, emails, client-supplied identities or raw provider metadata are
stored. A referral is counted only on a verified, newly registered identity.
"""
from datetime import datetime, timedelta, timezone
import re
import secrets
from uuid import UUID
from server import ApiError

CODE = re.compile(r'[A-Za-z0-9_-]{24}')
TTL = timedelta(days=7)

def ready(con):
    return con.execute("SELECT to_regclass('public.user_invites') IS NOT NULL AS ready").fetchone()['ready']

def require_ready(con):
    if not ready(con):
        raise ApiError(503,'Приглашения пока недоступны')

def active(con, code):
    if not isinstance(code,str) or not CODE.fullmatch(code):
        raise ApiError(404,'Приглашение недействительно')
    row=con.execute("""SELECT i.code,i.owner_id,p.name,p.handle,p.avatar_emoji
             FROM user_invites i JOIN profiles p ON p.id=i.owner_id
             WHERE i.code=? AND i.revoked_at IS NULL
               AND (p.discoverable OR p.allow_friend_invites)""",(code,)).fetchone()
    if not row:
        raise ApiError(404,'Приглашение недействительно')
    return row

def prepare_signup(con, code):
    require_ready(con)
    active(con,code)
    return (code,secrets.token_urlsafe(32),datetime.now(timezone.utc))

def record_signup(con, intent, provider, email):
    """Accept only a fresh non-obfuscated signup returned by the provider.
    The generated nonce distinguishes this request; it is not an auth claim.
    A duplicate signup response must not create attribution for an old user.
    """
    code,nonce,started=intent
    if not isinstance(provider,dict) or not provider.get('identities'):
        return
    if provider.get('email_confirmed_at'):
        return
    meta=provider.get('user_metadata')
    if not isinstance(meta,dict) or meta.get('shursh_signup_nonce')!=nonce:
        return
    try:
        uid=UUID(provider['id'])
        created=datetime.fromisoformat(provider['created_at'].replace('Z','+00:00'))
        if created.tzinfo is None or not started-timedelta(seconds=2)<=created<=datetime.now(timezone.utc)+timedelta(seconds=2):
            return
        if provider.get('email','').casefold()!=email.casefold():
            return
    except (KeyError,ValueError,TypeError,AttributeError):
        return
    con.execute('DELETE FROM referral_pending WHERE expires_at<=now()')
    # The code may have been revoked while the provider request was in flight.
    # No FK to a possibly obfuscated provider identity; expired rows are pruned.
    con.execute("""INSERT INTO referral_pending(provider_id,invite_code,signup_at,expires_at)
             SELECT ?,i.code,?,? FROM user_invites i JOIN profiles p ON p.id=i.owner_id
             WHERE i.code=? AND i.revoked_at IS NULL AND i.owner_id<>?
               AND (p.discoverable OR p.allow_friend_invites)
               AND NOT EXISTS (SELECT 1 FROM profiles old WHERE old.id=? AND old.created_at<?)
             ON CONFLICT(provider_id) DO NOTHING""",
             (uid,started,started+TTL,code,uid,uid,started-timedelta(seconds=2)))

def claim(con, uid):
    """Called only after verified provider login/confirmation, in its transaction.
    Unique referred_id makes retries and concurrent confirmation exactly-once.
    """
    row=con.execute("""INSERT INTO referral_attributions(referred_id,referrer_id,invite_code)
        SELECT r.provider_id,i.owner_id,i.code
        FROM referral_pending r JOIN user_invites i ON i.code=r.invite_code
        JOIN profiles p ON p.id=i.owner_id JOIN profiles new ON new.id=r.provider_id
        WHERE r.provider_id=? AND r.expires_at>now() AND i.revoked_at IS NULL
        AND i.owner_id<>r.provider_id AND (p.discoverable OR p.allow_friend_invites)
        AND new.created_at>=r.signup_at-interval '2 seconds'
        ON CONFLICT(referred_id) DO NOTHING RETURNING invite_code""",(uid,)).fetchone()
    con.execute('DELETE FROM referral_pending WHERE provider_id=?',(uid,))
    return '/i/'+row['invite_code'] if row else None

def own_invite(con, uid, origin):
    p=con.execute('SELECT discoverable,allow_friend_invites FROM profiles WHERE id=?',(uid,)).fetchone()
    if not p or not (p['discoverable'] or p['allow_friend_invites']):
        raise ApiError(403,'Разреши приглашения в настройках профиля')
    row=con.execute('SELECT code FROM user_invites WHERE owner_id=? AND revoked_at IS NULL',(uid,)).fetchone()
    if not row:
        code=secrets.token_urlsafe(18)
        con.execute('INSERT INTO user_invites(code,owner_id) VALUES(?,?)',(code,uid))
    else:
        code=row['code']
    url=origin.rstrip('/')+'/i/'+code
    # No external QR API, no data sent to a third party. Matrix includes a quiet zone.
    import qrcode
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=1)
    qr.add_data(url)
    qr.make(fit=True)
    return {'path':'/i/'+code,'url':url,'qr':[''.join('1' if bit else '0' for bit in row) for row in qr.get_matrix()]}
