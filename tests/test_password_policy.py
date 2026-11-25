import pytest
from cloud.password_policy import validate_new_password
from server import ApiError

@pytest.mark.parametrize('value',['abcdefgh','12345678','Ab3xy!90','A1'+'x'*70])
def test_weak_or_strong_shape_accepted(value):
    validate_new_password(value)

@pytest.mark.parametrize('value,message',[('a','Добавь ещё 7 символов'),('abc','Добавь ещё 5 символов'),('abcd','Добавь ещё 4 символа'),('abcdef','Добавь ещё 2 символа'),('abcdefg','Добавь ещё 1 символ'),('','Введи пароль'),('abcdefgЁ','Убери русские буквы из пароля'),('Abcdefgя','Убери русские буквы из пароля'),('Abcdefg'+'\x00','В пароле есть недопустимые символы'),('Abcdefg'+'\ud800','В пароле есть недопустимые символы'),('a'*73,'Пароль слишком длинный. Сократи его')])
def test_invalid_password(value,message):
    with pytest.raises(ApiError) as exc:
        validate_new_password(value)
    assert exc.value.message==message
