"""Authenticated social features. All operations use the server-side, RLS-scoped
shursh_backend database role. Never expose auth emails or reservation identities.
No new outbound integrations or background jobs.
"""
import re
from uuid import UUID
from server import ApiError, req, optional

def _uuid(value):
    try:
        parsed = UUID(value)
        if str(parsed) != value.lower():
            raise ValueError()
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise ApiError(404, 'Пользователь не найден') from None

def _pair(a, b):
    if a == b:
        raise ApiError(400, 'Нельзя добавить самого себя')
    return tuple(sorted((a, b), key=str))

def _relationship(con, current, other):
    if current == other:
        return 'self'
    low, high = _pair(current, other)
    f = con.execute('SELECT status,requested_by FROM friendships WHERE user_low=? AND user_high=?',
                    (low, high)).fetchone()
    if not f:
        return 'none'
    if f['status'] == 'accepted':
        return 'friends'
    if f['status'] == 'declined':
        return 'none'
    return 'outgoing' if f['requested_by'] == current else 'incoming'

def _notify(con, recipient, kind, message, url='/', actor=None):
    # The text and target URL must be constructed solely by the server.
    con.execute('''INSERT INTO social_notifications(recipient_id,actor_id,kind,message,target_path)
                   VALUES(?,?,?,?,?)''',(recipient,actor,kind,message[:240],url[:300]))

def _friends(con, current):
    rows = con.execute('''SELECT p.id,p.name,p.bio FROM friendships f
         JOIN profiles p ON p.id=(CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END)
         WHERE f.status='accepted' AND (f.user_low=? OR f.user_high=?)
         ORDER BY lower(p.name),p.id''',(current,current,current))
    return [dict(r) for r in rows]

def _friends_only(con, a, b):
    if _relationship(con,a,b) != 'friends':
        raise ApiError(403,'Доступно только друзьям')

def _notify_friends(con, actor, kind, message, url):
    for friend in _friends(con,actor):
        _notify(con,friend['id'],kind,message,url,actor)

def _member(con, handler, event_id):
    user=handler.auth(con)
    participant=con.execute('''SELECT p.id,p.name,p.event_id FROM participants p
          WHERE p.event_id=? AND p.user_id=?''',(event_id,user['id'])).fetchone()
    if not participant:
        raise ApiError(404,'Игра не найдена')
    return participant

