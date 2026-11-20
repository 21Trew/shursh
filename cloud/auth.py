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
              'resend': 'resend'}[action]
    # Confirmation links always use a fixed destination: never request Host.
    # Fail closed instead of silently falling back to Supabase's Site URL.
    if action in ('register', 'resend'):
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
        if action == 'resend':
            # Invalid/unknown/already-confirmed addresses get the same generic
            # response. Provider credentials/configuration failures do not.
            if exc.code in (400, 404, 422):
                return {}
            raise ApiError(503, 'Сервис подтверждения временно недоступен') from None
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
