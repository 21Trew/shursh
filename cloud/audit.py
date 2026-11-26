"""Allowlisted application audit events and administrator-only category details."""
import re
from uuid import UUID
from server import ApiError

CATEGORIES={
 'wishlists':("SELECT w.id,w.title,w.created_at,w.visibility AS status FROM wishlists w WHERE w.owner_id=? ORDER BY w.id DESC",),
 'gifts':("SELECT g.id,g.title,g.created_at,w.title AS context FROM wishes g JOIN wishlists w ON w.id=g.list_id WHERE w.owner_id=? ORDER BY g.id DESC",),
 'referrals':("SELECT p.id,p.name AS title,r.confirmed_at AS created_at FROM referral_attributions r JOIN profiles p ON p.id=r.referred_id WHERE r.referrer_id=? ORDER BY r.confirmed_at DESC,p.id DESC",),
 'organized':("SELECT e.id,e.title,e.created_at,e.status FROM santa_events e WHERE e.owner_id=? ORDER BY e.id DESC",),
 'joined':("SELECT e.id,e.title,p.created_at,e.status FROM participants p JOIN santa_events e ON e.id=p.event_id WHERE p.user_id=? ORDER BY p.id DESC",),
}
MUTATIONS=(
 ('POST',r'/api/lists','wishlist.created'),
 ('PATCH',r'/api/lists/(\d+)','wishlist.updated'),
 ('DELETE',r'/api/lists/(\d+)','wishlist.deleted'),
 ('POST',r'/api/lists/\d+/wishes','gift.created'),
 ('PATCH',r'/api/wishes/(\d+)','gift.updated'),
 ('DELETE',r'/api/wishes/(\d+)','gift.deleted'),
 ('POST',r'/api/santas','santa.created'),
 ('PATCH',r'/api/santas/(\d+)','santa.updated'),
 ('DELETE',r'/api/santas/(\d+)','santa.deleted'),
 ('POST',r'/api/santas/(\d+)/draw','santa.drawn'),
 ('POST',r'/api/santas/(\d+)/finish','santa.finished'),
 ('PUT',r'/api/santas/(\d+)/memory','santa.photo_saved'),
 ('DELETE',r'/api/santas/(\d+)/memory','santa.photo_deleted'),
 ('POST',r'/api/invites/[A-Za-z0-9_-]+/join','santa.joined'),
 ('POST',r'/api/personal-invites/[A-Za-z0-9_-]+/join','santa.joined'),
 ('PATCH',r'/api/profile/me','profile.updated'),
 ('POST',r'/api/friends/[0-9a-fA-F-]{36}','friend.requested'),
 ('PATCH',r'/api/friends/[0-9a-fA-F-]{36}','friend.updated'),
 ('DELETE',r'/api/friends/[0-9a-fA-F-]{36}','friend.removed'),
 ('POST',r'/api/feedback','feedback.created'),
 ('PATCH',r'/api/admin/feedback/(\d+)','feedback.updated'),
 ('DELETE',r'/api/friend-invites/me','invite.revoked'),
 ('POST',r'/api/logout','auth.logout'),
)

def ready(con):
    return con.execute("SELECT to_regclass('public.admin_audit_events') IS NOT NULL AS ready").fetchone()['ready']

def require_ready(con):
    if not ready(con):
        raise ApiError(503,'Журнал событий пока недоступен')

def record(con,actor,event,*,target=None,object_id=None,category=None,before=None,after=None,success=True,required=False):
    if not actor:
        return
    if not ready(con):
        if required: raise ApiError(503,'Журнал событий пока недоступен')
        return
    con.execute("""INSERT INTO admin_audit_events(audience,actor_id,target_id,event,object_id,category,before_visible,after_visible,success)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                ('admins' if actor.get('is_admin') else 'users',actor['id'],target,event,object_id,category,before,after,success))
    # Bounded physical retention, with indexed cutoff and no scheduled worker.
    con.execute("""DELETE FROM admin_audit_events WHERE id IN
        (SELECT id FROM admin_audit_events WHERE created_at<now()-interval '90 days' ORDER BY created_at LIMIT 100)""")

def after_mutation(con,handler,method,path,result):
    if result[0] not in (200,201,204): return
    for verb,pattern,event in MUTATIONS:
        match=re.fullmatch(pattern,path)
        if verb!=method or not match: continue
        actor=handler._user if handler._user_loaded else handler.user(con)
        if not actor: return
        oid=int(match.group(1)) if match.groups() else result[1].get('id') if isinstance(result[1],dict) else None
        if not isinstance(oid,int) or isinstance(oid,bool) or not 0<oid<2**63: oid=None
        record(con,actor,event,object_id=oid)
        return

def offset(request):
    value=request.args.get('offset','0')
    if not re.fullmatch(r'\d{1,5}',value) or int(value)>10000: raise ApiError(400,'Неверная страница')
    return int(value)

def user_id(raw):
    try:
        return UUID(raw)
    except (ValueError,TypeError):
        raise ApiError(404,'Пользователь не найден') from None

def visibility_target(con,uid):
    row=con.execute('SELECT id,name,discoverable FROM profiles WHERE id=?',(uid,)).fetchone()
    if not row: raise ApiError(404,'Пользователь не найден')
    return row

def handle(handler,method,path,con):
    match=re.fullmatch(r'/api/admin/users/([0-9a-fA-F-]{36})/(wishlists|gifts|referrals|organized|joined|discoverable)',path)
    if match and method=='POST':
        actor=handler.is_site_admin(con)
        require_ready(con)
        uid=user_id(match.group(1));category=match.group(2)
        profile=visibility_target(con,uid)
        page=offset(handler.request)
        if category=='discoverable':
            items=[];more=False
        else:
            rows=con.execute(CATEGORIES[category][0]+' LIMIT 26 OFFSET ?',(uid,page)).fetchall()
            items=[dict(row) for row in rows[:25]];more=len(rows)>25
        record(con,actor,'admin.user_details',target=uid,category=category,required=True)
        return 200,{'profile':dict(profile),'items':items,'offset':page,'more':more},None
    if path=='/api/admin/audit' and method=='GET':
        handler.is_site_admin(con);require_ready(con)
        audience=handler.request.args.get('audience','admins')
        if audience not in ('admins','users'): raise ApiError(400,'Неверная категория')
        page=offset(handler.request)
        rows=con.execute("""SELECT a.id,a.created_at,a.event,a.success,p.name AS actor_name
          FROM admin_audit_events a LEFT JOIN profiles p ON p.id=a.actor_id
          WHERE a.audience=? AND a.created_at>=now()-interval '90 days'
          ORDER BY a.id DESC LIMIT 26 OFFSET ?""",(audience,page)).fetchall()
        return 200,{'items':[dict(row) for row in rows[:25]],'offset':page,'more':len(rows)>25},None
    match=re.fullmatch(r'/api/admin/audit/(\d{1,18})',path)
    if match and method=='GET':
        handler.is_site_admin(con);require_ready(con)
        row=con.execute("""SELECT a.id,a.created_at,a.event,a.success,a.audience,a.actor_id,a.target_id,a.object_id,
          a.category,a.before_visible,a.after_visible,p.name AS actor_name,t.name AS target_name
          FROM admin_audit_events a LEFT JOIN profiles p ON p.id=a.actor_id LEFT JOIN profiles t ON t.id=a.target_id
          WHERE a.id=? AND a.created_at>=now()-interval '90 days'""",(int(match.group(1)),)).fetchone()
        if not row: raise ApiError(404,'Событие не найдено')
        return 200,{'event':dict(row)},None
    return None
