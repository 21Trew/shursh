"""End-to-end API + concurrency tests against a temporary local HTTP server."""
from __future__ import annotations
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import requests
import pytest

ROOT=Path(__file__).resolve().parents[1]
PORT=18787
BASE=f'http://127.0.0.1:{PORT}'
spec=importlib.util.spec_from_file_location('shursh_server',ROOT/'server.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@pytest.fixture(scope='session')
def server():
    with tempfile.TemporaryDirectory() as d:
        env=os.environ.copy();env.update(SHURSH_DB=str(Path(d)/'test.sqlite3'),SHURSH_DEMO='1',PORT=str(PORT))
        process=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=str(ROOT),env=env,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(70):
            try:
                if requests.get(BASE+'/api/me',timeout=.25).status_code==200: break
            except requests.RequestException: time.sleep(.1)
        else:
            process.terminate();raise RuntimeError('Server did not start')
        yield BASE
        process.terminate();process.wait(timeout=5)

@pytest.fixture
def owner(server):
    s=requests.Session()
    r=s.post(server+'/api/demo-login',json={})
    assert r.status_code==200,r.text
    return s

def test_matching_constraints_and_impossible():
    ids=[1,2,3,4,5]
    for _ in range(50):
        pairs=module.matching(ids,[(1,2),(1,3),(4,5)])
        assert len(pairs)==5
        assert set(a for a,b in pairs)==set(ids)
        assert set(b for a,b in pairs)==set(ids)
        assert all(a!=b and (a,b) not in ((1,2),(1,3),(4,5)) for a,b in pairs)
    with pytest.raises(module.ApiError,match='невозможна'):
        module.matching([1,2,3],[(1,2),(1,3)])
    with pytest.raises(module.ApiError,match='минимум 3'):
        module.matching([1,2],[])

def test_create_list_wish_public_reserve_and_cancel(server,owner):
    r=owner.post(server+'/api/lists',json={'title':'Мой тестовый список','description':'Здесь подарки','occasion':'День рождения','theme':'mint','visibility':'link'})
    assert r.status_code==201,r.text
    lid=r.json()['id']
    wish=owner.post(server+f'/api/lists/{lid}/wishes',json={'title':'Настольная игра','description':'Детективная','price':3500,'currency':'RUB','kind':'item','priority':'love'})
    assert wish.status_code==201,wish.text
    wid=wish.json()['id']
    l=owner.get(server+f'/api/lists/{lid}').json()
    key=l['list']['share_key']
    assert len(l['wishes'])==1 and 'reserved' not in l['wishes'][0]
    anon=requests.Session()
    p=anon.get(server+f'/api/public/{key}').json()
    assert p['wishes'][0]['reserved'] is False
    r=anon.post(server+f'/api/public/{key}/reserve/{wid}',json={'guest_name':'Тестовый даритель'})
    assert r.status_code==201,r.text
    manage=r.json()['manage_token']
    assert anon.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved'] is True
    assert 'reserved' not in owner.get(server+f'/api/lists/{lid}').json()['wishes'][0]
    owner_public=owner.get(server+f'/api/public/{key}').json()
    assert owner_public['owner_view'] is True
    assert 'reserved' not in owner_public['wishes'][0]
    assert owner.post(server+f'/api/public/{key}/reserve/{wid}',json={'guest_name':'Owner'}).status_code==403
    assert anon.post(server+f'/api/public/{key}/reserve/{wid}',json={'guest_name':'Other'}).status_code==409
    assert anon.get(server+f'/api/reservations/{manage}').json()['reservation']['guest_name']=='Тестовый даритель'
    assert anon.delete(server+f'/api/reservations/{manage}').status_code==200
    assert anon.delete(server+f'/api/reservations/{manage}').status_code==409
    assert anon.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved'] is False
    assert anon.get(server+f'/api/reservations/wrongtoken').status_code==404
    assert owner.patch(server+f'/api/lists/{lid}',json={'visibility':'private'}).status_code==200
    assert anon.get(server+f'/api/public/{key}').status_code==404

def test_double_reserve_race(server,owner):
    r=owner.post(server+'/api/lists',json={'title':'Гонка','visibility':'link'})
    lid=r.json()['id'];key=owner.get(server+f'/api/lists/{lid}').json()['list']['share_key']
    w=owner.post(server+f'/api/lists/{lid}/wishes',json={'title':'Последний подарок'})
    wid=w.json()['id']
    def reserve(n):return requests.post(server+f'/api/public/{key}/reserve/{wid}',json={'guest_name':f'Гость {n}'},timeout=5).status_code
    with ThreadPoolExecutor(max_workers=12) as pool:
        codes=list(pool.map(reserve,range(12)))
    assert codes.count(201)==1,codes
    assert codes.count(409)==11,codes

def test_santa_guest_access_reveal_and_frozen_rules(server,owner):
    r=owner.post(server+'/api/santas',json={'title':'Тестовый Санта','budget':2000,'exchange_date':'2026-12-30','rules':'Веселимся'})
    assert r.status_code==201,r.text
    eid=r.json()['id'];game=owner.get(server+f'/api/santas/{eid}').json();key=game['event']['invite_key']
    assert game['participants'][0]['user_id']==1
    joined=[]
    for name in ('Катя','Петя'):
        s=requests.Session()
        a=s.post(server+f'/api/invites/{key}/join',json={'name':name})
        assert a.status_code==201,a.text
        t=a.json()['participant_token'];joined.append((name,t,s))
        assert s.post(server+f'/api/participant/{t}/wishes',json={'title':f'Хочу подарок для {name}'}).status_code==201
    game=owner.get(server+f'/api/santas/{eid}').json()
    pids={p['name']:p['id'] for p in game['participants']}
    exclusion={'giver_id':pids['Катя'],'receiver_id':pids['Петя']}
    assert owner.post(server+f'/api/santas/{eid}/exclusions',json=exclusion).status_code==201
    d=owner.post(server+f'/api/santas/{eid}/draw',json={})
    assert d.status_code==200,d.text
    assert d.json()['already_drawn'] is False
    assert owner.post(server+f'/api/santas/{eid}/draw',json={}).json()['already_drawn'] is True
    assert owner.delete(server+f'/api/santas/{eid}/participants/{pids["Катя"]}').status_code==409
    assert owner.post(server+f'/api/santas/{eid}/exclusions',json=exclusion).status_code==409
    assert requests.post(server+f'/api/invites/{key}/join',json={'name':'Поздний гость'}).status_code==409
    for name,t,s in joined:
        before=s.get(server+f'/api/participant/{t}').json()
        assert before['assignment']=={'revealed':False}
        assert 'receiver_name' not in str(before)
        assert s.get(server+f'/api/participant/badtoken').status_code==404
        reveal=s.post(server+f'/api/participant/{t}/reveal',json={}).json()['assignment']
        assert reveal['revealed']
        assert reveal['receiver_name']!=name
        assert reveal['receiver_name'] in ('Саша','Катя','Петя')
        assert s.get(server+f'/api/participant/{t}').json()['assignment']==reveal
    katya=joined[0][1]
    assert requests.get(server+f'/api/participant/{katya}').status_code==200  # bearer-capability URL
    assert owner.get(server+f'/api/santas/{eid}').json()['my_assignment']=={'revealed':False}
    self_reveal=owner.post(server+f'/api/santas/{eid}/reveal',json={}).json()['assignment']
    assert self_reveal['revealed']
    assert 'assignments' not in owner.get(server+f'/api/santas/{eid}').json()
    assert requests.get(server+f'/api/santas/{eid}').status_code==401

def test_origin_and_bad_url(server,owner):
    assert owner.post(server+'/api/lists',json={'title':'X'},headers={'Origin':'https://evil.example'}).status_code==403
    l=owner.post(server+'/api/lists',json={'title':'Safe'}).json()['id']
    r=owner.post(server+f'/api/lists/{l}/wishes',json={'title':'Bad','shop_url':'javascript:alert(1)'})
    assert r.status_code==400
    assert owner.get(server+f'/api/lists/{l}').json()['wishes']==[]

def test_concurrent_draw_idempotent(server,owner):
    r=owner.post(server+'/api/santas',json={'title':'Параллельная жеребьёвка'})
    eid=r.json()['id'];key=owner.get(server+f'/api/santas/{eid}').json()['event']['invite_key']
    for name in ('А','Б','В'):
        assert requests.post(server+f'/api/invites/{key}/join',json={'name':name}).status_code==201
    cookies=owner.cookies.get_dict()
    def draw(_):
        r=requests.post(server+f'/api/santas/{eid}/draw',json={},cookies=cookies,timeout=10)
        return r.status_code,r.json()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(draw,range(8)))
    assert all(code==200 for code,_ in outcomes),outcomes
    assert sum(not obj['already_drawn'] for _,obj in outcomes)==1,outcomes
    assert owner.get(server+f'/api/santas/{eid}').json()['event']['status']=='drawn'
