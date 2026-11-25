"""Integration suite: real PostgreSQL, mocked only external Supabase Auth transport.
Never run this against a hosted database. CI provides a disposable database.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from uuid import UUID
import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://localhost'
IDS = {'owner@example.test': UUID('11111111-1111-4111-8111-111111111111'),
       'other@example.test': UUID('22222222-2222-4222-8222-222222222222')}
PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'test-image').decode()

@pytest.fixture(scope='session', autouse=True)
def db_setup():
    dsn = os.environ.get('SHURSH_DATABASE_URL', '')
    if not dsn:
        pytest.fail('A disposable PostgreSQL CI database is required')
    cfg = conninfo_to_dict(dsn)
    assert cfg.get('host') in ('localhost', '127.0.0.1') and cfg.get('dbname') == 'shursh_ci', 'Refusing non-CI database'
    with psycopg.connect(dsn, autocommit=True) as con:
        con.execute('CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS; CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY)')
        for migration in sorted((ROOT/'supabase/migrations').glob('*.sql')):
            con.execute(migration.read_text())
        for uid in IDS.values():
            con.execute('INSERT INTO auth.users(id) VALUES(%s)', (uid,))
    yield

@pytest.fixture
def application(monkeypatch):
    from app import app
    from cloud import auth
    from server import ApiError
    def provider(action, **data):
        if action == 'register':
            return {'user': {'id': str(IDS['owner@example.test'])}}
        if data['password'] != 'valid-password' or data['email'] not in IDS:
            raise ApiError(401, 'Invalid credentials')
        return {'access_token': 'not-a-real-token', 'user': {'id': str(IDS[data['email']]),
                'email': data['email'], 'email_confirmed_at':'2026-01-01T00:00:00Z',
                'user_metadata': {'name': 'Owner' if data['email'].startswith('owner') else 'Other'}}}
    monkeypatch.setattr(auth,'auth_request',provider)
    # Remove only ephemeral test rate records; never touch hosted Supabase.
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('DELETE FROM public.app_rate_limits')
    return app

def call(client, method, path, body=None, status=200, **kwargs):
    res = client.open(path, method=method, base_url=BASE, json=body, **kwargs)
    assert res.status_code == status, (method,path,res.status_code,res.get_data(as_text=True))
    return res

def login(app, email='owner@example.test'):
    c=app.test_client()
    call(c,'POST','/api/login',{'email':email,'password':'valid-password'})
    return c

def make_list(c):
    lid=call(c,'POST','/api/lists',{'title':'Test list'},201).json['id']
    wid=call(c,'POST',f'/api/lists/{lid}/wishes',{'title':'Gift'},201).json['id']
    key=call(c,'GET',f'/api/lists/{lid}').json['list']['share_key']
    return lid,wid,key

def test_game_ui_script_is_served_by_flask(application):
    result=application.test_client().get('/santa-ui.js')
    assert result.status_code==200
    assert b'gameGiftModal' in result.data
    assert result.headers.get('X-Content-Type-Options')=='nosniff'


@pytest.mark.performance
def test_authenticated_api_latency_baseline(application):
    """Disposable CI PostgreSQL only; not a hosted Vercel/Supabase benchmark."""
    import json
    import re
    from statistics import median
    from time import perf_counter
    client=application.test_client()
    logged=client.post('/api/login',base_url=BASE,json={'email':'owner@example.test','password':'valid-password'})
    assert logged.status_code == 200
    samples={}
    for endpoint in ('/api/me','/api/dashboard','/api/lists','/api/santas'):
        values=[]
        for _ in range(12):
            before=perf_counter()
            r=client.get(endpoint,base_url=BASE)
            wall_ms=(perf_counter()-before)*1000
            assert r.status_code==200
            timing=r.headers.get('Server-Timing','')
            app_ms=re.search(r'app;dur=([0-9.]+)',timing)
            conn_ms=re.search(r'db-connect;dur=([0-9.]+)',timing)
            sql_ms=re.search(r'sql-exec;dur=([0-9.]+);desc="([0-9]+) statement\(s\)"',timing)
            assert app_ms and conn_ms and sql_ms and 'region;desc=' in timing
            assert int(sql_ms.group(2)) > 0
            assert 'SELECT ' not in timing and 'owner@example.test' not in timing
            values.append({'wall':round(wall_ms,2),
                           'app':float(app_ms.group(1)),
                           'dbConnect':float(conn_ms.group(1)),
                           'sqlExec':float(sql_ms.group(1)),
                           'sqlStatements':int(sql_ms.group(2))})
        samples[endpoint]={
            'n':len(values),
            'wallP50':round(median(v['wall'] for v in values),2),
            'wallP95':round(sorted(v['wall'] for v in values)[10],2),
            'appP50':round(median(v['app'] for v in values),2),
            'dbConnectP50':round(median(v['dbConnect'] for v in values),2),
            'dbConnectMax':round(max(v['dbConnect'] for v in values),2),
            'sqlExecP50':round(median(v['sqlExec'] for v in values),2),
            'sqlStatementsP50':median(v['sqlStatements'] for v in values)}
    # Explicit scope prevents conflating these numbers with cross-region latency.
    print('SHURSH_CI_PERF=' + json.dumps({'scope':'CI-local-PostgreSQL-mocked-Auth',
        'unit':'ms', 'endpoints':samples},sort_keys=True))


def test_bounded_pool_reuse_and_independent_nested_transaction(application):
    from cloud import db
    dsn=os.environ['SHURSH_DATABASE_URL']
    pool=db._pool_for(dsn)
    assert pool.max_size==4
    seen=[]
    for _ in range(12):
        with db.transaction() as con:
            seen.append(con.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'])
    assert len(set(seen)) <= pool.max_size
    assert len(set(seen)) < len(seen), 'Warm workers should reuse sockets'
    with application.test_request_context('/api/test'):
        with db.transaction(write=True) as main_con:
            outer=main_con.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
            with db.transaction(write=True,rate_limit=True) as rate_con:
                inner=rate_con.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
                assert inner != outer, 'Nested rate limiter must use independent socket'


def test_auth_releases_db_connection_before_upstream(application, monkeypatch):
    from cloud import auth
    from flask import g
    provider=auth.auth_request
    checked=[]
    def assert_no_reserved_connection(action, **kwargs):
        checked.append(getattr(g, 'shursh_db_connection', None) is None)
        return provider(action, **kwargs)
    monkeypatch.setattr(auth, 'auth_request', assert_no_reserved_connection)
    client=application.test_client()
    response=client.post('/api/login',base_url=BASE,
        json={'email':'owner@example.test','password':'valid-password'})
    assert response.status_code==200
    assert checked==[True], 'Network authentication must not reserve a DB socket'
    assert client.get('/api/me',base_url=BASE).json['user']['email']=='owner@example.test'
    assert client.post('/api/logout',base_url=BASE,json={}).status_code==200



def test_auth_input_validation_rejects_bad_data_before_upstream(application, monkeypatch):
    """Protect the auth boundary even when JavaScript validation is bypassed."""
    from cloud import auth
    from cloud.backend import valid_auth_email, valid_auth_password, valid_signup_name
    from server import ApiError

    assert valid_auth_email(' Name+tag@Example.COM ') == 'name+tag@example.com'
    for address in ('a_b-c.d+tag@example.com', 'a!b@example.com', '#user@example.com', 'name+tag@gmail.com', 'first.last+tag@gmail.com', 'user@xn--e1afmkfd.xn--p1ai'):
        assert valid_auth_email(address)==address
    assert valid_signup_name('  Анна  ') == 'Анна'
    assert valid_auth_password('secure-passphrase') == 'secure-passphrase'
    assert valid_auth_password('legacy-Ёж') == 'legacy-Ёж'
    for address in ('x', 'john..doe@example.com', 'a@-example.com',
                    'a@example.c', 'a@domain..com', 'demo@shursh.local'):
        with pytest.raises(ApiError):
            valid_auth_email(address)
    for address,message in (
        ('invalid','Добавь знак @'),
        ('почта','Перед @ используй латинские буквы, цифры и допустимые знаки'),
        ('почта@','Перед @ используй латинские буквы, цифры и допустимые знаки'),
        ('a..b','Исправь точки в части почты перед @'),
        ('a.@','Исправь точки в части почты перед @'),
        ('a@@example.com','В адресе должен быть только один знак @'),
        ('@example.com','Укажи имя почты перед @'),
        ('a@','Укажи домен после @'),
        ('a@example','Укажи домен с точкой, например example.com'),
        ('12@mail.','Допиши окончание домена, например ru или com'),
        ('12@#mail','Убери символ # из домена'),
        ('12@#mail.com','Убери символ # из домена'),
        ('#username@gmail.com','Убери символ # из имени почты Gmail'),
        ('user_name@googlemail.com','Убери символ _ из имени почты Gmail'),
        ('+tag@gmail.com','Укажи имя почты Gmail перед +'),
        ('a@mail..','Убери лишние точки в домене'),
        ('a@.mail','Убери лишние точки в домене'),
        ('a@domain..com','Убери лишние точки в домене'),
        ('a@-example.com','Домен не должен начинаться или заканчиваться дефисом'),
        ('a@example.c','Проверь окончание домена, например .ru или .com'),
        ("a b@example.com","Убери пробелы из адреса"),
        ("user,name@example.com","Убери запятую из адреса"),
        ("user@example,com","Убери запятую из адреса"),
        ("\"user\"@example.com","Убери двойные кавычки из адреса"),
        ("user(name)@example.com","Убери скобки из адреса"),
        ("user:name@example.com","Убери двоеточие из адреса"),
        ("user;name@example.com","Убери точку с запятой из адреса"),
        ("user\\name@example.com","Убери обратную косую черту из адреса"),
        ("почта@78.yy","Перед @ используй латинские буквы, цифры и допустимые знаки"),
        ("user@почта.ru","Используй латинские буквы после @"),
        ("h@h.ю","Используй латинские буквы после @"),
        ("user@foo_bar.ru","Убери нижнее подчёркивание из домена"),
        ("user@example.123","Проверь окончание домена, например .ru или .com")):
        with pytest.raises(ApiError) as exc:
            valid_auth_email(address)
        assert exc.value.message==message
    for name in ('', '    ', 'a' * 41, 'ok\nInjected'):
        with pytest.raises(ApiError):
            valid_signup_name(name)

    def unexpected_upstream(*args, **kwargs):
        raise AssertionError('Malformed credentials reached upstream Auth')
    monkeypatch.setattr(auth, 'auth_request', unexpected_upstream)
    client=application.test_client()
    attempts=[
        ('/api/register',{'name':'','email':'good@example.com','password':'valid-password'}),
        ('/api/register',{'name':'Гость','email':'not-an-email','password':'valid-password'}),
        ('/api/register',{'name':'Гость','email':'good@example.com','password':'short'}),
        ('/api/register',{'name':'Гость','email':'good@example.com','password':'abcdefgЁ'}),
        ('/api/register',{'name':'bad\nname','email':'good@example.com','password':'valid-password'}),
        ('/api/login',{'email':'invalid','password':'valid-password'}),
        ('/api/login',{'email':'good@example.com','password':'short'}),
    ]
    for path,payload in attempts:
        response=client.post(path,base_url=BASE,json=payload)
        assert response.status_code==400,(path,response.status_code)
        assert 'Set-Cookie' not in response.headers
        assert response.json.get('error')


@pytest.mark.browser
def test_browser_auth_inline_validation_and_password_confirmation(browser_http):
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as play:
        for engine in (play.chromium,):
            browser=engine.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':390,'height':844})
                posts=[]
                page.on('request',lambda req: posts.append(req.url.rsplit('/',1)[-1])
                        if req.method=='POST' and req.url.endswith(('/api/login','/api/register')) else None)
                page.goto(browser_http+'/')
                page.locator('header [data-open="login"]').click()
                page.locator('.modal-fixed-footer [data-open="register"]').click()
                expect(page.locator('#fld-confirm_password')).to_be_visible()
                # Fresh modal, first edit: no blur or submit before error.
                email=page.locator('#fld-email')
                email.fill('h@h.ю')
                expect(email).to_have_value('h@h.ю')
                expect(email).to_be_focused()
                expect(email).to_have_attribute('aria-invalid','true')
                expect(page.locator('#auth-error-email')).to_have_text('Используй латинские буквы после @')
                overlay=page.locator('.auth-character-input-row .auth-character-overlay')
                expect(overlay).to_be_visible()
                assert overlay.evaluate("(c)=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).some((v,i)=>i%4===3&&v>0)")
                expect(overlay).to_have_attribute('aria-hidden','true')
                email.fill('user,name@example.com')
                expect(overlay).to_be_visible()
                expect(page.locator('#auth-error-email')).to_have_text('Убери запятую из адреса')
                email.fill('user@example.test')
                expect(page.locator('#auth-error-email')).to_be_hidden()
                expect(overlay).to_be_hidden()
                assert email.get_attribute('aria-invalid') is None
                email.fill('')
                page.locator('.modal-fixed-footer [type=submit]').click()
                expect(page.locator('#auth-error-name')).to_have_text('Укажи имя')
                expect(page.locator('#auth-error-email')).to_have_text('Укажи почту')
                expect(page.locator('#auth-error-password')).to_have_text('Введи пароль')
                expect(page.locator('#auth-error-confirm_password')).to_have_text('Повтори пароль')
                assert page.locator('#fld-email').get_attribute('aria-invalid')=='true'
                assert not posts, 'Invalid form must not call Auth API'

                page.locator('#fld-name').fill('Анна')
                page.locator('#fld-email').fill('not-email')
                page.locator('#fld-password').fill('short')
                page.locator('#fld-confirm_password').fill('different')
                page.locator('.modal-fixed-footer [type=submit]').click()
                expect(page.locator('#auth-error-email')).to_have_text('Добавь знак @')
                expect(page.locator('#auth-error-password')).to_have_text('Добавь ещё 3 символа')
                expect(page.locator('#password-hint')).to_have_text('Подходящие варианты от 8 символов, например:')
                expect(page.locator('[data-password-suggestions] button:visible').first).to_be_visible()
                expect(page.locator('#auth-error-confirm_password')).to_have_text('Пароли не совпадают')
                assert not posts

                for address,message in (
                    ('a@@example.com','В адресе должен быть только один знак @'),
                    ('@example.com','Укажи имя почты перед @'),
                    ('a@','Укажи домен после @'),
                    ('a@example','Укажи домен с точкой, например example.com'),
                    ('12@mail.','Допиши окончание домена, например ru или com'),
                    ('12@#mail','Убери символ # из домена'),
                    ('12@#mail.com','Убери символ # из домена'),
                    ('#username@gmail.com','Убери символ # из имени почты Gmail'),
                    ('user_name@googlemail.com','Убери символ _ из имени почты Gmail'),
                    ('+tag@gmail.com','Укажи имя почты Gmail перед +'),
                    ('a@mail..','Убери лишние точки в домене'),
                    ('a@.mail','Убери лишние точки в домене'),
                    ('a@domain..com','Убери лишние точки в домене'),
                    ('a@-example.com','Домен не должен начинаться или заканчиваться дефисом'),
                    ('a@example.c','Проверь окончание домена, например .ru или .com'),
                    ("a b@example.com","Убери пробелы из адреса"),
                    ("user,name@example.com","Убери запятую из адреса"),
                    ("user@example,com","Убери запятую из адреса"),
                    ("\"user\"@example.com","Убери двойные кавычки из адреса"),
                    ("user(name)@example.com","Убери скобки из адреса"),
                    ("user:name@example.com","Убери двоеточие из адреса"),
                    ("user;name@example.com","Убери точку с запятой из адреса"),
                    ("user\\name@example.com","Убери обратную косую черту из адреса"),
                    ("почта@78.yy","Перед @ используй латинские буквы, цифры и допустимые знаки"),
                    ("user@почта.ru","Используй латинские буквы после @"),
                    ("user@foo_bar.ru","Убери нижнее подчёркивание из домена"),
                    ("user@example.123","Проверь окончание домена, например .ru или .com")):
                    page.locator('#fld-email').fill(address)
                    expect(page.locator('#auth-error-email')).to_have_text(message)
                page.locator('#fld-email').fill('OWNER@EXAMPLE.TEST')
                page.locator('#fld-password').fill('abcdefgh1')
                expect(page.locator('#auth-error-password')).to_be_hidden()
                expect(page.locator('[data-password-strength-label]')).to_have_text('Слабый')
                expect(page.locator('#password-hint')).to_contain_text('Добавь хотя бы 1 заглавную латинскую букву и 1 спецсимвол, чтобы усилить пароль')
                for invalid in ('abcdefgя','abcdefgЁ','я'):
                    page.locator('#fld-password').fill(invalid)
                    expect(page.locator('#auth-error-password')).to_have_text('Убери русские буквы из пароля')
                    expect(page.locator('[data-password-strength-label]')).to_have_text('Не подходит')
                    assert not posts
                password=page.locator('#fld-password')
                toggle=page.locator('.password-field:has(#fld-password) [data-password-visibility]')
                overlay=page.locator('.password-field:has(#fld-password) .auth-character-overlay')
                password.fill('abЁcd123')
                expect(overlay).to_have_count(0)
                toggle.click()
                expect(overlay).to_be_visible()
                assert overlay.evaluate("(c)=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).some((v,i)=>i%4===3&&v>0)")
                assert password.input_value()=='abЁcd123'
                toggle.click()
                expect(overlay).to_be_hidden()
                assert overlay.evaluate('(c)=>c.width===0 && c.height===0')
                toggle.click()
                expect(overlay).to_be_visible()
                password.fill('abcd1234')
                expect(overlay).to_be_hidden()
                page.locator('#fld-password').fill('qvR!NtMkY@pLW')
                expect(page.locator('[data-password-strength-label]')).to_have_text(__import__('re').compile('^(Хороший|Надёжный)$'))
                expect(page.locator('#auth-error-password')).to_be_hidden()
                page.locator('#fld-password').fill('9!x'+'7'*35)
                expect(page.locator('#auth-error-password')).to_be_hidden()
                expect(page.locator('[data-password-strength-label]')).not_to_have_text('Не подходит')
                page.locator('[data-password-generate]').click()
                generated=page.locator('#fld-password').input_value()
                assert generated==page.locator('#fld-confirm_password').input_value()
                expect(page.locator('[data-password-strength-label]')).to_have_text('Надёжный')
                page.locator('.password-field:has(#fld-confirm_password) [data-password-visibility]').click()
                expect(page.locator('#fld-confirm_password')).to_have_attribute('type','text')
                page.locator('.password-field:has(#fld-confirm_password) [data-password-visibility]').click()
                expect(page.locator('#fld-confirm_password')).to_have_attribute('type','password')
                page.locator('#fld-password').fill('abcdefgh1')
                expect(page.locator('#password-hint')).not_to_contain_text('Пароль создан и повторён')
                page.locator('#fld-confirm_password').fill('abcdefgh1')
                expect(page.locator('#auth-error-email')).to_be_hidden()
                page.locator('.modal-fixed-footer [type=submit]').click()
                expect(page.get_by_role('dialog')).to_contain_text('Проверь почту',timeout=10000)
                assert posts==['register']
                dialog=page.get_by_role('dialog')
                expect(dialog).to_contain_text('Если аккаунт уже есть')
                expect(dialog).not_to_contain_text('Письмо с подтверждением отправлено!')
                dialog.locator('[data-open="login"]').click()
                expect(page.locator('#fld-email')).to_have_value('owner@example.test')
                page.locator('#fld-password').fill('valid-password')
                page.route('**/api/login', lambda route: route.fulfill(
                    status=401, json={'error':'Неверная почта или пароль'}))
                page.locator('.modal-fixed-footer [type=submit]').click()
                expect(dialog.locator('.auth-form-warning')).to_have_text('Неверная почта или пароль')
                expect(dialog).to_be_visible()
                assert page.locator('.toast').count()==0
                page.unroute('**/api/login')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                page.close()
            finally:
                browser.close()


def test_auth_and_session(application):
    c=application.test_client()
    assert call(c,'GET','/api/me').json == {'user':None,'demo':False}
    guest_dashboard=call(c,'GET','/api/dashboard')
    assert guest_dashboard.json == {'user':None,'demo':False,'lists':[],'events':[]}
    assert 'db-connect;dur=0.0' in guest_dashboard.headers['Server-Timing']
    assert 'sql-exec;dur=0.0;desc="0 statement(s)"' in guest_dashboard.headers['Server-Timing']
    call(c,'GET','/api/lists',status=401)
    call(c,'POST','/api/login',{'email':'owner@example.test','password':'bad-password'},401)
    r=call(c,'POST','/api/register',{'email':'owner@example.test','name':'Owner','password':'Valid-new-password7'},202)
    assert r.json['pending_confirmation'] and 'Set-Cookie' not in r.headers
    r=call(c,'POST','/api/login',{'email':'owner@example.test','password':'valid-password'})
    cookie=r.headers['Set-Cookie']; assert all(s in cookie for s in ('HttpOnly','Secure','SameSite=Lax'))
    assert 'not-a-real-token' not in r.get_data(as_text=True)
    assert call(c,'GET','/api/me').json['user']['id']==str(IDS['owner@example.test'])
    owner_dashboard=call(c,'GET','/api/dashboard')
    assert owner_dashboard.json['user']['id']==str(IDS['owner@example.test'])
    assert 'db-connect;dur=' in owner_dashboard.headers['Server-Timing']
    # A rate-limit transaction and the owner data read share one connection.
    assert 'desc="1 connection(s)"' in owner_dashboard.headers['Server-Timing']
    assert 'desc="1 connection(s)"' in call(c,'GET','/api/lists').headers['Server-Timing']
    call(c,'POST','/api/lists',{'title':'CSRF'},403,headers={'Origin':'https://evil.example'})
    call(c,'POST','/api/logout',{})
    assert call(c,'GET','/api/me').json['user'] is None
    call(c,'POST','/api/demo-login',{},404)


def test_booking_isolation_and_private_images(application):
    c=login(application); other=login(application,'other@example.test'); guest=application.test_client()
    lid,wid,key=make_list(c)
    summary=call(c,'GET','/api/dashboard').json
    assert len(summary['lists'])==1 and summary['lists'][0]['id']==lid
    assert call(other,'GET','/api/dashboard').json['lists']==[]
    for method,path,body in [('GET',f'/api/lists/{lid}',None),('PATCH',f'/api/lists/{lid}',{'title':'Stolen'}),('DELETE',f'/api/wishes/{wid}',None)]:
        call(other,method,path,body,404)
    call(c,'PATCH',f'/api/wishes/{wid}',{'image_data':PNG})
    path=call(c,'GET',f'/api/lists/{lid}').json['wishes'][0]['image_path']
    call(guest,'GET',path)
    reserve=f'/api/public/{key}/reserve/{wid}'
    call(c,'POST',reserve,{'guest_name':'Owner'},403)
    call(guest,'POST',reserve,{},401)
    call(guest,'DELETE',reserve,status=401)
    # Concurrent authenticated requests preserve the one-active-reservation invariant.
    clients=[login(application,'other@example.test') for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(lambda client: client.post(reserve,base_url=BASE,json={}),clients))
    assert sorted(r.status_code for r in responses)==[201]+[409]*5
    assert all('manage_token' not in r.json for r in responses)
    public=call(guest,'GET',f'/api/public/{key}').json['wishes'][0]
    assert public['reserved'] is True and public['reserved_by_me'] is False
    assert call(other,'GET',f'/api/public/{key}').json['wishes'][0]['reserved_by_me'] is True
    assert 'reserved' not in call(c,'GET',f'/api/public/{key}').json['wishes'][0]
    assert 'reserved_by_me' not in call(c,'GET',f'/api/public/{key}').json['wishes'][0]
    assert 'reserved' not in call(c,'GET',f'/api/lists/{lid}').json['wishes'][0]
    call(c,'DELETE',reserve,status=403)
    call(other,'DELETE',reserve)
    call(other,'DELETE',reserve,status=409)
    call(c,'PATCH',f'/api/lists/{lid}',{'visibility':'private'})
    call(guest,'GET',f'/api/public/{key}',status=404)
    call(guest,'GET',path,status=404)
    call(other,'GET',path,status=404)
    call(c,'GET',path)
    call(c,'DELETE',f'/api/wishes/{wid}')
    call(c,'GET',path,status=404)


def test_santa_atomic_draw_and_isolation(application):
    c=login(application); other=login(application,'other@example.test')
    eid=call(c,'POST','/api/santas',{'title':'Game'},201).json['id']
    key=call(c,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    call(other,'GET',f'/api/santas/{eid}',status=404)
    guests=[]
    for name in ['A','B','C']:
        guest=application.test_client()
        t=call(c,'POST',f'/api/santas/{eid}/participants',{'name':name},201).json['participant_token']
        call(guest,'POST',f'/api/participant/{t}/wishes',{'title':name+' gift'},201)
        guests.append((guest,t,name))
    people={p['name']:p['id'] for p in call(c,'GET',f'/api/santas/{eid}').json['participants']}
    for name in ['B','C','Owner']:
        call(c,'POST',f'/api/santas/{eid}/exclusions',{'giver_id':people['A'],'receiver_id':people[name]},201)
    call(c,'POST',f'/api/santas/{eid}/draw',{},409)
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        assert con.execute('SELECT count(*) FROM public.assignments WHERE event_id=%s',(eid,)).fetchone()[0]==0
    call(c,'DELETE',f'/api/santas/{eid}/exclusions/{people["A"]}/{people["B"]}')
    cookie=c.get_cookie('shursh_sid',domain='localhost').value
    def draw(_):
        client=application.test_client();client.set_cookie('shursh_sid',cookie,domain='localhost')
        return client.post(f'/api/santas/{eid}/draw',base_url=BASE,json={})
    with ThreadPoolExecutor(max_workers=5) as pool:
        draws=list(pool.map(draw,range(5)))
    assert all(r.status_code==200 for r in draws), [r.status_code for r in draws]
    assert sum(not r.json['already_drawn'] for r in draws)==1
    call(c,'DELETE',f'/api/santas/{eid}/participants/{people["A"]}',status=409)
    call(other,'POST',f'/api/santas/{eid}/draw',{},404)
    call(application.test_client(),'POST',f'/api/invites/{key}/join',{'name':'Late'},401)
    for guest,t,name in guests:
        assert call(guest,'GET',f'/api/participant/{t}').json['assignment']=={'revealed':False}
        r=call(guest,'POST',f'/api/participant/{t}/reveal',{}).json['assignment']
        assert r['revealed'] and r['receiver_name']!=name
        if name=='A': assert r['receiver_name']=='B'
    game=call(c,'GET',f'/api/santas/{eid}').json
    assert game['my_assignment']=={'revealed':False} and 'assignments' not in game
    assert game['my_wishes']==[]


def test_cloud_santa_management_and_wishlist_import(application):
    """PostgreSQL checks: owner isolation, personal invitations and no self-join."""
    owner=login(application)
    other=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Вечеринка'},201).json['id']
    game=call(owner,'GET',f'/api/santas/{eid}').json
    invite=game['event']['invite_key']
    assert call(owner,'GET',f'/api/invites/{invite}').json['already_joined'] is True
    assert call(other,'GET',f'/api/invites/{invite}').json['already_joined'] is False
    call(owner,'POST',f'/api/invites/{invite}/join',{'name':'Подменённое имя'},409)
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Owner'},409)
    call(other,'POST',f'/api/santas/{eid}/participants',{'name':'Guest'},404)

    created=call(owner,'POST',f'/api/santas/{eid}/participants',
                 {'name':'Игрок 1'},201).json
    original=created['participant_token']
    assert call(application.test_client(),'GET',f'/api/participant/{original}').json['participant']['name']=='Игрок 1'
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'ИГРОК 1'},409)
    call(other,'POST',f'/api/invites/{invite}/join',
         {'name':'игрок 1'},409)
    new=call(owner,'POST',f'/api/santas/{eid}/participants/{created["id"]}/new-link',
             {},200).json['participant_token']
    call(application.test_client(),'GET',f'/api/participant/{original}',status=404)
    assert call(application.test_client(),'GET',f'/api/participant/{new}').json['participant']['name']=='Игрок 1'

    call(owner,'PATCH',f'/api/santas/{eid}',
         {'exchange_date':'2027-01-14','budget':2000})
    call(other,'PATCH',f'/api/santas/{eid}',{'budget':4000},404)
    call(owner,'PATCH',f'/api/santas/{eid}',{'exchange_date':'2027-02-30'},400)
    updated=call(owner,'GET',f'/api/santas/{eid}').json['event']
    assert updated['exchange_date']=='2027-01-14'
    assert updated['budget_cents']==200000

    list_id=call(owner,'POST','/api/lists',{'title':'Подарки участника'},201).json['id']
    a=call(owner,'POST',f'/api/lists/{list_id}/wishes',
           {'title':'Подарок из моего списка'},201).json['id']
    b=call(owner,'POST',f'/api/lists/{list_id}/wishes',
           {'title':'Ещё один подарок'},201).json['id']
    import_api=f'/api/santas/{eid}/my-wishes/import'
    r=call(owner,'POST',import_api,
           {'list_id':list_id,'wish_ids':[a,b]}).json
    assert r['added']==2 and r['snapshot'] is True
    assert call(owner,'POST',import_api,{'list_id':list_id}).json['added']==0
    call(owner,'POST',import_api,{'list_id':list_id,'wish_ids':[123456789]},400)
    call(other,'POST',import_api,{'list_id':list_id},404)
    assert len(call(owner,'GET',f'/api/santas/{eid}').json['my_wishes'])==2
    call(application.test_client(),'POST',f'/api/participant/{new}/wishes/import',
         {'list_id':list_id},401)
    r=call(owner,'POST',f'/api/participant/{new}/wishes/import',
           {'list_id':list_id,'wish_ids':[a]}).json
    assert r['added']==1
    assert call(application.test_client(),'GET',f'/api/participant/{new}').json['wishes'][0]['title']=='Подарок из моего списка'

    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Игрок 2'},201)
    call(owner,'POST',f'/api/santas/{eid}/draw',{},200)
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Поздний'},409)
    call(owner,'PATCH',f'/api/santas/{eid}',{'budget':2500},200)
    assert call(owner,'GET',f'/api/santas/{eid}').json['event']['budget_cents']==250000


def test_permissions_and_rollback(application):
    from cloud import db
    dsn=os.environ['SHURSH_DATABASE_URL']
    for role in ['anon','authenticated']:
        with psycopg.connect(dsn) as con:
            con.execute('SET LOCAL ROLE '+role)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                con.execute('SELECT * FROM public.assignments')
            con.rollback()
    login(application)
    with pytest.raises(RuntimeError):
        with db.transaction(write=True) as con:
            con.execute('INSERT INTO wishlists(owner_id,title,share_key) VALUES(?,?,?)',(IDS['owner@example.test'],'rollback','r'*43))
            raise RuntimeError('exercise rollback')
    with psycopg.connect(dsn) as con:
        assert con.execute("SELECT count(*) FROM public.wishlists WHERE share_key=%s",('r'*43,)).fetchone()[0]==0
    c=application.test_client()
    assert call(c,'GET','/').headers['Referrer-Policy']=='no-referrer'
    call(c,'GET','/shursh-preview.html',status=404)
    call(c,'GET','/server.py',status=404)


def test_direct_browser_links_and_api_errors(application):
    owner=login(application)
    guest=application.test_client()
    lid,wid,key=make_list(owner)
    eid=call(owner,'POST','/api/santas',{'title':'Deep links'},201).json['id']
    invite=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    participant=call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Guest'},201).json['participant_token']
    # Legacy bearer routes stay addressable for pre-existing bookings,
    # but anonymous users can no longer create new reservations.
    call(guest,'POST',f'/api/public/{key}/reserve/{wid}',{},401)
    from server import token, token_hash
    reservation=token()
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute("""INSERT INTO public.reservations(wish_id,guest_name,manage_hash)
                       VALUES (%s,%s,%s)""",(wid,'Guest',token_hash(reservation)))
    for path in ['/', '/lists', '/santas', f'/list/{lid}', f'/santa/{eid}',
                 f'/w/{key}', f'/join/{invite}', f'/p/{participant}', f'/r/{reservation}']:
        page=call(guest,'GET',path)
        assert 'text/html' in page.content_type
        assert re.search(r'src="/ui/[a-f0-9]{20}/app\.js"',page.get_data(as_text=True))
        assert page.headers['Cache-Control']=='no-store'
    for path in ['/join/', '/join/../../server.py', '/list/abc', '/cloud/auth.py', '/.env.example']:
        call(guest,'GET',path,status=404)
    for invalid in [42, [], 'http://[invalid', 'https://example.org:invalid', 'https://user:pass@example.org']:
        call(owner,'POST',f'/api/lists/{lid}/wishes',{'title':'Invalid','shop_url':invalid},400)
    call(owner,'POST','/api/lists',{'title':'invalid\u0000title'},400)
    call(owner,'POST','/api/lists',{'title':'valid','description':[]},400)
    assert len(call(owner,'GET',f'/api/lists/{lid}').json['wishes'])==1


def test_session_cookie_rotation_and_expiry(application):
    from server import token_hash
    client=login(application)
    first=client.get_cookie('shursh_sid',domain='localhost').value
    call(client,'POST','/api/login',{'email':'owner@example.test','password':'valid-password'})
    second=client.get_cookie('shursh_sid',domain='localhost').value
    assert first!=second
    replay=application.test_client()
    replay.set_cookie('shursh_sid',first,domain='localhost')
    assert call(replay,'GET','/api/me').json['user'] is None
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('UPDATE public.app_sessions SET expires_at=0 WHERE token_hash=%s',(token_hash(second),))
    assert call(client,'GET','/api/me').json['user'] is None
    call(client,'GET','/api/lists',status=401)

# Browser E2E: Chrome against the real Flask API and a disposable PostgreSQL DB.
# External Supabase Auth is mocked here; live provider/email requires a separate test.
import re
import threading
from uuid import uuid4

@pytest.fixture
def browser_http(application):
    from werkzeug.serving import make_server, WSGIRequestHandler
    class PrivateTestHandler(WSGIRequestHandler):
        # Guest invitation/reservation URLs are bearer capabilities. Never put
        # their raw paths in public CI logs, including failed test output.
        def log_request(self, code='-', size='-'):
            pass
    server = make_server('127.0.0.1', 0, application, threaded=True,
                         request_handler=PrivateTestHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://localhost:{server.server_port}'
    finally:
        server.shutdown()
        worker.join(timeout=5)


def browser_login(page, email='owner@example.test', landing='dashboard'):
    from playwright.sync_api import expect
    page.locator('header button[data-open="login"]').click()
    page.locator('#fld-email').fill(email)
    # Regression: an old 10 ms deferred modal autofocus stole focus from
    # the password field during fast typing. Type like a human and assert
    # the value before submit, without exposing credentials in CI output.
    password=page.locator('#fld-password')
    password.press_sequentially('valid-password', delay=2)
    expect(password).to_have_value('valid-password')
    # A previous CI flake never sent the POST because native form validation
    # prevented submission. Detect this at the point of failure; never dump
    # field values, email, credentials or cookies into CI logs.
    validity=page.evaluate("""() => ({
      formValid: document.querySelector('#modal-form').checkValidity(),
      invalid: [...document.querySelectorAll('#modal-form input')]
        .filter(input => !input.checkValidity())
        .map(input => ({
          name: input.name, type: input.type, length: input.value.length,
          required: input.required, tooShort: input.validity.tooShort,
          tooLong: input.validity.tooLong, typeMismatch: input.validity.typeMismatch,
          valueMissing: input.validity.valueMissing
        }))
    })""")
    assert validity['formValid'], f'Browser login form invalid before submit: {validity["invalid"]}'
    # Distinguish no submit, pending request, HTTP error and render regression.
    # Diagnostics intentionally omit email, password, cookies, and URLs.
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    sent=[]
    page.on('request',lambda r: sent.append('sent') if r.url.endswith('/api/login') and r.method=='POST' else None)
    try:
        with page.expect_response(lambda r: r.url.endswith('/api/login') and r.request.method == 'POST', timeout=20000) as result:
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
        response=result.value
    except PlaywrightTimeout as exc:
        fields=page.evaluate("""() => [...document.querySelectorAll('#modal-form input')].map(el=>({
          type:el.type, name:el.name, valid:el.checkValidity(),
          valueLength:el.value.length, required:el.required,
          missing:el.validity.valueMissing, typeMismatch:el.validity.typeMismatch,
          tooShort:el.validity.tooShort, tooLong:el.validity.tooLong,
          badInput:el.validity.badInput, customError:el.validity.customError
        }))""")
        disabled=page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').is_disabled() if page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').count() else None
        raise AssertionError(f'Login timed out: request_sent={bool(sent)}, field_constraints={fields}, submit_disabled={disabled}') from exc
    native=bool(response.request.is_navigation_request())
    assert response.status==(303 if native else 200), (
        f'Login HTTP {response.status}; '
        f'Server-Timing: {response.headers.get("server-timing", "missing")}')
    if landing=='invite':
        expect(page.locator('#join-form')).to_be_visible(timeout=15000)
    elif landing=='friend_invite':
        expect(page.locator('[data-social-action="invite-add"]')).to_be_visible(timeout=15000)
    elif landing=='identity':
        expect(page.locator('.dashboard-page')).to_be_visible(timeout=15000)
    else:
        expect(page.locator('.dashboard-page h1')).to_contain_text(
            'Owner' if email.startswith('owner') else 'Other', timeout=15000)
    expect(page.locator('header .header-avatar')).to_be_visible()
    expect(page.get_by_role('dialog')).to_have_count(0)



def test_product_preview_is_disabled_in_manual_link_release(application, monkeypatch):
    from cloud import product_metadata as importer
    monkeypatch.setattr(importer, '_request_public',
                        lambda *args: pytest.fail('Disabled scraper must never fetch'))
    url = 'https://www.ozon.ru/product/lego-classic-30947723/'
    anonymous = application.test_client()
    response = anonymous.post('/api/product-preview', json={'url': url})
    assert response.status_code == 404
    user = login(application)
    response = user.post('/api/product-preview', json={'url': url})
    assert response.status_code == 404
    assert isinstance(call(user, 'GET', '/api/lists').json['lists'], list)



def test_static_product_copy_avoids_sentence_final_periods():
    """All shipped Russian UI copy follows Shursh punctuation; user data is untouched."""
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    ending=re.compile(r"""[А-Яа-яЁё]\.(?=</(?:p|small|h[1-6]|strong|span|div|li|a|button)\b|['"`])""")
    paths=('public/app.js','public/shursh-preview.html','templates/index.html','server.py','app.py','cloud/backend.py')
    for name in paths:
        data=(root/name).read_text(encoding='utf-8')
        assert not ending.search(data), f'Russian text ends in a period: {name}'





def test_site_text_uses_only_short_hyphens_and_calm_confirmation_card():
    """Protect the shipped product copy and onboarding card from regressions."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('public/app.js', 'public/shursh-preview.html',
                 'templates/index.html', 'server.py', 'app.py', 'cloud/backend.py',
                 'DESIGN.md'):
        data = (root / name).read_text(encoding='utf-8')
        assert chr(0x2014) not in data and chr(0x2013) not in data, name
    css = (root / 'public/styles.css').read_text(encoding='utf-8')
    block = css.split('.auth-confirm-card{', 1)[1].split(
        '/* Signed-in home dashboard. */', 1)[0]
    assert '.auth-confirm-card:before' not in block
    assert 'box-shadow:' not in block
    assert 'transform:' not in block
    assert 'border-radius:24px' in block
    assert 'background:#e9f4ec' in block




@pytest.mark.browser
def test_browser_manual_product_link_and_uncluttered_header(browser_http):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 850})
            page.set_default_timeout(15000)
            intercepted = []
            def intercept_import(route):
                intercepted.append(route.request.url)
                route.abort()
            page.route('**/api/product-preview', intercept_import)
            page.goto(browser_http + '/')
            expect(page.locator('main h1')).to_be_visible()
            expect(page.locator('.footer')).to_contain_text('Сделано с заботой о сюрпризах')
            expect(page.locator('.footer')).to_contain_text('Место для хотелок и сюрпризов')
            assert page.locator('header .logo-dot').count()==0
            assert page.locator('header .nav').count()==0, 'Landing must show logo and login only'
            assert page.locator('header button[data-open="login"]').count()==1
            page.locator('.footer-developer').click()
            expect(page.locator('.modal')).to_contain_text('Написать разработчику')
            expect(page.locator('#fld-name')).to_be_visible()
            expect(page.locator('#fld-email')).to_be_visible()
            expect(page.locator('#fld-message')).to_be_visible()
            expect(page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]')).to_contain_text('Отправить')
            page.locator('.modal-close').click()
            assert page.locator('.footer a[href^="mailto:"]').count() == 0
            assert page.locator('header button[data-open="list"]').count() == 0
            browser_login(page)
            assert page.locator('header button[data-nav="/lists"]').count() == 0
            assert page.locator('button[data-action="refresh-owner"]').count() == 0

            page.locator('main button[data-open="list"]').first.click()
            page.locator('#fld-title').fill('Ручные ссылки')
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page.locator('main h1')).to_contain_text('Ручные ссылки')

            url = 'https://www.ozon.ru/product/lego-classic-30947723/'
            page.locator('button[data-open="wish"]').first.click()
            expect(page.locator('[data-import-product]')).to_have_count(0)
            assert page.locator('#fld-shop_url').evaluate(
                "(input) => input.compareDocumentPosition(document.querySelector('#fld-title')) & Node.DOCUMENT_POSITION_FOLLOWING"
            ), 'Shop URL must be before the title field'
            page.locator('#fld-shop_url').fill(url)
            page.wait_for_timeout(950)
            expect(page.locator('#fld-title')).to_have_value('')
            expect(page.locator('#fld-price')).to_have_value('')
            chooser=page.locator('.ui-select-trigger[data-select-id="fld-priority"]')
            expect(chooser).to_have_text('Было бы здорово')
            chooser.click()
            expect(page.locator('.ui-select-menu [role="option"]')).to_have_count(2)
            page.locator('.ui-select-menu [role="option"]').filter(has_text='Очень хочу!').click()
            assert page.locator('#fld-priority').input_value()=='love'
            chooser.focus()
            chooser.press('ArrowUp')
            chooser.press('Enter')
            assert page.locator('#fld-priority').input_value()=='nice'
            assert page.locator('.ui-select-menu').count()==0
            page.locator('#fld-title').fill('Кот и настольная игра')
            page.locator('#fld-price').fill('1299')
            assert page.locator('.modal').evaluate("(el) => getComputedStyle(el).overflowY")=='hidden'
            assert page.locator('.modal-scroll-area').count()==1
            # A manually uploaded image must still work without a scraper.
            from base64 import b64decode
            photo = b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAIAAABvFaqvAAAAIklEQVR4nGN8fWILAzUAE1VMGTVo1KBRg0YNGjVo1CCKAAAYaAKXC2f7qAAAAABJRU5ErkJggg==')
            page.locator('#wish-file').set_input_files({
                'name': 'gift.png', 'mimeType': 'image/png', 'buffer': photo,
            })
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            card = page.locator('.wish-card').filter(has_text='Кот и настольная игра')
            expect(card).to_be_visible()
            expect(card.locator('img')).to_be_visible()
            assert '.webp' in (card.locator('img').get_attribute('src') or '')
            expect(card.locator('a[href]')).to_have_attribute('href', url)
            assert intercepted == [], 'Pasting product links must not trigger parsing'

            card.locator('button[data-action="edit-wish"]').click()
            expect(page.locator('#fld-shop_url')).to_have_value(url)
            expect(page.locator('#fld-price')).to_have_value('1299')
            page.locator('.modal-close').click()
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'mobile overflow'
        finally:
            browser.close()



@pytest.mark.browser
def test_browser_register_wishlist_reservation_and_isolation(browser_http):
    from playwright.sync_api import sync_playwright, expect
    title = 'Playwright список ' + uuid4().hex[:8]
    wish = 'Настольная игра для теста'
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            owner = browser.new_context(viewport={'width': 1366, 'height': 900})
            page = owner.new_page()
            page.set_default_timeout(15000)
            page.goto(browser_http + '/')
            expect(page.locator('main h1')).to_be_visible()

            # Registration and email-confirmation copy in the real UI.
            page.locator('main button[data-open="list"]').first.click()
            expect(page.get_by_role('dialog')).to_contain_text('Давай знакомиться!')
            page.locator('#fld-name').fill('Owner')
            page.locator('#fld-email').fill('owner@example.test')
            page.locator('[data-password-generate]').click()
            generated=page.locator('#fld-password').input_value()
            assert len(generated)==20
            assert re.search(r'[A-Z]',generated) and re.search(r'[a-z]',generated)
            assert re.search(r'[0-9]',generated) and re.search(r'[^A-Za-z0-9]',generated)
            assert page.locator('#fld-password').get_attribute('type')=='text'
            page.locator('.password-field:has(#fld-password) [data-password-visibility]').click()
            assert page.locator('#fld-password').get_attribute('type')=='password'
            page.locator('.password-field:has(#fld-password) [data-password-visibility]').click()
            page.locator('#fld-password').fill('Valid-new-password7')
            page.locator('#fld-confirm_password').fill('Valid-new-password7')
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page.get_by_role('dialog')).to_contain_text('Проверь почту')
            expect(page.locator('.auth-confirm-card')).to_be_visible()
            expect(page.locator('.auth-confirm-card .auth-confirm-symbol .icon')).to_be_visible()
            expect(page.locator('.auth-confirm-card')).to_contain_text('Запрос принят')
            expect(page.get_by_role('dialog')).to_contain_text('owner@example.test')
            assert page.locator('.toast').count()==0, 'No duplicate registration toast'
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => getComputedStyle(el).borderTopLeftRadius === '24px'")
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => getComputedStyle(el).backgroundColor === 'rgb(233, 244, 236)'")
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => getComputedStyle(el).boxShadow === 'none'")
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => ['none', 'normal'].includes(getComputedStyle(el, '::before').content)")
            assert page.locator('.auth-confirm-symbol').evaluate(
                "(el) => getComputedStyle(el).transform === 'none'")
            assert page.locator('.auth-confirm-card p').inner_text().strip().endswith('.') is False
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('.auth-confirm-card')).to_be_visible()
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => getComputedStyle(el).borderTopLeftRadius === '20px'")
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'Mobile horizontal overflow'
            page.set_viewport_size({'width':1366,'height':900})
            expect(page.locator('header .user-name')).to_have_count(0)
            page.locator('[data-close]').click()
            browser_login(page)
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
            assert 'Подарки, о которых' not in page.locator('main').inner_text()
            page.reload()
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
            summary=page.evaluate('''async () => (await (await fetch('/api/dashboard')).json())''')
            assert summary['user']['email']=='owner@example.test'
            assert not any('access_token' in cookie['name'] for cookie in owner.cookies())
            assert any(c['name'] == 'shursh_sid' and c['httpOnly'] and c['secure'] for c in owner.cookies())

            page.locator('main button[data-open="list"]').first.click()
            page.locator('#fld-title').fill(title)
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/list/\d+$'))
            lid = page.url.rsplit('/', 1)[-1]
            expect(page.locator('main h1')).to_have_text(title)

            page.locator('button[data-open="wish"]').first.click()
            page.set_viewport_size({'width':390,'height':700})
            expect(page.locator('.wish-edit-modal .modal-fixed-header')).to_be_visible()
            expect(page.locator('.wish-edit-modal .modal-fixed-footer')).to_be_visible()
            assert page.locator('.modal-fixed-footer button[type="submit"]').get_attribute('form') == 'modal-form'
            positions=page.evaluate("""() => {
              const head=document.querySelector('.modal-fixed-header');
              const foot=document.querySelector('.modal-fixed-footer');
              const scroller=document.querySelector('.wish-edit-modal .modal-scroll-area');
              const initial=[head.getBoundingClientRect().top,foot.getBoundingClientRect().bottom];
              scroller.scrollTop=scroller.scrollHeight;
              const after=[head.getBoundingClientRect().top,foot.getBoundingClientRect().bottom];
              return {initial,after,scrolled:scroller.scrollTop>0,
                      inside:foot.getBoundingClientRect().bottom<=innerHeight+1};
            }""")
            assert positions['scrolled'], 'Long mobile wish form should scroll'
            assert positions['inside'], 'Submit footer must stay inside viewport'
            assert all(abs(a-b)<2 for a,b in zip(positions['initial'],positions['after']))
            page.locator('.wish-edit-modal [data-select-id="fld-priority"]').click()
            popup=page.evaluate("""() => {
              const menu=document.querySelector('.ui-select-menu').getBoundingClientRect();
              const trigger=document.querySelector('[data-select-id="fld-priority"]').getBoundingClientRect();
              return {gap:Math.min(Math.abs(menu.bottom-trigger.top),Math.abs(menu.top-trigger.bottom)),
                      onscreen:menu.top>=0&&menu.bottom<=innerHeight+1};
            }""")
            assert popup['gap']<14 and popup['onscreen'], 'Select popup must touch its anchor'
            page.locator('.ui-select-menu [data-ui-index="1"]').click()
            page.locator('#fld-title').fill(wish)
            page.locator('.modal-fixed-footer button[type="submit"]').click()
            page.set_viewport_size({'width':1366,'height':900})
            expect(page.locator('.wishlist-grid')).to_contain_text(wish)
            # A compact "Очень хочу" badge must never inherit the 125px
            # SVG illustration rule, including on narrow mobile cards.
            badge=page.locator('.wishlist-grid .wish-priority').first
            expect(badge).to_contain_text('Очень хочу')
            for width in (390,768,1366):
                page.set_viewport_size({'width':width,'height':900})
                size=badge.evaluate("""el => {
                    const b=el.getBoundingClientRect();
                    const icon=el.querySelector('svg').getBoundingClientRect();
                    const art=el.closest('.wish-image').querySelector(':scope > svg').getBoundingClientRect();
                    const image=el.closest('.wish-image').getBoundingClientRect();
                    return {badgeWidth:b.width,badgeHeight:b.height,iconWidth:icon.width,
                            iconHeight:icon.height,artWidth:art.width,
                            inside:b.left>=image.left&&b.right<=image.right+1};
                }""")
                assert size['badgeWidth']<165 and size['badgeHeight']<46,(width,size)
                assert size['iconWidth']<=16 and size['iconHeight']<=16,(width,size)
                assert size['artWidth']>=85 and size['inside'],(width,size)
            page.set_viewport_size({'width':1366,'height':900})
            share = page.locator('button[data-action="copy"][data-url*="/w/"]').get_attribute('data-url')
            assert share.startswith(browser_http + '/w/')
            key = share.rsplit('/', 1)[-1]

            guest_ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
            guest = guest_ctx.new_page()
            guest.set_default_timeout(15000)
            guest.goto(share)
            expect(guest.locator('main h1')).to_have_text(title)
            expect(guest.locator('.wishlist-grid')).to_contain_text(wish)
            assert guest.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'Mobile horizontal overflow'
            guest.locator('button[data-action="reserve"]').click()
            expect(guest.get_by_role('dialog')).to_contain_text('Давай знакомиться!')
            assert guest.evaluate("async k => (await fetch('/api/public/'+k)).status",key)==200
            guest.locator('[data-close]').first.click()
            # Login on the same shared list preserves its URL.
            guest.goto(browser_http+'/')
            browser_login(guest,'other@example.test')
            guest.goto(share)
            expect(guest.locator('main h1')).to_have_text(title)
            reserve=guest.locator('.wishlist-grid button[data-action="reserve"]')
            expect(reserve).to_have_text('Забронировать')
            guest.evaluate("""() => {
                window.__wishlistMain=document.querySelector('main');
                window.__wishlistGrid=document.querySelector('.wishlist-grid');
            }""")
            reads=[]
            guest.on('request',lambda req: reads.append(req.url)
                     if req.method=='GET' and req.url==browser_http+'/api/public/'+key else None)
            reserve.click()
            expect(guest).to_have_url(share)
            expect(reserve).to_contain_text('Отменить бронь')
            assert guest.evaluate("""() => window.__wishlistMain===document.querySelector('main')
                && window.__wishlistGrid===document.querySelector('.wishlist-grid')""")
            assert not reads, 'Reservation must not re-fetch the shared wishlist'
            assert guest.locator('#fld-guest_name').count()==0
            assert guest.locator('.modal').count()==0
            assert not guest.evaluate("Object.keys(localStorage).some(k=>k.startsWith('shursh-reservation-v2:'))")
            assert '/r/' not in guest.url

            watcher_ctx = browser.new_context()
            watcher = watcher_ctx.new_page()
            watcher.goto(share)
            expect(watcher.locator('button[data-action="reserve"]')).to_be_disabled()
            assert 'Уже забронировано' in watcher.locator('.wishlist-grid').inner_text()

            # Owner cannot infer a friend's booking from their private view.
            page.goto(browser_http + f'/list/{lid}')
            expect(page.locator('.wishlist-grid')).to_contain_text(wish)
            assert 'Уже забронировано' not in page.locator('.wishlist-grid').inner_text()
            owner_detail = page.evaluate('''async id => (await (await fetch('/api/lists/' + id)).json())''', lid)
            assert 'reserved' not in owner_detail['wishes'][0]

            other_ctx = browser.new_context()
            other = other_ctx.new_page()
            other.goto(browser_http + '/')
            browser_login(other, 'other@example.test')
            assert other.evaluate('''async id => (await fetch('/api/lists/' + id)).status''', lid) == 404
            assert other.evaluate('''async id => (await fetch('/api/public/' + id)).status''', 'not-a-real-key') == 404
            assert owner.cookies() != other_ctx.cookies(), 'Browser sessions must be isolated'
            other_summary=other.evaluate('''async () => (await (await fetch('/api/dashboard')).json())''')
            assert not any(l['id']==int(lid) for l in other_summary['lists'])

            # A second device with the same account can cancel the reservation.
            other.goto(share)
            expect(other.locator('button[data-action="reserve"]')).to_contain_text('Отменить бронь')
            other.locator('button[data-action="reserve"]').click()
            expect(other.locator('button[data-action="reserve"]')).to_contain_text('Забронировать')
            guest.reload()
            expect(guest.locator('button[data-action="reserve"]')).to_contain_text('Забронировать')
            watcher.reload()
            expect(watcher.locator('button[data-action="reserve"]')).to_be_enabled()

            page.locator('button[data-action="edit-list"]').click()
            page.locator('#fld-visibility').select_option('private')
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page.locator('.alert')).to_contain_text('Список приватный')
            assert guest.evaluate('''async k => (await fetch('/api/public/' + k)).status''', key) == 404
            guest.goto(share)
            expect(guest.locator('main')).to_contain_text('Страница не загрузилась')
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_santa_invites_draw_and_private_reveals(browser_http):
    from playwright.sync_api import sync_playwright, expect
    title = 'Санта Playwright ' + uuid4().hex[:8]
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            owner_ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
            owner = owner_ctx.new_page()
            owner.set_default_timeout(15000)
            owner.goto(browser_http + '/')
            browser_login(owner)
            owner.locator('main button[data-open="santa"]').first.click()
            owner.locator('#fld-title').fill(title)
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/santa/\d+$'))
            eid = owner.url.rsplit('/', 1)[-1]
            assert owner.locator('.error-page').count()==0, owner.locator('.error-page p').all_inner_texts()
            invite = owner.locator('input[aria-label="Ссылка-приглашение"]').input_value()
            assert invite.startswith(browser_http + '/join/')

            members = []
            for name, mobile in [('Петя', True), ('Катя', False)]:
                context = browser.new_context(viewport={'width': 390, 'height': 844} if mobile else {'width': 1366, 'height': 900}, is_mobile=mobile)
                guest = context.new_page()
                guest.set_default_timeout(15000)
                # Historical bearer-member E2E uses a pre-created legacy slot.
                # New public joins require a registered account (covered separately).
                issued=owner.evaluate("""async ({id,name}) => {
                    const response=await fetch('/api/santas/'+id+'/participants',{
                      method:'POST',headers:{'Content-Type':'application/json'},
                      body:JSON.stringify({name})});
                    if(!response.ok)throw Error('Fixture creation failed');
                    return await response.json();
                }""",{'id':eid,'name':name})
                token=issued['participant_token']
                guest.goto(browser_http+'/p/'+token)
                expect(guest).to_have_url(re.compile(r'/p/[A-Za-z0-9_-]+$'))

                expect(guest.locator('#game-chat [data-chat-room="general"]')).to_be_visible()
                guest.locator('#santa-preferences-display > button[data-action="edit-santa-preferences"]').click()
                expect(guest.locator('#santa-preferences-form')).to_be_visible()
                guest.locator('#santa-preferences-form #fld-wanted').fill('Красный цвет, точная модель')
                guest.locator('#santa-preferences-form #fld-unwanted').fill('Не нужен пластик')
                guest.locator('#santa-preferences-form button[type="submit"]').click()
                guest.locator('button[data-action="add-game-gift"]').click()
                guest.locator('#fld-title').fill('Подарок для ' + name)
                guest.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
                expect(guest.locator('.my-wishes-list')).to_contain_text('Подарок для ' + name)
                expect(guest.locator('.my-wishes-list .game-gifts-track .game-gift-card')).to_have_count(1)
                guest.locator('.game-gift-card .card-hitarea').first.click()
                expect(guest.locator('.modal')).not_to_contain_text('Красный цвет, точная модель')
                guest.locator('.modal-close').click()
                expect(guest.locator('#santa-preferences-form #fld-wanted')).to_have_value('Красный цвет, точная модель')
                if mobile:
                    for extra in ('Второй', 'Третий'):
                        guest.locator('button[data-action="add-game-gift"]').click()
                        expect(guest.locator('.wish-edit-modal .modal-fixed-footer')).to_be_visible()
                        guest.locator('#fld-title').fill(extra+' подарок')
                        guest.locator('.modal-fixed-footer button[type="submit"]').click()
                        expect(guest.locator('.my-wishes-list .game-gifts-track .game-gift-card')).to_have_count(
                            2 if extra=='Второй' else 3)
                    track=guest.locator('.my-wishes-list .game-gifts-track')
                    measurements=track.evaluate("""el => ({scrollWidth:el.scrollWidth,clientWidth:el.clientWidth})""")
                    assert measurements['scrollWidth']>measurements['clientWidth']+10
                    guest.locator('.my-wishes-list [data-action="scroll-game-gifts"][data-direction="next"]').click()
                    guest.wait_for_function("""() => document.querySelector('.my-wishes-list .game-gifts-track').scrollLeft > 10""")
                    assert guest.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
                guest.locator('#game-chat-input').fill('Привет от ' + name)
                guest.locator('#game-chat-form button[type="submit"]').click()
                expect(guest.locator('.game-chat-messages')).to_contain_text('Привет от ' + name)
                members.append((name, context, guest, token))

            # Roster polling updates the existing view; no page reload.
            expect(owner.locator('.person-row')).to_have_count(3,timeout=27000)
            assert owner.locator('.game-chat-panel').count()==1
            other = browser.new_context().new_page()
            other.goto(browser_http + '/')
            browser_login(other, 'other@example.test')
            assert other.evaluate('''async id => (await fetch('/api/santas/' + id)).status''', eid) == 404

            # Before drawing nobody can read recipient identities.
            for name, _, guest, token in members:
                state = guest.evaluate('''async token => (await (await fetch('/api/participant/' + token)).json())''', token)
                assert state['assignment'] is None
                assert 'receiver_name' not in str(state)
            owner.locator('button[data-action="draw"]').click()
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner.locator('button[data-action="reveal"]')).to_be_visible()
            assert owner.locator('.secret-card .recipient').count() == 0

            for name, _, guest, token in members:
                guest.reload()
                expect(guest.locator('button[data-action="reveal"]')).to_be_visible()
                state = guest.evaluate('''async token => (await (await fetch('/api/participant/' + token)).json())''', token)
                assert state['assignment'] == {'revealed': False}
                assert 'receiver_name' not in str(state)

            first_name, _, first, first_token = members[0]
            expect(first.locator('.panel h2',has_text='Кому ты даришь')).to_be_visible()
            first.locator('button[data-action="reveal"]').click()
            expect(first.locator('.secret-card .recipient')).to_be_visible()
            assert first.locator('.secret-card .recipient').inner_text() != first_name
            second_name, _, second, second_token = members[1]
            second_state = second.evaluate('''async token => (await (await fetch('/api/participant/' + token)).json())''', second_token)
            assert second_state['assignment'] == {'revealed': False}
            second.locator('button[data-action="reveal"]').click()
            expect(second.locator('.secret-card .recipient')).to_be_visible()
            assert second.locator('.secret-card .recipient').inner_text() != second_name
            # Event administrator still sees only their own recipient.
            owner_state = owner.evaluate('''async id => (await (await fetch('/api/santas/' + id)).json())''', eid)
            assert 'assignments' not in owner_state
            assert owner_state['my_assignment'] == {'revealed': False}
        finally:
            browser.close()
@pytest.mark.browser
def test_browser_card_clicks_and_santa_settings(browser_http):
    """Card surfaces navigate, while nested controls retain their own actions."""
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            owner=browser.new_page(viewport={'width':1280,'height':850})
            owner.set_default_timeout(15000)
            owner.goto(browser_http+'/')
            browser_login(owner)
            owner.locator('main button[data-open="list"]').first.click()
            owner.locator('#fld-title').fill('Подарки для игры')
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/list/\d+'))
            owner.locator('button[data-open="wish"]').first.click()
            owner.locator('#fld-title').fill('Настольная игра')
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            owner.locator('.wish-card .card-hitarea').click(position={'x':35,'y':35})
            expect(owner.locator('.modal h2')).to_have_text('Настольная игра')
            owner.locator('.wish-detail-actions [data-action="edit-wish"]').click()
            expect(owner.locator('#fld-title')).to_have_value('Настольная игра')
            owner.locator('.modal-close').click()

            owner.locator('header .logo[data-nav="/"]').click()
            target=owner.locator('.dashboard-page .list-card .card-hitarea').first
            target.focus()
            owner.keyboard.press('Enter')
            expect(owner).to_have_url(re.compile(r'/list/\d+'))
            owner.locator('header .logo[data-nav="/"]').click()
            owner.locator('main button[data-open="santa"]').first.click()
            owner.locator('#fld-title').fill('Санта без дублей')
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/santa/\d+'))
            eid=owner.url.rsplit('/',1)[-1]
            assert owner.locator('.error-page').count()==0, owner.locator('.error-page p').all_inner_texts()
            invite=owner.locator('input[aria-label="Ссылка-приглашение"]').input_value()
            owner.goto(invite)
            expect(owner.locator('.invite-card')).to_contain_text('Ты уже участвуешь')
            expect(owner.locator('#join-form')).to_have_count(0)

            owner.goto(browser_http+'/santa/'+eid)
            owner.locator('button[data-action="edit-santa-budget"]').click()
            owner.locator('input.santa-inline-editor-budget').fill('2450')
            owner.locator('input.santa-inline-editor-budget').press('Enter')
            expect(owner.locator('.details-box')).to_contain_text('2 450')
            owner.locator('button[data-action="edit-santa-date"]').click()
            owner.locator('input.santa-inline-editor-exchange_date').fill('2027-02-12')
            owner.locator('input.santa-inline-editor-exchange_date').press('Enter')
            expect(owner.locator('.details-box')).to_contain_text('12 февраля')
            assert owner.locator('.modal-backdrop').count()==0
            owner.locator('button[data-action="add-player"]').click()
            expect(owner.locator('.modal')).not_to_contain_text('Имя участника')
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner.locator('.modal h2')).to_have_text('Личное приглашение')
            participant_link=owner.locator('input[aria-label="Личная ссылка для приглашения"]').input_value()
            owner.locator('.modal-close').click()
            # A link does not insert a placeholder participant.
            expect(owner.locator('.person-row')).to_have_count(1)
            owner.locator('button[data-action="import-own-wishes"]').first.click()
            expect(owner.locator('[name="wish_ids"]:checked')).to_have_count(1)
            owner.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(owner.locator('.my-wishes-list')).to_contain_text('Настольная игра')

            owner.locator('header .logo[data-nav="/"]').click()
            owner.locator('.dashboard-santa-card .card-hitarea').first.click(position={'x':35,'y':35})
            expect(owner).to_have_url(re.compile(r'/santa/\d+'))
            owner.locator('header .nav [data-nav="/santas"]').click()
            owner.locator('.santa-list-card .card-hitarea').first.click(position={'x':35,'y':35})
            expect(owner).to_have_url(re.compile(r'/santa/\d+'))

            other=browser.new_page(viewport={'width':390,'height':844})
            other.set_default_timeout(15000)
            other.goto(browser_http+'/')
            expect(other.locator('header button[data-open="login"]')).to_be_visible()
            browser_login(other,'other@example.test')
            expect(other.locator('header button[data-action="logout"]')).to_be_visible()
            other.locator('main button[data-open="list"]').first.click()
            other.locator('#fld-title').fill('Другой список')
            other.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            other.locator('button[data-open="wish"]').first.click()
            other.locator('#fld-title').fill('Тёплый шарф')
            other.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            other.goto(participant_link)
            expect(other.locator('#join-form')).to_be_visible()
            other.locator('#join-name').fill('Аня')
            other.locator('#join-form button[type="submit"]').click()
            expect(other).to_have_url(re.compile(r'/santa/\d+$'))
            other.locator('button[data-action="import-own-wishes"]').click()
            expect(other.locator('[name="wish_ids"]:checked')).to_have_count(1)
            other.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(other.locator('.my-wishes-list')).to_contain_text('Тёплый шарф')
            assert other.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        finally:
            browser.close()


def test_auth_uses_fixed_confirmation_destination_not_request_host(monkeypatch):
    """Verify outgoing Supabase signup request without sending email or tokens."""
    import io
    import json
    from urllib.parse import urlsplit, parse_qs
    from cloud import auth
    monkeypatch.setenv('SUPABASE_URL','https://unit-project.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_for_testing')
    redirect='https://shursh-preview-git-feat-supabase-mvp-21trews-projects.vercel.app/'
    monkeypatch.setenv('SHURSH_AUTH_REDIRECT_URL',redirect)
    calls=[]
    def mock_urlopen(request,timeout):
        calls.append((request.full_url,json.loads(request.data),dict(request.headers)))
        return io.BytesIO(b'{"user":{"id":"test"},"access_token":null}')
    monkeypatch.setattr(auth,'urlopen',mock_urlopen)
    auth.auth_request('register',email='someone@example.test',password='some-password',
                      data={'name':'Test'})
    url,payload,headers=calls[-1]
    assert urlsplit(url).path=='/auth/v1/signup'
    assert parse_qs(urlsplit(url).query)=={'redirect_to':[redirect]}
    assert 'password=some-password' not in url
    assert payload['email']=='someone@example.test'
    assert 'sb_publishable_for_testing' not in url
    auth.auth_request('login',email='someone@example.test',password='some-password')
    url,_,_=calls[-1]
    assert url.endswith('/auth/v1/token?grant_type=password')
    assert 'redirect_to' not in url
    for invalid in ('http://localhost:3000/','https://evil.test/?a=b',
                    'https://name:pass@evil.test/','https://evil.test/#token',
                    'https://evil.test:8443/'):
        monkeypatch.setenv('SHURSH_AUTH_REDIRECT_URL',invalid)
        with pytest.raises((RuntimeError,ValueError)):
            auth.auth_request('register',email='someone@example.test',password='some-password')
    assert len(calls)==2


@pytest.mark.browser
def test_browser_login_logout_and_mobile_dashboard(browser_http):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':1366,'height':900})
            page.goto(browser_http+'/')
            expect(page.locator('main h1')).to_contain_text('Подарки')
            browser_login(page)
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'mobile overflow'
            page.set_viewport_size({'width':1366,'height':900})
            for _ in range(6):
                page.locator('header button[data-action="logout"]').click()
                expect(page.locator('main h1')).to_contain_text('Подарки')
                expect(page.locator('.dashboard-page')).to_have_count(0)
                browser_login(page)
                expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_navigation_cache_invalidation_and_persistent_header(browser_http):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':1280,'height':820})
            page.set_default_timeout(15000)
            page.goto(browser_http+'/')
            browser_login(page)
            expect(page.locator('.dashboard-metrics')).to_have_count(0)
            expect(page.locator('header .header-bell')).to_be_visible()
            page.evaluate('window.__stableHeader = document.querySelector(".site-header")')
            page.evaluate('window.__stableFooter = document.querySelector("footer")')
            visited=[]
            page.on('request',lambda request: visited.append((request.method,request.url.split(browser_http)[-1]))
                    if request.url.startswith(browser_http+'/api/') else None)
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Вишлисты')
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main h1')).to_contain_text('Тайный Санта')
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Вишлисты')
            assert sum(method=='GET' and path=='/api/lists' for method,path in visited)==0,visited
            assert sum(method=='GET' and path=='/api/santas' for method,path in visited)==0,visited
            assert page.evaluate('document.querySelector(".site-header") === window.__stableHeader')
            assert page.evaluate('document.querySelector("footer") === window.__stableFooter')
            before=len(visited)
            page.locator('header .nav [data-nav="/lists"]').click()
            assert len(visited)==before,'same-route click should not fetch'
            title='No redraw '+uuid4().hex[:7]
            page.locator('main button[data-open="list"]').first.click()
            page.locator('#fld-title').fill(title)
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/list/\d+$'))
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main')).to_contain_text(title)
            assert sum(method=='GET' and path=='/api/lists' for method,path in visited)==1,visited
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main h1')).to_contain_text('Тайный Санта')
            santa='No redraw game '+uuid4().hex[:7]
            page.locator('main button[data-open="santa"]').first.click()
            page.locator('#fld-title').fill(santa)
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/santa/\d+$'))
            assert page.locator('.error-page').count()==0, page.locator('.error-page p').all_inner_texts()
            expect(page.locator('main h1')).to_contain_text(santa)
            assert sum('/my-wishes' in path for method,path in visited)==0,visited
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main')).to_contain_text(santa)
            assert sum(method=='GET' and path=='/api/santas' for method,path in visited)==1,visited
            page.locator('header .nav [data-nav="/"]').click()
            expect(page.locator('.dashboard-page')).to_contain_text(title)
            expect(page.locator('.dashboard-page')).to_contain_text(santa)
            assert page.evaluate('localStorage.length===0 && sessionStorage.length===0')
        finally:
            browser.close()


def test_static_assets_cache_but_private_endpoints_do_not(application):
    client=application.test_client()
    for path in ('/app.js','/styles.css','/favicon.svg'):
        result=client.get(path)
        assert result.status_code==200
        assert result.headers['Cache-Control']=='public, max-age=300, must-revalidate'
    for path in ('/','/api/me','/api/dashboard'):
        result=client.get(path)
        assert result.status_code==200
        assert result.headers['Cache-Control']=='no-store'


@pytest.mark.browser
def test_owner_tab_navigation_reuses_data_and_dom(browser_http):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page()
            page.goto(browser_http+'/')
            browser_login(page)
            expect(page.locator('.dashboard-page')).to_be_visible()
            # Wait for the first cold dashboard API response. The optimistic
            # skeleton already contains the owner's heading but has not seeded
            # /api/lists and /api/santas yet. The test measures WARM navigation.
            expect(page.locator('.dashboard-skeleton')).to_have_count(0,timeout=15000)
            requests=[]
            page.on('request', lambda r: requests.append(r.url) if '/api/' in r.url else None)
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Вишлисты')
            page.locator('main').evaluate("(el) => el.dataset.identity = 'same-node'")
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main h1')).to_contain_text('Тайный Санта')
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main')).to_have_attribute('data-identity','same-node')
            page.locator('header .nav [data-nav="/"]').click()
            expect(page.locator('.dashboard-page')).to_be_visible()
            assert not any('/api/lists' in url or '/api/santas' in url for url in requests), requests
            page.locator('main button[data-open="list"]').first.click()
            page.locator('#fld-title').fill('Cache invalidation integration')
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/list/[0-9]+$'))
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main')).to_contain_text('Cache invalidation integration')
            assert any('/api/lists' in url for url in requests), requests
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_confirmation_return_clears_provider_hash(browser_http):
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page()
            page.goto(browser_http+'/#access_token=fake-test-value&refresh_token=fake-refresh&type=signup')
            expect(page).to_have_url(browser_http+'/')
            expect(page.get_by_role('dialog')).to_contain_text('Не получилось завершить подтверждение')
            assert 'fake-test-value' not in page.url
            # A provider confirmation redirects from Supabase to a new document.
            # A same-document hash navigation would not rerun startup logic.
            page=browser.new_page()
            page.goto(browser_http+'/#error=access_denied&error_code=otp_expired&error_description=test')
            expect(page).to_have_url(browser_http+'/')
            expect(page.get_by_role('dialog')).to_contain_text('истекла')
            # Providers may redirect with only error/error_code, without
            # error_description. Do not leave such callback fragments in the URL.
            page=browser.new_page()
            page.goto(browser_http+'/#error=access_denied&error_code=otp_expired')
            expect(page).to_have_url(browser_http+'/')
            expect(page.get_by_role('dialog')).to_contain_text('истекла')
            assert 'otp_expired' not in page.url
            page=browser.new_page()
            page.goto(browser_http+'/#error_code=otp_expired')
            expect(page).to_have_url(browser_http+'/')
            expect(page.get_by_role('dialog')).to_contain_text('истекла')
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.fontperf
def test_font_loading_observation(browser_http):
    """Fonts load from first-party static assets without a Google Fonts dependency."""
    import json
    from time import perf_counter
    from playwright.sync_api import sync_playwright
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':1280,'height':800})
            started=perf_counter()
            page.goto(browser_http+'/',wait_until='domcontentloaded',timeout=30000)
            dom_ms=round((perf_counter()-started)*1000,1)
            fonts=page.evaluate(r"""async () => {
              const done=await Promise.race([
                document.fonts.ready.then(()=>true),
                new Promise(resolve=>setTimeout(()=>resolve(false),8000))
              ]);
              const faces=[...document.fonts].map(f=>({family:f.family,status:f.status}));
              const all=performance.getEntriesByType('resource');
              const external=all.filter(x=>/^https:\/\/fonts\.(?:googleapis|gstatic)\.com\//.test(x.name));
              const local=all.filter(x=>/\/fonts\/(?:onest|unbounded)-.*\.woff2/.test(x.name));
              return {fontReady:done,fontFaces:faces.length,
                loadedFaces:faces.filter(x=>x.status==='loaded').length,
                externalCount:external.length,localCount:local.length};
            }""")
            assert fonts['fontReady'], fonts
            assert fonts['externalCount']==0, fonts
            assert fonts['loadedFaces']>0 and fonts['localCount']>0, fonts
            print('SHURSH_FONT_PERF='+json.dumps({
                'scope':'CI-Chromium-local-fonts','domContentLoadedMs':dom_ms,
                **fonts},ensure_ascii=False))
        finally:
            browser.close()


def test_santa_gift_details_group_chat_and_anonymous_pair_chat(application):
    """Isolated CI PostgreSQL: private gifts/chats require membership, pairs stay anonymous."""
    owner=login(application)
    outsider=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Чаты и пожелания'},201).json['id']
    event=call(owner,'GET',f'/api/santas/{eid}').json['event']
    guest=application.test_client()
    tokens={}
    for name in ('Альфа','Бета'):
        tokens[name]=call(owner,'POST',f'/api/santas/{eid}/participants',
                          {'name':name},201).json['participant_token']
    t=tokens['Альфа']
    gift=call(guest,'POST',f'/api/participant/{t}/wishes',{
        'title':'Умная лампа','wanted':'Тёплый свет','unwanted':'Без цветных вспышек',
        'description':'Для чтения','price':'1250','currency':'RUB',
        'shop_url':'https://example.com/lamp','image_data':PNG},201).json['id']
    saved=call(guest,'GET',f'/api/participant/{t}').json
    assert saved['wishes'][0]['wanted']=='Тёплый свет'
    assert saved['wishes'][0]['unwanted']=='Без цветных вспышек'
    assert saved['wishes'][0]['price_cents']==125000
    assert saved['wishes'][0]['image_data']==PNG
    assert 'Умная лампа' not in str(call(guest,'GET',f'/api/participant/{tokens["Бета"]}').json)
    assert 'Умная лампа' not in str(call(owner,'GET',f'/api/santas/{eid}').json)
    call(guest,'PATCH',f'/api/participant/{tokens["Бета"]}/wishes/{gift}',
         {'title':'Подмена'},404)
    call(outsider,'GET',f'/api/santas/{eid}/messages/general',status=404)
    call(guest,'GET',f'/api/participant/no-such-key/messages/general',status=404)
    call(guest,'GET',f'/api/participant/{t}/messages/to-recipient',status=409)
    call(guest,'POST',f'/api/participant/{t}/messages/general',
         {'message':'Всем привет!'},201)
    visible=call(guest,'GET',f'/api/participant/{tokens["Бета"]}/messages/general').json
    assert visible['messages'][-1]['message']=='Всем привет!'
    assert visible['messages'][-1]['author']=='Альфа'
    assert 'sender_id' not in str(visible) and 'pair_giver_id' not in str(visible)
    call(guest,'POST',f'/api/participant/{t}/messages/general',{'message':'x'*501},400)
    call(guest,'PATCH',f'/api/participant/{t}/wishes/{gift}',{
        'title':'Лампа','wanted':'Стекло','unwanted':'Пластик','image_data':PNG},200)
    edited=call(guest,'GET',f'/api/participant/{t}').json['wishes'][0]
    assert edited['title']=='Лампа'
    assert edited['image_data']==PNG
    call(guest,'PATCH',f'/api/participant/{t}/wishes/{gift}',
         {'title':'Лампа 2','wanted':'Тёплый свет'},200)
    assert call(guest,'GET',f'/api/participant/{t}').json['wishes'][0]['image_data']==PNG
    call(owner,'POST',f'/api/santas/{eid}/draw',{},200)
    # Pair A -> assigned recipient, and ONLY that recipient reads it as an
    # anonymous Santa message; no recipient identity in the chat payload.
    assigned=call(guest,'POST',f'/api/participant/{t}/reveal',{}).json['assignment']
    assert assigned['revealed']
    call(guest,'POST',f'/api/participant/{t}/messages/to-recipient',
         {'message':'Какой цвет подойдёт?'},201)
    recipient=assigned['receiver_name']
    if recipient=='Owner':
        received=call(owner,'GET',f'/api/santas/{eid}/messages/from-santa').json
    else:
        received=call(guest,'GET',
                      f'/api/participant/{tokens[recipient]}/messages/from-santa').json
    assert received['messages'][-1]['author']=='Тайный даритель'
    assert received['messages'][-1]['message']=='Какой цвет подойдёт?'
    assert 'sender_id' not in str(received)
    assert 'giver_id' not in str(received)
    call(guest,'DELETE',f'/api/participant/{tokens["Бета"]}/wishes/{gift}',status=404)
    call(guest,'DELETE',f'/api/participant/{t}/wishes/{gift}')
    assert call(guest,'GET',f'/api/participant/{t}').json['wishes']==[]


def test_santa_legacy_database_feature_gate(application,monkeypatch):
    """A missing migration must never make existing game pages fail with 503."""
    from cloud.backend import CloudRequest
    owner=login(application)
    eid=call(owner,'POST','/api/santas',{'title':'Старая схема'},201).json['id']
    monkeypatch.setattr(CloudRequest,'santa_schema_ready',lambda self,con:False)
    data=call(owner,'GET',f'/api/santas/{eid}').json
    assert data['rich_enabled'] is False
    assert data['participants'][0]['name']=='Owner'
    created=call(owner,'POST',f'/api/santas/{eid}/my-wishes',{'title':'Простой подарок'},201)
    assert created.json['id']>0
    game=call(owner,'GET',f'/api/santas/{eid}').json
    assert game['my_wishes'][0]['title']=='Простой подарок'
    assert game['my_wishes'][0]['wanted']==''
    call(owner,'GET',f'/api/santas/{eid}/messages/general',status=409)
    invite=game['event']['invite_key']
    participant=call(owner,'POST',f'/api/santas/{eid}/participants',
                     {'name':'Гость'},201).json['participant_token']
    guest=call(application.test_client(),'GET',f'/api/participant/{participant}').json
    assert guest['rich_enabled'] is False
    assert len(guest['participants'])==2


def test_live_santa_roster_is_private_and_updates_on_join(application):
    owner=login(application)
    outsider=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Realtime members'},201).json['id']
    own_roster=f'/api/santas/{eid}/roster'
    assert call(owner,'GET',own_roster).json['participants'][0]['is_organizer']==1
    call(outsider,'GET',own_roster,status=404)
    call(application.test_client(),'GET',own_roster,status=401)
    invitation=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    member=application.test_client()
    key=call(owner,'POST',f'/api/santas/{eid}/participants',
             {'name':'Гость'},201).json['participant_token']
    guest_roster=f'/api/participant/{key}/roster'
    data=call(member,'GET',guest_roster).json
    assert [x['name'] for x in data['participants']]==['Owner','Гость']
    assert data['status']=='open'
    assert not any(k in str(data) for k in ('access_hash','receiver_id','giver_id','email'))
    call(member,'GET','/api/participant/invalid-key/roster',status=404)
    call(member,'POST',f'/api/participant/{key}/wishes',
         {'title':'Пазл'},201)
    changed=call(owner,'GET',own_roster).json
    assert changed['participants'][1]['wish_count']==1
    assert changed['participants'][1]['is_organizer']==0


def test_santa_wishlist_library_single_request_and_owner_only(application):
    owner=login(application)
    other=login(application,'other@example.test')
    lid=call(owner,'POST','/api/lists',{'title':'Private library'},201).json['id']
    w1=call(owner,'POST',f'/api/lists/{lid}/wishes',
            {'title':'Gift 1'},201).json['id']
    w2=call(owner,'POST',f'/api/lists/{lid}/wishes',
            {'title':'Gift 2'},201).json['id']
    empty=call(owner,'POST','/api/lists',{'title':'Empty'},201).json['id']
    collection=call(owner,'GET','/api/santa/library').json['lists']
    assert [item['id'] for item in collection[:2]]==[empty,lid]
    assert collection[0]['wishes']==[]
    assert {w['id'] for w in collection[1]['wishes']}=={w1,w2}
    assert 'image_data' not in str(collection) and 'image_path' not in str(collection)
    assert lid not in {item['id'] for item in call(other,'GET','/api/santa/library').json['lists']}
    call(application.test_client(),'GET','/api/santa/library',status=401)


def test_participant_preferences_and_chat_post_ack(application):
    owner=login(application)
    guest=application.test_client()
    eid=call(owner,'POST','/api/santas',{'title':'Preference isolation'},201).json['id']
    invite=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    token=call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Visitor'},201).json['participant_token']
    saved=call(guest,'PATCH',f'/api/participant/{token}/preferences',
               {'wanted':'Книги','unwanted':'Пластик'}).json
    assert saved['preferences']=={'wanted':'Книги','unwanted':'Пластик'}
    participant=call(guest,'GET',f'/api/participant/{token}').json
    assert participant['preferences']==saved['preferences']
    assert call(owner,'GET',f'/api/santas/{eid}').json['my_preferences']=={'wanted':'','unwanted':''}
    assert call(guest,'PATCH',f'/api/participant/invalid/preferences',
                {'wanted':'x','unwanted':''},404).status_code==404
    assert call(guest,'PATCH',f'/api/participant/{token}/preferences',
                {'wanted':'x'*2001,'unwanted':''},400).status_code==400
    sent=call(guest,'POST',f'/api/participant/{token}/messages/general',
              {'message':'One trip only'},201).json
    assert sent['message']['mine'] is True
    assert sent['message']['message']=='One trip only'
    assert sent['message']['author']=='Ты'
    assert isinstance(sent['message']['id'],int)
    assert 'sender_id' not in str(sent)


def test_developer_feedback_admin_inbox_isolation(application,monkeypatch):
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    anon=application.test_client()
    owner=login(application)
    other=login(application,'other@example.test')
    assert call(anon,'GET','/api/admin/feedback',status=401).status_code==401
    assert call(other,'GET','/api/admin/feedback',status=403).status_code==403
    assert call(anon,'POST','/api/feedback',{'name':'A','email':'invalid',
         'topic':'bug','message':'Broken feature'},400).status_code==400
    assert call(anon,'POST','/api/feedback',{'name':'User','email':'user@example.test',
         'topic':'bug','message':'The send button hangs'},201).json['ok']
    entries=call(owner,'GET','/api/admin/feedback').json['items']
    target=next(x for x in entries if x['email']=='user@example.test')
    assert target['message']=='The send button hangs'
    assert target['status']=='new'
    call(other,'PATCH',f"/api/admin/feedback/{target['id']}",{'status':'resolved'},403)
    call(owner,'PATCH',f"/api/admin/feedback/{target['id']}",{'status':'resolved'})
    assert next(x for x in call(owner,'GET','/api/admin/feedback').json['items']
                if x['id']==target['id'])['status']=='resolved'
    monkeypatch.delenv('SHURSH_ADMIN_EMAILS')
    call(owner,'GET','/api/admin/feedback',status=403)


def test_confirmation_creates_app_session_from_verified_provider(application,monkeypatch):
    from cloud import auth
    from server import ApiError
    called=[]
    def verified(token):
        called.append('validated')
        assert token=='header.payload.signature'
        return {'id':str(IDS['owner@example.test']),
                'email':'owner@example.test','email_confirmed_at':'2026-11-20T00:00:00Z',
                'user_metadata':{'name':'Owner'}}
    monkeypatch.setattr(auth,'verified_user',verified)
    client=application.test_client()
    assert call(client,'GET','/api/me').json['user'] is None
    call(client,'POST','/api/auth/complete',{'access_token':'not-a-token'},400)
    assert not called, 'Malformed tokens must not reach Supabase'
    result=call(client,'POST','/api/auth/complete',
                {'access_token':'header.payload.signature'})
    assert result.json['user']['email']=='owner@example.test'
    assert 'HttpOnly' in result.headers['Set-Cookie']
    assert 'header.payload.signature' not in str(result.headers)
    assert call(client,'GET','/api/me').json['user']['email']=='owner@example.test'
    assert len(called)==1
    call(application.test_client(),'POST','/api/auth/complete',
         {'access_token':'header.payload.signature'},403,headers={'Origin':'https://untrusted.example'})


def test_confirmation_rejects_unverified_provider_identity(application,monkeypatch):
    from cloud import auth
    from server import ApiError
    def reject(_token):
        raise ApiError(401,'Ссылка подтверждения истекла или недействительна')
    monkeypatch.setattr(auth,'verified_user',reject)
    client=application.test_client()
    call(client,'POST','/api/auth/complete',{'access_token':'header.payload.signature'},401)
    assert call(client,'GET','/api/me').json['user'] is None


def test_resend_confirmation_is_generic_and_rate_limited(application,monkeypatch):
    from cloud import auth
    sent=[]
    def fake(action,**payload):
        assert action=='resend' and payload['type']=='signup'
        sent.append(payload['email'])
        return {}
    monkeypatch.setattr(auth,'auth_request',fake)
    client=application.test_client()
    call(client,'POST','/api/auth/resend',{'email':'invalid'},400)
    for _ in range(3):
        result=call(client,'POST','/api/auth/resend',
                    {'email':'someone@example.test'},202)
        assert result.json == {'ok':True}
        assert 'Set-Cookie' not in result.headers
    assert sent==['someone@example.test']*3
    call(client,'POST','/api/auth/resend',
         {'email':'someone@example.test'},429)


@pytest.mark.browser
def test_browser_confirmation_callback_and_recovery(browser_http,monkeypatch):
    from cloud import auth
    from server import ApiError
    from playwright.sync_api import sync_playwright,expect
    def provider_token(token):
        if token=='expired.token.example':
            raise ApiError(401,'Ссылка подтверждения истекла')
        assert token=='header.payload.signature'
        return {'id':str(IDS['owner@example.test']),
                'email':'owner@example.test','email_confirmed_at':'2026-11-20T00:00:00Z',
                'user_metadata':{'name':'Owner'}}
    monkeypatch.setattr(auth,'verified_user',provider_token)
    monkeypatch.setattr(auth,'auth_request',
                        lambda action,**kwargs: {} if action=='resend' else
                        pytest.fail('Unexpected provider request'))
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page()
            page.goto(browser_http+'/#access_token=header.payload.signature&refresh_token=not-used')
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
            assert page.evaluate('location.hash')==''
            assert page.evaluate('document.cookie')==''
            # Expired confirmations must show a persistent recovery dialog.
            expired=browser.new_page()
            expired.goto(browser_http+'/#access_token=expired.token.example')
            expect(expired.get_by_role('dialog')).to_contain_text('Не получилось завершить подтверждение')
            assert expired.evaluate('location.hash')==''
            expired.locator('[data-open="resend"]').click()
            expired.locator('#fld-email').fill('owner@example.test')
            expired.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(expired.get_by_role('dialog')).to_contain_text('Проверь почту')
        finally:
            browser.close()


def test_resend_provider_rejection_does_not_claim_email_sent(monkeypatch):
    import io
    from urllib.error import HTTPError
    from cloud import auth
    from server import ApiError
    monkeypatch.delenv('SHURSH_ENV', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('SUPABASE_URL','https://unit-project.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_for_test')
    monkeypatch.setenv('SHURSH_AUTH_REDIRECT_URL','https://shursh.vercel.app')
    def reject(request,timeout):
        raise HTTPError(request.full_url,400,'Rejected redirect',{},
                        io.BytesIO(b'{"error_code":"redirect_to_not_allowed"}'))
    monkeypatch.setattr(auth,'urlopen',reject)
    with pytest.raises(ApiError) as exc:
        auth.auth_request('resend',type='signup',email='owner@example.test')
    assert exc.value.status==503



# Social v1: real PostgreSQL, synthetic Auth users and no hosted secrets.
def test_social_friends_profiles_and_notifications(application):
    from cloud import db
    owner=login(application)
    friend=login(application,'other@example.test')
    owner_id=str(IDS['owner@example.test'])
    friend_id=str(IDS['other@example.test'])
    # Guests cannot enumerate users or access the social graph.
    call(application.test_client(),'GET','/api/friends',status=401)
    call(application.test_client(),'GET','/api/users/search?q=Own',status=401)
    call(owner,'POST',f'/api/friends/{owner_id}',{},400)
    # Start with an owner-only private list; it must remain invisible to friends.
    private_id=call(owner,'POST','/api/lists',{'title':'Private list',
                                 'visibility':'private'},201).json['id']
    public_id=call(owner,'POST','/api/lists',{'title':'Shared list'},201).json['id']
    before=call(friend,'GET',f'/api/users/{owner_id}').json
    assert before['lists']==[] and 'email' not in str(before)
    assert before['relationship']=='none'
    call(owner,'POST',f'/api/friends/{friend_id}',{},200)
    incoming=call(friend,'GET','/api/friends').json['incoming']
    assert any(str(x['id'])==owner_id for x in incoming)
    notices=call(friend,'GET','/api/notifications').json
    assert any(n['kind']=='friend_request' for n in notices['items'])
    first=next(n['id'] for n in notices['items'] if n['kind']=='friend_request')
    call(owner,'POST',f'/api/notifications/{first}/read',{},200)
    # Unauthorized mark-read must not change another user's notification.
    assert any(n['id']==first and n['read_at'] is None
               for n in call(friend,'GET','/api/notifications').json['items'])
    call(friend,'PATCH',f'/api/friends/{owner_id}',{'action':'accept'})
    profile=call(friend,'GET',f'/api/users/{owner_id}').json
    assert profile['relationship']=='friends'
    assert any(x['id']==public_id for x in profile['lists'])
    assert all(x['id']!=private_id for x in profile['lists'])
    assert 'email' not in str(profile)
    shared=call(friend,'GET','/api/friends/wishlists').json['lists']
    assert any(x['id']==public_id for x in shared)
    assert all(x['id']!=private_id for x in shared)
    assert all('email' not in str(x) for x in shared)
    call(owner,'POST','/api/lists',{'title':'Gift list added with friends'},201)
    feed=call(friend,'GET','/api/notifications').json['items']
    assert any(n['kind']=='wishlist_new' for n in feed)
    call(friend,'POST',f'/api/notifications/{first}/read',{})
    call(owner,'POST','/api/notifications/read-all',{})
    assert all(x['read_at'] is not None for x in
               call(owner,'GET','/api/notifications').json['items'])
    call(application.test_client(),'POST','/api/notifications/read-all',{},401)
    assert any(n['id']==first and n['read_at'] is not None
               for n in call(friend,'GET','/api/notifications').json['items'])
    search=call(friend,'GET','/api/users/search?q=Own').json['users']
    assert any(str(x['id'])==owner_id for x in search)
    call(owner,'PATCH','/api/profile/me',{'bio':'Люблю сюрпризы','discoverable':False})
    assert not any(str(x['id'])==owner_id for x in
                   call(friend,'GET','/api/users/search?q=Own').json['users'])
    assert call(friend,'GET',f'/api/users/{owner_id}').json['profile']['bio']=='Люблю сюрпризы'
    call(owner,'PATCH','/api/profile/me',{'discoverable':True})
    call(friend,'DELETE',f'/api/friends/{owner_id}',{})
    assert call(friend,'GET',f'/api/users/{owner_id}').json['lists']==[]
    assert not any(x['id']==public_id for x in
                   call(friend,'GET','/api/friends/wishlists').json['lists'])
    call(application.test_client(),'GET','/api/friends/wishlists',status=401)


def test_social_gift_request_and_anonymous_booking(application):
    owner=login(application)
    friend=login(application,'other@example.test')
    owner_id=str(IDS['owner@example.test'])
    friend_id=str(IDS['other@example.test'])
    call(owner,'POST',f'/api/friends/{friend_id}',{})
    call(friend,'PATCH',f'/api/friends/{owner_id}',{'action':'accept'})
    lid,wid,key=make_list(owner)
    call(owner,'POST',f'/api/wishes/{wid}/request-friend/{friend_id}',{},201)
    items=call(friend,'GET','/api/notifications').json['items']
    assert any(x['kind']=='wish_request' for x in items)
    call(owner,'POST',f'/api/wishes/{wid}/request-friend/{friend_id}',{},409)
    guest=application.test_client()
    call(guest,'POST',f'/api/public/{key}/reserve/{wid}',{},401)
    response=call(friend,'POST',f'/api/public/{key}/reserve/{wid}',{},201).json
    assert response=={'ok':True}
    assert call(friend,'GET',f'/api/public/{key}').json['wishes'][0]['reserved_by_me'] is True
    feed=[x for x in call(owner,'GET','/api/notifications').json['items']
          if x['kind']=='reservation_anonymous']
    assert feed
    assert all('Анонимный даритель' not in x['message'] and 'Gift' not in x['message']
               and str(wid) not in x['target_path'] for x in feed)


def test_social_game_invitation_member_permissions_and_admin(application,monkeypatch):
    # Session-scoped CI database is shared; isolate relationships from prior tests.
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('DELETE FROM public.friendships WHERE user_low=%s AND user_high=%s',
                    (IDS['owner@example.test'], IDS['other@example.test']))
    owner=login(application)
    friend=login(application,'other@example.test')
    owner_id=str(IDS['owner@example.test'])
    friend_id=str(IDS['other@example.test'])
    # Friend-only invite cannot be sent before acceptance.
    event_id=call(owner,'POST','/api/santas',{'title':'Synthetic Santa'},201).json['id']
    call(owner,'POST',f'/api/santas/{event_id}/invite-friend/{friend_id}',{},403)
    call(owner,'POST',f'/api/friends/{friend_id}',{})
    call(friend,'PATCH',f'/api/friends/{owner_id}',{'action':'accept'})
    call(owner,'POST',f'/api/santas/{event_id}/invite-friend/{friend_id}',{},201)
    invitation=[x for x in call(friend,'GET','/api/notifications').json['items']
                if x['kind']=='santa_invitation']
    assert invitation
    assert any(x['id']==event_id for x in call(friend,'GET','/api/santas').json['invitations'])
    assert not any(x['id']==event_id for x in call(owner,'GET','/api/santas').json['invitations'])
    key=call(owner,'GET',f'/api/santas/{event_id}').json['event']['invite_key']
    joined=call(friend,'POST',f'/api/invites/{key}/join',{'name':'Friend'},201)
    assert joined.json=={'event_id':event_id}
    assert not any(x['id']==event_id for x in call(friend,'GET','/api/santas').json['invitations'])
    game=call(friend,'GET',f'/api/member/{event_id}').json
    assert game['event']['id']==event_id and game['participant']['name']=='Friend'
    assert 'assignments' not in str(game)
    assert any(x['id']==event_id for x in call(friend,'GET','/api/santas').json['events'])
    assert any(x['id']==event_id for x in call(friend,'GET','/api/dashboard').json['events'])
    call(application.test_client(),'GET',f'/api/member/{event_id}',status=401)
    call(friend,'GET',f'/api/santas/{event_id}',status=404)
    call(friend,'GET','/api/admin/overview',status=403)
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    assert call(owner,'GET','/api/admin/overview').json['stats']['users']>=2
    assert call(friend,'GET','/api/admin/overview',status=403)
    new_login=login(application)
    assert new_login.get('/api/me',base_url=BASE).json['user']['is_admin'] is True
    assert new_login.post('/api/logout',base_url=BASE,json={}).status_code==200


def test_profile_identity_emoji_handles_friend_cancel_and_privacy(application):
    """All personal edits are owner-scoped; email must never leak to others."""
    from cloud import db
    owner=login(application)
    friend=login(application,'other@example.test')
    owner_id=str(IDS['owner@example.test'])
    friend_id=str(IDS['other@example.test'])
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('DELETE FROM public.friendships WHERE user_low=%s AND user_high=%s',
                    (IDS['owner@example.test'], IDS['other@example.test']))
    mine=call(owner,'GET','/api/profile/me').json
    assert mine['profile']['email']=='owner@example.test'
    assert mine['profile']['avatar_emoji']=='🎁'
    assert isinstance(mine['lists'],list)
    updated=call(owner,'PATCH','/api/profile/me',{
        'name':'Owner Profile','handle':'Owner_2026','avatar_emoji':'🐱',
        'city':'Санкт-Петербург','bio':'Люблю настольные игры',
        'discoverable':True}).json['profile']
    assert updated['handle']=='owner_2026'
    assert updated['avatar_emoji']=='🐱'
    assert updated['city']=='Санкт-Петербург'
    assert updated['name']=='Owner Profile'
    assert 'email' in updated
    public=call(friend,'GET',f'/api/users/{owner_id}').json['profile']
    assert public['avatar_emoji']=='🐱' and public['handle']=='owner_2026'
    assert 'email' not in public and 'owner@example.test' not in str(public)
    q=call(friend,'GET','/api/users/search?q=%40owner_2026').json
    assert any(str(x['id'])==owner_id and x['avatar_emoji']=='🐱' for x in q['users'])
    call(friend,'PATCH','/api/profile/me',{'handle':'owner_2026'},409)
    call(friend,'PATCH','/api/profile/me',{'avatar_emoji':'<img src=x onerror=alert(1)>'},400)
    call(friend,'PATCH','/api/profile/me',{'handle':' bad handle '},400)
    call(friend,'PATCH','/api/profile/me',{'city':'x'*61},400)
    call(friend,'POST',f'/api/friends/{owner_id}',{},200)
    # Recipient may not cancel another person's pending outgoing request.
    call(owner,'DELETE',f'/api/friends/{friend_id}',{},404)
    assert call(friend,'GET','/api/friends').json['outgoing']
    call(friend,'DELETE',f'/api/friends/{owner_id}',{},200)
    assert not any(n['kind']=='friend_request' and n['read_at'] is None
                   for n in call(owner,'GET','/api/notifications').json['items'])
    assert not call(friend,'GET','/api/friends').json['outgoing']
    assert not call(owner,'GET','/api/friends').json['incoming']
    call(owner,'PATCH','/api/profile/me',{'name':'Owner','handle':'',
        'avatar_emoji':'🎁','city':'','bio':'','discoverable':True})
    call(friend,'PATCH','/api/profile/me',{'handle':''})


def test_santa_private_link_claim_to_logged_in_account(application):
    """Private capability is proof for a single binding, not transferable."""
    organizer=login(application,'other@example.test')
    target=login(application)
    event_id=call(organizer,'POST','/api/santas',{'title':'Account link claim'},201).json['id']
    key=call(organizer,'GET',f'/api/santas/{event_id}').json['event']['invite_key']
    guest=application.test_client()
    join=call(organizer,'POST',f'/api/santas/{event_id}/participants',{'name':'Guest for account'},201)
    personal_token=join.json['participant_token']
    assert len(personal_token)==43
    before=call(target,'GET','/api/santas').json['events']
    assert not any(x['id']==event_id for x in before)
    # A matching name is not an identity proof: only a private capability can claim.
    assert call(target,'GET','/api/santas').json['invitations']==[] or all(
        x['id']!=event_id for x in call(target,'GET','/api/santas').json['invitations'])
    call(guest,'POST',f'/api/participant/{personal_token}/claim',{},401)
    call(target,'POST','/api/participant/invalid/claim',{},404)
    bound=call(target,'POST',f'/api/participant/{personal_token}/claim',{},200).json
    assert bound['event_id']==event_id
    assert any(x['id']==event_id for x in call(target,'GET','/api/santas').json['events'])
    assert any(x['id']==event_id for x in call(target,'GET','/api/dashboard').json['events'])
    call(target,'POST',f'/api/participant/{personal_token}/claim',{},404)
    call(organizer,'POST',f'/api/participant/{personal_token}/claim',{},404)
    call(guest,'GET',f'/api/participant/{personal_token}',status=404)
    # Authenticated membership no longer depends on retaining the bearer link.
    member=call(target,'GET',f'/api/member/{event_id}').json
    assert member['participant']['name']=='Guest for account'
    assert member['assignment'] is None


def test_account_changes_require_password_and_exact_authenticated_identity(application,monkeypatch):
    """Never permit credentials changes with just a persistent app cookie."""
    from cloud import auth
    client=login(application)
    seen=[]
    def provider(user_id,email,current_password,change):
        assert str(user_id)==str(IDS['owner@example.test'])
        assert email=='owner@example.test'
        assert current_password=='valid-password'
        seen.append(change)
        return True
    monkeypatch.setattr(auth,'update_verified_account',provider)
    call(client,'POST','/api/account/email',{'current_password':'bad',
        'email':'new@example.test'},400)
    call(client,'POST','/api/account/password',{'current_password':'valid-password',
        'new_password':'valid-password'},400)
    call(client,'POST','/api/account/email',{'current_password':'valid-password',
        'email':'not-an-address'},400)
    good=call(client,'POST','/api/account/email',{'current_password':'valid-password',
        'email':'new@example.test'},200).json
    assert good['pending_confirmation'] is True
    other=call(client,'POST','/api/account/password',{
        'current_password':'valid-password','new_password':'another-strong-password'},200).json
    assert other['pending_confirmation'] is False
    assert seen==[{'email':'new@example.test'},{'password':'another-strong-password'}]
    call(application.test_client(),'POST','/api/account/password',
         {'current_password':'valid-password','new_password':'another-strong-password'},401)


@pytest.mark.browser
def test_browser_social_tabs_cache_notification_bell_and_mobile_heading(browser_http):
    """Same social DOM node and zero redundant API calls on tab return."""
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            page.goto(browser_http+'/')
            browser_login(page)
            expect(page.locator('.dashboard-metrics')).to_have_count(0)
            expect(page.locator('header .header-bell')).to_be_visible()
            expect(page.locator('header .nav [data-nav="/notifications"]')).to_have_count(0)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            page.wait_for_function("() => typeof ownerWarmupReady !== 'undefined' && ownerWarmupReady && !socialUnreadBusy",timeout=15000)
            requests=[]
            page.on('request',lambda r: requests.append(r.url.split('?')[0])
                    if '/api/friends' in r.url or '/api/profile/me' in r.url else None)
            page.locator('header [data-nav="/friends"]').click()
            expect(page.locator('main h1')).to_have_text('Друзья')
            expect(page.locator('.social-search h2')).to_have_text('Найти друга')
            page.locator('main').evaluate("(el)=>el.dataset.sameNode='friends'")
            page.locator('header .nav [data-nav="/profile"]').click()
            expect(page.locator('main h1').first).to_have_text('Мой профиль')
            expect(page.locator('.emoji-avatar').first).to_be_visible()
            page.locator('header .header-bell').click()
            expect(page.get_by_role('dialog',name='Уведомления')).to_be_visible()
            expect(page.locator('[data-notification-tab]')).to_have_count(4)
            expect(page.locator('main h1').first).to_have_text('Мой профиль')
            page.keyboard.press('Escape')
            page.locator('header [data-nav="/friends"]').click()
            expect(page.locator('main')).to_have_attribute('data-same-node','friends')
            assert sum('/api/friends' in u for u in requests)==0,requests
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_santa_preferences_readonly_until_edit_and_mobile_density(browser_http):
    """Editor remains closed until requested and saves inline without whole-page render."""
    from playwright.sync_api import sync_playwright, expect
    from uuid import uuid4
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':375,'height':760})
            page.goto(browser_http+'/')
            browser_login(page)
            page.locator('button[data-open="santa"]').first.click()
            page.locator('#fld-title').fill('Mobile preferences '+uuid4().hex[:6])
            page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
            expect(page).to_have_url(__import__('re').compile(r'/santa/\d+$'))
            expect(page.locator('#santa-preferences-display')).to_be_visible()
            expect(page.locator('#santa-preferences-form')).to_be_hidden()
            expect(page.locator('#santa-preferences-display')).to_contain_text('Что хотелось бы')
            expect(page.locator('#santa-preferences-display')).to_contain_text('Чего не хотелось бы')
            page.locator('#santa-preferences-display > button[data-action="edit-santa-preferences"]').click()
            expect(page.locator('#santa-preferences-form')).to_be_visible()
            expect(page.locator('#santa-preferences-display')).to_be_hidden()
            page.locator('#santa-preferences-form [name="wanted"]').fill('Настольные игры')
            page.locator('#santa-preferences-form [name="unwanted"]').fill('Настойки')
            page.locator('#santa-preferences-form button[type="submit"]').click()
            expect(page.locator('#santa-preferences-form')).to_be_hidden()
            expect(page.locator('#santa-preferences-display')).to_contain_text('Настольные игры')
            expect(page.locator('#santa-preferences-display')).to_contain_text('Настойки')
            expect(page.locator('#santa-preferences-display > button')).to_contain_text('Редактировать')
            expect(page.locator('#santa-preferences-display .santa-pref-row')).to_have_count(2)
            expect(page.locator('#santa-preferences-display')).to_contain_text('Настойки')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            assert page.evaluate('document.querySelector("#game-chat").getBoundingClientRect().width <= innerWidth')
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_guest_member_claim_after_email_confirmation_and_manual_link(browser_http,monkeypatch):
    """A personal link, not a name, binds the guest after verified signup."""
    from cloud import auth
    from playwright.sync_api import sync_playwright,expect
    from uuid import uuid4
    def verified(token):
        assert token=='header.payload.signature'
        return {'id':str(IDS['owner@example.test']),
                'email':'owner@example.test','email_confirmed_at':'2026-11-20T00:00:00Z',
                'user_metadata':{'name':'Owner'}}
    monkeypatch.setattr(auth,'verified_user',verified)
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            organizer=browser.new_page()
            organizer.goto(browser_http+'/')
            browser_login(organizer,'other@example.test')
            def new_guest():
                title='Guest membership '+uuid4().hex[:8]
                event=organizer.evaluate("""async title => {
                  const r=await fetch('/api/santas',{method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({title})});
                  if(!r.ok)throw Error('Could not create fixture');
                  return await r.json();
                }""",title)
                participant=organizer.evaluate("""async id => {
                  const r=await fetch('/api/santas/'+id+'/participants',{method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({name:'Приглашённый гость'})});
                  if(!r.ok)throw Error('Could not create guest fixture');
                  return await r.json();
                }""",event['id'])
                return event['id'],participant['participant_token']
            first_id,personal=new_guest()
            guest_ctx=browser.new_context()
            guest=guest_ctx.new_page()
            guest.goto(browser_http+'/p/'+personal)
            expect(guest.locator('[data-action="claim-game"]')).to_be_visible()
            assert guest.evaluate("sessionStorage.getItem('shursh-pending-game-claim')") is None
            guest.locator('[data-action="claim-game"]').click()
            expect(guest.get_by_role('dialog')).to_contain_text('С возвращением!')
            guest.locator('[data-open="register"]').click()
            expect(guest.get_by_role('dialog')).to_contain_text('Давай знакомиться!')
            # Pending token stays within the tab until registration actually succeeds.
            assert guest.evaluate("localStorage.getItem('shursh-pending-game-claim')") is None
            guest.locator('#fld-name').fill('Гость')
            guest.locator('#fld-email').fill('owner@example.test')
            guest.locator('#fld-password').fill('Valid-new-password7')
            guest.locator('#fld-confirm_password').fill('Valid-new-password7')
            guest.locator('.modal-fixed-footer button[type="submit"]').click()
            expect(guest.get_by_role('dialog')).to_contain_text('Проверь почту')
            assert guest.evaluate("!!localStorage.getItem('shursh-pending-game-claim')")
            # Opening confirmation in a new tab must recover the pending membership.
            confirmed=guest_ctx.new_page()
            confirmed.goto(browser_http+'/#access_token=header.payload.signature&type=signup')
            expect(confirmed.locator('.dashboard-page h1')).to_contain_text('Owner')
            confirmed.wait_for_function("""async id => {
               const r=await fetch('/api/santas');
               return r.ok&&(await r.json()).events.some(x=>x.id===id);
            }""",arg=first_id,timeout=15000)
            assert confirmed.evaluate("localStorage.getItem('shursh-pending-game-claim')") is None
            assert confirmed.evaluate("sessionStorage.getItem('shursh-pending-game-claim')") is None
            # Separately linked games can also be restored after registration.
            second_id,second_token=new_guest()
            confirmed.goto(browser_http+'/santas')
            expect(confirmed.get_by_role('button',name='Привязать игру по ссылке')).to_be_visible()
            confirmed.get_by_role('button',name='Привязать игру по ссылке').click()
            field=confirmed.locator('#fld-personal_link')
            field.fill('https://other.example/p/'+second_token)
            confirmed.locator('.modal-fixed-footer button[type="submit"]').click()
            expect(confirmed.locator('.toast')).to_contain_text('с этого сайта')
            assert not confirmed.evaluate("""async id =>
               (await(await fetch('/api/santas')).json()).events.some(x=>x.id===id)
            """,second_id)
            field.fill(browser_http+'/p/'+second_token)
            confirmed.locator('.modal-fixed-footer button[type="submit"]').click()
            confirmed.wait_for_function("""async id => {
                const r=await fetch('/api/santas');
                return r.ok&&(await r.json()).events.some(x=>x.id===id);
            }""",arg=second_id,timeout=15000)
            expect(confirmed.locator('.santa-grid')).to_contain_text('Guest membership')
            # Direct sign-in from a private game page must also work when
            # the guest uses the ordinary header instead of the explicit CTA.
            third_id,third_token=new_guest()
            another_ctx=browser.new_context()
            another=another_ctx.new_page()
            another.goto(browser_http+'/p/'+third_token)
            assert another.evaluate("sessionStorage.getItem('shursh-pending-game-claim')") is None
            another.locator('header button[data-open="login"]').click()
            expect(another.get_by_role('dialog')).to_contain_text('После входа сохраним эту игру')
            another.locator('#fld-email').fill('owner@example.test')
            another.locator('#fld-password').fill('valid-password')
            another.locator('.modal-fixed-footer button[type="submit"]').click()
            another.wait_for_function("""async id => {
                const response=await fetch('/api/santas');
                return response.ok&&(await response.json()).events.some(e=>e.id===id);
            }""",arg=third_id,timeout=15000)
            another.wait_for_function("() => sessionStorage.getItem('shursh-pending-game-claim')===null",timeout=15000)
            another_ctx.close()
            # No bearer link is left behind after a successful claim.
            assert confirmed.evaluate("localStorage.getItem('shursh-pending-game-claim')") is None
            assert '/p/' not in confirmed.url
            guest_ctx.close()
        finally:
            browser.close()



def test_finished_santa_state_and_mutual_friend_games(application):
    """Finishing freezes the lifecycle but preserves assignments and mutual visibility."""
    from uuid import uuid4
    owner=login(application)
    member=login(application,'other@example.test')
    owner_id=str(IDS['owner@example.test'])
    member_id=str(IDS['other@example.test'])
    friendship=call(owner,'GET','/api/friends').json
    if not any(str(x['id'])==member_id for x in friendship['friends']):
        if any(str(x['id'])==member_id for x in friendship['incoming']):
            call(owner,'PATCH',f'/api/friends/{member_id}',{'action':'accept'})
        else:
            if not any(str(x['id'])==member_id for x in friendship['outgoing']):
                call(owner,'POST',f'/api/friends/{member_id}',{},200)
            call(member,'PATCH',f'/api/friends/{owner_id}',{'action':'accept'})
    eid=call(owner,'POST','/api/santas',{'title':'Close game '+uuid4().hex[:8]},201).json['id']
    other=call(owner,'POST','/api/santas',{'title':'Not shared '+uuid4().hex[:8]},201).json['id']
    assert not any(g['id']==eid for g in call(owner,'GET',f'/api/users/{member_id}').json['shared_games'])
    assert not any(g['id']==other for g in call(member,'GET',f'/api/users/{owner_id}').json['shared_games'])
    # An unplayed game can now be archived without generating assignments.
    unplayed=call(owner,'POST','/api/santas',
                  {'title':'Unplayed '+uuid4().hex[:8]},201).json['id']
    call(member,'POST',f'/api/santas/{unplayed}/finish',{},404)
    call(owner,'POST',f'/api/santas/{unplayed}/finish',{},200)
    unplayed_result=call(owner,'GET',f'/api/santas/{unplayed}').json
    assert unplayed_result['event']['status']=='finished'
    assert unplayed_result['my_assignment'] is None
    call(owner,'POST',f'/api/santas/{unplayed}/draw',{},409)
    call(member,'DELETE',f'/api/santas/{unplayed}',status=404)
    call(owner,'DELETE',f'/api/santas/{unplayed}')
    call(owner,'GET',f'/api/santas/{unplayed}',status=404)
    call(member,'POST',f'/api/santas/{eid}/finish',{},404)
    key=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    call(member,'POST',f'/api/invites/{key}/join',{'name':'Other'},201)
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Extra guest'},201)
    games=call(member,'GET',f'/api/users/{owner_id}').json['shared_games']
    assert any(g['id']==eid for g in games)
    assert all(g['id']!=other for g in games)
    call(owner,'POST',f'/api/santas/{eid}/draw',{},200)
    assigned=call(owner,'GET',f'/api/santas/{eid}').json['my_assignment']
    assert assigned is not None
    call(owner,'POST',f'/api/santas/{eid}/finish',{},200)
    assert call(owner,'POST',f'/api/santas/{eid}/finish',{},200).json['already_finished']
    finished=call(owner,'GET',f'/api/santas/{eid}').json
    assert finished['event']['status']=='finished'
    assert finished['my_assignment']==assigned
    assert call(member,'GET',f'/api/member/{eid}').json['event']['status']=='finished'
    assert any(g['id']==eid and g['status']=='finished'
               for g in call(member,'GET',f'/api/users/{owner_id}').json['shared_games'])
    call(owner,'POST',f'/api/santas/{eid}/draw',{},409)
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Too late'},409)


def test_private_finished_santa_memory_upload_and_no_public_leak(application):
    from server import token
    owner=login(application)
    member=login(application,'other@example.test')
    anonymous=application.test_client()
    title='Photo memory '+token()[:8]
    eid=call(owner,'POST','/api/santas',{'title':title},201).json['id']
    base=f'/api/santas/{eid}/memory'
    invite=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    guest_link=call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Guest'},201).json['participant_token']
    call(owner,'POST',base,{'image_data':PNG},404)
    call(owner,'PUT',base,{'image_data':PNG},409)
    call(owner,'GET',base,status=409)
    call(member,'GET',base,status=404)
    member_link=call(member,'POST',f'/api/invites/{invite}/join',{'name':'Member'},201).json['event_id']
    call(owner,'POST',f'/api/santas/{eid}/draw',{},200)
    call(owner,'POST',f'/api/santas/{eid}/finish',{},200)
    assert call(owner,'GET',base).json['memory'] is None
    assert call(anonymous,'GET',f'/api/participant/{guest_link}/memory').json['memory'] is None
    call(anonymous,'PUT',base,{'image_data':PNG},401)
    call(member,'PUT',base,{'image_data':PNG},403)
    call(anonymous,'GET',f'/api/participant/{token()}/memory',status=404)
    photo='data:image/png;base64,'+base64.b64encode(
        base64.b64decode(PNG.split(',',1)[1])+b'photo-fixture'*8).decode()
    assert call(owner,'PUT',base,{'image_data':photo}).json=={'ok':True}
    assert call(owner,'PUT',base,{'image_data':photo}).json=={'ok':True}
    assert call(member,'GET',f'/api/member/{eid}/memory').json['memory']['image_data']==photo
    assert call(anonymous,'GET',f'/api/participant/{guest_link}/memory').json['memory']['image_data']==photo
    assert call(owner,'GET',base).json['can_edit'] is True
    assert call(member,'GET',base).json['can_edit'] is False
    assert photo not in str(call(owner,'GET',f'/api/santas/{eid}').json)
    assert photo not in str(call(owner,'GET','/api/dashboard').json)
    call(member,'DELETE',base,status=404)


def test_db_persisted_admin_permission_is_identity_scoped(application,monkeypatch):
    monkeypatch.delenv('SHURSH_ADMIN_EMAILS',raising=False)
    owner=login(application)
    other=login(application,'other@example.test')
    assert call(other,'GET','/api/admin/overview',status=403).status_code==403
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('INSERT INTO public.site_admins(user_id) VALUES(%s) ON CONFLICT DO NOTHING',
                    (IDS['owner@example.test'],))
    try:
        role=login(application)
        assert call(role,'GET','/api/me').json['user']['is_admin'] is True
        assert call(role,'GET','/api/admin/overview').json['stats']['users']>=2
        call(other,'GET','/api/admin/feedback',status=403)
    finally:
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            con.execute('DELETE FROM public.site_admins WHERE user_id=%s',(IDS['owner@example.test'],))
    assert call(login(application),'GET','/api/me').json['user']['is_admin'] is False


def test_santa_finish_can_store_optional_webp_atomically(application):
    """A photo failure must not silently complete a game; no public photo leaks."""
    from uuid import uuid4
    owner=login(application)
    stranger=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Atomic photo '+uuid4().hex[:8]},201).json['id']
    for label in ('Guest A','Guest B'):
        call(owner,'POST',f'/api/santas/{eid}/participants',{'name':label},201)
    call(owner,'POST',f'/api/santas/{eid}/draw',{},200)
    endpoint=f'/api/santas/{eid}/finish'
    wrong=call(owner,'POST',endpoint,{'image_data':PNG},400)
    assert 'WebP' in wrong.json['error']
    assert call(owner,'GET',f'/api/santas/{eid}').json['event']['status']=='drawn'
    webp='data:image/webp;base64,UklGRm4AAABXRUJQVlA4IGIAAABwAgCdASoQABAAAoBCJbACdH8D2HQYpXUXjD8AAP77IWDmzt26izyt8eYKFcTtb3XnAkGE+9epPGxyqy+v1gLcFDH4nfz/zkEhMSQ/HhVx/d+JHYr9yBD/Rbv3+sws+CAAAA=='
    finished=call(owner,'POST',endpoint,{'image_data':webp},200).json
    assert finished['already_finished'] is False
    assert call(owner,'GET',f'/api/santas/{eid}/memory').json['memory']['image_data']==webp
    assert call(stranger,'GET',f'/api/santas/{eid}/memory',status=404).status_code==404
    assert webp not in str(call(owner,'GET','/api/dashboard').json)
    call(owner,'POST',endpoint,{'image_data':webp},409)
    assert call(owner,'POST',endpoint,{},200).json['already_finished'] is True


@pytest.mark.browser
def test_mobile_auth_header_marquee_footer_and_warm_focus(browser_http):
    """Regression coverage for condensed guest header and all three auth modals."""
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            for width in (375,390):
                page=browser.new_page(viewport={'width':width,'height':760})
                page.goto(browser_http+'/')
                page.evaluate('window.scrollTo(0,260)')
                expect(page.locator('.site-header')).to_have_class(re.compile(r'is-condensed'))
                login=page.locator('header button[data-open="login"]')
                expect(login).to_be_visible()
                expect(login).to_have_text('Войти')
                metrics=login.evaluate("""el => {
                  const css=getComputedStyle(el),rect=el.getBoundingClientRect();
                  return {font:parseFloat(css.fontSize),height:rect.height,
                          inside:rect.left>=0&&rect.right<=innerWidth+1}
                }""")
                assert metrics['font']>=13 and metrics['height']>=44 and metrics['inside'],metrics
                duration=page.locator('.marquee-line .marquee-inner').evaluate(
                    "el => getComputedStyle(el).animationDuration")
                assert duration=='19s',duration
                login.click()

                def check_auth_footer():
                    expect(page.locator('.modal-fixed-footer .form-actions')).to_be_visible()
                    foot=page.locator('.modal-fixed-footer .form-actions + .modal-foot')
                    expect(foot).to_be_visible()
                    margin=foot.evaluate("el=>parseFloat(getComputedStyle(el).marginTop)")
                    compact=page.locator('.modal[data-auth-screen]').count()>0
                    assert (10<=margin<=12 if compact else margin>=18),margin
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')

                check_auth_footer()
                mail=page.locator('#fld-email')
                mail.click()
                assert mail.evaluate(
                    "el=>getComputedStyle(el).backgroundColor")=='rgb(255, 249, 233)'
                page.locator('.modal-foot [data-open="register"]').click()
                expect(page.get_by_role('dialog')).to_contain_text('Давай знакомиться!')
                check_auth_footer()
                page.locator('.modal-foot [data-open="login"]').click()
                check_auth_footer()
                page.locator('.modal-foot [data-open="resend"]').click()
                check_auth_footer()
                page.close()
        finally:
            browser.close()


def test_personal_santa_invites_require_login_and_are_single_use(application):
    """PostgreSQL/RLS: capability invitation creates no guest slot and cannot be replayed."""
    owner=login(application)
    other=login(application,'other@example.test')
    anonymous=application.test_client()
    eid=call(owner,'POST','/api/santas',{'title':'Private invitation enforcement'},201).json['id']
    event=call(owner,'GET',f'/api/santas/{eid}').json['event']
    assert len(call(owner,'GET',f'/api/santas/{eid}').json['participants'])==1
    call(other,'POST',f'/api/santas/{eid}/personal-invites',{},404)
    created=call(owner,'POST',f'/api/santas/{eid}/personal-invites',{},201).json
    value=created['invite_token']
    assert len(value)==43
    assert len(call(owner,'GET',f'/api/santas/{eid}').json['participants'])==1
    info=call(anonymous,'GET',f'/api/personal-invites/{value}').json
    assert info['used'] is False and info['event']['title']=='Private invitation enforcement'
    assert info['event_id']==eid
    call(anonymous,'POST',f'/api/personal-invites/{value}/join',{'name':'Незарегистрированный'},401)
    call(anonymous,'POST',f'/api/invites/{event["invite_key"]}/join',{'name':'Незарегистрированный'},401)
    accepted=call(other,'POST',f'/api/personal-invites/{value}/join',{'name':'Пользователь'},201).json
    assert accepted['event_id']==eid
    assert call(other,'GET',f'/api/member/{eid}').json['participant']['name']=='Пользователь'
    assert call(anonymous,'GET',f'/api/personal-invites/{value}').json['used'] is True
    call(owner,'POST',f'/api/personal-invites/{value}/join',{'name':'Повтор'},409)
    assert len(call(owner,'GET',f'/api/santas/{eid}').json['participants'])==2
    call(other,'POST',f'/api/invites/{event["invite_key"]}/join',{'name':'Дубликат'},409)

@pytest.mark.browser
def test_browser_registered_santa_join_from_shared_and_personal_links(browser_http):
    """A personal invitation is one-time; guest sees login gate; name belongs to the account."""
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            owner=browser.new_page(viewport={'width':390,'height':844})
            owner.goto(browser_http+'/')
            browser_login(owner)
            created=owner.evaluate("""async () => {
                const response=await fetch('/api/santas',{method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({title:'Registered personal browser game'})});
                if(!response.ok)throw Error('Game fixture creation failed');
                return await response.json();
            }""")
            eid=created['id']
            personal=owner.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id+'/personal-invites',{
                    method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
                if(!response.ok)throw Error('Personal invite creation failed');
                return await response.json();
            }""",eid)
            invite_url=browser_http+'/join/p/'+personal['invite_token']
            guest=browser.new_page(viewport={'width':375,'height':760})
            guest.goto(invite_url)
            expect(guest.locator('.invite-auth-gate')).to_be_visible()
            expect(guest.locator('#join-form')).to_have_count(0)
            browser_login(guest,'other@example.test',landing='invite')
            expect(guest.locator('#join-form')).to_be_visible()
            guest.locator('#join-name').fill('Новый игрок')
            guest.locator('#join-form button[type="submit"]').click()
            expect(guest).to_have_url(re.compile(r'/santa/\d+$'))
            expect(guest.locator('.person-list')).to_contain_text('Новый игрок')
            assert owner.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id);
                return (await response.json()).participants.length;
            }""",eid)==2
            # A private invite cannot be redeemed by another account after use.
            observer=browser.new_page()
            observer.goto(invite_url)
            expect(observer.locator('.invite-card')).to_contain_text('уже использована')
            game=owner.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id);
                return (await response.json()).event;
            }""",eid)
            other_event=owner.evaluate("""async () => {
                const response=await fetch('/api/santas',{method:'POST',
                   headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({title:'Shared invite game'})});
                return await response.json();
            }""")
            other_id=other_event['id']
            share=owner.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id);
                return (await response.json()).event.invite_key;
            }""",other_id)
            other_guest=browser.new_page(viewport={'width':390,'height':844})
            other_guest.goto(browser_http+'/join/'+share)
            expect(other_guest.locator('.invite-auth-gate')).to_be_visible()
            browser_login(other_guest,'other@example.test',landing='invite')
            expect(other_guest.locator('#join-form')).to_be_visible()
            other_guest.locator('#join-name').fill('Участник общей ссылки')
            other_guest.locator('#join-form button[type="submit"]').click()
            expect(other_guest).to_have_url(re.compile(r'/santa/\d+$'))
            assert other_guest.url.endswith('/santa/'+str(other_id))
        finally:
            browser.close()


def test_flask_serves_one_time_personal_santa_deep_link(application):
    """The Flask SPA allowlist must serve the new nested /join/p/<token> route."""
    secret='A'*43
    page=application.test_client().get('/join/p/'+secret)
    assert page.status_code==200
    assert b'/app.js' in page.data
    bad=application.test_client().get('/join/p/not-43-chars')
    assert bad.status_code==404


def test_admin_user_directory_is_paginated_and_only_for_site_admin(application,monkeypatch):
    """Admin directory never exposes passwords, emails or other private content."""
    monkeypatch.delenv('SHURSH_ADMIN_EMAILS',raising=False)
    anon=application.test_client()
    user=login(application,'other@example.test')
    manager=login(application)
    call(anon,'GET','/api/admin/users',status=401)
    call(user,'GET','/api/admin/users',status=403)
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    result=call(manager,'GET','/api/admin/users').json
    assert result['limit']==25 and result['offset']==0 and result['total']>=2
    allowed={'id','name','handle','avatar_emoji','created_at','discoverable',
             'wishlists_count','organized_games','joined_games','last_seen_at','last_platform','last_seen_source'}
    assert all(set(u)==allowed for u in result['users'])
    assert all('@example.test' not in str(u) for u in result['users'])
    assert call(manager,'GET','/api/admin/users?q=owner').json['total']>=1
    assert call(manager,'GET','/api/admin/users?offset=10000').json['users']==[]
    call(manager,'GET','/api/admin/users?offset=-1',status=400)
    call(manager,'GET','/api/admin/users?offset=10001',status=400)
    call(manager,'GET','/api/admin/users?q='+'a'*51,status=400)
    call(user,'GET','/api/admin/overview',status=403)


def test_admin_directory_profile_link_does_not_bypass_private_content(application,monkeypatch):
    monkeypatch.delenv('SHURSH_ADMIN_EMAILS',raising=False)
    manager=login(application)
    hidden=login(application,'other@example.test')
    uid=str(IDS['other@example.test'])
    # The integration suite shares its disposable DB; explicitly establish
    # non-friend access before testing the administrator exception.
    call(manager,'DELETE','/api/friends/'+uid,{})
    call(hidden,'PATCH','/api/profile/me',{'discoverable':True})
    assert call(manager,'GET','/api/users/'+uid).json['relationship']=='none'
    call(hidden,'PATCH','/api/profile/me',{'discoverable':False,'bio':'Private bio','city':'Private city'})
    call(hidden,'POST','/api/lists',{'title':'Hidden wish list','visibility':'private'},201)
    call(hidden,'POST','/api/santas',{'title':'Hidden game'},201)
    path='/api/users/'+uid
    call(application.test_client(),'GET',path,status=401)
    call(manager,'GET',path,status=404)
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    data=call(manager,'GET',path).json
    assert data['relationship']=='admin_directory'
    assert data['profile']['id']==uid
    assert data['profile']['bio']==data['profile']['city']==''
    assert data['lists']==data['shared_games']==[]
    assert 'email' not in str(data) and 'Private bio' not in str(data)
    assert not any(u['id']==uid for u in call(manager,'GET','/api/users/search?q=Other').json['users'])
    monkeypatch.delenv('SHURSH_ADMIN_EMAILS')
    call(manager,'GET',path,status=404)
    call(hidden,'PATCH','/api/profile/me',{'discoverable':True,'bio':'','city':''})


def test_cross_user_wishlist_santa_and_capability_isolation(application):
    """BOLA/IDOR: sequential IDs cannot access other users' resources."""
    owner=login(application)
    outsider=login(application,'other@example.test')
    anon=application.test_client()
    eid=call(owner,'POST','/api/santas',{'title':'Private game IDOR'},201).json['id']
    lid=call(owner,'POST','/api/lists',{'title':'Private list IDOR','visibility':'private'},201).json['id']
    wid=call(owner,'POST',f'/api/lists/{lid}/wishes',{'title':'Secret gift'},201).json['id']
    share=call(owner,'GET',f'/api/lists/{lid}').json['list']['share_key']
    for path in (f'/api/santas/{eid}',f'/api/santas/{eid}/roster',
                 f'/api/santas/{eid}/my-wishes',f'/api/santas/{eid}/memory',
                 f'/api/member/{eid}',f'/api/member/{eid}/roster',
                 f'/api/member/{eid}/wishes',f'/api/member/{eid}/messages/general',
                 f'/api/lists/{lid}'):
        call(outsider,'GET',path,status=404)
    call(anon,'GET',f'/api/santas/{eid}',status=401)
    call(anon,'GET',f'/api/member/{eid}',status=401)
    call(outsider,'POST',f'/api/santas/{eid}/my-wishes',{'title':'Injected'},404)
    call(outsider,'POST',f'/api/santas/{eid}/draw',{},404)
    call(outsider,'DELETE',f'/api/santas/{eid}',status=404)
    call(outsider,'PATCH',f'/api/wishes/{wid}',{'title':'Hijacked'},404)
    call(outsider,'DELETE',f'/api/wishes/{wid}',status=404)
    call(anon,'GET',f'/api/public/{share}',status=404)
    call(outsider,'GET',f'/api/public/{share}',status=404)
    call(outsider,'POST',f'/api/public/{share}/reserve/{wid}',{},404)
    assert call(owner,'GET',f'/api/lists/{lid}').json['wishes'][0]['title']=='Secret gift'


