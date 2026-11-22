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

def registered_buyer(server):
    s=requests.Session()
    response=s.post(server+'/api/register',json={
        'email':f'buyer-{time.time_ns()}@example.test',
        'password':'ValidPassword123!', 'name':'Даритель'})
    assert response.status_code==200,response.text
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
    assert anon.post(server+f'/api/public/{key}/reserve/{wid}',json={}).status_code==401
    buyer=registered_buyer(server)
    r=buyer.post(server+f'/api/public/{key}/reserve/{wid}',json={})
    assert r.status_code==201,r.text
    assert r.json()=={'ok':True}
    assert anon.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved'] is True
    assert anon.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved_by_me'] is False
    assert buyer.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved_by_me'] is True
    assert 'reserved' not in owner.get(server+f'/api/lists/{lid}').json()['wishes'][0]
    owner_public=owner.get(server+f'/api/public/{key}').json()
    assert owner_public['owner_view'] is True
    assert 'reserved' not in owner_public['wishes'][0]
    assert owner.post(server+f'/api/public/{key}/reserve/{wid}',json={}).status_code==403
    assert anon.delete(server+f'/api/public/{key}/reserve/{wid}').status_code==401
    assert buyer.delete(server+f'/api/public/{key}/reserve/{wid}').status_code==200
    assert buyer.delete(server+f'/api/public/{key}/reserve/{wid}').status_code==409
    assert anon.get(server+f'/api/public/{key}').json()['wishes'][0]['reserved'] is False
    assert anon.get(server+f'/api/reservations/wrongtoken').status_code==404
    assert owner.patch(server+f'/api/lists/{lid}',json={'visibility':'private'}).status_code==200
    assert anon.get(server+f'/api/public/{key}').status_code==404

def test_double_reserve_race(server,owner):
    r=owner.post(server+'/api/lists',json={'title':'Гонка','visibility':'link'})
    lid=r.json()['id'];key=owner.get(server+f'/api/lists/{lid}').json()['list']['share_key']
    w=owner.post(server+f'/api/lists/{lid}/wishes',json={'title':'Последний подарок'})
    wid=w.json()['id']
    buyer=registered_buyer(server)
    cookie=buyer.cookies.get('shursh_sid')
    assert cookie
    def reserve(n):return requests.post(server+f'/api/public/{key}/reserve/{wid}',
                  cookies={'shursh_sid':cookie},json={},timeout=5).status_code
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
        a=owner.post(server+f'/api/santas/{eid}/participants',json={'name':name})
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
    assert requests.post(server+f'/api/invites/{key}/join',json={'name':'Поздний гость'}).status_code==401
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
        assert owner.post(server+f'/api/santas/{eid}/participants',json={'name':name}).status_code==201
    cookies=owner.cookies.get_dict()
    def draw(_):
        r=requests.post(server+f'/api/santas/{eid}/draw',json={},cookies=cookies,timeout=10)
        return r.status_code,r.json()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(draw,range(8)))
    assert all(code==200 for code,_ in outcomes),outcomes
    assert sum(not obj['already_drawn'] for _,obj in outcomes)==1,outcomes
    assert owner.get(server+f'/api/santas/{eid}').json()['event']['status']=='drawn'


