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

def test_auth_and_session(application):
    c=application.test_client()
    assert call(c,'GET','/api/me').json == {'user':None,'demo':False}
    call(c,'GET','/api/lists',status=401)
    call(c,'POST','/api/login',{'email':'owner@example.test','password':'bad-password'},401)
    r=call(c,'POST','/api/register',{'email':'owner@example.test','name':'Owner','password':'valid-password'},202)
    assert r.json['pending_confirmation'] and 'Set-Cookie' not in r.headers
    r=call(c,'POST','/api/login',{'email':'owner@example.test','password':'valid-password'})
    cookie=r.headers['Set-Cookie']; assert all(s in cookie for s in ('HttpOnly','Secure','SameSite=Lax'))
    assert 'not-a-real-token' not in r.get_data(as_text=True)
    assert call(c,'GET','/api/me').json['user']['id']==str(IDS['owner@example.test'])
    call(c,'POST','/api/lists',{'title':'CSRF'},403,headers={'Origin':'https://evil.example'})
    call(c,'POST','/api/logout',{})
    assert call(c,'GET','/api/me').json['user'] is None
    call(c,'POST','/api/demo-login',{},404)


def test_booking_isolation_and_private_images(application):
    c=login(application); other=login(application,'other@example.test'); guest=application.test_client()
    lid,wid,key=make_list(c)
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
