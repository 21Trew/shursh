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


def test_auth_and_session(application):
    c=application.test_client()
    assert call(c,'GET','/api/me').json == {'user':None,'demo':False}
    guest_dashboard=call(c,'GET','/api/dashboard')
    assert guest_dashboard.json == {'user':None,'demo':False,'lists':[],'events':[]}
    assert 'db-connect;dur=0.0' in guest_dashboard.headers['Server-Timing']
    assert 'sql-exec;dur=0.0;desc="0 statement(s)"' in guest_dashboard.headers['Server-Timing']
    call(c,'GET','/api/lists',status=401)
    call(c,'POST','/api/login',{'email':'owner@example.test','password':'bad-password'},401)
    r=call(c,'POST','/api/register',{'email':'owner@example.test','name':'Owner','password':'valid-password'},202)
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
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(lambda _: application.test_client().post(reserve,base_url=BASE,json={'guest_name':'Guest'}), range(6)))
    assert sorted(r.status_code for r in responses)==[201]+[409]*5
    token=next(r.json['manage_token'] for r in responses if r.status_code==201)
    assert call(guest,'GET',f'/api/public/{key}').json['wishes'][0]['reserved'] is True
    assert 'reserved' not in call(c,'GET',f'/api/public/{key}').json['wishes'][0]
    assert 'reserved' not in call(c,'GET',f'/api/lists/{lid}').json['wishes'][0]
    call(guest,'DELETE',f'/api/reservations/{token}')
    call(guest,'DELETE',f'/api/reservations/{token}',status=409)
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
        t=call(guest,'POST',f'/api/invites/{key}/join',{'name':name},201).json['participant_token']
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
    call(application.test_client(),'POST',f'/api/invites/{key}/join',{'name':'Late'},409)
    for guest,t,name in guests:
        assert call(guest,'GET',f'/api/participant/{t}').json['assignment']=={'revealed':False}
        r=call(guest,'POST',f'/api/participant/{t}/reveal',{}).json['assignment']
        assert r['revealed'] and r['receiver_name']!=name
        if name=='A': assert r['receiver_name']=='B'
    game=call(c,'GET',f'/api/santas/{eid}').json
    assert game['my_assignment']=={'revealed':False} and 'assignments' not in game
    assert game['my_wishes']==[]


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
    participant=call(guest,'POST',f'/api/invites/{invite}/join',{'name':'Guest'},201).json['participant_token']
    reservation=call(guest,'POST',f'/api/public/{key}/reserve/{wid}',{'guest_name':'Guest'},201).json['manage_token']
    for path in ['/', '/lists', '/santas', f'/list/{lid}', f'/santa/{eid}',
                 f'/w/{key}', f'/join/{invite}', f'/p/{participant}', f'/r/{reservation}']:
        page=call(guest,'GET',path)
        assert 'text/html' in page.content_type
        assert 'src="/app.js"' in page.get_data(as_text=True)
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


def browser_login(page, email='owner@example.test'):
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
            page.locator('#modal-form button[type="submit"]').click()
        response=result.value
    except PlaywrightTimeout as exc:
        fields=page.evaluate("""() => [...document.querySelectorAll('#modal-form input')].map(el=>({
          type:el.type, name:el.name, valid:el.checkValidity(),
          valueLength:el.value.length, required:el.required,
          missing:el.validity.valueMissing, typeMismatch:el.validity.typeMismatch,
          tooShort:el.validity.tooShort, tooLong:el.validity.tooLong,
          badInput:el.validity.badInput, customError:el.validity.customError
        }))""")
        disabled=page.locator('#modal-form button[type="submit"]').is_disabled() if page.locator('#modal-form button[type="submit"]').count() else None
        raise AssertionError(f'Login timed out: request_sent={bool(sent)}, field_constraints={fields}, submit_disabled={disabled}') from exc
    assert response.status==200, (
        f'Login HTTP {response.status}; '
        f'Server-Timing: {response.headers.get("server-timing", "missing")}')
    expect(page.locator('header .user-name')).to_contain_text(
        'Owner' if email.startswith('owner') else 'Other', timeout=15000)
    expect(page.get_by_role('dialog')).to_have_count(0)