def test_santa_organizer_can_add_players_and_prevent_self_join(server,owner):
    game=owner.post(server+'/api/santas',json={'title':'Без дублей'})
    assert game.status_code==201
    eid=game.json()['id']
    key=owner.get(server+f'/api/santas/{eid}').json()['event']['invite_key']
    assert owner.get(server+f'/api/invites/{key}').json()['already_joined'] is True
    assert owner.post(server+f'/api/invites/{key}/join',
                      json={'name':'Совсем другое имя'}).status_code==409
    assert owner.post(server+f'/api/santas/{eid}/participants',
                      json={'name':'Саша'}).status_code==409

    added=owner.post(server+f'/api/santas/{eid}/participants',json={'name':'Маша'})
    assert added.status_code==201, added.text
    token=added.json()['participant_token']
    assert requests.get(server+f'/api/participant/{token}').status_code==200
    assert owner.post(server+f'/api/santas/{eid}/participants',
                      json={'name':'  МАША  '}).status_code==409
    assert registered_buyer(server).post(server+f'/api/invites/{key}/join',
                         json={'name':'маша'}).status_code==409
    assert owner.get(server+f'/api/santas/{eid}').json()['participants'][-1]['name']=='Маша'

    pid=added.json()['id']
    changed=owner.post(server+f'/api/santas/{eid}/participants/{pid}/new-link',json={})
    assert changed.status_code==200,changed.text
    assert requests.get(server+f'/api/participant/{token}').status_code==404
    assert requests.get(server+f'/api/participant/{changed.json()["participant_token"]}').status_code==200
    assert requests.post(server+f'/api/santas/{eid}/participants',
                         json={'name':'Нарушитель'}).status_code==401


def test_santa_edit_budget_date_and_freeze_participants(server,owner):
    r=owner.post(server+'/api/santas',json={'title':'Меняем планы','budget':1500})
    eid=r.json()['id']
    update=owner.patch(server+f'/api/santas/{eid}',
                       json={'budget':2500,'exchange_date':'2027-01-15'})
    assert update.status_code==200,update.text
    event=owner.get(server+f'/api/santas/{eid}').json()['event']
    assert event['budget_cents']==250000
    assert event['exchange_date']=='2027-01-15'
    assert owner.patch(server+f'/api/santas/{eid}',
                       json={'exchange_date':'2027-02-30'}).status_code==400
    assert owner.patch(server+f'/api/santas/{eid}',json={'title':'Что угодно'}).status_code==400
    assert owner.patch(server+f'/api/santas/{eid}',
                       json={'budget':-10}).status_code==400
    for name in ('Гость А','Гость Б'):
        assert owner.post(server+f'/api/santas/{eid}/participants',
                          json={'name':name}).status_code==201
    assert owner.post(server+f'/api/santas/{eid}/draw',json={}).status_code==200
    assert owner.post(server+f'/api/santas/{eid}/participants',
                      json={'name':'Поздний'}).status_code==409
    assert owner.patch(server+f'/api/santas/{eid}',
                       json={'budget':2900,'exchange_date':'2027-01-20'}).status_code==200
    event=owner.get(server+f'/api/santas/{eid}').json()['event']
    assert event['budget_cents']==290000
    assert event['exchange_date']=='2027-01-20'
    assert event['status']=='drawn'


def test_import_only_owned_wishlist_items_into_santa(server,owner):
    l=owner.post(server+'/api/lists',json={'title':'Подарки для Санты'})
    lid=l.json()['id']
    a=owner.post(server+f'/api/lists/{lid}/wishes',json={'title':'Тёплый плед'})
    b=owner.post(server+f'/api/lists/{lid}/wishes',json={'title':'Настольная игра'})
    assert a.status_code==201 and b.status_code==201
    ids=[a.json()['id'],b.json()['id']]
    e=owner.post(server+'/api/santas',json={'title':'Санта с подарками'}).json()['id']
    path=server+f'/api/santas/{e}/my-wishes/import'
    result=owner.post(path,json={'list_id':lid,'wish_ids':ids})
    assert result.status_code==200,result.text
    assert result.json()['added']==2
    assert result.json()['snapshot'] is True
    assert owner.post(path,json={'list_id':lid}).json()['added']==0
    wishes=owner.get(server+f'/api/santas/{e}').json()['my_wishes']
    assert {w['title'] for w in wishes}=={'Тёплый плед','Настольная игра'}
    assert owner.post(path,json={'list_id':lid,'wish_ids':[999999]}).status_code==400
    assert owner.post(path,json={'list_id':lid,'wish_ids':[ids[0],ids[0]]}).status_code==400

    event=owner.get(server+f'/api/santas/{e}').json()['event']
    guest=requests.Session()
    join=owner.post(server+f'/api/santas/{e}/participants',json={'name':'Гость'})
    assert join.status_code==201
    token=join.json()['participant_token']
    assert guest.post(server+f'/api/participant/{token}/wishes/import',
                      json={'list_id':lid,'wish_ids':ids}).status_code==401
    assert owner.post(server+f'/api/participant/{token}/wishes/import',
                      json={'list_id':lid,'wish_ids':[ids[0]]}).status_code==200
    own=guest.get(server+f'/api/participant/{token}').json()['wishes']
    assert len(own)==1 and own[0]['title']=='Тёплый плед'
    assert owner.get(server+f'/api/lists/{lid}').json()['wishes'][0]['title'] in {'Тёплый плед','Настольная игра'}


