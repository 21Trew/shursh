"""New-password shape validation only; legacy login remains unchanged."""
import re
from server import ApiError

def validate_new_password(password):
    if not isinstance(password,str) or not password:
        raise ApiError(400,'Введи пароль')
    if re.search(r'[А-Яа-яЁё]', password):
        raise ApiError(400,'Убери русские буквы из пароля')
    if len(password)<8:
        count=8-len(password)
        word='символ' if count==1 else 'символа' if count<=4 else 'символов'
        raise ApiError(400,f'Добавь ещё {count} {word}')
    if any(ord(ch)<32 or ord(ch)==127 or 0xD800<=ord(ch)<=0xDFFF for ch in password):
        raise ApiError(400,'В пароле есть недопустимые символы')
    # bcrypt must never silently truncate the password.
    if len(password.encode('utf-8'))>72:
        raise ApiError(400,'Пароль слишком длинный. Сократи его')
