"""Authenticated social features. All operations use the server-side, RLS-scoped
shursh_backend database role. Never expose auth emails or reservation identities.
No new outbound integrations or background jobs.
"""
import re
import os
from uuid import UUID

NOTIFY_FIELDS=('notify_friends','notify_santa','notify_gifts','notify_system')
NOTIFY_KIND_FIELD={
 'friend_request':'notify_friends','friend_accept':'notify_friends',
 'santa_invitation':'notify_santa','santa_joined':'notify_santa','santa_drawn':'notify_santa',
 'wishlist_new':'notify_gifts','wish_new':'notify_gifts','wish_request':'notify_gifts',
 'reservation_anonymous':'notify_gifts'
}
PROFILE_EMOJIS = frozenset(["🎁","🎄","🐱","🦊","🐻","🐼","🐸","🦄","🐰","🧸","✨","🌸","🌼","🌙","⭐","🎮","🎨","📚","🎵","🚀","☕","🍓","💚"])
from server import ApiError, req, optional, token_hash
from cloud import referrals

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
    setting=NOTIFY_KIND_FIELD.get(kind,'notify_system')
    pref=con.execute('SELECT '+setting+' FROM profiles WHERE id=?',(recipient,)).fetchone()
    if not pref or not pref[setting]:
        return
    con.execute('''INSERT INTO social_notifications(recipient_id,actor_id,kind,message,target_path)
                   VALUES(?,?,?,?,?)''',(recipient,actor,kind,message[:240],url[:300]))