def test_santa_game_gift_cards_and_anonymous_chats(server,owner):
    """SQLite parity: member gifts, general room, hidden pair identities."""
    eid=owner.post(server+'/api/santas',json={'title':'Новый праздничный чат'}).json()['id']
    key=owner.get(server+f'/api/santas/{eid}').json()['event']['invite_key']
    users={}
    for name in ('Первый','Второй'):
        session=requests.Session()
        response=owner.post(server+f'/api/santas/{eid}/participants',json={'name':name})
        assert response.status_code==201,response.text
        users[name]=(session,response.json()['participant_token'])
    one,t1=users['Первый']
    two,t2=users['Второй']
    create=one.post(server+f'/api/participant/{t1}/wishes',json={
        'title':'Подарок','wanted':'Стекло','unwanted':'Не пластик',
        'price':1000,'currency':'RUB','shop_url':'https://example.com/gift'})
    assert create.status_code==201,create.text
    wid=create.json()['id']
    gift=one.get(server+f'/api/participant/{t1}').json()['wishes'][0]
    assert gift['title']=='Подарок' and gift['wanted']=='Стекло'
    assert gift['unwanted']=='Не пластик' and gift['price_cents']==100000
    assert 'Подарок' not in str(two.get(server+f'/api/participant/{t2}').json())
    assert two.patch(server+f'/api/participant/{t2}/wishes/{wid}',json={'title':'Грязный'}).status_code==404
    change=one.patch(server+f'/api/participant/{t1}/wishes/{wid}',json={
        'title':'Подарок 2','wanted':'Большой','unwanted':'Без батареек'})
    assert change.status_code==200,change.text
    assert one.get(server+f'/api/participant/{t1}').json()['wishes'][0]['wanted']=='Большой'
    assert one.get(server+f'/api/participant/{t1}/messages/to-recipient').status_code==409
    assert one.post(server+f'/api/participant/{t1}/messages/general',json={'message':'Привет всем!'}).status_code==201
    general=two.get(server+f'/api/participant/{t2}/messages/general').json()
    assert general['messages'][0]['author']=='Первый'
    assert general['messages'][0]['message']=='Привет всем!'
    assert 'sender_id' not in str(general)
    assert requests.get(server+f'/api/participant/bad-token/messages/general').status_code==404
    assert owner.post(server+f'/api/santas/{eid}/draw',json={}).status_code==200
    name=one.post(server+f'/api/participant/{t1}/reveal',json={}).json()['assignment']['receiver_name']
    sent=one.post(server+f'/api/participant/{t1}/messages/to-recipient',json={'message':'Это тайный подарок'})
    assert sent.status_code==201,sent.text
    if name=='Саша':
        inbox=owner.get(server+f'/api/santas/{eid}/messages/from-santa')
    else:
        inbox=users[name][0].get(server+f'/api/participant/{users[name][1]}/messages/from-santa')
    assert inbox.status_code==200
    message=inbox.json()['messages'][-1]
    assert message['author']=='Тайный даритель' and not message['mine']
    assert 'sender_id' not in message
    assert two.delete(server+f'/api/participant/{t2}/wishes/{wid}').status_code==404
    assert one.delete(server+f'/api/participant/{t1}/wishes/{wid}').status_code==200