def test_claimed_guest_capability_requires_same_registered_identity(application):
    """A copied bearer link may not bypass UID after the guest seat is claimed."""
    organizer=login(application,'other@example.test')
    member=login(application)
    anonymous=application.test_client()
    eid=call(organizer,'POST','/api/santas',{'title':'Claimed bearer privacy'},201).json['id']
    created=call(organizer,'POST',f'/api/santas/{eid}/participants',
                {'name':'Guest fixture'},201).json
    bearer=created['participant_token']
    assert call(anonymous,'GET',f'/api/participant/{bearer}').status_code==200
    call(member,'POST',f'/api/participant/{bearer}/claim',{},200)
    for path in (f'/api/participant/{bearer}',f'/api/participant/{bearer}/roster'):
        call(anonymous,'GET',path,status=404)
        call(organizer,'GET',path,status=404)
        call(member,'GET',path,status=404)
    call(anonymous,'POST',f'/api/participant/{bearer}/wishes',{'title':'Hijacked'},404)
    call(organizer,'PATCH',f'/api/participant/{bearer}/preferences',
         {'wanted':'Hijacked'},404)
    assert call(member,'GET',f'/api/member/{eid}').json['participant']['name']=='Guest fixture'
    call(organizer,'POST',f'/api/santas/{eid}/participants/{created["id"]}/new-link',{},409)