def test_static_product_copy_avoids_sentence_final_periods():
    """All shipped Russian UI copy follows Shursh punctuation; user data is untouched."""
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    ending=re.compile(r"""[А-Яа-яЁё]\.(?=</(?:p|small|h[1-6]|strong|span|div|li|a|button)\b|['"`])""")
    paths=('public/app.js','public/shursh-preview.html','server.py','app.py','cloud/backend.py')
    for name in paths:
        data=(root/name).read_text(encoding='utf-8')
        assert not ending.search(data), f'Russian text ends in a period: {name}'




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
            page.locator('[data-password-visibility]').click()
            assert page.locator('#fld-password').get_attribute('type')=='password'
            page.locator('[data-password-visibility]').click()
            page.locator('#fld-password').fill('valid-password')
            page.locator('#modal-form button[type="submit"]').click()
            expect(page.get_by_role('dialog')).to_contain_text('Проверь почту')
            expect(page.locator('.auth-confirm-card')).to_be_visible()
            expect(page.locator('.auth-confirm-card .auth-confirm-symbol .icon')).to_be_visible()
            expect(page.locator('.auth-confirm-card')).to_contain_text('Письмо с подтверждением отправлено!')
            expect(page.get_by_role('dialog')).to_contain_text('owner@example.test')
            assert page.locator('.toast').count()==0, 'No duplicate registration toast'
            assert page.locator('.auth-confirm-card').evaluate(
                "(el) => getComputedStyle(el).borderTopLeftRadius !== '18px'")
            assert page.locator('.auth-confirm-card p').inner_text().strip().endswith('.') is False
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('.auth-confirm-card')).to_be_visible()
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
            page.locator('#modal-form button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/list/\d+$'))
            lid = page.url.rsplit('/', 1)[-1]
            expect(page.locator('main h1')).to_have_text(title)

            page.locator('button[data-open="wish"]').first.click()
            page.locator('#fld-title').fill(wish)
            page.locator('#modal-form button[type="submit"]').click()
            expect(page.locator('.wishlist-grid')).to_contain_text(wish)
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
            guest.locator('#fld-guest_name').fill('Друг с телефона')
            guest.locator('#modal-form button[type="submit"]').click()
            expect(guest).to_have_url(re.compile(r'/r/[A-Za-z0-9_-]+$'))
            expect(guest.locator('main h1')).to_contain_text('Подарок ждёт')

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

            guest.locator('button[data-action="cancel-reservation"]').click()
            guest.locator('#modal-form button[type="submit"]').click()
            expect(guest.locator('main h1')).to_contain_text('Бронь отменена')
            watcher.reload()
            expect(watcher.locator('button[data-action="reserve"]')).to_be_enabled()

            page.locator('button[data-action="edit-list"]').click()
            page.locator('#fld-visibility').select_option('private')
            page.locator('#modal-form button[type="submit"]').click()
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
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/santa/\d+$'))
            eid = owner.url.rsplit('/', 1)[-1]
            invite = owner.locator('input[aria-label="Ссылка-приглашение"]').input_value()
            assert invite.startswith(browser_http + '/join/')

            members = []
            for name, mobile in [('Петя', True), ('Катя', False)]:
                context = browser.new_context(viewport={'width': 390, 'height': 844} if mobile else {'width': 1366, 'height': 900}, is_mobile=mobile)
                guest = context.new_page()
                guest.set_default_timeout(15000)
                guest.goto(invite)
                expect(guest.locator('.invite-card h1')).to_have_text(title)
                guest.locator('#join-name').fill(name)
                guest.locator('#join-form button[type="submit"]').click()
                expect(guest).to_have_url(re.compile(r'/p/[A-Za-z0-9_-]+$'))
                token = guest.url.rsplit('/', 1)[-1]
                guest.locator('#participant-wish-form input[name="title"]').fill('Подарок для ' + name)
                guest.locator('#participant-wish-form button[type="submit"]').click()
                expect(guest.locator('.my-wishes-list')).to_contain_text('Подарок для ' + name)
                members.append((name, context, guest, token))

            owner.reload()
            expect(owner.locator('.person-row')).to_have_count(3)
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
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner.locator('button[data-action="reveal"]')).to_be_visible()
            assert owner.locator('.secret-card .recipient').count() == 0

            for name, _, guest, token in members:
                guest.reload()
                expect(guest.locator('button[data-action="reveal"]')).to_be_visible()
                state = guest.evaluate('''async token => (await (await fetch('/api/participant/' + token)).json())''', token)
                assert state['assignment'] == {'revealed': False}
                assert 'receiver_name' not in str(state)

            first_name, _, first, first_token = members[0]
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
            expect(page.locator('.dashboard-metrics')).to_be_visible()
            page.evaluate('window.__stableHeader = document.querySelector(".site-header")')
            page.evaluate('window.__stableFooter = document.querySelector("footer")')
            visited=[]
            page.on('request',lambda request: visited.append((request.method,request.url.split(browser_http)[-1]))
                    if request.url.startswith(browser_http+'/api/') else None)
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Твои вишлисты')
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main h1')).to_contain_text('Тайный Санта')
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Твои вишлисты')
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
            page.locator('#modal-form button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/list/\d+$'))
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main')).to_contain_text(title)
            assert sum(method=='GET' and path=='/api/lists' for method,path in visited)==1,visited
            page.locator('header .nav [data-nav="/santas"]').click()
            expect(page.locator('main h1')).to_contain_text('Тайный Санта')
            santa='No redraw game '+uuid4().hex[:7]
            page.locator('main button[data-open="santa"]').first.click()
            page.locator('#fld-title').fill(santa)
            page.locator('#modal-form button[type="submit"]').click()
            expect(page).to_have_url(re.compile(r'/santa/\d+$'))
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
            requests=[]
            page.on('request', lambda r: requests.append(r.url) if '/api/' in r.url else None)
            page.locator('header .nav [data-nav="/lists"]').click()
            expect(page.locator('main h1')).to_contain_text('Твои вишлисты')
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
            page.locator('#modal-form button[type="submit"]').click()
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
            expect(page.locator('.toast')).to_contain_text('подтверждён')
            assert 'fake-test-value' not in page.url
            # A provider confirmation redirects from Supabase to a new document.
            # A same-document hash navigation would not rerun startup logic.
            page=browser.new_page()
            page.goto(browser_http+'/#error=access_denied&error_code=otp_expired&error_description=test')
            expect(page).to_have_url(browser_http+'/')
            expect(page.locator('.toast')).to_contain_text('истекла')
            # Providers may redirect with only error/error_code, without
            # error_description. Do not leave such callback fragments in the URL.
            page=browser.new_page()
            page.goto(browser_http+'/#error=access_denied&error_code=otp_expired')
            expect(page).to_have_url(browser_http+'/')
            expect(page.locator('.toast')).to_contain_text('истекла')
            assert 'otp_expired' not in page.url
            page=browser.new_page()
            page.goto(browser_http+'/#error_code=otp_expired')
            expect(page).to_have_url(browser_http+'/')
            expect(page.locator('.toast')).to_contain_text('истекла')
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.fontperf
def test_font_loading_observation(browser_http):
    """Browser-observed font requests; external third-party timing is non-gating."""
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
              const resources=performance.getEntriesByType('resource')
                .filter(x=>/^https:\/\/fonts\.(?:googleapis|gstatic)\.com\//.test(x.name))
                .map(x=>({domain:new URL(x.name).hostname,
                           durationMs:Math.round(x.duration),
                           transferSize:x.transferSize}));
              return {fontReady:done,fontFaces:faces.length,
                loadedFaces:faces.filter(x=>x.status==='loaded').length,
                resources};
            }""")
            assert isinstance(fonts['resources'],list)
            print('SHURSH_FONT_PERF='+json.dumps({
                'scope':'CI-Chromium-external-Google-Fonts','domContentLoadedMs':dom_ms,
                'fontReady':fonts['fontReady'],'fontFaceCount':fonts['fontFaces'],
                'loadedFaceCount':fonts['loadedFaces'],
                'resources':fonts['resources']},ensure_ascii=False))
        finally:
            browser.close()
