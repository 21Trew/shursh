/* Шурш! — Social pages. Backend owns access controls and notification privacy. */
'use strict';
let socialUnreadLast=0;
let socialUnreadBusy=false;
async function socialRefreshBadge(force=false){
 if(isPreview||!currentUser||document.visibilityState==='hidden')return;
 if(socialUnreadBusy||(!force&&Date.now()-socialUnreadLast<120000))return;
 socialUnreadBusy=true;socialUnreadLast=Date.now();
 try{
  const data=await api('/api/notifications/unread');
  document.querySelectorAll('[data-notification-count]').forEach(el=>{
   const amount=Number(data.unread||0);
   el.textContent=amount?String(Math.min(99,amount)):'';
   el.hidden=!amount;
  });
 }catch{ /* A background badge failure must never block navigation. */ }
 finally{socialUnreadBusy=false;}
}
setInterval(()=>{if(typeof currentUser!=='undefined')socialRefreshBadge();},120000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)socialRefreshBadge(true);});

const socialEmojiChoices=["🎁","🎄","🐱","🦊","🐻","🐼","🐸","🦄","🐰","🧸","✨","🌸","🌼","🌙","⭐","🎮","🎨","📚","🎵","🚀","☕","🍓","💚"];
function socialAvatar(p,extra=''){
 return '<span class="avatar emoji-avatar '+extra+'" aria-hidden="true">'+esc(p.avatar_emoji||'🎁')+'</span>';
}
function socialIdentity(p,editable=false){
 const avatar=socialAvatar(p,'profile-emoji');
 return '<div class="social-profile-identity">'+(editable?
  '<button class="profile-avatar-edit" type="button" data-social-action="edit-avatar" aria-label="Изменить аватарку" title="Изменить аватарку">'+avatar+'<span class="profile-avatar-edit-icon">'+ico('edit',16)+'</span></button>':avatar)+
 '<div class="profile-identity-text"><h1>'+esc(p.name)+'</h1>'+
 (p.handle?'<span class="profile-handle">@'+esc(p.handle)+'</span>':'')+
 (p.city?'<div class="profile-city">'+ico('home',16)+' '+esc(p.city)+'</div>':'')+
 '<p class="profile-bio">'+esc(p.bio||'Расскажи немного о себе — чем увлекаешься и каким подаркам радуешься')+'</p></div></div>';
}
function socialUserCard(user,actions=''){
 return '<div class="social-person"><button class="social-person-link" type="button" data-nav="/users/'+attr(user.id)+'">'+
  socialAvatar(user)+
  '<span class="social-person-name">'+esc(user.name)+(user.handle?'<small>@'+esc(user.handle)+'</small>':'')+'</span></button>'+actions+'</div>';
}
async function socialFriendsPage(marker=lastRenderToken){
 if(!currentUser){loginModal();return;}
 const data=await api('/api/friends');if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page"><div class="page-hero"><div><div class="section-label">Вместе приятнее</div>'+
  '<h1>Друзья</h1><p>Ищи знакомых, делись доступными вишлистами и приглашай в игры</p></div></div>'+
  '<section class="panel social-search"><h2>Найти друга</h2><p class="note">По имени или никнейму — без поиска по чужой почте</p><form id="social-search-form" class="share-field">'+
  '<input class="input" name="q" minlength="2" maxlength="40" required placeholder="Имя друга" aria-label="Найти пользователя по имени">'+
  '<button class="btn btn-dark btn-small" type="submit">Найти</button></form>'+
  '<div id="social-search-results" aria-live="polite"></div></section>'+
  (data.incoming.length?'<section class="panel"><h2>Заявки тебе <span class="chip">'+data.incoming.length+'</span></h2>'+
   data.incoming.map(u=>socialUserCard(u,
    '<div class="btn-row"><button class="btn btn-dark btn-small" data-social-action="accept" data-user-id="'+attr(u.id)+'">Принять</button>'+
    '<button class="btn btn-soft btn-small" data-social-action="decline" data-user-id="'+attr(u.id)+'">Отклонить</button></div>')).join('')+'</section>':'')+
  '<section class="panel"><h2>Мои друзья <span class="chip">'+data.friends.length+'</span></h2>'+
  (data.friends.length?data.friends.map(u=>socialUserCard(u,
    '<button class="btn btn-soft btn-small" data-social-action="unfriend" data-user-id="'+attr(u.id)+'">Убрать</button>')).join(''):
    '<p class="note">Пока никого нет. Найди друга и отправь заявку</p>')+'</section>'+
  (data.outgoing.length?'<section class="panel"><h2>Отправленные заявки</h2>'+
    data.outgoing.map(u=>socialUserCard(u,'<div class="social-request-actions"><span class="chip">Ожидает ответа</span><button class="btn btn-soft btn-small" data-social-action="cancel" data-user-id="'+attr(u.id)+'">Отменить</button></div>')).join('')+'</section>':'')+
  '</main>');
 document.querySelector('#social-search-form')?.addEventListener('submit',async ev=>{
  ev.preventDefault();
  const input=ev.currentTarget.elements.q;
  const results=document.querySelector('#social-search-results');
  results.textContent='Ищем…';
  try{
   const {users}=await api('/api/users/search?q='+encodeURIComponent(input.value.trim()));
   results.innerHTML=users.length?users.map(u=>socialUserCard(u,
    '<button type="button" class="btn btn-soft btn-small" data-social-action="add" data-user-id="'+attr(u.id)+'">В друзья</button>')).join(''):'<p class="note">Ничего не найдено. Проверь имя</p>';
  }catch(err){results.textContent=err.message;}
 });
}
async function socialProfilePage(uid,marker=lastRenderToken){
 if(!currentUser){loginModal();return;}
 const data=await api('/api/users/'+encodeURIComponent(uid));if(marker!==lastRenderToken)return;
 const p=data.profile,relation=data.relationship;
 let action='';
 if(relation==='none')action='<button class="btn btn-dark btn-small" data-social-action="add" data-user-id="'+attr(uid)+'">Добавить в друзья</button>';
 if(relation==='incoming')action='<button class="btn btn-dark btn-small" data-social-action="accept" data-user-id="'+attr(uid)+'">Принять заявку</button>';
 if(relation==='outgoing')action='<div class="social-request-actions"><span class="chip">Заявка отправлена</span><button class="btn btn-soft btn-small" data-social-action="cancel" data-user-id="'+attr(uid)+'">Отменить заявку</button></div>';
 if(relation==='friends')action='<span class="chip chip-green">Вы друзья</span>';
 if(relation==='self')action='<button class="btn btn-soft btn-small" data-nav="/profile">Редактировать профиль</button>';
 shell('<main class="container page social-page social-profile-page"><div class="social-profile-hero profile-main-card">'+socialIdentity(p)+
   '<div class="profile-actions">'+action+'</div></div>'+
   '<section class="dashboard-section"><div class="dashboard-section-head"><h2>Вишлисты <span class="chip">'+data.lists.length+'</span></h2></div>'+
  (data.lists.length?'<div class="cards-grid">'+data.lists.map(list=>
   '<article class="list-card"><a class="card-hitarea" href="/w/'+attr(list.share_key)+'" data-nav="/w/'+attr(list.share_key)+'" aria-label="Открыть список '+attr(list.title)+'"></a>'+
   '<div class="list-cover cover-'+attr(list.theme)+'">'+fallbackArt('gift')+'</div>'+
   '<div class="list-info"><h3>'+esc(list.title)+'</h3><p>'+esc(list.description||'Список подарков')+'</p>'+
   '<div class="list-bottom"><span>'+ruCount(list.wish_count,'желание','желания','желаний')+'</span><button class="text-link" data-nav="/w/'+attr(list.share_key)+'">Посмотреть '+ico('arrow')+'</button></div></div></article>').join('')+'</div>':
   '<div class="panel"><p class="note">'+(relation==='friends'||relation==='self'?'Пока нет доступных вишлистов':'Вишлисты доступны после добавления в друзья')+'</p></div>')+'</section>'+
   ((relation==='friends'||relation==='self')?'<section class="dashboard-section shared-santa-section"><div class="dashboard-section-head"><h2>Наш общий Тайный Санта <span class="chip">'+(data.shared_games||[]).length+'</span></h2></div>'+
   ((data.shared_games||[]).length?'<div class="shared-santa-grid">'+data.shared_games.map(game=>santaGameCard(game,{shared:true})).join('')+'</div>':
    '<div class="panel"><p class="note">Пока нет игр, в которых вы оба участвуете</p></div>')+'</section>':'')+'</main>');
}
async function socialOwnProfilePage(marker=lastRenderToken){
 if(!currentUser){loginModal();return;}
 const data=await api('/api/profile/me');if(marker!==lastRenderToken)return;
 const p=data.profile;
 shell('<main class="container page social-page social-profile-page">'+
  '<div class="social-page-heading"><span class="section-label">Твоя визитная карточка</span><h1>Мой профиль</h1>'+
  '<p>Имя, никнейм и аватар видят другие. Почта остаётся приватной</p></div>'+
  '<section class="panel profile-main-card">'+socialIdentity(p,true)+
  '<div class="profile-actions">'+
  '<button type="button" class="btn btn-dark btn-small" data-social-action="edit-profile">'+ico('edit')+' Редактировать профиль</button>'+
  '<button type="button" class="btn btn-soft btn-small" data-nav="/users/'+attr(p.id)+'">Как видят друзья</button></div></section>'+
  '<section class="panel profile-security"><div><h2>Вход и безопасность</h2><p class="note">Почта не отображается в публичном профиле</p><div class="account-email">'+esc(p.email||'')+'</div></div>'+
  '<div class="profile-actions"><button class="btn btn-soft btn-small" data-social-action="change-email">Изменить почту</button>'+
  '<button class="btn btn-soft btn-small" data-social-action="change-password">Изменить пароль</button></div></section></main>');
}
async function socialEditProfileModal(){
 const d=await api('/api/profile/me'),p=d.profile;
 const choices=socialEmojiChoices.map(emoji=>
  '<button type="button" class="emoji-choice'+(emoji===(p.avatar_emoji||'🎁')?' selected':'')+
  '" data-avatar-pick="'+attr(emoji)+'" aria-pressed="'+String(emoji===(p.avatar_emoji||'🎁'))+'">'+esc(emoji)+'</button>').join('');
 modal({title:'Редактировать профиль',subtitle:'Настрой, как тебя видят друзья',
  content:'<div class="field"><label>Твой аватар — только эмодзи</label><div class="emoji-grid" role="group" aria-label="Выбрать эмодзи">'+choices+'</div>'+
   '<input type="hidden" name="avatar_emoji" id="social-avatar-value" value="'+attr(p.avatar_emoji||'🎁')+'"></div>'+
   field('Имя','name','Как к тебе обращаться','text',p.name,true,'maxlength="40"')+
   field('Никнейм (@)','handle','Например, shursh_friend','text',p.handle||'',false,'maxlength="20" autocomplete="username"')+
   field('Город (необязательно)','city','Например, Санкт-Петербург','text',p.city||'',false,'maxlength="60"')+
   textArea('О себе','bio','Что любишь, чем увлекаешься и что тебя радует',p.bio||'')+
   '<label class="switch-label"><input type="checkbox" name="discoverable"'+(p.discoverable?' checked':'')+'> Показывать мой профиль в поиске</label>',
  submitLabel:'Сохранить профиль',onSubmit:async form=>{
   const data=readForm(form);data.discoverable=form.elements.discoverable.checked;
   const response=await api('/api/profile/me',{method:'PATCH',body:data});
   currentUser.name=response.profile.name;currentUser.avatar_emoji=response.profile.avatar_emoji;currentUser.handle=response.profile.handle;
   clearOwnerTabViews(['/profile']);notice('Профиль обновлён');await socialOwnProfilePage();
  }});
 const bio=modalRoot.querySelector('#fld-bio');if(bio)bio.maxLength=500;
}
async function socialEditAvatarModal(){
 if(!currentUser){loginModal();return;}
 const {profile}=await api('/api/profile/me');
 const choices=socialEmojiChoices.map(emoji=>
  '<button type="button" class="emoji-choice'+(emoji===profile.avatar_emoji?' selected':'')+
  '" data-avatar-pick="'+attr(emoji)+'" aria-pressed="'+String(emoji===profile.avatar_emoji)+'">'+esc(emoji)+'</button>').join('');
 modal({title:'Изменить аватарку',subtitle:'Выбери эмодзи, который будет виден друзьям',
  content:'<div class="emoji-grid" role="group" aria-label="Выбрать эмодзи">'+choices+'</div>'+
    '<input type="hidden" name="avatar_emoji" id="social-avatar-value" value="'+attr(profile.avatar_emoji||'🎁')+'">',
  submitLabel:'Сохранить',onSubmit:async form=>{
   const value=form.elements.avatar_emoji.value;
   const updated=await api('/api/profile/me',{method:'PATCH',body:{avatar_emoji:value}});
   currentUser.avatar_emoji=updated.profile.avatar_emoji;
   document.querySelectorAll('.header-avatar').forEach(button=>button.textContent=currentUser.avatar_emoji);
   clearOwnerTabViews(['/profile']);
   if(currentPath()==='/profile')await socialOwnProfilePage();
   notice('Аватарка обновлена');
  }});
}
async function socialAccountModal(kind){
 if(isPreview){notice('Настройки входа доступны только на сайте',true);return;}
 const email=kind==='email';
 modal({title:email?'Изменить почту':'Изменить пароль',subtitle:'Для защиты аккаунта сначала подтверди текущий пароль',
  content:field('Текущий пароль','current_password','Твой текущий пароль','password','',true,'autocomplete="current-password" minlength="8" maxlength="200"')+
   (email?field('Новая почта','email','new@example.com','email','',true,'autocomplete="email" maxlength="254"'):
    field('Новый пароль','new_password','Не менее 8 символов','password','',true,'autocomplete="new-password" minlength="8" maxlength="200"')),
  submitLabel:email?'Отправить подтверждение':'Обновить пароль',onSubmit:async form=>{
   const result=await api('/api/account/'+kind,{method:'POST',body:readForm(form)});
   notice(email&&result.pending_confirmation?'Проверь новую почту и подтверди изменение':'Пароль изменён');
  }});
}
let notificationModalItems=[];
let notificationModalTab='new';
function notificationCategory(item){
 return ['friend_request','friend_accept','wishlist_new','wish_new','wish_request','santa_invitation','santa_joined'].includes(item.kind)?'friends':'system';
}
function renderNotificationModalTab(tab=notificationModalTab){
 const panel=modalRoot.querySelector('#notification-modal-list');if(!panel)return;
 notificationModalTab=tab;
 for(const button of modalRoot.querySelectorAll('[data-notification-tab]')){
  const chosen=button.dataset.notificationTab===tab;
  button.classList.toggle('active',chosen);button.setAttribute('aria-selected',String(chosen));
 }
 const items=notificationModalItems.filter(item=>
  tab==='new'?!item.read_at:
  tab==='read'?!!item.read_at:
  notificationCategory(item)===tab);
 panel.innerHTML=items.length?items.map(item=>
  '<div class="notification-item'+(item.read_at?'':' unread')+'">'+
  '<button class="notification-open" type="button" data-social-action="open-notification" data-id="'+item.id+'" data-path="'+attr(item.target_path)+'">'+
  '<strong>'+esc(item.message)+'</strong><small>'+esc(new Date(item.created_at).toLocaleString('ru-RU'))+'</small></button>'+
  (!item.read_at?'<button class="btn btn-soft btn-small" type="button" data-social-action="read-notification" data-id="'+item.id+'">Прочитано</button>':'')+
  '</div>').join(''):'<p class="note">Здесь пока пусто</p>';
 const unread=notificationModalItems.filter(i=>!i.read_at).length;
 const all=modalRoot.querySelector('[data-social-action="read-all-notifications"]');if(all)all.disabled=!unread;
}
async function socialNotificationsModal(){
 if(!currentUser)return;
 const response=await api('/api/notifications');
 notificationModalItems=response.items||[];
 notificationModalTab='new';
 const tabs=[['new','Новое'],['friends','Друзья'],['system','Системные'],['read','Прочитано']];
 modal({title:'Уведомления',subtitle:'Новости друзей, подарков и игр',
  content:'<div class="notification-dialog"><div class="notification-dialog-toolbar"><div class="notification-tabs" role="tablist" aria-label="Фильтр уведомлений">'+
  tabs.map(([id,label])=>'<button type="button" role="tab" data-notification-tab="'+id+'" aria-selected="'+(id==='new'?'true':'false')+'" class="'+(id==='new'?'active':'')+'">'+label+'</button>').join('')+
  '</div><button type="button" class="btn btn-soft btn-small notification-read-all" data-social-action="read-all-notifications">Прочесть все</button></div>'+
  '<div id="notification-modal-list" role="tabpanel" aria-live="polite"></div></div>'});
 const anchor=document.querySelector('header .header-bell')?.getBoundingClientRect();
 const overlay=modalRoot.querySelector('.modal-backdrop');
 if(overlay&&anchor){
  overlay.classList.add('notification-popover');
  const top=Math.round(anchor.bottom+10);
  const right=Math.max(12,Math.round(innerWidth-anchor.right));
  overlay.style.setProperty('--notification-top',top+'px');
  overlay.style.setProperty('--notification-right',right+'px');
  // Also pin geometry on the panel itself: flex/padding changes must never
  // move notifications away from the bell during header transitions.
  const panel=overlay.querySelector('.modal');
  if(panel){panel.style.top=top+'px';panel.style.right=right+'px';}
 }
 renderNotificationModalTab('new');
 socialRefreshBadge(true);
}
document.addEventListener('click',event=>{
 const tab=event.target.closest('[data-notification-tab]');
 if(tab){event.preventDefault();renderNotificationModalTab(tab.dataset.notificationTab);}
});
async function socialNotificationsPage(marker=lastRenderToken){
 if(!currentUser){loginModal();return;}
 const res=await api('/api/notifications');if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page"><div class="page-hero"><div><div class="section-label">Новости друзей и игр</div>'+
  '<h1>Уведомления</h1><p>Новые подарки, приглашения и события Тайного Санты</p></div></div>'+
  '<section class="panel notification-feed">'+(res.items.length?res.items.map(n=>
   '<div class="notification-item'+(n.read_at?'':' unread')+'">'+
   '<button class="notification-open" data-social-action="open-notification" data-id="'+n.id+'" data-path="'+attr(n.target_path)+'">'+
   '<strong>'+esc(n.message)+'</strong><small>'+esc(new Date(n.created_at).toLocaleString('ru-RU'))+'</small></button>'+
   (!n.read_at?'<button class="btn btn-soft btn-small" data-social-action="read-notification" data-id="'+n.id+'">Прочитано</button>':'')+
   '</div>').join(''):'<p class="note">Пока всё спокойно. Как только появятся новости, они будут здесь</p>')+
  '</section></main>');
 socialRefreshBadge();
}
function socialAdminUsersMarkup(page){
 const rows=(page.users||[]).map(u=>'<tr><td><div class="admin-user-identity"><span class="admin-user-emoji">'+
    esc(u.avatar_emoji||'🎁')+'</span><span><strong>'+esc(u.name)+'</strong>'+
    '<small>ID: '+esc(String(u.id).slice(0,8))+'</small></span></div></td>'+
    '<td>'+(u.handle?'@'+esc(u.handle):'<span class="muted">—</span>')+'</td>'+
    '<td><time datetime="'+attr(u.created_at)+'">'+esc(new Date(u.created_at).toLocaleString('ru-RU',{dateStyle:'medium',timeStyle:'short'}))+'</time></td>'+
    '<td>'+Number(u.wishlists_count||0)+'</td><td>'+Number(u.organized_games||0)+'</td>'+
    '<td>'+Number(u.joined_games||0)+'</td><td>'+(u.discoverable?'В поиске':'Скрыт')+'</td></tr>').join('');
 const from=page.total?Number(page.offset)+1:0;
 const to=Math.min(Number(page.offset)+Number(page.limit),Number(page.total));
 return '<div class="admin-users-table-scroll"><table class="admin-users-table"><thead><tr>'+
  '<th>Игрок</th><th>Ник</th><th>Регистрация</th><th>Вишлисты</th>'+
  '<th>Свои Санты</th><th>Участие</th><th>Профиль</th></tr></thead><tbody>'+
  (rows||'<tr><td colspan="7" class="muted">Игроки не найдены</td></tr>')+'</tbody></table></div>'+
  '<div class="admin-users-pager"><span>'+from+'–'+to+' из '+Number(page.total)+'</span>'+
  '<div class="btn-row"><button type="button" class="btn btn-soft btn-small" data-social-action="admin-users-prev" data-offset="'+Math.max(0,page.offset-page.limit)+'"'+(page.offset===0?' disabled':'')+'>Назад</button>'+
  '<button type="button" class="btn btn-soft btn-small" data-social-action="admin-users-next" data-offset="'+(page.offset+page.limit)+'"'+(to>=page.total?' disabled':'')+'>Вперёд</button></div></div>';
}
async function socialLoadAdminUsers(offset=0){
 const root=document.querySelector('[data-admin-users-content]');if(!root)return;
 const query=document.getElementById('admin-users-query')?.value.trim()||'';
 const page=await api('/api/admin/users?offset='+offset+'&q='+encodeURIComponent(query));
 if(root.isConnected){root.innerHTML=socialAdminUsersMarkup(page);}
}
async function socialAdminPage(marker=lastRenderToken){
 if(!currentUser?.is_admin){errorView(new Error('Доступ только администратору'));return;}
 const [{stats},page]=await Promise.all([api('/api/admin/overview'),api('/api/admin/users')]);
 if(marker!==lastRenderToken)return;
 const labels={users:'Активных профилей',wishlists:'Вишлистов',wishes:'Подарков',events:'Игр',friends:'Дружеских связей',notifications:'Уведомлений',new_feedback:'Новых обращений'};
 shell('<main class="container page social-page admin-page"><div class="page-hero"><div><div class="section-label">Шурш! / управление</div>'+
  '<h1>Админка</h1><p>Статистика проекта и зарегистрированные пользователи. Без доступа к личным перепискам и секретам жеребьёвки</p></div></div>'+
  '<div class="social-stat-grid">'+Object.entries(labels).map(([key,label])=>'<article class="panel"><strong>'+Number(stats[key]||0)+'</strong><span>'+label+'</span></article>').join('')+'</div>'+
  '<section class="panel admin-users-panel"><div class="panel-heading-actions"><h2>Зарегистрированные игроки</h2><span class="chip">'+Number(page.total)+'</span></div>'+
  '<form id="admin-users-search" class="admin-users-search"><label for="admin-users-query" class="sr-only">Найти игрока</label>'+
  '<input id="admin-users-query" class="input" type="search" placeholder="Поиск по имени или нику" maxlength="50" autocomplete="off">'+
  '<button class="btn btn-dark btn-small" type="submit">Найти</button></form>'+
  '<div data-admin-users-content>'+socialAdminUsersMarkup(page)+'</div></section>'+
  '<button class="btn btn-dark" data-nav="/admin/feedback">Обращения пользователей '+ico('arrow')+'</button></main>');
 document.getElementById('admin-users-search')?.addEventListener('submit',async e=>{
   e.preventDefault();
   try{await socialLoadAdminUsers(0);}catch(error){notice(error.message,true);}
 });
}
async function socialInviteFriendsModal(){
 if(!currentUser||!loadedSanta?.event||loadedSanta.event.status!=='open')return;
 const {friends}=await api('/api/friends');
 if(!friends.length){notice('Сначала добавь друзей',true);nav('/friends');return;}
 modal({title:'Позвать друзей в игру',subtitle:'Друг получит приглашение в уведомлениях',
  content:selectField('Кого пригласить','friend_id',friends.map(x=>[x.id,x.name]),friends[0].id),
  submitLabel:'Отправить приглашение',onSubmit:async form=>{
   const uid=readForm(form).friend_id;
   await api('/api/santas/'+loadedSanta.event.id+'/invite-friend/'+encodeURIComponent(uid),{method:'POST',body:{}});
   notice('Приглашение отправлено');await render();
  }});
}
async function socialAskGiftModal(wishId){
 if(!currentUser){loginModal();return;}
 const {friends}=await api('/api/friends');
 if(!friends.length){notice('Чтобы попросить подарок, сначала добавь друга',true);nav('/friends');return;}
 modal({title:'Попросить друга о подарке',subtitle:'Друг увидит пожелание и сможет забронировать подарок, если он свободен',
  content:selectField('Кому отправить просьбу','friend_id',friends.map(f=>[f.id,f.name]),friends[0].id),
  submitLabel:'Попросить',onSubmit:async form=>{
   const uid=readForm(form).friend_id;
   await api('/api/wishes/'+wishId+'/request-friend/'+encodeURIComponent(uid),{method:'POST',body:{}});
   notice('Просьба отправлена'); 
  }});
}
document.addEventListener('click',async e=>{
 const picker=e.target.closest('[data-avatar-pick]');if(picker){e.preventDefault();const root=picker.closest('.emoji-grid');root?.querySelectorAll('[data-avatar-pick]').forEach(x=>{x.classList.toggle('selected',x===picker);x.setAttribute('aria-pressed',String(x===picker));});const input=modalRoot.querySelector('#social-avatar-value');if(input)input.value=picker.dataset.avatarPick;return;}
 const target=e.target.closest('[data-social-action]');if(!target)return;
 e.preventDefault();
 const action=target.dataset.socialAction,uid=target.dataset.userId;
 target.disabled=true;
 try{
  if(action==='open-notifications'){await socialNotificationsModal();return;}
  if(action==='read-all-notifications'){
   await api('/api/notifications/read-all',{method:'POST',body:{}});
   const time=new Date().toISOString();notificationModalItems.forEach(x=>{if(!x.read_at)x.read_at=time;});
   renderNotificationModalTab();socialUnreadLast=0;void socialRefreshBadge(true);return;
  }
  if(action==='edit-profile'){await socialEditProfileModal();return;}
  if(action==='edit-avatar'){await socialEditAvatarModal();return;}
  if(action==='admin-users-next'||action==='admin-users-prev'){await socialLoadAdminUsers(Number(target.dataset.offset)||0);return;}
   if(action==='change-email'){await socialAccountModal('email');return;}
   if(action==='change-password'){await socialAccountModal('password');return;}
  if(action==='invite-friends'){await socialInviteFriendsModal();return;}
  if(action==='ask-gift'){await socialAskGiftModal(target.dataset.wishId);return;}
  if(action==='open-notification'){
   await api('/api/notifications/'+target.dataset.id+'/read',{method:'POST',body:{}});
   socialUnreadLast=0;closeModal();nav(target.dataset.path||'/');return;
  }
  if(action==='read-notification'){
   await api('/api/notifications/'+target.dataset.id+'/read',{method:'POST',body:{}});
   socialUnreadLast=0;
   if(modalRoot.querySelector('.notification-dialog')){
    const item=notificationModalItems.find(x=>String(x.id)===String(target.dataset.id));
    if(item)item.read_at=new Date().toISOString();
    renderNotificationModalTab();void socialRefreshBadge(true);
   }else await socialNotificationsPage();
   return;
  }
  if(action==='add'||action==='accept'||action==='decline'||action==='unfriend'||action==='cancel'){
   const method=action==='add'?'POST':(action==='unfriend'||action==='cancel')?'DELETE':'PATCH';
   const payload=(action==='accept'||action==='decline')?{action:action==='accept'?'accept':'decline'}:{};
   await api('/api/friends/'+encodeURIComponent(uid),{method,body:payload});
   socialUnreadLast=0;
   notice(action==='add'?'Заявка в друзья отправлена':action==='accept'?'Теперь вы друзья':action==='decline'?'Заявка отклонена':action==='cancel'?'Заявка отменена':'Друг удалён');
   if(currentPath()==='/friends')await socialFriendsPage();
   else if(/^\/users\//.test(currentPath()))await socialProfilePage(uid);
  }
 }catch(err){notice(err.message,true);}
 finally{if(target.isConnected)target.disabled=false;}
});