def test_social_meta_profile_and_legacy_link_ux_static(application):
    """Prevent markup regressions on invite URLs, metadata and buttons."""
    html=application.test_client().get('/').get_data(as_text=True)
    js=application.test_client().get('/app.js').get_data(as_text=True)
    social=application.test_client().get('/social-ui.js').get_data(as_text=True)
    assert 'property="og:title"' in html and 'property="og:description"' in html
    assert 'место для хотелок и сюрпризов' not in html
    assert 'Тайный Санта ' + '$' + '{ico("plus")}' not in js
    assert 'memberView&&participantToken&&!d.participant.user_id' in js
    assert 'data-nav="/profile" aria-label="Открыть профиль"' in js
    assert 'async function socialEditAvatarModal' in social


@pytest.mark.browser
def test_browser_ux_fixes_avatar_gift_placeholder_and_admin_directory(browser_http,monkeypatch,application):
    """Real Chromium interaction for the new avatar picker, Santa fallback and admin table."""
    from playwright.sync_api import sync_playwright,expect
    from uuid import uuid4
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    other=login(application,'other@example.test')
    call(other,'PATCH','/api/profile/me',{'discoverable':False,'bio':'Hidden profile text'})
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            page.set_default_timeout(15000)
            page.goto(browser_http+'/')
            browser_login(page)
            expect(page.locator('.santa-create-cta')).not_to_contain_text('ico')
            assert page.locator('.santa-create-cta svg.icon').count()==1
            assert page.locator('.dashboard-welcome .welcome-name').evaluate(
                "el => getComputedStyle(el).whiteSpace")=='nowrap'

            event=page.evaluate("""async name => {
                const response=await fetch('/api/santas',{method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({title:name})});
                if(!response.ok)throw Error('Game fixture failed');
                return await response.json();
            }""",'UI regression '+uuid4().hex[:8])
            eid=event['id']
            page.goto(browser_http+'/santa/'+str(eid))
            expect(page.locator('button[data-action="add-game-gift"]')).to_be_visible()
            page.locator('button[data-action="add-game-gift"]').click()
            page.locator('#fld-title').fill('Подарок без фото')
            page.locator('#fld-shop_url').fill('https://example.com/gift')
            page.locator('.modal-fixed-footer button[type="submit"]').click()
            expect(page.locator('.game-gift-card .game-gift-placeholder svg')).to_be_visible()
            page.locator('.game-gift-primary').first.click()
            expect(page.locator('.gift-details-modal .gift-dialog-fallback svg')).to_be_visible()
            edit_icon=page.locator('.gift-details-modal .gift-dialog-edit')
            expect(edit_icon).to_be_visible()
            expect(edit_icon.locator('svg.icon')).to_have_count(1)
            assert edit_icon.get_attribute('aria-label')=='Изменить подарок'
            assert page.locator('.gift-details-modal .gift-dialog-footer [data-action="edit-game-gift"]').count()==0
            shop=page.locator('.gift-details-modal .gift-dialog-copy > a.btn')
            expect(shop).to_be_visible()
            for width in (390,1280):
                page.set_viewport_size({'width':width,'height':844})
                edges=page.locator('.gift-details-modal').evaluate("""dialog => {
                    const right = selector => {
                        const el = dialog.querySelector(selector);
                        return el?.getBoundingClientRect().right;
                    };
                    return {
                        edit:right('.gift-dialog-edit'),
                        shop:right('.gift-dialog-copy > a.btn'),
                        close:right('.gift-dialog-footer [data-close]'),
                        content:right('.gift-dialog-layout')
                    };
                }""")
                assert all(isinstance(v,(int,float)) for v in edges.values()),(width,edges)
                assert abs(edges['edit']-edges['shop'])<=2,(width,edges)
                assert abs(edges['edit']-edges['close'])<=2,(width,edges)
                assert abs(edges['edit']-edges['content'])<=2,(width,edges)
            page.set_viewport_size({'width':390,'height':844})
            close=page.locator('.gift-details-modal .gift-dialog-footer .btn-dark')
            close.hover()
            assert close.evaluate("el => getComputedStyle(el).color")=='rgb(255, 255, 255)'
            close.click()
            row=page.locator('.person-row[data-santa-profile]').first
            assert row.count()==1 and row.get_attribute('title') is None
            page.locator('header .header-avatar').click()
            expect(page.locator('.social-page-heading h1')).to_contain_text('Мой профиль')
            page.locator('button.profile-avatar-edit').click()
            expect(page.get_by_role('dialog',name='Изменить аватарку')).to_be_visible()
            page.locator('[data-avatar-pick="🦊"]').click()
            page.locator('.modal-fixed-footer button[type="submit"]').click()
            expect(page.locator('header .header-avatar')).to_have_text('🦊')
            page.goto(browser_http+'/profile')
            expect(page.locator('button.profile-avatar-edit')).to_be_visible()
            page.locator('button.profile-avatar-edit').click()
            expect(page.get_by_role('dialog',name='Изменить аватарку')).to_be_visible()
            page.keyboard.press('Escape')
            page.goto(browser_http+'/admin')
            expect(page.locator('.admin-hub-card')).to_have_count(2)
            assert page.locator('.social-stat-grid').count()==0
            assert page.locator('.admin-users-table').count()==0
            page.locator('.admin-hub-users').click()
            expect(page).to_have_url(re.compile('/admin/users'))
            expect(page.locator('.admin-users-table')).to_be_visible()
            expect(page.locator('.admin-users-panel .panel-heading-actions .chip')).to_have_count(0)
            expect(page.locator('.admin-users-table th')).to_have_text(['Игрок','Ник','Регистрация','Последний визит','Вишлисты','Свои Санты','Участие','В поиске'])
            visit=page.locator('.admin-users-table tbody tr').filter(has_text='Owner').locator('td').nth(3)
            expect(visit.get_by_role('img',name='Linux',exact=True)).to_be_visible()
            expect(visit.locator('svg title')).to_have_text('Linux')
            expect(visit.locator('time')).to_be_visible()
            expect(visit.locator('small')).to_have_count(0)
            # Stripe only the body, preserve the header and existing table layout.
            rows=page.locator('.admin-users-table tbody tr')
            assert rows.count()>=2
            assert rows.nth(1).evaluate("r=>getComputedStyle(r).backgroundColor")=='rgb(250, 247, 242)'
            assert rows.nth(0).evaluate("r=>getComputedStyle(r).backgroundColor")!='rgb(250, 247, 242)'
            assert page.locator('.admin-users-table th').first.evaluate("r=>getComputedStyle(r).backgroundColor")=='rgb(244, 239, 232)'
            # Clicking even the empty right edge of the player cell navigates.
            uid=str(IDS['other@example.test'])
            player=page.get_by_role('link',name='Открыть профиль Other',exact=True)
            expect(player).to_have_attribute('href','/users/'+uid)
            cell=player.locator('..')
            cell.scroll_into_view_if_needed()
            rect=cell.bounding_box()
            cell.click(position={'x':rect['width']-4,'y':rect['height']/2})
            expect(page).to_have_url(browser_http+'/users/'+uid)
            expect(page.locator('main h1')).to_have_text('Other')
            expect(page.locator('.profile-actions')).to_contain_text('Скрыт из поиска')
            expect(page.locator('main')).not_to_contain_text('Hidden profile text')
            expect(page.locator('.profile-bio')).to_have_count(0)
            expect(page.locator('[data-social-action="add"]')).to_have_count(0)
            page.go_back()
            expect(page.locator('.admin-users-table')).to_be_visible()
            own=page.get_by_role('link',name='Открыть профиль Owner',exact=True)
            own.focus()
            expect(own).to_be_focused()
            own.press('Enter')
            expect(page).to_have_url(browser_http+'/users/'+str(IDS['owner@example.test']))
            expect(page.locator('main h1')).to_have_text('Owner')
            page.go_back()
            expect(page.locator('.admin-users-table')).to_be_visible()
            page.locator('#admin-users-query').fill('owner')
            assert page.locator('#admin-users-search button[type="submit"]').count()==0
            expect(page.locator('.admin-users-table tbody')).to_contain_text('Owner',timeout=10000)
            assert '@example.test' not in page.locator('.admin-users-table').inner_text()
            page.locator('#admin-users-query').fill('nonexistent-shursh-player')
            expect(page.locator('.admin-users-table tbody')).to_contain_text('Игроки не найдены',timeout=10000)
            page.locator('.admin-section-back [data-nav="/admin"]').click()
            page.locator('.admin-hub-feedback').click()
            expect(page).to_have_url(re.compile('/admin/feedback'))
            expect(page.locator('main h1')).to_contain_text('Обращения')
            assert page.evaluate("""async () => {
                const response=await fetch('/api/profile/me',{method:'PATCH',
                  headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({avatar_emoji:'🎁'})});
                return response.status;
            }""")==200
        finally:
            browser.close()


