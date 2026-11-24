"""Supabase Auth password/confirmation flow; never expose provider tokens."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlsplit

from server import ApiError
from cloud.environment import assert_staging_target


def auth_request(action, **payload):
    assert_staging_target(require_database=False)
    url= os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if not url.startswith('https://') or not key:
        raise RuntimeError('Supabase Auth is not configured')
    suffix = {'register': 'signup', 'login': 'token?grant_type=password',
              'resend': 'resend', 'otp': 'otp', 'otp_verify': 'verify'}[action]
    # Confirmation links always use a fixed destination: never request Host.
    # Fail closed instead of silently falling back to Supabase's Site URL.
    if action in ('register', 'resend', 'otp'):
        redirect = os.environ.get('SHURSH_AUTH_REDIRECT_URL', '').strip()
        if not redirect:
            raise RuntimeError('SHURSH_AUTH_REDIRECT_URL is not configured')
        parts = urlsplit(redirect)
        if (parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment
                or parts.path not in ('', '/') or parts.port not in (None, 443)):
            raise RuntimeError('SHURSH_AUTH_REDIRECT_URL must be a trusted HTTPS origin')
        suffix += '?' + urlencode({'redirect_to': redirect})
    request = Request(f'{url}/auth/v1/{suffix}', method='POST',
                      data=json.dumps(payload).encode(),
                      headers={'apikey': key, 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            raise ApiError(429, 'Слишком много попыток. Повтори позже.') from None
        if exc.code >= 500:
            raise ApiError(503, 'Сервис входа временно недоступен') from None
        # Normalize typed duplicate-signup errors to the same response as
        # confirmation-required signup. Never reveal account existence.
        if action == 'register' and exc.code in (400, 422):
            try:
                details = json.loads(exc.read(2048))
            except (ValueError, TypeError):
                details = {}
            if isinstance(details, dict) and details.get('error_code') in (
                    'user_already_exists', 'email_exists'):
                return {}
        if action == 'otp_verify' and exc.code in (400, 401, 403, 422):
            raise ApiError(400, 'Код неверный или истёк. Запроси новый при необходимости') from None
        if action == 'otp':
            # Never relay existence-sensitive provider error codes or raw data.
            if exc.code in (400, 403, 422):
                try:
                    details=json.loads(exc.read(2048))
                except (ValueError, TypeError):
                    details={}
                if isinstance(details,dict) and details.get('error_code') in (
                        'user_already_exists','email_exists','user_not_found',
                        'signup_disabled','email_not_confirmed','user_banned'):
                    return {}
            raise ApiError(503, 'Не удалось запросить код. Попробуй позже') from None
        if action == 'resend':
            # Never claim an email was sent when GoTrue rejected the request,
            # including invalid redirect URL configuration.
            raise ApiError(503, 'Не удалось отправить письмо. Повтори позже') from None
        if action == 'login' and exc.code in (400, 403):
            # Only classify a typed provider error, never expose its raw body.
            try:
                details = json.loads(exc.read(2048))
                if details.get('error_code') == 'email_not_confirmed':
                    raise ApiError(403, 'Почта ещё не подтверждена. Запроси новое письмо') from None
            except (ValueError, AttributeError, TypeError):
                pass
        # Do not relay provider details or reveal whether an email exists.
        raise ApiError(400 if action == 'register' else 401,
                       'Не удалось создать аккаунт. Проверь данные и почту.' if action == 'register'
                       else 'Неверная почта или пароль') from None
    except (URLError, TimeoutError, ValueError):
        raise ApiError(503, 'Сервис входа временно недоступен') from None
    if not isinstance(result, dict):
        raise ApiError(503, 'Сервис входа временно недоступен')
    return result


def verified_user(access_token):
    """Exchange the email-confirmation access token for a verified identity.

    No bearer token is logged or persisted. Supabase Auth validates its own JWT
    and session at /auth/v1/user; we never trust client-supplied identity.
    """
    assert_staging_target(require_database=False)
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if not url.startswith('https://') or not key:
        raise RuntimeError('Supabase Auth is not configured')
    request = Request(f'{url}/auth/v1/user', method='GET',
                      headers={'apikey':key, 'Authorization':f'Bearer {access_token}',
                               'Accept':'application/json'})
    try:
        with urlopen(request, timeout=10) as response:
            user=json.load(response)
    except HTTPError as exc:
        if exc.code in (400, 401, 403, 404):
            raise ApiError(401, 'Ссылка подтверждения истекла или недействительна') from None
        if exc.code == 429:
            raise ApiError(429, 'Слишком много попыток. Повтори позже') from None
        raise ApiError(503, 'Сервис входа временно недоступен') from None
    except (URLError, TimeoutError, ValueError):
        raise ApiError(503, 'Сервис входа временно недоступен') from None
    if not isinstance(user, dict) or not user.get('email_confirmed_at') or not user.get('email'):
        raise ApiError(401, 'Адрес электронной почты ещё не подтверждён')
    return user

def update_verified_account(user_id,email,current_password,change):
    """Supabase Auth owns password/email. A valid Shursh cookie is necessary,
    but never sufficient to alter credentials: verify current password first.
    The upstream access token is short-lived and never returned to the browser.
    """
    reauth=auth_request('login',email=email,password=current_password)
    identity=reauth.get('user') or {}
    access=reauth.get('access_token')
    if not isinstance(access,str) or str(identity.get('id'))!=str(user_id):
        raise ApiError(401,'Текущий пароль неверный')
    assert_staging_target(require_database=False)
    base=os.environ.get('SUPABASE_URL','').rstrip('/')
    key=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
    req=Request(f'{base}/auth/v1/user',method='PUT',
                data=json.dumps(change).encode(),
                headers={'apikey':key,'Authorization':f'Bearer {access}',
                         'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=10) as response:
            updated=json.load(response)
    except HTTPError as error:
        if error.code==429:
            raise ApiError(429,'Слишком много попыток, попробуй позже') from None
        if error.code in (400,401,403,422):
            raise ApiError(400,'Не получилось изменить данные. Проверь пароль и новый адрес') from None
        raise ApiError(503,'Изменить данные сейчас не удалось') from None
    except (URLError,TimeoutError,ValueError):
        raise ApiError(503,'Изменить данные сейчас не удалось') from None
    if not isinstance(updated,dict) or str(updated.get('id'))!=str(user_id):
        raise ApiError(503,'Не удалось подтвердить изменение в системе входа')
    return True

def set_password_from_otp(access, user_id, email, password):
    """Only a server-verified, single-use OTP challenge may call this helper."""
    assert_staging_target(require_database=False)
    base=os.environ.get('SUPABASE_URL','').rstrip('/')
    key=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
    if not base.startswith('https://') or not key:
        raise RuntimeError('Supabase Auth is not configured')
    headers={'apikey':key,'Authorization':f'Bearer {access}',
             'Content-Type':'application/json'}
    req=Request(f'{base}/auth/v1/user',method='PUT',
                data=json.dumps({'password':password}).encode(),headers=headers)
    try:
        with urlopen(req,timeout=10) as response:
            updated=json.load(response)
    except HTTPError as error:
        if error.code==429:
            raise ApiError(429,'Слишком много попыток. Попробуй позже') from None
        if error.code in (400,422):
            try:
                details=json.loads(error.read(2048))
            except (ValueError,TypeError):
                details={}
            if isinstance(details,dict) and details.get('error_code')=='same_password':
                raise ApiError(400,'Новый пароль должен отличаться от текущего') from None
        raise ApiError(503,'Не удалось обновить пароль. Запроси новый код') from None
    except (URLError,TimeoutError,ValueError):
        raise ApiError(503,'Не удалось обновить пароль. Запроси новый код') from None
    if (not isinstance(updated,dict) or str(updated.get('id'))!=str(user_id)
            or str(updated.get('email','')).casefold()!=email.casefold()
            or not updated.get('email_confirmed_at')):
        raise ApiError(503,'Не удалось подтвердить изменение пароля')


def revoke_provider_sessions(access):
    """Revoke refresh sessions using a fresh proof of the accepted password."""
    assert_staging_target(require_database=False)
    base=os.environ.get('SUPABASE_URL','').rstrip('/')
    key=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
    if not base.startswith('https://') or not key:
        raise RuntimeError('Supabase Auth is not configured')
    # Access JWTs may remain valid until expiry; vNext never exchanges them
    # for app sessions, and credential stamps reject unapproved changes.
    headers={'apikey':key,'Authorization':f'Bearer {access}'}
    req=Request(f'{base}/auth/v1/logout?scope=global',method='POST',headers=headers)
    try:
        with urlopen(req,timeout=10) as response:
            if response.status not in (200,204):
                raise ValueError('Unexpected logout response')
    except (HTTPError,URLError,TimeoutError,ValueError):
        raise ApiError(503,'Пароль мог измениться. Запроси новый код для безопасного входа') from None
