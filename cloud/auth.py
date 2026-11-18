"""Supabase Auth password/confirmation flow; never expose provider tokens."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from server import ApiError


def auth_request(action, **payload):
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if not url.startswith('https://') or not key:
        raise RuntimeError('Supabase Auth is not configured')
    suffix = {'register': 'signup', 'login': 'token?grant_type=password'}[action]
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
        # Do not relay provider details or reveal whether an email exists.
        raise ApiError(400 if action == 'register' else 401,
                       'Не удалось создать аккаунт. Проверь данные и почту.' if action == 'register'
                       else 'Неверная почта, пароль или адрес ещё не подтверждён') from None
    except (URLError, TimeoutError, ValueError):
        raise ApiError(503, 'Сервис входа временно недоступен') from None
    if not isinstance(result, dict):
        raise ApiError(503, 'Сервис входа временно недоступен')
    return result