def test_favicon_ico_fallback_is_available(application):
    """Static fallback favicon matches the shipped brand and is never a 404."""
    ico=application.test_client().get('/favicon.ico')
    assert ico.status_code==200
    assert ico.data[:4]==b'\x00\x00\x01\x00'
    assert len(ico.data)>500
    svg=application.test_client().get('/favicon.svg')
    assert svg.status_code==200
    html=application.test_client().get('/').get_data(as_text=True)
    assert 'href="/favicon.ico"' in html and 'href="/favicon.svg"' in html


def test_personal_invites_expire_after_24h_and_are_pruned_without_touching_seats(application):
    """Expired unused invite tokens never grant access and are pruned on the next issuance."""
    from server import token_hash
    owner=login(application)
    guest=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'24-hour invite TTL'},201).json['id']
    key=call(owner,'POST',f'/api/santas/{eid}/personal-invites',{},201).json['invite_token']
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute("UPDATE public.santa_personal_invites SET created_at=now()-interval '25 hours' WHERE token_hash=%s",
                    (token_hash(key),))
    call(guest,'GET',f'/api/personal-invites/{key}',status=404)
    call(guest,'POST',f'/api/personal-invites/{key}/join',{'name':'Too late'},404)
    before=call(owner,'GET',f'/api/santas/{eid}').json
    assert len(before['participants'])==1
    call(owner,'POST',f'/api/santas/{eid}/personal-invites',{},201)
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        assert con.execute('SELECT count(*) FROM public.santa_personal_invites WHERE token_hash=%s',
                           (token_hash(key),)).fetchone()[0]==0