def test_santa_owner_can_finish_before_draw_and_delete_any_state(server, owner):
    """Owner may archive an unplayed game or delete open/drawn/finished games."""
    stranger = registered_buyer(server)
    for initial in ('open', 'drawn', 'finished'):
        created = owner.post(server + '/api/santas', json={'title': 'Удаляем ' + initial})
        assert created.status_code == 201, created.text
        eid = created.json()['id']
        url = server + f'/api/santas/{eid}'
        part = owner.post(url + '/participants', json={'name': 'Гость с доступом'})
        assert part.status_code == 201, part.text
        token = part.json()['participant_token']
        assert stranger.delete(url).status_code == 404
        assert requests.delete(url).status_code == 401
        if initial in ('drawn', 'finished'):
            assert owner.post(url + '/participants', json={'name': 'Третий'}).status_code == 201
            assert owner.post(url + '/draw', json={}).status_code == 200
        if initial == 'finished':
            finished = owner.post(url + '/finish', json={})
            assert finished.status_code == 200, finished.text
            assert owner.get(url).json()['event']['status'] == 'finished'
        if initial == 'open':
            archived = owner.post(url + '/finish', json={})
            assert archived.status_code == 200, archived.text
            assert archived.json()['already_finished'] is False
            assert owner.get(url).json()['event']['status'] == 'finished'
            assert owner.post(url + '/draw', json={}).status_code == 409
        deleted = owner.delete(url)
        assert deleted.status_code == 200, deleted.text
        assert owner.get(url).status_code == 404
        assert requests.get(server + f'/api/participant/{token}').status_code == 404
        assert owner.delete(url).status_code == 404


def test_registered_only_invites_and_one_time_personal_link(server, owner):
    """New Santa invitations do not create guest participants until authenticated acceptance."""
    event = owner.post(server+'/api/santas',json={'title':'Registered Santa'})
    assert event.status_code==201,event.text
    eid=event.json()['id']
    url=server+f'/api/santas/{eid}'
    key=owner.get(url).json()['event']['invite_key']
    assert len(owner.get(url).json()['participants'])==1

    private=owner.post(url+'/personal-invites',json={})
    assert private.status_code==201,private.text
    secret=private.json()['invite_token']
    assert len(secret)==43
    assert len(owner.get(url).json()['participants'])==1, 'No placeholder participants'
    info=requests.get(server+'/api/personal-invites/'+secret)
    assert info.status_code==200,info.text
    assert info.json()['event']['title']=='Registered Santa'
    assert info.json()['used'] is False

    assert requests.post(server+'/api/invites/'+key+'/join',json={'name':'Гость'}).status_code==401
    assert requests.post(server+'/api/personal-invites/'+secret+'/join',
                         json={'name':'Гость'}).status_code==401
    buyer=registered_buyer(server)
    joined=buyer.post(server+'/api/personal-invites/'+secret+'/join',json={'name':'Новый участник'})
    assert joined.status_code==201,joined.text
    assert joined.json()['event_id']==eid
    assert requests.get(server+'/api/personal-invites/'+secret).json()['used'] is True
    assert len(owner.get(url).json()['participants'])==2

    second=registered_buyer(server)
    again=second.post(server+'/api/personal-invites/'+secret+'/join',json={'name':'Второй'})
    assert again.status_code==409,again.text
    assert len(owner.get(url).json()['participants'])==2
    public_join=second.post(server+'/api/invites/'+key+'/join',json={'name':'Второй'})
    assert public_join.status_code==201,public_join.text
    assert public_join.json()=={'event_id':eid}, 'Registered players must never receive anonymous bearer tokens'
    assert len(owner.get(url).json()['participants'])==3