def _friends(con, current):
    rows = con.execute('''SELECT p.id,p.name,p.bio,p.handle,p.avatar_emoji FROM friendships f
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

def request_friend(con, user, other, *, invitation=False):
    a,b=_pair(user['id'],other)
    where='(discoverable OR allow_friend_invites)' if invitation else 'discoverable=true'
    target=con.execute('SELECT id FROM profiles WHERE id=? AND '+where,(other,)).fetchone()
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
        con.execute("""INSERT INTO friendships(user_low,user_high,requested_by,status)
              VALUES(?,?,?,'pending') ON CONFLICT(user_low,user_high) DO UPDATE
              SET requested_by=excluded.requested_by,status='pending',updated_at=now()""",(a,b,user['id']))
        _notify(con,other,'friend_request','Тебе отправили заявку в друзья','/friends',user['id'])

def handle(handler, method, path, con):
    """Return an API response triple or None for non-social endpoints."""
    if path=='/api/friend-invites/me' and method in ('POST','DELETE'):
        user=handler.auth(con)
        referrals.require_ready(con)
        if method=='DELETE':
            con.execute('UPDATE user_invites SET revoked_at=now() WHERE owner_id=? AND revoked_at IS NULL',(user['id'],))
            return 200,{'ok':True},None
        origin=('https://'+handler.request.host) if os.getenv('VERCEL') else handler.request.host_url
        return 200,referrals.own_invite(con,user['id'],origin),None
    invite=re.fullmatch(r'/api/friend-invites/([A-Za-z0-9_-]{24})(/friend)?',path)
    if invite and ((method=='GET' and not invite.group(2)) or (method=='POST' and invite.group(2))):
        referrals.require_ready(con)
        p=referrals.active(con,invite.group(1))
        if method=='POST':
            user=handler.auth(con)
            request_friend(con,user,p['owner_id'],invitation=True)
            return 200,{'ok':True},None
        user=handler.user(con)
        return 200,{'inviter':{'id':p['owner_id'],'name':p['name'],'handle':p['handle'],
                               'avatar_emoji':p['avatar_emoji']},
                    'relationship':_relationship(con,user['id'],p['owner_id']) if user else 'guest'},None
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
        invitations=con.execute('''SELECT e.id,e.title,e.description,e.exchange_date,
                      e.budget_cents,e.currency,e.invite_key
                      FROM santa_friend_invitations i
                      JOIN santa_events e ON e.id=i.event_id
                      WHERE i.invited_user_id=? AND i.status='pending'
                        AND e.status='open' AND NOT EXISTS(
                            SELECT 1 FROM participants p
                            WHERE p.event_id=e.id AND p.user_id=?)
                      ORDER BY i.created_at DESC LIMIT 30''',(user['id'],user['id']))
        return 200,{'events':[dict(e) for e in rows],
                    'invitations':[dict(e) for e in invitations]},None

    if path == '/api/admin/overview' and method == 'GET':
        handler.is_site_admin(con)
        # Admin hub only needs actionable totals; do not scan unrelated private tables.
        counts={'users':con.execute('SELECT count(*) AS n FROM profiles').fetchone()['n']}
        counts['new_feedback']=con.execute("SELECT count(*) AS n FROM developer_feedback WHERE status='new'").fetchone()['n']
        if referrals.ready(con):
            counts['referrals']=con.execute('SELECT count(*) AS n FROM referral_attributions').fetchone()['n']
        return 200,{'stats':counts},None

    if path == '/api/admin/users' and method == 'GET':
        # Never return passwords, session tokens, emails, friendship edges,
        # gift reservations, private wishes or private Santa assignments.
        handler.is_site_admin(con)
        raw_offset=(handler.request.args.get('offset') or '0').strip()
        if not re.fullmatch(r'\d{1,5}',raw_offset) or int(raw_offset)>10000:
            raise ApiError(400,'Неверная страница')
        offset=int(raw_offset)
        search=(handler.request.args.get('q') or '').strip()
        if len(search)>50:
            raise ApiError(400,'Слишком длинный поисковый запрос')
        where='WHERE (p.name ILIKE ? OR coalesce(p.handle,\'\') ILIKE ?)' if search else ''
        args=('%'+search+'%','%'+search.lstrip('@')+'%') if search else ()
        total=con.execute('SELECT count(*) AS n FROM profiles p '+where,args).fetchone()['n']
        # Backward-safe read during rollout: no invented historical activity.
        ready=con.execute("SELECT to_regclass('public.admin_user_activity') IS NOT NULL AS ready").fetchone()['ready']
        seen='a.last_seen_at' if ready else 'NULL::timestamptz'
        platform='a.last_platform' if ready else 'NULL::text'
        recorded=f'({seen} IS NOT NULL AND (s.latest_session_at IS NULL OR {seen}>=s.latest_session_at))'
        activity_columns=f'''GREATEST({seen},s.latest_session_at) AS last_seen_at,
          CASE WHEN {recorded} THEN {platform} WHEN s.latest_session_at IS NOT NULL THEN 'unknown' END AS last_platform,
          CASE WHEN {recorded} THEN 'visit' WHEN s.latest_session_at IS NOT NULL THEN 'session' END AS last_seen_source'''
        activity_join=(' LEFT JOIN admin_user_activity a ON a.user_id=p.id ' if ready else ' ')+'''
          LEFT JOIN LATERAL (SELECT max(created_at) AS latest_session_at FROM app_sessions
                             WHERE user_id=p.id) s ON TRUE '''
        rows=con.execute('''SELECT p.id,p.name,p.handle,p.avatar_emoji,p.created_at,p.discoverable,
                 '''+activity_columns+''',
                 (SELECT count(*) FROM wishlists w WHERE w.owner_id=p.id) AS wishlists_count,
                 (SELECT count(*) FROM santa_events e WHERE e.owner_id=p.id) AS organized_games,
                 (SELECT count(*) FROM participants m WHERE m.user_id=p.id) AS joined_games
                 FROM profiles p '''+activity_join+where+'''
                 ORDER BY p.created_at DESC,p.id DESC LIMIT ? OFFSET ?''',
                 (*args,25,offset)).fetchall()
        return 200,{'users':[dict(row) for row in rows],
                    'total':total,'offset':offset,'limit':25},None

    if path == '/api/profile/me' and method in ('GET','PATCH'):
        user=handler.auth(con)
        enabled=referrals.ready(con)
        if method=='PATCH':
            data=handler.body()
            fields={}
            if 'name' in data:
                fields['name']=req(data['name'],'Имя',40)
            if 'bio' in data:
                fields['bio']=optional(data['bio'],'О себе',500)
            for key,label in (('last_name','Фамилия'),('patronymic','Отчество')):
                if key in data:
                    if not enabled: raise ApiError(503,'Настройки пока недоступны')
                    fields[key]=optional(data[key],label,60)
            for key in ('show_full_name','allow_friend_invites'):
                if key in data:
                    if not enabled: raise ApiError(503,'Настройки пока недоступны')
                    if not isinstance(data[key],bool): raise ApiError(400,'Неверная настройка видимости')
                    fields[key]=data[key]
            if 'handle' in data:
                handle=data['handle']
                if not isinstance(handle,str):
                    raise ApiError(400,'Неверный никнейм')
                handle=handle.strip().lower().removeprefix('@')
                if handle and not re.fullmatch(r'[a-z][a-z0-9_]{2,19}',handle):
                    raise ApiError(400,'Никнейм: 3–20 латинских символов, цифры и _; первая — буква')
                if handle and con.execute('SELECT 1 FROM profiles WHERE lower(handle)=? AND id<>?',(handle,user['id'])).fetchone():
                    raise ApiError(409,'Этот никнейм уже занят')
                fields['handle']=handle or None
            if 'avatar_emoji' in data:
                if not isinstance(data['avatar_emoji'],str) or data['avatar_emoji'] not in PROFILE_EMOJIS:
                    raise ApiError(400,'Выбери аватар из предложенных эмодзи')
                fields['avatar_emoji']=data['avatar_emoji']
            if 'city' in data:
                fields['city']=optional(data['city'],'Город',60)
            if 'discoverable' in data:
                if not isinstance(data['discoverable'],bool):
                    raise ApiError(400,'Неверная настройка видимости')
                fields['discoverable']=data['discoverable']
            for setting in NOTIFY_FIELDS:
                if setting in data:
                    if not isinstance(data[setting],bool):
                        raise ApiError(400,'Неверная настройка уведомлений')
                    fields[setting]=data[setting]
            if not fields:
                raise ApiError(400,'Нет изменений')
            con.execute('UPDATE profiles SET '+', '.join(k+'=?' for k in fields)+' WHERE id=?',
                        (*fields.values(),user['id']))
        extra=',last_name,patronymic,show_full_name,allow_friend_invites' if enabled else ''
        p=con.execute('SELECT id,name,bio,discoverable,handle,avatar_emoji,city,notify_friends,notify_santa,notify_gifts,notify_system'+extra+' FROM profiles WHERE id=?',(user['id'],)).fetchone()
        if enabled and method=='PATCH' and not (p['discoverable'] or p['allow_friend_invites']):
            con.execute('UPDATE user_invites SET revoked_at=now() WHERE owner_id=? AND revoked_at IS NULL',(user['id'],))
        lists=con.execute("""SELECT l.id,l.title,l.description,l.occasion,l.theme,l.share_key,
                            count(w.id) AS wish_count FROM wishlists l
                            LEFT JOIN wishes w ON w.list_id=l.id
                            WHERE l.owner_id=? AND l.visibility='link'
                            GROUP BY l.id ORDER BY l.id DESC""",(user['id'],)).fetchall()
        count=con.execute('SELECT count(*) AS n FROM referral_attributions WHERE referrer_id=?',(user['id'],)).fetchone()['n'] if enabled else 0
        return 200,{'profile':{**dict(p),'email':user['email']},'lists':[dict(l) for l in lists],'invites_enabled':enabled,'referral_count':count},None

    if path == '/api/users/search' and method=='GET':
        user=handler.auth(con)
        q=' '.join((handler.request.args.get('q') or '').split())
        if len(q)<2 or len(q)>120:
            return 200,{'users':[]},None
        exact=q.startswith('@')
        if '@' in q and not exact:
            return 200,{'users':[]},None
        term=q[1:].lower() if exact else q.lower()
        if exact and not re.fullmatch(r'[a-z][a-z0-9_]{2,19}',term):
            return 200,{'users':[]},None
        escaped=term.replace('!','!!').replace('%','!%').replace('_','!_')
        enabled=referrals.ready(con)
        full=("CASE WHEN p.show_full_name THEN concat_ws(' ',nullif(p.last_name,''),p.name,nullif(p.patronymic,'')) ELSE p.name END"
              if enabled else 'p.name')
        full_alt=("CASE WHEN p.show_full_name THEN concat_ws(' ',p.name,nullif(p.last_name,''),nullif(p.patronymic,'')) ELSE p.name END" if enabled else 'p.name')
        cols=("CASE WHEN p.show_full_name THEN p.last_name ELSE '' END AS last_name,"
              "CASE WHEN p.show_full_name THEN p.patronymic ELSE '' END AS patronymic," if enabled else '')
        base="""SELECT p.id,p.name,p.handle,p.avatar_emoji,"""+cols+"""
             CASE WHEN f.status='accepted' THEN 'friends'
                  WHEN f.status='pending' AND f.requested_by=? THEN 'outgoing'
                  WHEN f.status='pending' THEN 'incoming' ELSE 'none' END AS relationship
             FROM profiles p LEFT JOIN friendships f ON
             ((f.user_low=? AND f.user_high=p.id) OR (f.user_high=? AND f.user_low=p.id))
             WHERE p.discoverable=true AND p.id<>? AND """
        uid=user['id']
        if exact:
            rows=con.execute(base+'lower(p.handle)=? LIMIT 1',(uid,uid,uid,uid,term))
        else:
            rows=con.execute(base+'('+full+" ILIKE ? ESCAPE '!' OR "+full_alt+" ILIKE ? ESCAPE '!' OR p.name ILIKE ? ESCAPE '!' OR p.handle ILIKE ? ESCAPE '!') "
                +'ORDER BY CASE WHEN lower(p.handle)=? THEN 0 WHEN lower('+full+')=? OR lower('+full_alt+')=? OR lower(p.name)=? THEN 1 '
                + "WHEN "+full+" ILIKE ? ESCAPE '!' OR p.name ILIKE ? ESCAPE '!' THEN 2 ELSE 3 END,lower(p.name),p.id LIMIT 20",
                (uid,uid,uid,uid,*(['%'+escaped+'%']*4),term,term,term,term,escaped+'%',escaped+'%'))
        return 200,{'users':[dict(p) for p in rows]},None

    match=re.fullmatch(r'/api/users/([0-9a-fA-F-]{36})',path)
    if match and method=='GET':
        user=handler.auth(con)
        uid=_uuid(match.group(1))
        enabled=referrals.ready(con)
        profile=con.execute('SELECT id,name,bio,discoverable,handle,avatar_emoji,city'+(',last_name,patronymic,show_full_name' if enabled else '')+' FROM profiles WHERE id=?',(uid,)).fetchone()
        state=_relationship(con,user['id'],uid)
        if not profile:
            raise ApiError(404,'Профиль не найден')
        if not profile['discoverable'] and state not in ('self','friends'):
            if not user.get('is_admin'):
                raise ApiError(404,'Профиль не найден')
            # The admin directory already exposes this identity. Opening its
            # profile must not grant access to hidden bio, city, lists or games.
            return 200,{'profile':{'id':profile['id'],'name':profile['name'],
                         'handle':profile['handle'],'avatar_emoji':profile['avatar_emoji'],
                         'bio':'','city':''},'relationship':'admin_directory',
                         'lists':[],'shared_games':[]},None
        lists=[]
        if state in ('self','friends'):
            rows=con.execute('''SELECT l.id,l.title,l.description,l.occasion,l.theme,l.share_key,
                       count(w.id) AS wish_count
                       FROM wishlists l LEFT JOIN wishes w ON w.list_id=l.id
                       WHERE l.owner_id=? AND l.visibility='link'
                       GROUP BY l.id ORDER BY l.id DESC''',(uid,))
            lists=[dict(r) for r in rows]
        shared_games=[]
        if state in ('friends','self'):
            # Both authenticated users must belong to the game. No secret pairing or
            # third-party game is revealed by the profile endpoint.
            rows=con.execute("""SELECT DISTINCT e.id,e.title,e.exchange_date,e.status
                                FROM santa_events e
                                JOIN participants a ON a.event_id=e.id AND a.user_id=?
                                JOIN participants b ON b.event_id=e.id AND b.user_id=?
                                ORDER BY e.id DESC LIMIT 40""",(user['id'],uid))
            shared_games=[dict(row) for row in rows]
        return 200,{'profile':{'id':profile['id'],'name':profile['name'],'bio':profile['bio'],'handle':profile['handle'],'avatar_emoji':profile['avatar_emoji'],'city':profile['city'], **({'last_name':profile['last_name'],'patronymic':profile['patronymic']} if enabled and (state=='self' or profile['show_full_name']) else {})},
                    'relationship':state,'lists':lists,'shared_games':shared_games},None

    if path=='/api/friends/wishlists' and method=='GET':
        user=handler.auth(con)
        rows=con.execute('''SELECT l.id,l.title,l.description,l.occasion,l.theme,
                         l.share_key,p.name AS owner_name,p.avatar_emoji,l.owner_id AS owner_id,
                         count(w.id) AS wish_count
                     FROM wishlists l
                     JOIN profiles p ON p.id=l.owner_id
                     JOIN friendships f ON f.status='accepted'
                       AND ((f.user_low=? AND f.user_high=l.owner_id)
                         OR (f.user_high=? AND f.user_low=l.owner_id))
                     LEFT JOIN wishes w ON w.list_id=l.id
                     WHERE l.visibility='link'
                     GROUP BY l.id,p.id ORDER BY l.id DESC LIMIT 150''',
                     (user['id'],user['id']))
        return 200,{'lists':[dict(r) for r in rows]},None

    if path=='/api/friends' and method=='GET':
        user=handler.auth(con)
        enabled=referrals.ready(con)
        rows=con.execute('''SELECT f.user_low,f.user_high,f.requested_by,f.status,
                    p.id AS other_id,p.name AS other_name,p.handle AS other_handle,p.avatar_emoji AS other_avatar_emoji'''+(",CASE WHEN p.show_full_name THEN p.last_name ELSE '' END AS other_last_name,CASE WHEN p.show_full_name THEN p.patronymic ELSE '' END AS other_patronymic" if enabled else '')+'''
                    FROM friendships f
                    JOIN profiles p ON p.id=(CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END)
                    WHERE f.user_low=? OR f.user_high=?
                    ORDER BY f.updated_at DESC''',(user['id'],user['id'],user['id']))
        friends=[];incoming=[];outgoing=[]
        for item in rows:
            data={'id':item['other_id'],'name':item['other_name'],'handle':item['other_handle'],'avatar_emoji':item['other_avatar_emoji'],**({'last_name':item['other_last_name'],'patronymic':item['other_patronymic']} if enabled else {})}
            if item['status']=='accepted':
                friends.append(data)
            elif item['status']=='pending':
                (outgoing if item['requested_by']==user['id'] else incoming).append(data)
        return 200,{'friends':friends,'incoming':incoming,'outgoing':outgoing,'invites_enabled':enabled},None

    match=re.fullmatch(r'/api/friends/([0-9a-fA-F-]{36})',path)
    if match and method in ('POST','PATCH','DELETE'):
        user=handler.auth(con);other=_uuid(match.group(1));a,b=_pair(user['id'],other)
        if method=='POST':
            request_friend(con,user,other)
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
            existing=con.execute('SELECT requested_by,status FROM friendships WHERE user_low=? AND user_high=?',(a,b)).fetchone()
            if not existing or (existing['status']=='pending' and existing['requested_by']!=user['id']):
                raise ApiError(404,'Исходящая заявка не найдена')
            con.execute('DELETE FROM friendships WHERE user_low=? AND user_high=?',(a,b))
            if existing['status']=='pending':
                # Suppress only this outstanding unread friend-request alert.
                con.execute("""DELETE FROM social_notifications
                       WHERE recipient_id=? AND actor_id=? AND kind='friend_request'
                         AND read_at IS NULL""",(other,user['id']))
        return 200,{'ok':True},None

    if path=='/api/notifications' and method=='GET':
        user=handler.auth(con)
        before=handler.request.args.get('before')
        if before is not None and (not re.fullmatch(r'[1-9][0-9]{0,18}',before) or int(before)>9223372036854775807):
            raise ApiError(400,'Некорректный курсор')
        extra=' AND id < ?' if before is not None else ''
        args=(user['id'],int(before)) if before is not None else (user['id'],)
        rows=con.execute('''SELECT id,kind,message,target_path,created_at,read_at
                      FROM social_notifications WHERE recipient_id=?'''+extra+
                      ' ORDER BY id DESC LIMIT 61',args).fetchall()
        more=len(rows)>60
        rows=rows[:60]
        unread=con.execute('SELECT count(*) AS n FROM social_notifications WHERE recipient_id=? AND read_at IS NULL',
                           (user['id'],)).fetchone()['n']
        return 200,{'items':[dict(r) for r in rows],'unread':unread,'has_more':more},None
    if path=='/api/notifications/unread' and method=='GET':
        user=handler.auth(con)
        count=con.execute('SELECT count(*) AS n FROM social_notifications WHERE recipient_id=? AND read_at IS NULL',
                          (user['id'],)).fetchone()['n']
        return 200,{'unread':count},None
    if path=='/api/notifications/read-all' and method=='POST':
        user=handler.auth(con)
        con.execute('''UPDATE social_notifications SET read_at=now()
                     WHERE recipient_id=? AND read_at IS NULL''',(user['id'],))
        return 200,{'ok':True,'unread':0},None
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

    # Possession of a private capability permits binding an unclaimed player.
    match=re.fullmatch(r'/api/participant/([A-Za-z0-9_-]{43})/claim',path)
    if match and method=='POST':
        user=handler.auth(con)
        participant=con.execute('SELECT id,event_id,user_id FROM participants WHERE access_hash=?',
                                (token_hash(match.group(1)),)).fetchone()
        if not participant:
            raise ApiError(404,'Личная ссылка недействительна')
        if participant['user_id'] is not None:
            if participant['user_id']==user['id']:
                return 200,{'ok':True,'event_id':participant['event_id']},None
            raise ApiError(409,'Этот участник уже привязан к другому аккаунту')
        if con.execute('SELECT id FROM participants WHERE event_id=? AND user_id=?',
                       (participant['event_id'],user['id'])).fetchone():
            raise ApiError(409,'Ты уже участвуешь в этой игре')
        # Use a conditional row update to reject a second, concurrent claim.
        # A stale read must never be reported as a successful account binding.
        updated=con.execute('''UPDATE participants SET user_id=?,access_hash=NULL
                              WHERE id=? AND user_id IS NULL
                                AND NOT EXISTS (
                                  SELECT 1 FROM participants other
                                  WHERE other.event_id=? AND other.user_id=?)
                              RETURNING id''',
                            (user['id'],participant['id'],participant['event_id'],user['id'])).fetchone()
        if not updated:
            raise ApiError(409,'Эта личная ссылка уже привязана или ты участвуешь в игре')
        con.execute("""UPDATE santa_friend_invitations SET status='accepted'
                       WHERE event_id=? AND invited_user_id=?""",
                    (participant['event_id'],user['id']))
        return 200,{'ok':True,'event_id':participant['event_id']},None

    # Authenticated game members can revisit the same game without keeping
    # a bearer URL in localStorage. Member-only projections are enforced by UID.
    match=re.fullmatch(r'/api/member/(\d+)(?:/(roster|preferences|wishes|wishes/import|wishes/\d+|messages/(?:general|to-recipient|from-santa)|reveal|memory))?',path)
    if match:
        eid=int(match.group(1));sub=match.group(2)
        part=_member(con,handler,eid)
        if not sub and method=='GET':
            event=con.execute('SELECT id,title,description,exchange_date,budget_cents,currency,rules,status,invite_key FROM santa_events WHERE id=?',(eid,)).fetchone()
            participants=handler.santa_roster(con,eid)
            detail=dict(event)
            if detail['status']!='open':
                detail.pop('invite_key',None)
            assignment=handler.assignment_view(con,eid,part['id']) if event['status'] in ('drawn','finished') else None
            return 200,{'event':detail,'participant':dict(part),'participants':participants,
                        'wishes':handler.game_wishes(con,part['id']),
                        'preferences':handler.participant_preferences(con,part['id']),
                        'assignment':assignment,'rich_enabled':handler.santa_schema_ready(con)},None
        if sub=='memory' and method=='GET':
            return handler.santa_memory(con,eid,'GET')
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
    personal_match=re.fullmatch(r'/api/personal-invites/([A-Za-z0-9_-]{43})/join',path)
    if match or personal_match:
        if match:
            event=con.execute('SELECT id,owner_id FROM santa_events WHERE invite_key=?',(match.group(1),)).fetchone()
        else:
            event=con.execute('''SELECT e.id,e.owner_id FROM santa_personal_invites i
                 JOIN santa_events e ON e.id=i.event_id WHERE i.token_hash=?''',
                 (token_hash(personal_match.group(1)),)).fetchone()
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
