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
    call(application.test_client(),'POST',f'/api/invites/{invite}/join',
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
    paths=('public/app.js','public/shursh-preview.html','public/index.html','server.py','app.py','cloud/backend.py')
    for name in paths:
        data=(root/name).read_text(encoding='utf-8')
        assert not ending.search(data), f'Russian text ends in a period: {name}'





def test_site_text_uses_only_short_hyphens_and_calm_confirmation_card():
    """Protect the shipped product copy and onboarding card from regressions."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('public/app.js', 'public/shursh-preview.html',
                 'public/index.html', 'server.py', 'app.py', 'cloud/backend.py',
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
            assert page.locator('header .nav a.active').count()==1
            page.locator('.footer-developer').click()
            expect(page.locator('.modal')).to_contain_text('Написать разработчику')
            expect(page.locator('#fld-name')).to_be_visible()
            expect(page.locator('#fld-email')).to_be_visible()
            expect(page.locator('#fld-message')).to_be_visible()
            expect(page.locator('#modal-form button[type="submit"]')).to_contain_text('Отправить')
            page.locator('.modal-close').click()
            assert page.locator('.footer a[href^="mailto:"]').count() == 0
            assert page.locator('header button[data-open="list"]').count() == 0
            browser_login(page)
            assert page.locator('header button[data-nav="/lists"]').count() == 0
            assert page.locator('button[data-action="refresh-owner"]').count() == 0

            page.locator('main button[data-open="list"]').first.click()
            page.locator('#fld-title').fill('Ручные ссылки')
            page.locator('#modal-form button[type="submit"]').click()
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
            photo = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9aer6aQAAAAASUVORK5CYII=')
            page.locator('#wish-file').set_input_files({
                'name': 'gift.png', 'mimeType': 'image/png', 'buffer': photo,
            })
            page.locator('#modal-form button[type="submit"]').click()
            card = page.locator('.wish-card').filter(has_text='Кот и настольная игра')
            expect(card).to_be_visible()
            expect(card.locator('img')).to_be_visible()
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
            assert owner.locator('.error-page').count()==0, owner.locator('.error-page p').all_inner_texts()
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
                expect(guest.locator('#game-chat [data-chat-room="general"]')).to_be_visible()
                guest.locator('#santa-preferences-form #fld-wanted').fill('Красный цвет, точная модель')
                guest.locator('#santa-preferences-form #fld-unwanted').fill('Не нужен пластик')
                guest.locator('#santa-preferences-form button[type="submit"]').click()
                guest.locator('button[data-action="add-game-gift"]').click()
                guest.locator('#fld-title').fill('Подарок для ' + name)
                guest.locator('#modal-form button[type="submit"]').click()
                expect(guest.locator('.my-wishes-list')).to_contain_text('Подарок для ' + name)
                expect(guest.locator('.my-wishes-list .game-gifts-track .game-gift-card')).to_have_count(1)
                guest.locator('.game-gift-card .card-hitarea').first.click()
                expect(guest.locator('.modal')).not_to_contain_text('Красный цвет, точная модель')
                guest.locator('.modal-close').click()
                expect(guest.locator('#santa-preferences-form #fld-wanted')).to_have_value('Красный цвет, точная модель')
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
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/list/\d+'))
            owner.locator('button[data-open="wish"]').first.click()
            owner.locator('#fld-title').fill('Настольная игра')
            owner.locator('#modal-form button[type="submit"]').click()
            owner.locator('.wish-card .card-hitarea').click(position={'x':35,'y':35})
            expect(owner.locator('.modal h2')).to_have_text('Настольная игра')
            owner.locator('.wish-detail-actions [data-action="edit-wish"]').click()
            expect(owner.locator('#fld-title')).to_have_value('Настольная игра')
            owner.locator('.modal-close').click()

            owner.locator('header .nav [data-nav="/"]').click()
            target=owner.locator('.dashboard-page .list-card .card-hitarea').first
            target.focus()
            owner.keyboard.press('Enter')
            expect(owner).to_have_url(re.compile(r'/list/\d+'))
            owner.locator('header .nav [data-nav="/"]').click()
            owner.locator('main button[data-open="santa"]').first.click()
            owner.locator('#fld-title').fill('Санта без дублей')
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner).to_have_url(re.compile(r'/santa/\d+'))
            eid=owner.url.rsplit('/',1)[-1]
            assert owner.locator('.error-page').count()==0, owner.locator('.error-page p').all_inner_texts()
            invite=owner.locator('input[aria-label="Ссылка-приглашение"]').input_value()
            owner.goto(invite)
            expect(owner.locator('.invite-card')).to_contain_text('Ты уже участвуешь')
            expect(owner.locator('#join-form')).to_have_count(0)

            owner.goto(browser_http+'/santa/'+eid)
            owner.locator('button[data-action="edit-santa"]').click()
            owner.locator('#fld-budget').fill('2450')
            owner.locator('#fld-exchange_date').fill('2027-02-12')
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner.locator('.details-box')).to_contain_text('2 450')
            owner.locator('button[data-action="add-player"]').click()
            owner.locator('#fld-name').fill('Аня')
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner.locator('.modal h2')).to_have_text('Личная ссылка участника')
            participant_link=owner.locator('input[aria-label="Личная ссылка участника"]').input_value()
            owner.locator('.modal-close').click()
            expect(owner.locator('.person-row')).to_have_count(2)
            owner.locator('button[data-action="import-own-wishes"]').first.click()
            expect(owner.locator('[name="wish_ids"]:checked')).to_have_count(1)
            owner.locator('#modal-form button[type="submit"]').click()
            expect(owner.locator('.my-wishes-list')).to_contain_text('Настольная игра')

            owner.locator('header .nav [data-nav="/"]').click()
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
            other.locator('#modal-form button[type="submit"]').click()
            other.locator('button[data-open="wish"]').first.click()
            other.locator('#fld-title').fill('Тёплый шарф')
            other.locator('#modal-form button[type="submit"]').click()
            other.goto(participant_link)
            other.locator('button[data-action="import-own-wishes"]').click()
            expect(other.locator('[name="wish_ids"]:checked')).to_have_count(1)
            other.locator('#modal-form button[type="submit"]').click()
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


def test_santa_gift_details_group_chat_and_anonymous_pair_chat(application):
    """Isolated CI PostgreSQL: private gifts/chats require membership, pairs stay anonymous."""
    owner=login(application)
    outsider=login(application,'other@example.test')
    eid=call(owner,'POST','/api/santas',{'title':'Чаты и пожелания'},201).json['id']
    event=call(owner,'GET',f'/api/santas/{eid}').json['event']
    guest=application.test_client()
    tokens={}
    for name in ('Альфа','Бета'):
        tokens[name]=call(guest,'POST',f'/api/invites/{event["invite_key"]}/join',
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
    participant=call(application.test_client(),'POST',f'/api/invites/{invite}/join',
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
    key=call(member,'POST',f'/api/invites/{invitation}/join',
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
    token=call(guest,'POST',f'/api/invites/{invite}/join',{'name':'Visitor'},201).json['participant_token']
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
            expect(page.locator('header .user-name')).to_contain_text('Owner')
            assert page.evaluate('location.hash')==''
            assert page.evaluate('document.cookie')==''
            # Expired confirmations must show a persistent recovery dialog.
            expired=browser.new_page()
            expired.goto(browser_http+'/#access_token=expired.token.example')
            expect(expired.get_by_role('dialog')).to_contain_text('Не получилось завершить подтверждение')
            assert expired.evaluate('location.hash')==''
            expired.locator('[data-open="resend"]').click()
            expired.locator('#fld-email').fill('owner@example.test')
            expired.locator('#modal-form button[type="submit"]').click()
            expect(expired.get_by_role('dialog')).to_contain_text('Проверь почту')
        finally:
            browser.close()