def test_owner_can_edit_santa_title_and_description_without_changing_memberships(application):
    owner=login(application)
    other=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Original game'},201).json['id']
    call(other,'PATCH',f'/api/santas/{eid}',{'title':'Takeover'},404)
    call(owner,'PATCH',f'/api/santas/{eid}',{'title':'Новый заголовок','description':'Новое описание'},200)
    event=call(owner,'GET',f'/api/santas/{eid}').json
    assert event['event']['title']=='Новый заголовок'
    assert event['event']['description']=='Новое описание'
    assert len(event['participants'])==1
    call(owner,'PATCH',f'/api/santas/{eid}',{'title':' '},400)
    call(owner,'PATCH',f'/api/santas/{eid}',{'description':'x'*501},400)


def test_notification_settings_are_owner_scoped_and_filter_future_delivery(application):
    from cloud import db, social
    owner=login(application)
    other=login(application,'other@example.test')
    settings=call(owner,'GET','/api/profile/me').json['profile']
    assert all(settings[name] is True for name in social.NOTIFY_FIELDS)
    call(other,'PATCH','/api/profile/me',{'notify_friends':'false'},400)
    updated=call(owner,'PATCH','/api/profile/me',{'notify_friends':False,'notify_santa':True}).json['profile']
    assert updated['notify_friends'] is False
    assert updated['notify_santa'] is True
    with application.test_request_context('/api/test'):
        with db.transaction(write=True) as con:
            social._notify(con,str(IDS['owner@example.test']),'friend_request','suppress-notify-test','/')
            social._notify(con,str(IDS['owner@example.test']),'santa_drawn','allow-notify-test','/')
    data=call(owner,'GET','/api/notifications').json['items']
    assert any(row['message']=='allow-notify-test' for row in data)
    assert not any(row['message']=='suppress-notify-test' for row in data)
    restored=call(owner,'PATCH','/api/profile/me',{'notify_friends':True}).json['profile']
    assert restored['notify_friends'] is True


