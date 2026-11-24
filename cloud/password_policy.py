"""Server-only new-password screening; never used on ordinary login."""
import hashlib
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from server import ApiError


def validate_new_password(password):
    if not isinstance(password,str) or len(password)<8:
        raise ApiError(400,'Минимум 8 символов')
    if any(ord(ch)<32 or ord(ch)==127 or 0xD800<=ord(ch)<=0xDFFF for ch in password):
        raise ApiError(400,'В пароле есть недопустимые символы')
    # bcrypt must never silently truncate the password.
    if len(password.encode('utf-8'))>72:
        raise ApiError(400,'Пароль слишком длинный. Сократи его')
    missing=[label for pattern,label in (
        (r'[a-z]','строчную латинскую букву'),
        (r'[A-Z]','заглавную латинскую букву'),
        (r'[0-9]','цифру')) if not re.search(pattern,password)]
    if missing:
        description=missing[0] if len(missing)==1 else ', '.join(missing[:-1])+' и '+missing[-1]
        raise ApiError(400,'Добавь '+description)


def screen_new_password(password):
    validate_new_password(password)
    digest = hashlib.sha1(password.encode('utf-8'), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    # HIBP Pwned Passwords range API: no email, password or full hash leaves
    # the backend. Padding reduces response size side-channel leakage.
    request = Request('https://api.pwnedpasswords.com/range/' + prefix,
                      headers={'Add-Padding': 'true', 'User-Agent': 'Shursh-password-screening'})
    try:
        with urlopen(request, timeout=4) as response:
            # Do not accept redirects to an unrelated host or truncated ranges.
            if response.geturl() != request.full_url or response.status != 200:
                raise ValueError('Invalid range response')
            body = response.read(200001)
        if not body or len(body) > 200000:
            raise ValueError('Invalid range size')
        lines = body.decode('ascii').splitlines()
        found = False
        if not lines:
            raise ValueError('Empty range')
        for line in lines:
            if not re.fullmatch(r'[A-Fa-f0-9]{35}:[0-9]{1,12}', line):
                raise ValueError('Invalid range row')
            candidate, count = line.split(':')
            if candidate.upper() == suffix and int(count) > 0:
                found = True
        if found:
            raise ApiError(400, 'Этот пароль встречался в утечках данных. Придумай другой')
    except (URLError, OSError, ValueError) as exc:
        # Neither the request URL nor the upstream error/body may be logged.
        # Fail closed only for new passwords; existing users can still log in.
        raise ApiError(503, 'Сейчас не удалось проверить безопасность пароля. Попробуй ещё раз') from None