def handle(handler, method, path, con):
    """Return an API response triple or None for non-social endpoints."""
    if path=='/api/santas' and method=='GET':
        user=handler.auth(con)
        rows=con.execute('''SELECT e.*,count(p.id) AS participant_count,
                    (e.owner_id=?) AS is_owner
                    FROM santa_events e LEFT JOIN participants p ON p.event_id=e.id
                    WHERE e.owner_id=? OR EXISTS(
                        SELECT 1 FROM participants mine
                        WHERE mine.event_id=e.id AND mine.user_id=?)
                    GROUP BY e.id ORDER BY e.id DESC''',
                    (user['id'],user['id'],user['id']))
        return 200,{'events':[dict(e) for e in rows]},None

    if path == '/api/admin/overview' and method == 'GET':
        handler.is_site_admin(con)
        counts={}
        for key,table in (('users','profiles'),('wishlists','wishlists'),
                          ('wishes','wishes'),('events','santa_events'),
                          ('friends','friendships'),('notifications','social_notifications')):
            counts[key]=con.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n']
        counts['new_feedback']=con.execute("SELECT count(*) AS n FROM developer_feedback WHERE status='new'").fetchone()['n']
        return 200,{'stats':counts},None

    if path == '/api/profile/me' and method in ('GET','PATCH'):
        user=handler.auth(con)
        if method=='PATCH':
            data=handler.body()
            fields={}
            if 'name' in data:
                fields['name']=req(data['name'],'Имя',40)
            if 'bio' in data:
                fields['bio']=optional(data['bio'],'О себе',500)
            if 'discoverable' in data:
                if not isinstance(data['discoverable'],bool):
                    raise ApiError(400,'Неверная настройка видимости')
                fields['discoverable']=data['discoverable']
            if not fields:
                raise ApiError(400,'Нет изменений')
            con.execute('UPDATE profiles SET '+', '.join(k+'=?' for k in fields)+' WHERE id=?',
                        (*fields.values(),user['id']))
        p=con.execute('SELECT id,name,bio,discoverable FROM profiles WHERE id=?',(user['id'],)).fetchone()
        return 200,{'profile':dict(p)},None

    if path == '/api/users/search' and method=='GET':
        user=handler.auth(con)
        q=(handler.request.args.get('q') or '').strip()
        if len(q)<2 or len(q)>40:
            return 200,{'users':[]},None
        rows=con.execute('''SELECT p.id,p.name FROM profiles p
              WHERE p.discoverable=true AND p.id<>? AND p.name ILIKE ?
              ORDER BY lower(p.name),p.id LIMIT 20''',(user['id'],'%'+q+'%'))
        return 200,{'users':[dict(p) for p in rows]},None

    match=re.fullmatch(r'/api/users/([0-9a-fA-F-]{36})',path)
    if match and method=='GET':
        user=handler.auth(con)
        uid=_uuid(match.group(1))
        profile=con.execute('SELECT id,name,bio,discoverable FROM profiles WHERE id=?',(uid,)).fetchone()
        state=_relationship(con,user['id'],uid)
        if not profile or (not profile['discoverable'] and state not in ('self','friends')):
            raise ApiError(404,'Профиль не найден')
        lists=[]
        if state in ('self','friends'):
            rows=con.execute('''SELECT l.id,l.title,l.description,l.occasion,l.theme,l.share_key,
                       count(w.id) AS wish_count
                       FROM wishlists l LEFT JOIN wishes w ON w.list_id=l.id
                       WHERE l.owner_id=? AND l.visibility='link'
                       GROUP BY l.id ORDER BY l.id DESC''',(uid,))
            lists=[dict(r) for r in rows]
        return 200,{'profile':{'id':profile['id'],'name':profile['name'],'bio':profile['bio']},
                    'relationship':state,'lists':lists},None

    if path=='/api/friends' and method=='GET':
        user=handler.auth(con)
        rows=con.execute('''SELECT f.user_low,f.user_high,f.requested_by,f.status,
                    p.id AS other_id,p.name AS other_name
                    FROM friendships f
                    JOIN profiles p ON p.id=(CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END)
                    WHERE f.user_low=? OR f.user_high=?
                    ORDER BY f.updated_at DESC''',(user['id'],user['id'],user['id']))
        friends=[];incoming=[];outgoing=[]
        for item in rows:
            data={'id':item['other_id'],'name':item['other_name']}
            if item['status']=='accepted':
                friends.append(data)
            elif item['status']=='pending':
                (outgoing if item['requested_by']==user['id'] else incoming).append(data)
        return 200,{'friends':friends,'incoming':incoming,'outgoing':outgoing},None

    match=re.fullmatch(r'/api/friends/([0-9a-fA-F-]{36})',path)
    if match and method in ('POST','PATCH','DELETE'):
        user=handler.auth(con);other=_uuid(match.group(1));a,b=_pair(user['id'],other)
        if method=='POST':
            target=con.execute('SELECT id FROM profiles WHERE id=? AND discoverable=true',(other,)).fetchone()
            if not target:
                raise ApiError(404,'Профиль не найден')
            old=con.execute('SELECT status,requested_by FROM friendships WHERE user_low=? AND user_high=?',(a,b)).fetchone()
            if old and old['status']=='accepted':
                raise ApiError(409,'Вы уже друзья')
            if old and old['status']=='pending' and old['requested_by']==user['id']:
                raise ApiError(409,'Заявка уже отправлена')
            if old and old['status']=='pending' and old['requested_by']==other:
                con.execute("UPDATE friendships SET status='accepted',updated_at=now() WHERE user_low=? AND user_high=?",(a,b))
                _notify(con,other,'friend_accept','Заявка в друзья принята',f'/users/{user["id"]}',user['id'])
            else:
                con.execute('''INSERT INTO friendships(user_low,user_high,requested_by,status)
                      VALUES(?,?,?,'pending')
                      ON CONFLICT(user_low,user_high) DO UPDATE SET requested_by=excluded.requested_by,
                      status='pending',updated_at=now()''',(a,b,user['id']))
                _notify(con,other,'friend_request','Тебе отправили заявку в друзья',f'/friends',user['id'])
        elif method=='PATCH':
            data=handler.body()
            choice=data.get('action')
            if choice not in ('accept','decline'):
                raise ApiError(400,'Неверное действие')
            old=con.execute('SELECT status,requested_by FROM friendships WHERE user_low=? AND user_high=?',(a,b)).fetchone()
            if not old or old['status']!='pending' or old['requested_by']!=other:
                raise ApiError(404,'Входящая заявка не найдена')
            con.execute('UPDATE friendships SET status=?,updated_at=now() WHERE user_low=? AND user_high=?',
                        ('accepted' if choice=='accept' else 'declined',a,b))
            if choice=='accept':
                _notify(con,other,'friend_accept','Твою заявку в друзья приняли',f'/users/{user["id"]}',user['id'])
        else:
            con.execute('DELETE FROM friendships WHERE user_low=? AND user_high=?',(a,b))
        return 200,{'ok':True},None

    if path=='/api/notifications' and method=='GET':
        user=handler.auth(con)
        rows=con.execute('''SELECT id,kind,message,target_path,created_at,read_at
                      FROM social_notifications WHERE recipient_id=?
                      ORDER BY id DESC LIMIT 60''',(user['id'],))
        unread=con.execute('SELECT count(*) AS n FROM social_notifications WHERE recipient_id=? AND read_at IS NULL',
                           (user['id'],)).fetchone()['n']
        return 200,{'items':[dict(r) for r in rows],'unread':unread},None
    if path=='/api/notifications/unread' and method=='GET':
        user=handler.auth(con)
        count=con.execute('SELECT count(*) AS n FROM social_notifications WHERE recipient_id=? AND read_at IS NULL',
                          (user['id'],)).fetchone()['n']
        return 200,{'unread':count},None
    match=re.fullmatch(r'/api/notifications/(\d+)/read',path)
    if match and method=='POST':
        user=handler.auth(con)
        con.execute('UPDATE social_notifications SET read_at=COALESCE(read_at,now()) WHERE id=? AND recipient_id=?',
                    (int(match.group(1)),user['id']))
        return 200,{'ok':True},None

    match=re.fullmatch(r'/api/santas/(\d+)/invite-friend/([0-9a-fA-F-]{36})',path)
    if match and method=='POST':
        user=handler.auth(con);eid=int(match.group(1));other=_uuid(match.group(2))
        _friends_only(con,user['id'],other)
        e=con.execute('SELECT title,invite_key,status FROM santa_events WHERE id=? AND owner_id=?',(eid,user['id'])).fetchone()
        if not e:
            raise ApiError(404,'Игра не найдена')
        if e['status']!='open':
            raise ApiError(409,'Приглашения закрыты после жеребьёвки')
        if con.execute('SELECT 1 FROM participants WHERE event_id=? AND user_id=?',(eid,other)).fetchone():
            raise ApiError(409,'Друг уже участвует')
        if con.execute('SELECT 1 FROM santa_friend_invitations WHERE event_id=? AND invited_user_id=?',(eid,other)).fetchone():
            raise ApiError(409,'Приглашение уже отправлено')
        con.execute('INSERT INTO santa_friend_invitations(event_id,invited_user_id,invited_by) VALUES(?,?,?)',
                    (eid,other,user['id']))
        _notify(con,other,'santa_invitation','Тебя зовут в Тайного Санту: '+e['title'],
                '/join/'+e['invite_key'],user['id'])
        return 201,{'ok':True},None

    match=re.fullmatch(r'/api/wishes/(\d+)/request-friend/([0-9a-fA-F-]{36})',path)
    if match and method=='POST':
        user=handler.auth(con);wid=int(match.group(1));other=_uuid(match.group(2))
        _friends_only(con,user['id'],other)
        wish=con.execute('''SELECT w.title,l.share_key FROM wishes w
                  JOIN wishlists l ON l.id=w.list_id
                  WHERE w.id=? AND l.owner_id=? AND l.visibility='link' ''',
                  (wid,user['id'])).fetchone()
        if not wish:
            raise ApiError(404,'Подарок не найден в доступном списке')
        if con.execute('SELECT 1 FROM wish_friend_requests WHERE wish_id=? AND friend_id=?',(wid,other)).fetchone():
            raise ApiError(409,'Просьба уже отправлена этому другу')
        con.execute('INSERT INTO wish_friend_requests(wish_id,requester_id,friend_id) VALUES(?,?,?)',
                    (wid,user['id'],other))
        _notify(con,other,'wish_request','Друг просит подарить ему: '+wish['title'],
                '/w/'+wish['share_key'],user['id'])
        return 201,{'ok':True},None

    # Authenticated game members can revisit the same game without keeping
    # a bearer URL in localStorage. Member-only projections are enforced by UID.
    match=re.fullmatch(r'/api/member/(\d+)(?:/(roster|preferences|wishes|wishes/import|wishes/\d+|messages/(?:general|to-recipient|from-santa)|reveal))?',path)
    if match:
        eid=int(match.group(1));sub=match.group(2)
        part=_member(con,handler,eid)
        if not sub and method=='GET':
            event=con.execute('SELECT id,title,description,exchange_date,budget_cents,currency,rules,status,invite_key FROM santa_events WHERE id=?',(eid,)).fetchone()
            participants=handler.santa_roster(con,eid)
            detail=dict(event)
            if detail['status']!='open':
                detail.pop('invite_key',None)
            assignment=handler.assignment_view(con,eid,part['id']) if event['status']=='drawn' else None
            return 200,{'event':detail,'participant':dict(part),'participants':participants,
                        'wishes':handler.game_wishes(con,part['id']),
                        'preferences':handler.participant_preferences(con,part['id']),
                        'assignment':assignment,'rich_enabled':handler.santa_schema_ready(con)},None
        if sub=='roster' and method=='GET':
            e=con.execute('SELECT status FROM santa_events WHERE id=?',(eid,)).fetchone()
            return 200,{'status':e['status'],'participants':handler.santa_roster(con,eid)},None
        if sub=='preferences' and method=='PATCH':
            return handler.edit_participant_preferences(con,part['id'])
        if sub=='wishes' and method=='POST':
            return 201,handler.add_game_wish(con,part['id'],handler.body()),None
        if sub=='wishes' and method=='GET':
            return 200,{'wishes':handler.game_wishes(con,part['id'])},None
        if sub=='wishes/import' and method=='POST':
            return 200,handler.import_wishlist_wishes(con,handler.auth(con),part['id'],handler.body()),None
        if sub and sub.startswith('wishes/') and method in ('PATCH','DELETE'):
            return handler.mutate_game_wish(con,part['id'],int(sub.split('/')[1]),method)
        if sub=='reveal' and method=='POST':
            return 200,{'assignment':handler.reveal(con,eid,part['id'])},None
        if sub and sub.startswith('messages/') and method in ('GET','POST'):
            return handler.chat_messages(con,eid,part['id'],sub.split('/')[1],method)
        raise ApiError(405,'Метод не поддерживается')
    return None