def test_small_scoped_ui_updates_and_user_settings_source(application):
    js=application.test_client().get('/app.js').get_data(as_text=True)
    social=application.test_client().get('/social-ui.js').get_data(as_text=True)
    css=application.test_client().get('/polish.css').get_data(as_text=True)
    assert "function refreshSantaRules()" in js
    assert 'data-action="toggle-santa-rule-form"' in js
    assert 'data-action="edit-santa-title"' in js
    assert 'data-action="edit-santa-description"' in js
    assert 'function ensureCookieNotice()' in js
    assert 'function shurshCheckbox(' in social
    assert 'new Intl.DateTimeFormat' in social
    assert 'notification-settings-form' in social
    assert '.game-gifts-arrows[hidden]' in css


@pytest.mark.browser
def test_browser_santa_rules_are_collapsed_and_update_without_page_redraw(browser_http):
    """Adding/removing exclusions must preserve the game DOM and chat state."""
    from playwright.sync_api import sync_playwright, expect
    from uuid import uuid4
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            page.set_default_timeout(15000)
            page.goto(browser_http+'/')
            browser_login(page)
            game=page.evaluate("""async name=>{
              const r=await fetch('/api/santas',{method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({title:name})});
              if(!r.ok)throw Error('game fixture failed');
              return await r.json();
            }""",'No-repaint '+uuid4().hex[:7])
            eid=game['id']
            player=page.evaluate("""async id=>{
              const r=await fetch('/api/santas/'+id+'/participants',{method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:'Other gift giver'})});
              if(!r.ok)throw Error('participant fixture failed');
              return await r.json();
            }""",eid)
            guest_id=str(player['id'])
            page.goto(browser_http+'/santa/'+str(eid))
            expect(page.locator('#rule-form')).to_be_hidden()
            page.locator('[data-action="toggle-santa-rule-form"]').first.click()
            expect(page.locator('#rule-form')).to_be_visible()
            giver=page.locator('select[name="giver_id"]')
            recipient=page.locator('select[name="receiver_id"]')
            options=giver.locator('option').evaluate_all('els=>els.map(e=>e.value)')
            owner_id=next(value for value in options if value and value!=guest_id)
            giver.select_option(owner_id)
            recipient.select_option(guest_id)
            page.evaluate("window.__santaStableRoot=document.querySelector('main')")
            page.locator('#rule-form [type="submit"]').click()
            expect(page.locator('#santa-rules-list .rule-chip')).to_have_count(1)
            assert page.evaluate("document.querySelector('main')===window.__santaStableRoot")
            page.locator('#santa-rules-list [data-action="remove-rule"]').click()
            expect(page.locator('#santa-rules-list .rule-chip')).to_have_count(0)
            assert page.evaluate("document.querySelector('main')===window.__santaStableRoot")
            page.locator('[data-action="edit-santa-title"]').click()
            page.locator('input.santa-inline-editor-title').fill('Изменённое название')
            page.locator('input.santa-inline-editor-title').press('Enter')
            expect(page.locator('[data-santa-field="title"]')).to_have_text('Изменённое название')
            assert page.locator('.modal-backdrop').count()==0
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_cookie_notice_has_intrinsic_width_on_mobile_and_desktop(browser_http):
    """Cookie banner hugs its two text lines and button rather than stretching."""
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport_width in (320, 375, 768, 1280):
                page = browser.new_page(viewport={'width': viewport_width, 'height': 720})
                try:
                    page.goto(browser_http, wait_until='domcontentloaded')
                    notice = page.locator('.cookie-notice')
                    expect(notice).to_be_visible()
                    page.evaluate('document.fonts.ready')
                    geometry = notice.evaluate("""element => {
                        const box = element.getBoundingClientRect();
                        const style = getComputedStyle(element);
                        const message = element.querySelector('.cookie-message');
                        const button = element.querySelector('button');
                        const messageBox = message.getBoundingClientRect();
                        const buttonBox = button.getBoundingClientRect();
                        const innerWidth = box.width - parseFloat(style.paddingLeft) -
                            parseFloat(style.paddingRight) - parseFloat(style.borderLeftWidth) -
                            parseFloat(style.borderRightWidth);
                        const gap = parseFloat(style.columnGap) || 0;
                        const desiredInnerWidth = style.flexDirection === 'column'
                            ? Math.max(messageBox.width, buttonBox.width)
                            : messageBox.width + buttonBox.width + gap;
                        return { left: box.left, width: box.width, center: box.left + box.width / 2,
                            viewportWidth: innerWidth, desiredInnerWidth,
                            messageWidth: messageBox.width,
                            lineCount: message.querySelectorAll(':scope > span').length,
                            clipped: [...message.children].some(line => line.scrollWidth > line.clientWidth + 1) };
                    }""")
                    assert abs(geometry['center'] - viewport_width / 2) <= 1, geometry
                    assert geometry['width'] <= viewport_width - (20 if viewport_width <= 400 else 32) + 1, geometry
                    assert abs(geometry['viewportWidth'] - geometry['desiredInnerWidth']) <= 2, geometry
                    assert geometry['lineCount'] == 2 and not geometry['clipped'], geometry
                finally:
                    page.close()
        finally:
            browser.close()


def test_duplicate_signup_provider_outcomes_are_indistinguishable(application,monkeypatch):
    from cloud import auth
    for provider in ({'id':'new-user','identities':[{'id':'new'}]},
                     {'id':'fake-user','identities':[]}):
        monkeypatch.setattr(auth,'auth_request',lambda action, **data: provider)
        client=application.test_client()
        res=call(client,'POST','/api/register',
                 {'name':'Tester','email':'owner@example.test','password':'Valid-new-password7'},202)
        assert res.json=={'user':None,'pending_confirmation':True}
        assert 'Set-Cookie' not in res.headers


def test_typed_duplicate_signup_transport_is_generic(monkeypatch):
    import io
    import json
    from urllib.error import HTTPError
    from cloud import auth
    from server import ApiError
    monkeypatch.delenv('SHURSH_ENV',raising=False)
    monkeypatch.delenv('VERCEL_ENV',raising=False)
    monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.setenv('SUPABASE_URL','https://unit-project.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','sb_publishable_for_test')
    monkeypatch.setenv('SHURSH_AUTH_REDIRECT_URL','https://shursh.fun')
    for code in ('user_already_exists','email_exists','weak_password'):
        def reject(request,timeout):
            raise HTTPError(request.full_url,422,'Rejected',{},io.BytesIO(json.dumps({'error_code':code}).encode()))
        monkeypatch.setattr(auth,'urlopen',reject)
        if code=='weak_password':
            with pytest.raises(ApiError) as exc:
                auth.auth_request('register',email='owner@example.test',password='valid-password')
            assert exc.value.status==400
        else:
            assert auth.auth_request('register',email='owner@example.test',password='valid-password')=={}


def test_ui_release_keeps_legacy_auth(application):
    client=application.test_client()
    assert 'auth_vnext' not in call(client,'GET','/api/me').json
    for route in ('start','verify','finish'):
        call(client,'POST','/api/auth/'+route,{},404)
    assert call(client,'POST','/api/login',{'email':'owner@example.test','password':'valid-password'}).json['user'] is not None