def after_mutation(handler, method, path, con, result):
    """Emit durable notifications in the SAME transaction as the business change."""
    if method!='POST' or result[0]>=300:
        return
    user=handler.user(con)
    if path=='/api/lists' and user and result[1].get('id'):
        lid=result[1]['id']
        item=con.execute('SELECT title,visibility,share_key FROM wishlists WHERE id=? AND owner_id=?',
                         (lid,user['id'])).fetchone()
        if item and item['visibility']=='link':
            _notify_friends(con,user['id'],'wishlist_new','Друг создал вишлист «'+item['title']+'»',
                            '/w/'+item['share_key'])
    match=re.fullmatch(r'/api/lists/(\d+)/wishes',path)
    if match and user and result[1].get('id'):
        wish=con.execute('''SELECT w.title,l.visibility,l.share_key FROM wishes w
                 JOIN wishlists l ON l.id=w.list_id
                 WHERE w.id=? AND l.owner_id=?''',(result[1]['id'],user['id'])).fetchone()
        if wish and wish['visibility']=='link':
            _notify_friends(con,user['id'],'wish_new','Друг добавил новый подарок: '+wish['title'],
                            '/w/'+wish['share_key'])
    match=re.fullmatch(r'/api/public/([A-Za-z0-9_-]+)/reserve/(\d+)',path)
    if match:
        owner=con.execute('''SELECT l.owner_id FROM wishes w JOIN wishlists l ON l.id=w.list_id
                              WHERE w.id=? AND l.share_key=?''',(int(match.group(2)),match.group(1))).fetchone()
        if owner:
            # NEVER include wish title, ID, guest name or reservation token.
            _notify(con,owner['owner_id'],'reservation_anonymous',
                    'Для тебя анонимно забронировали подарок','/lists')
    match=re.fullmatch(r'/api/santas/(\d+)/draw',path)
    if match and not result[1].get('already_drawn'):
        eid=int(match.group(1))
        for member in con.execute('SELECT user_id FROM participants WHERE event_id=? AND user_id IS NOT NULL',(eid,)):
            _notify(con,member['user_id'],'santa_drawn','Жеребьёвка прошла! Тайный Санта начался',
                    '/santa/'+str(eid))
    match=re.fullmatch(r'/api/invites/([A-Za-z0-9_-]+)/join',path)
    if match:
        event=con.execute('SELECT id,owner_id FROM santa_events WHERE invite_key=?',(match.group(1),)).fetchone()
        if event:
            # Notify every registered member, not merely the organizer.
            # Guests without a registered user ID do not receive account alerts.
            for member in con.execute(
                'SELECT DISTINCT user_id FROM participants WHERE event_id=? AND user_id IS NOT NULL',
                (event['id'],)):
                if not user or member['user_id']!=user['id']:
                    _notify(con,member['user_id'],'santa_joined',
                            'К Тайному Санте присоединился новый участник',
                            '/santa/'+str(event['id']))
            if user:
                con.execute("UPDATE santa_friend_invitations SET status='accepted' WHERE event_id=? AND invited_user_id=?",
                            (event['id'],user['id']))