@pytest.mark.parametrize('headers,expected',[
    ({'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},'windows'),
    ({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},'macos'),
    ({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64)'},'linux'),
    ({'User-Agent':'Mozilla/5.0 (Linux; Android 14)'},'android'),
    ({'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)'},'ios'),
    ({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)','X-Shursh-Platform':'ios'},'ios'),
    ({'User-Agent':'Mozilla/5.0 (X11; CrOS x86_64)'},'unknown'),
    ({},'unknown')])
def test_visit_platform_family(headers,expected):
    from cloud.activity import platform_family
    assert platform_family(headers)==expected


def test_admin_last_visit_across_devices(application,monkeypatch):
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    manager=login(application)
    first=application.test_client()
    second=application.test_client()
    credentials={'email':'other@example.test','password':'valid-password'}
    windows={'User-Agent':'Mozilla/5.0 (Windows NT 10.0)'}
    android={'User-Agent':'Mozilla/5.0 (Linux; Android 14)'}
    call(first,'POST','/api/login',credentials,headers=windows)
    def row():
        return next(u for u in call(manager,'GET','/api/admin/users').json['users'] if u['id']==str(IDS['other@example.test']))
    a=row()
    assert a['last_seen_at'] and a['last_platform']=='windows'
    call(second,'POST','/api/login',credentials,headers=android)
    b=row()
    assert b['last_platform']=='android' and b['last_seen_at']>=a['last_seen_at']
    # Ordinary API and guest bootstrap cannot overwrite the last visit.
    call(first,'GET','/api/me',headers=windows)
    call(application.test_client(),'GET','/api/me',headers={**windows,'X-Shursh-Visit':'1'})
    assert row()['last_seen_at']==b['last_seen_at']
    call(first,'GET','/api/dashboard',headers={**windows,'X-Shursh-Visit':'1'})
    c=row()
    assert c['last_platform']=='windows' and c['last_seen_at']>=b['last_seen_at']
    assert 'last_seen_at' not in call(first,'GET','/api/me').json['user']
    call(first,'GET','/api/admin/users',status=403)
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        for role in ('anon','authenticated'):
            assert not con.execute("SELECT has_table_privilege(%s,'public.admin_user_activity','SELECT')",(role,)).fetchone()[0]


@pytest.mark.browser
def test_browser_reveal_for_account_member_owner_and_guest(browser_http,application):
    """All three access modes reveal only their existing assigned recipient."""
    from playwright.sync_api import sync_playwright,expect
    owner=login(application)
    member=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Reveal regression '+uuid4().hex[:8]},201).json['id']
    key=call(owner,'GET',f'/api/santas/{eid}').json['event']['invite_key']
    call(member,'POST',f'/api/invites/{key}/join',{'name':'Member'},201)
    token=call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Guest'},201).json['participant_token']
    call(owner,'POST',f'/api/santas/{eid}/draw',{})
    owner_path=f'/api/santas/{eid}'
    member_path=f'/api/member/{eid}'
    guest_path=f'/api/participant/{token}'
    assert call(owner,'GET',owner_path).json['my_assignment']=={'revealed':False}
    assert call(member,'GET',member_path).json['assignment']=={'revealed':False}
    call(member,'POST',owner_path+'/reveal',{},404)
    call(application.test_client(),'POST',member_path+'/reveal',{},401)
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            for email,route,endpoint in (
                ('other@example.test',f'/santa/{eid}',member_path),
                ('owner@example.test',f'/santa/{eid}',owner_path),
                (None,f'/p/{token}',guest_path)):
                context=browser.new_context(viewport={'width':390,'height':844})
                page=context.new_page()
                if email:
                    page.goto(browser_http+'/')
                    browser_login(page,email)
                page.goto(browser_http+route)
                button=page.locator('button[data-action="reveal"]')
                expect(button).to_be_visible()
                expect(page.locator('.secret-card .recipient')).to_have_count(0)
                # The reveal must patch only its card, not rebuild the game or chat.
                page.locator('[data-chat-room="to-recipient"]').click()
                page.locator('#game-chat-input').fill('Unsent draft')
                button.evaluate("(el)=>el.scrollIntoView({block:'center',behavior:'instant'})")
                page.evaluate("""() => {
                    window.__revealMain=document.querySelector('main');
                    window.__revealChat=document.querySelector('#game-chat');
                    window.__revealPreferences=document.querySelector('#santa-preferences-form');
                    window.__revealScroll=window.scrollY;
                }""")
                assert page.evaluate('window.__revealScroll>0')
                requests=[]
                detail_reads=[]
                page.on('request',lambda req: detail_reads.append(True)
                        if req.method=='GET' and req.url==browser_http+endpoint else None)
                page.on('request',lambda req: requests.append(req.url.rsplit('/reveal',1)[0]==browser_http+endpoint)
                        if req.method=='POST' and req.url.endswith('/reveal') else None)
                with page.expect_response(lambda res: res.url==browser_http+endpoint+'/reveal' and res.request.method=='POST') as pending:
                    button.click()
                assert pending.value.status==200
                assigned=pending.value.json()['assignment']
                assert assigned['revealed'] is True
                expect(page.locator('.secret-card .recipient')).to_have_text(assigned['receiver_name'])
                assert requests==[True]
                assert not detail_reads
                assert page.evaluate("""() => window.__revealMain===document.querySelector('main')
                    && window.__revealChat===document.querySelector('#game-chat')
                    && window.__revealPreferences===document.querySelector('#santa-preferences-form')""")
                expect(page.locator('#game-chat-input')).to_have_value('Unsent draft')
                expect(page.locator('[data-chat-room="to-recipient"]')).to_have_attribute('aria-pressed','true')
                assert page.evaluate("""() => window.scrollY>0 && Math.abs(window.scrollY-
                    Math.min(window.__revealScroll,document.documentElement.scrollHeight-innerHeight))<=8""")
                expect(page.locator('.secret-card [data-action="edit-santa-preferences"]')).to_have_count(0)
                page.locator('[data-action="add-game-gift"]').click()
                page.locator('#fld-title').fill('Scoped gift')
                page.locator('.modal-fixed-footer [type=submit]').click()
                expect(page.locator('.my-wishes-list')).to_contain_text('Scoped gift')
                assert page.evaluate("window.__revealMain===document.querySelector('main') && window.__revealChat===document.querySelector('#game-chat')")
                expect(page.locator('#game-chat-input')).to_have_value('Unsent draft')
                expect(page.locator('[data-chat-room="to-recipient"]')).to_have_attribute('aria-pressed','true')
                assert not detail_reads
                page.locator('#game-chat-form button[type="submit"]').click()
                expect(page.locator('.game-chat-messages')).to_contain_text('Unsent draft')
                page.reload()
                expect(page.locator('.secret-card .recipient')).to_have_text(assigned['receiver_name'])
                context.close()
                if email=='other@example.test':
                    assert call(owner,'GET',owner_path).json['my_assignment']=={'revealed':False}
                    assert call(application.test_client(),'GET',guest_path).json['assignment']=={'revealed':False}
        finally:
            browser.close()


@pytest.mark.browser
def test_browser_login_password_manager_contract(browser_http):
    """Correct autofill semantics, store only successful credentials, tolerate refusal."""
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            page.add_init_script("""(() => {
              window.__credentialCalls=[];
              Object.defineProperty(window,'PasswordCredential',{configurable:true,value:class {
                constructor(data){this.id=data.id;this.password=data.password;}
              }});
              Object.defineProperty(navigator.credentials,'store',{configurable:true,value:credential=>{
                window.__credentialCalls.push(credential.id==='owner@example.test'&&credential.password==='valid-password');
                return Promise.reject(new Error('Password saving declined'));
              }});
            })();""")
            page.goto(browser_http+'/')
            assert page.evaluate('window.__credentialCalls')==[], 'Credential test hook did not initialize'
            page.locator('header [data-open="login"]').click()
            expect(page.locator('#modal-form')).to_have_attribute('method','post')
            expect(page.locator('#modal-form')).to_have_attribute('action','/api/login')
            expect(page.locator('#modal-form')).to_have_attribute('autocomplete','on')
            expect(page.locator('#fld-email')).to_have_attribute('autocomplete','username')
            expect(page.locator('#fld-password')).to_have_attribute('autocomplete','current-password')
            page.locator('#fld-email').fill('owner@example.test')
            page.locator('#fld-password').fill('wrong-password')
            page.locator('.modal-fixed-footer [type=submit]').click()
            expect(page.locator('.auth-form-warning')).to_be_visible()
            assert page.evaluate('window.__credentialCalls')==[]
            page.locator('#fld-password').fill('valid-password')
            page.locator('.modal-fixed-footer [type=submit]').click()
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
            assert page.evaluate('window.__credentialCalls')==[True]
            assert page.evaluate("""() => ![...Object.values(localStorage),...Object.values(sessionStorage)].some(v=>v.includes('valid-password'))""")
            page.reload()
            expect(page.locator('.dashboard-page h1')).to_contain_text('Owner')
        finally:
            browser.close()

def test_native_login_redirect_remember_and_admin_limit(application,monkeypatch):
    from cloud.backend import SESSION_SECONDS,REMEMBER_SESSION_SECONDS
    ordinary=application.test_client()
    def csrf(client):
        html=client.get('/',base_url=BASE)
        token=re.search(r'<meta name="shursh-login-csrf" content="([A-Za-z0-9_-]{43})">',html.get_data(as_text=True)).group(1)
        cookie=html.headers.get('Set-Cookie','')
        assert '__Host-shursh_login_csrf=' in cookie and 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=Strict' in cookie
        return token
    import re
    data={'email':'other@example.test','password':'valid-password','remember':'on','return_path':'//evil.test','login_csrf':csrf(ordinary)}
    response=ordinary.post('/api/login',base_url=BASE,data=data,headers={'Origin':'null'})
    assert response.status_code==303 and response.headers['Location']=='/?shursh_login=ok'
    cookie=response.headers['Set-Cookie']
    assert f'Max-Age={REMEMBER_SESSION_SECONDS}' in cookie and 'HttpOnly' in cookie and 'Secure' in cookie
    assert call(ordinary,'GET','/api/me').json['user']['id']==str(IDS['other@example.test'])
    anonymous=application.test_client()
    denied=anonymous.post('/api/login',base_url=BASE,data=data,headers={'Origin':'null'})
    assert denied.status_code==403
    anonymous_data={**data,'login_csrf':csrf(anonymous)}
    for headers,body in (({'Origin':'https://evil.test'},anonymous_data),
                         ({'Origin':'null','Sec-Fetch-Site':'cross-site'},anonymous_data),
                         ({'Origin':'null'},{**anonymous_data,'login_csrf':data['login_csrf']}),
                         ({'Origin':BASE},{**anonymous_data,'login_csrf':''})):
        assert anonymous.post('/api/login',base_url=BASE,data=body,headers=headers).status_code==403
    invalid=anonymous.post('/api/login',base_url=BASE,data={**anonymous_data,'password':'wrong-password'},headers={'Origin':BASE})
    assert invalid.status_code==303 and invalid.headers['Location']=='/?shursh_login=invalid'
    assert 'Set-Cookie' not in invalid.headers
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    manager=application.test_client()
    reply=manager.post('/api/login',base_url=BASE,data={**data,'email':'owner@example.test','login_csrf':csrf(manager)},headers={'Origin':BASE})
    assert f'Max-Age={SESSION_SECONDS}' in reply.headers['Set-Cookie']
    # Later admin grants cannot silently extend privilege to 30 days.
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute("UPDATE public.app_sessions SET created_at=now()-interval '2 days' WHERE user_id=%s",(IDS['other@example.test'],))
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','other@example.test')
    assert call(ordinary,'GET','/api/me').json['user'] is None


def test_admin_visit_fallback_uses_known_session(application,monkeypatch):
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    manager=login(application)
    member=login(application,'other@example.test')
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('DELETE FROM public.admin_user_activity WHERE user_id=%s',(IDS['other@example.test'],))
        expected=con.execute('SELECT max(created_at) FROM public.app_sessions WHERE user_id=%s',(IDS['other@example.test'],)).fetchone()[0]
    from datetime import datetime
    row=next(u for u in call(manager,'GET','/api/admin/users').json['users'] if u['id']==str(IDS['other@example.test']))
    assert row['last_seen_source']=='session' and row['last_platform']=='unknown'
    assert datetime.fromisoformat(row['last_seen_at'])==expected


@pytest.mark.browser
def test_touch_login_native_and_admin_date_labels(browser_http,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True)
        try:
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            page=context.new_page()
            page.goto(browser_http+'/')
            page.locator('header [data-open="login"]').click()
            page.locator('#fld-email').fill('other@example.test')
            page.locator('#fld-password').fill('valid-password')
            page.locator('label.shursh-checkbox').filter(has=page.locator('[name=remember]')).click()
            expect(page.locator('[name=remember]')).to_be_checked()
            with page.expect_response(lambda res: res.url.endswith('/api/login') and res.request.is_navigation_request()) as login_response:
                page.locator('.modal-fixed-footer [type=submit]').click()
            assert login_response.value.status==303
            assert login_response.value.request.headers['content-type'].startswith('application/x-www-form-urlencoded')
            expect(page.locator('.dashboard-page h1')).to_contain_text('Other')
            assert page.evaluate("!location.search.includes('shursh_login')")
            cookie=next(c for c in context.cookies() if c['name']=='shursh_sid')
            assert cookie['secure'] and cookie['httpOnly'] and cookie['sameSite']=='Lax'
            import time
            assert 29*86400<cookie['expires']-time.time()<=30*86400+2
            page.reload()
            expect(page.locator('.dashboard-page h1')).to_contain_text('Other')
            result=page.evaluate("""() => {
                const now=new Date(2026,10,25,15,0),today=new Date(2026,10,25,9,48),yesterday=new Date(2026,10,24,23,15);
                return [socialAdminVisitDate(today,now),socialAdminVisitDate(yesterday,now),
                    socialAdminVisitMarkup({last_seen_at:today.toISOString(),last_platform:'ios'}),
                    socialAdminVisitMarkup({last_seen_at:today.toISOString(),last_platform:'macos'})];
            }""")
            assert result[:2]==['сегодня, 09:48','вчера, 23:15']
            assert 'aria-label="iOS"' in result[2] and '<rect' not in result[2]
            assert '>Mac</span>' in result[3] and '<svg' not in result[3]
        finally:
            browser.close()

def test_release_asset_fingerprint_and_stale_reveal_safe_failure(application):
    import re
    from app import UI_ASSETS,UI_VERSION
    client=application.test_client()
    assert not (ROOT/'public'/'index.html').exists(), 'Vercel static shell shadows Flask and its CSRF/version headers'
    for route in ('/','/index.html','/santa/5','/profile'):
        page=client.get(route,base_url=BASE)
        assert page.status_code==200
        assert page.headers['Cache-Control']=='no-store'
        assert re.fullmatch(r'[a-f0-9]{20}',UI_VERSION)
        assert page.headers['X-Shursh-UI-Version']==UI_VERSION
        html=page.get_data(as_text=True)
        for asset in UI_ASSETS:
            assert f'"/ui/{UI_VERSION}/{asset}"' in html
            result=client.get(f'/ui/{UI_VERSION}/{asset}',base_url=BASE)
            assert result.status_code==200 and result.headers['X-Shursh-UI-Version']==UI_VERSION
            assert result.data==(ROOT/'public'/asset).read_bytes()
    stale=client.get('/ui/'+'0'*20+'/app.js',base_url=BASE)
    assert stale.status_code==404 and stale.headers['Cache-Control']=='no-store'
    for suffix in ('reveal','null/reveal','undefined/reveal','/reveal'):
        reply=call(client,'POST','/api/participant/'+suffix,{},409)
        assert 'Обнови страницу' in reply.json['error']
        assert 'assignment' not in reply.json
    # A valid-looking but unknown bearer must not enter the compatibility path.
    call(client,'POST','/api/participant/'+'z'*43+'/reveal',{},404)


@pytest.mark.browser
def test_browser_profile_copy_respects_viewer_identity(browser_http,application):
    """Self prompts, visitor placeholders and real biographies stay distinct."""
    from playwright.sync_api import sync_playwright,expect
    owner=login(application)
    other=login(application,'other@example.test')
    previous=[call(c,'GET','/api/profile/me').json['profile'] for c in (owner,other)]
    uid=str(IDS['other@example.test'])
    own_id=str(IDS['owner@example.test'])
    prompt='Расскажи немного о себе: чем увлекаешься и каким подаркам радуешься'
    try:
        call(owner,'PATCH','/api/profile/me',{'bio':''})
        call(other,'PATCH','/api/profile/me',{'bio':'','discoverable':True})
        with sync_playwright() as play:
            browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
            try:
                page=browser.new_page(viewport={'width':390,'height':844})
                page.goto(browser_http+'/')
                browser_login(page)
                page.goto(browser_http+'/profile')
                expect(page.locator('.profile-bio')).to_have_text(prompt)
                page.goto(browser_http+'/users/'+own_id)
                expect(page.locator('.profile-bio')).to_have_text(prompt)
                expect(page.locator('.shared-santa-section h2')).to_contain_text('Мои игры в Тайного Санту')
                page.goto(browser_http+'/users/'+uid)
                expect(page.locator('.profile-bio')).to_have_text('Пока нет информации о себе')
                expect(page.locator('main')).not_to_contain_text('Расскажи немного о себе')
                call(other,'PATCH','/api/profile/me',{'bio':'Люблю книги и настольные игры'})
                page.reload()
                expect(page.locator('.profile-bio')).to_have_text('Люблю книги и настольные игры')
                call(owner,'PATCH','/api/profile/me',{'bio':'Моя биография'})
                page.goto(browser_http+'/profile')
                expect(page.locator('.profile-bio')).to_have_text('Моя биография')
            finally:
                browser.close()
    finally:
        for client,profile in zip((owner,other),previous):
            call(client,'PATCH','/api/profile/me',{'bio':profile.get('bio') or '',
                                                 'discoverable':profile['discoverable']})


def test_history_cursors_are_bounded_and_owner_scoped(application):
    """Actual disposable PostgreSQL; cursor boundaries cannot escape room or owner."""
    from cloud import db
    owner=login(application)
    other=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Cursor regression'},201).json['id']
    with db.transaction(write=True) as con:
        pid=con.execute('SELECT id FROM participants WHERE event_id=?',(eid,)).fetchone()['id']
        for i in range(125):
            con.execute("""INSERT INTO santa_messages(event_id,sender_id,room,message,created_at)
                           VALUES(?,?,'general',?,now())""",(eid,pid,f'cursor-message-{i}'))
            con.execute("""INSERT INTO social_notifications(recipient_id,kind,message,target_path)
                           VALUES(?,'wishlist_new',?,'/')""",(IDS['owner@example.test'],f'cursor-notice-{i}'))
    path=f'/api/santas/{eid}/messages/general'
    recent=call(owner,'GET',path).json
    assert len(recent['messages'])==60 and recent['has_more']
    ids=[m['id'] for m in recent['messages']]
    older=call(owner,'GET',path+'?before='+str(ids[0])).json
    assert len(older['messages'])==60 and older['has_more']
    older_ids=[m['id'] for m in older['messages']]
    oldest=call(owner,'GET',path+'?before='+str(older_ids[0])).json
    assert len(oldest['messages'])==5 and not oldest['has_more']
    assert not set(ids)&set(older_ids)
    delta=call(owner,'GET',path+'?after='+str(older_ids[-1])).json
    assert [m['id'] for m in delta['messages']]==ids
    for invalid in ('?before=0','?after=-1','?before=1&after=2','?after=9223372036854775808'):
        call(owner,'GET',path+invalid,status=400)
    call(other,'GET',path+'?before='+str(ids[0]),status=404)
    feed=call(owner,'GET','/api/notifications').json
    assert len(feed['items'])==60 and feed['has_more']
    cursor=feed['items'][-1]['id']
    history=call(owner,'GET',f'/api/notifications?before={cursor}').json
    assert all(n['id']<cursor for n in history['items'])
    assert not {n['id'] for n in feed['items']}&{n['id'] for n in history['items']}
    assert history['unread']==feed['unread']
    assert not any(n['message'].startswith('cursor-notice-') for n in
                   call(other,'GET',f'/api/notifications?before={cursor}').json['items'])
    call(owner,'GET','/api/notifications?before=invalid',status=400)


def test_friend_invites_search_full_names_privacy_and_qr(application):
    from cloud import db
    import qrcode
    a=login(application); b=login(application,'other@example.test')
    aid,bid=map(str,IDS.values())
    with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
        con.execute('DELETE FROM public.friendships WHERE user_low=%s AND user_high=%s',(aid,bid))
    try:
        call(a,'PATCH','/api/profile/me',{'name':'Александр','handle':'Alex_invite','last_name':'Иванов','patronymic':'Петрович','show_full_name':False,'discoverable':True,'allow_friend_invites':False})
        call(b,'PATCH','/api/profile/me',{'name':'Александр','handle':'alex_other','discoverable':True})
        assert not call(b,'GET','/api/users/search?q=Иванов').json['users']
        match=call(b,'GET','/api/users/search?q=%40ALEX_INVITE').json['users']
        assert len(match)==1 and match[0]['id']==aid and match[0]['last_name']==''
        assert match[0]['relationship']=='none' and 'email' not in match[0]
        assert not call(b,'GET','/api/users/search?q=%40alex').json['users']
        assert not call(b,'GET','/api/users/search?q=%25%25').json['users']
        assert not call(b,'GET','/api/users/search?q=__').json['users']
        call(b,'PATCH','/api/profile/me',{'handle':'@ALEX_INVITE'},409)
        call(a,'PATCH','/api/profile/me',{'show_full_name':True})
        match=call(b,'GET','/api/users/search?q=Иванов').json['users']
        assert match[0]['last_name']=='Иванов' and match[0]['patronymic']=='Петрович'
        assert call(b,'GET','/api/users/search?q=Александр%20Иванов').json['users'][0]['id']==aid
        invite=call(a,'POST','/api/friend-invites/me',{}).json
        assert call(a,'POST','/api/friend-invites/me',{}).json==invite
        code=invite['path'].split('/')[-1]
        assert len(code)==24 and invite['url']==BASE+invite['path']
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=1)
        qr.add_data(invite['url']);qr.make(fit=True)
        assert invite['qr']==[''.join('1' if bit else '0' for bit in row) for row in qr.get_matrix()]
        guest=application.test_client()
        landing=call(guest,'GET','/api/friend-invites/'+code).json
        assert set(landing['inviter'])=={'id','name','handle','avatar_emoji'}
        assert landing['relationship']=='guest'
        call(guest,'POST','/api/friend-invites/'+code+'/friend',{},401)
        call(a,'POST','/api/friend-invites/'+code+'/friend',{},400)
        call(b,'POST','/api/friend-invites/'+code+'/friend',{})
        assert call(b,'GET','/api/users/search?q=%40alex_invite').json['users'][0]['relationship']=='outgoing'
        assert call(a,'GET','/api/friend-invites/'+code).json['relationship']=='self'
        call(a,'PATCH','/api/friends/'+bid,{'action':'accept'})
        assert call(b,'GET','/api/friend-invites/'+code).json['relationship']=='friends'
        call(a,'PATCH','/api/profile/me',{'discoverable':False,'allow_friend_invites':False})
        call(guest,'GET','/api/friend-invites/'+code,status=404)
        call(a,'POST','/api/friend-invites/me',{},403)
        assert not call(b,'GET','/api/users/search?q=%40alex_invite').json['users']
        call(a,'PATCH','/api/profile/me',{'allow_friend_invites':True})
        new=call(a,'POST','/api/friend-invites/me',{}).json
        assert new['path']!=invite['path']
        assert call(guest,'GET','/api/friend-invites/'+new['path'].split('/')[-1]).json['relationship']=='guest'
        call(a,'DELETE','/api/friend-invites/me',{})
        call(guest,'GET','/api/friend-invites/'+new['path'].split('/')[-1],status=404)
    finally:
        call(a,'PATCH','/api/profile/me',{'name':'Owner','handle':'','last_name':'','patronymic':'','show_full_name':False,'discoverable':True,'allow_friend_invites':False})
        call(b,'PATCH','/api/profile/me',{'name':'Other','handle':''})
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            con.execute('DELETE FROM public.friendships WHERE user_low=%s AND user_high=%s',(aid,bid))
            con.execute('DELETE FROM public.user_invites WHERE owner_id=%s',(aid,))


def test_referral_verified_confirmation_exactly_once_and_revocation(application,monkeypatch):
    from cloud import auth
    from datetime import datetime,timezone
    from uuid import uuid4
    owner=login(application); other=login(application,'other@example.test')
    aid,bid=map(str,IDS.values())
    invite=call(owner,'POST','/api/friend-invites/me',{}).json['path'].split('/')[-1]
    alternative=call(other,'POST','/api/friend-invites/me',{}).json['path'].split('/')[-1]
    users={}
    upstream=auth.auth_request
    def provider(action,**payload):
        if action!='register':return upstream(action,**payload)
        email=payload['email']
        if email in users:
            return {'id':str(users[email]['id']),'identities':[],'email':email}
        uid=uuid4()
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            con.execute('INSERT INTO auth.users(id) VALUES(%s)',(uid,))
        data={'id':str(uid),'email':email,'created_at':datetime.now(timezone.utc).isoformat(),
              'identities':[{'provider':'email'}],'user_metadata':payload['data']}
        users[email]=data
        # GoTrue may return the user directly for confirmation-required signup.
        return data
    monkeypatch.setattr(auth,'auth_request',provider)
    guest=application.test_client()
    def register(email,code):
        return call(guest,'POST','/api/register',{'name':'Referral user','email':email,'password':'valid-password','invite_code':code},202)
    def confirm(email):
        monkeypatch.setattr(auth,'verified_user',lambda token:{**users[email],'email_confirmed_at':datetime.now(timezone.utc).isoformat()})
        return call(application.test_client(),'POST','/api/auth/complete',{'access_token':'abc.def.ghi'}).json
    def count(client):
        return call(client,'GET','/api/profile/me').json['referral_count']
    initial=count(owner);initial_other=count(other)
    try:
        register('referral-a@example.test',invite)
        assert count(owner)==initial
        register('referral-a@example.test',alternative)
        result=confirm('referral-a@example.test')
        assert result['invite_path']=='/i/'+invite
        assert count(owner)==initial+1 and count(other)==initial_other
        assert 'invite_path' not in confirm('referral-a@example.test')
        assert count(owner)==initial+1
        # Revocation before confirmation and expiration both fail closed.
        register('referral-b@example.test',invite)
        register('referral-expired@example.test',alternative)
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            con.execute("UPDATE public.referral_pending SET signup_at=now()-interval '9 days',expires_at=now()-interval '1 day' WHERE provider_id=%s",(users['referral-expired@example.test']['id'],))
        call(owner,'DELETE','/api/friend-invites/me',{})
        assert 'invite_path' not in confirm('referral-b@example.test')
        assert 'invite_path' not in confirm('referral-expired@example.test')
        assert count(owner)==initial+1 and count(other)==initial_other
        call(guest,'POST','/api/register',{'name':'Revoked','email':'referral-c@example.test','password':'valid-password','invite_code':invite},404)
        assert 'referral-c@example.test' not in users
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            for table in ('user_invites','referral_pending','referral_attributions'):
                assert con.execute("SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass",('public.'+table,)).fetchone()[0]
                for role in ('anon','authenticated'):
                    assert not con.execute("SELECT has_table_privilege(%s,%s,'SELECT')",(role,'public.'+table)).fetchone()[0]
    finally:
        with psycopg.connect(os.environ['SHURSH_DATABASE_URL']) as con:
            for u in users.values():
                con.execute('DELETE FROM public.referral_pending WHERE provider_id=%s',(u['id'],))
                con.execute('DELETE FROM auth.users WHERE id=%s',(u['id'],))
            con.execute('DELETE FROM public.user_invites WHERE owner_id IN (%s,%s)',(aid,bid))
