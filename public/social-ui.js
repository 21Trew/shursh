/* Шурш! — Social pages. Backend owns access controls and notification privacy. */
'use strict';
let socialUnreadLast=0;
let socialUnreadBusy=false,socialUnreadRequest=0;
function resetSocialBadge(){socialUnreadRequest++;socialUnreadLast=0;socialUnreadBusy=false;}
async function socialRefreshBadge(force=false){
 if(isPreview||!currentUser||document.visibilityState==='hidden')return;
 if(socialUnreadBusy||(!force&&Date.now()-socialUnreadLast<120000))return;
 const request=++socialUnreadRequest,epoch=ownerSessionEpoch;
 socialUnreadBusy=true;socialUnreadLast=Date.now();
 try{
  const data=await api('/api/notifications/unread',{visit:true});
  if(request!==socialUnreadRequest||epoch!==ownerSessionEpoch)return;
  document.querySelectorAll('[data-notification-count]').forEach(el=>{
   const amount=Number(data.unread||0);
   const label=amount?String(Math.min(99,amount)):'';
   if(el.textContent!==label)el.textContent=label;
   if(el.hidden!==!amount)el.hidden=!amount;
  });
 }catch{ /* A background badge failure must never block navigation. */ }
 finally{if(request===socialUnreadRequest)socialUnreadBusy=false;}
}
setInterval(()=>{if(typeof currentUser!=='undefined')socialRefreshBadge();},120000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)socialRefreshBadge(true);});

const socialEmojiChoices=["🐱","🐈","🐶","🦊","🐻","🐼","🐸","🦄","🐰","🦦","🐧","🐨","🦉","🦋","❤️","💚","💜","💛","✨","⭐","🌙","🌈","🔥","🪐","🚀","🌸","🌼","🌻","🍀","🍄","🪴","🎄","🍓","🍒","🍋","☕","🍩","🍪","🧁","🎁","🧸","🎮","🎨","📚","🎵","🎧","🎬","🛹"];
function socialAvatar(p,extra=''){
 return '<span class="avatar emoji-avatar '+extra+'" aria-hidden="true">'+esc(p.avatar_emoji||'🎁')+'</span>';
}
function socialFullName(p){return [p.last_name,p.name,p.patronymic].filter(Boolean).join(' ');}
function socialIdentity(p,{editable=false,own=false,showBio=true}={}){
 const avatar=socialAvatar(p,'profile-emoji');
 const bio=(p.bio||'').trim()||(own?'Расскажи немного о себе: чем увлекаешься и каким подаркам радуешься':'Пока нет информации о себе');
 return '<div class="social-profile-identity">'+(editable?
  '<button class="profile-avatar-edit" type="button" data-social-action="edit-avatar" aria-label="Изменить аватарку" title="Изменить аватарку">'+avatar+'<span class="profile-avatar-edit-icon">'+ico('edit',16)+'</span></button>':avatar)+
 '<div class="profile-identity-text"><h1>'+esc(socialFullName(p))+'</h1>'+
 (p.handle?'<a class="profile-handle" href="/u/'+attr(p.handle)+'" data-nav="/u/'+attr(p.handle)+'">@'+esc(p.handle)+'</a>':'')+
 (p.city?'<div class="profile-city">'+ico('home',16)+' '+esc(p.city)+'</div>':'')+
 (showBio?'<p class="profile-bio">'+esc(bio)+'</p>':'')+'</div></div>';
}
function socialUserCard(user,actions=''){
 return '<div class="social-person" data-person-id="'+attr(user.id)+'"'+(user.relationship?' data-relationship="'+attr(user.relationship)+'"':'')+'><button class="social-person-link" type="button" data-nav="/users/'+attr(user.id)+'">'+
  socialAvatar(user)+
  '<span class="social-person-name">'+esc(socialFullName(user))+(user.handle?'<small>@'+esc(user.handle)+'</small>':'')+'</span></button>'+actions+'</div>';
}
function socialInviteButton(){
 return '<button type="button" class="btn btn-peach btn-small" data-social-action="personal-invite">'+ico('users')+' Пригласить друга</button>';
}
function socialSearchAction(u){
 const id=attr(u.id);
 if(u.relationship==='friends')return '<span class="chip chip-green">Вы друзья</span>';
 if(u.relationship==='outgoing')return '<span class="chip">Заявка отправлена</span>';
 if(u.relationship==='incoming')return '<button type="button" class="btn btn-soft btn-small" data-social-action="accept" data-user-id="'+id+'">Принять</button>';
 return '<button type="button" class="btn btn-soft btn-small" data-social-action="add" data-user-id="'+id+'">В друзья</button>';
}
let socialSearchSequence=0;
async function socialFriendsPage(marker=lastRenderToken,snapshot=null){
 if(!currentUser){loginModal();return;}
 const data=snapshot||await api('/api/friends');if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page"><div class="page-hero"><div><div class="section-label">Вместе веселее</div>'+
  '<h1>Друзья</h1><p>Ищи знакомых, делись доступными вишлистами и приглашай в игры</p></div>'+(data.invites_enabled?socialInviteButton():'')+'</div>'+
  '<section class="panel social-search"><h2>Найти друга</h2><p class="note">По имени, фамилии или @никнейму. Точный @никнейм поможет найти нужного человека</p><form id="social-search-form" class="share-field">'+
  '<input class="input" name="q" minlength="2" maxlength="120" required placeholder="Имя или @никнейм" aria-label="Найти пользователя по имени">'+
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
  (data.invites_enabled?'<section class="panel"><h2>Приглашённые друзья</h2><p class="note">'+Number(data.referral_count||0)+' подтверждённых регистраций по твоей ссылке</p></section>':'')+
  (data.outgoing.length?'<section class="panel"><h2>Отправленные заявки</h2>'+
    data.outgoing.map(u=>socialUserCard(u,'<div class="social-request-actions"><span class="chip">Ожидает ответа</span><button class="btn btn-soft btn-small" data-social-action="cancel" data-user-id="'+attr(u.id)+'">Отменить</button></div>')).join('')+'</section>':'')+
  '</main>');
 if(snapshot){syncSocialSearchRelationships(ownerPatchRoot||app.querySelector('#page-view > main'),data);return;}
 document.querySelector('#social-search-form')?.addEventListener('submit',async ev=>{
  ev.preventDefault();
  const input=ev.currentTarget.elements.q;
  const sequence=++socialSearchSequence,epoch=ownerSessionEpoch,query=input.value.trim();
  const results=document.querySelector('#social-search-results');
  results.textContent='Ищем…';
  try{
   const {users}=await api('/api/users/search?q='+encodeURIComponent(query));
   if(sequence!==socialSearchSequence||epoch!==ownerSessionEpoch||!results.isConnected||input.value.trim()!==query)return;
   results.innerHTML=users.length?users.map(u=>socialUserCard(u,socialSearchAction(u))).join(''):'<p class="note">Ничего не найдено. Проверь имя или попроси персональную ссылку</p>';
  }catch(err){if(sequence===socialSearchSequence&&epoch===ownerSessionEpoch&&results.isConnected)results.textContent=err.message;}
 });
}
async function socialProfilePage(uid,marker=lastRenderToken,byHandle=false){
 if(!currentUser&&!byHandle){loginModal();return;}
 const data=await api((byHandle?'/api/u/':'/api/users/')+encodeURIComponent(uid));if(marker!==lastRenderToken)return;
 if(data.relationship==='guest'){shell('<main class="container page social-page"><section class="panel profile-main-card">'+socialAvatar(data.profile,'profile-emoji')+'<h1>'+esc(data.profile.name)+'</h1><p>@'+esc(data.profile.handle)+'</p><button class="btn btn-dark" data-open="login">Войти, чтобы открыть профиль</button></section></main>');return;}
 const p=data.profile,relation=data.relationship;
 const coverAssignments=assignWishlistCovers(data.lists);
 let action='';
 if(relation==='none')action='<button class="btn btn-dark btn-small" data-social-action="add" data-user-id="'+attr(uid)+'">Добавить в друзья</button>';
 if(relation==='incoming')action='<button class="btn btn-dark btn-small" data-social-action="accept" data-user-id="'+attr(uid)+'">Принять заявку</button>';
 if(relation==='outgoing')action='<div class="social-request-actions"><span class="chip">Заявка отправлена</span><button class="btn btn-soft btn-small" data-social-action="cancel" data-user-id="'+attr(uid)+'">Отменить заявку</button></div>';
 if(relation==='friends')action='<span class="chip chip-green">Вы друзья</span>';
 if(relation==='self')action='<button class="btn btn-soft btn-small" data-nav="/profile">Редактировать профиль</button>';
 if(relation==='admin_directory')action='<span class="chip">Скрыт из поиска</span>';
 shell('<main class="container page social-page social-profile-page"><div class="social-profile-hero profile-main-card">'+socialIdentity(p,{own:relation==='self',showBio:relation!=='admin_directory'})+
   '<div class="profile-actions">'+action+'</div></div>'+
   '<section class="dashboard-section"><div class="dashboard-section-head"><h2>Вишлисты <span class="chip">'+data.lists.length+'</span></h2></div>'+
  (data.lists.length?'<div class="cards-grid">'+data.lists.map(list=>
   '<article class="list-card"><a class="card-hitarea" href="/w/'+attr(list.share_key)+'" data-nav="/w/'+attr(list.share_key)+'" aria-label="Открыть список '+attr(list.title)+'"></a>'+
   '<div class="list-cover cover-'+attr(list.theme)+'">'+wishlistCover(list,coverAssignments)+'</div>'+
   '<div class="list-info"><h3>'+esc(list.title)+'</h3><p>'+esc(list.description||'Список подарков')+'</p>'+
   '<div class="list-bottom"><span>'+ruCount(list.wish_count,'желание','желания','желаний')+'</span><button class="text-link" data-nav="/w/'+attr(list.share_key)+'">Посмотреть '+ico('arrow')+'</button></div></div></article>').join('')+'</div>':
   '<div class="panel"><p class="note">'+(relation==='admin_directory'?'Личные вишлисты недоступны':relation==='self'?'У тебя пока нет открытых вишлистов':relation==='friends'?'Пока нет доступных вишлистов':'Вишлисты доступны после добавления в друзья')+'</p></div>')+'</section>'+
   ((relation==='friends'||relation==='self')?'<section class="dashboard-section shared-santa-section"><div class="dashboard-section-head"><h2>'+(relation==='self'?'Мои игры в Тайного Санту':'Наш общий Тайный Санта')+' <span class="chip">'+(data.shared_games||[]).length+'</span></h2></div>'+
   ((data.shared_games||[]).length?'<div class="shared-santa-grid">'+data.shared_games.map(game=>santaGameCard(game,{shared:true})).join('')+'</div>':
    '<div class="panel"><p class="note">'+(relation==='self'?'Ты пока не участвуешь в играх':'Пока нет игр, в которых вы оба участвуете')+'</p></div>')+'</section>':'')+'</main>');
}
function socialSessionsMarkup(data){
 if(!Array.isArray(data.sessions))return '';
 const otherCount=data.sessions.filter(s=>!s.current).length;
 return '<section class="panel profile-sessions"><div class="panel-heading-actions"><h2>Активные сеансы</h2><div class="btn-row"><button type="button" class="btn btn-soft btn-small" data-social-action="refresh-sessions">Обновить</button>'+
 (otherCount?'<button type="button" class="btn btn-soft btn-small" data-social-action="revoke-other-sessions">Завершить остальные</button>':'')+'</div></div>'+
 '<p class="note">Здесь можно завершить вход на других устройствах</p><div class="profile-session-list">'+
 data.sessions.map(s=>'<div class="profile-session-row"><div><strong>'+(s.current?'Текущий сеанс':'Другой сеанс')+'</strong><small>Вход: '+esc(new Date(s.created_at).toLocaleString('ru-RU'))+'</small><small>Действует до: '+esc(new Date(s.expires_at*1000).toLocaleString('ru-RU'))+'</small></div>'+
 (s.current?'<span class="chip chip-green">Этот сеанс</span>':'<button type="button" class="btn btn-soft btn-small" data-social-action="revoke-session" data-session-id="'+attr(s.id)+'">Завершить</button>')+'</div>').join('')+'</div></section>';
}
async function socialOwnProfilePage(marker=lastRenderToken,snapshot=null){
 if(!currentUser){loginModal();return;}
 const data=snapshot||await api('/api/profile/me');if(marker!==lastRenderToken)return;
 const p=data.profile;
 shell('<main class="container page social-page social-profile-page">'+
  '<div class="social-page-heading"><span class="section-label">Твоя визитная карточка</span><h1>Мой профиль</h1>'+
  '<p>Имя, никнейм и аватар видят другие. Почта остаётся приватной</p></div>'+
  '<section class="panel profile-main-card">'+socialIdentity(p,{editable:true,own:true})+
  '<div class="profile-actions">'+
  '<button type="button" class="btn btn-dark btn-small" data-social-action="edit-profile">'+ico('edit')+' Редактировать профиль</button>'+
  '<button type="button" class="btn btn-soft btn-small" data-nav="/users/'+attr(p.id)+'">Как видят друзья</button></div></section>'+
  '<section class="panel profile-security"><div><h2>Вход и безопасность</h2><p class="note">Почта не отображается в публичном профиле</p><div class="account-email">'+esc(p.email||'')+'</div></div>'+
  '<div class="profile-actions"><button class="btn btn-soft btn-small" data-social-action="change-email">Изменить почту</button>'+
  '<button class="btn btn-soft btn-small" data-social-action="change-password">Изменить пароль</button></div></section>'+
  socialSessionsMarkup(data)+
  '<section class="panel profile-notifications"><h2>Какие уведомления получать</h2><p class="note">Настрой события, которые появляются в колокольчике</p>'+
  '<form id="notification-settings-form" class="notification-settings-list">'+
  shurshCheckbox('notify_friends','Друзья и заявки',p.notify_friends)+
  shurshCheckbox('notify_santa','Тайный Санта и приглашения',p.notify_santa)+
  shurshCheckbox('notify_gifts','Вишлисты и подарки',p.notify_gifts)+
  shurshCheckbox('notify_system','Системные сообщения',p.notify_system)+
  '<button class="btn btn-peach btn-small" type="submit">Сохранить настройки</button></form></section></main>');
 if(snapshot)return;
 document.getElementById('notification-settings-form')?.addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget,button=form.querySelector('[type="submit"]');button.disabled=true;
  const payload={};for(const name of ['notify_friends','notify_santa','notify_gifts','notify_system'])payload[name]=form.elements[name].checked;
  try{await api('/api/profile/me',{method:'PATCH',body:payload});clearOwnerTabViews(['/profile']);notice('Настройки уведомлений сохранены');}
  catch(error){notice(error.message,true);}finally{button.disabled=false;}
 });
}
function profileVisibilityField(label,name,placeholder,value,visible,extra=''){
 const key='show_'+name,tip=(visible?'Скрыть ':'Показывать ')+(name==='last_name'?'фамилию':'отчество');
 return '<div class="profile-name-visibility">'+field(label,name,placeholder,'text',value||'',false,extra)+
 '<input type="hidden" name="'+key+'" value="'+String(!!visible)+'">'+
 '<button type="button" class="profile-visibility-toggle" data-profile-visibility="'+key+'" aria-pressed="'+String(!!visible)+'" aria-label="'+tip+'" title="'+tip+'">'+ico(visible?'eye':'eye-off')+'</button></div>';
}
async function socialEditProfileModal(){
 const d=await api('/api/profile/me'),p=d.profile;
 modal({title:'Редактировать профиль',subtitle:'Настрой, как тебя видят друзья',
  content:field('Имя *','name','Как к тебе обращаться','text',p.name,true,'maxlength="40"')+
   (d.invites_enabled?profileVisibilityField('Фамилия','last_name','Твоя фамилия',p.last_name,p.show_last_name,'maxlength="60" autocomplete="family-name"')+profileVisibilityField('Отчество','patronymic','Твоё отчество',p.patronymic,p.show_patronymic,'maxlength="60"'):'')+
   field('Никнейм (@)','handle','Например, shurshfriend','text',p.handle||'',false,'maxlength="20" autocomplete="username"')+
   field('Город','city','Например, Санкт-Петербург','text',p.city||'',false,'maxlength="60"')+
   textArea('О себе','bio','Что любишь, чем увлекаешься и что тебя радует',p.bio||'')+
   shurshCheckbox('discoverable','Показывать мой профиль в поиске',p.discoverable),
  submitLabel:'Сохранить профиль',onSubmit:async form=>{
   const data=readForm(form);data.discoverable=form.elements.discoverable.checked;
   if(d.invites_enabled){data.show_last_name=form.elements.show_last_name.value==='true';data.show_patronymic=form.elements.show_patronymic.value==='true';}
   const response=await api('/api/profile/me',{method:'PATCH',body:data});
   currentUser.name=response.profile.name;currentUser.avatar_emoji=response.profile.avatar_emoji;currentUser.handle=response.profile.handle;
   clearOwnerTabViews(['/profile']);notice('Профиль обновлён');await socialOwnProfilePage();
  }});
 modalRoot.querySelector('.modal')?.classList.add('profile-edit-modal');
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
   (email?field('Новая почта','email','new@example.com','text','',true,'inputmode="email" autocomplete="email" autocapitalize="none" spellcheck="false" maxlength="200"'):
    passwordField(true,'new_password','Новый пароль')+confirmPasswordField())+authFormWarning(),
  onError:showAuthFormWarning,
  submitLabel:email?'Отправить подтверждение':'Обновить пароль',onSubmit:async form=>{
   clearAuthFormWarning(form);
   const payload=readForm(form);
   if(!email&&payload.new_password!==payload.confirm_password){const err=new Error('Пароли не совпадают');err.status=400;throw err;}
   delete payload.confirm_password;
   const result=await api('/api/account/'+kind,{method:'POST',body:payload});
   notice(email&&result.pending_confirmation?'Проверь новую почту и подтверди изменение':'Пароль изменён');
  }});
 setupAuthFormValidation(modalRoot.querySelector('#modal-form'),!email);
}
function socialNotificationDate(date){
 const value=new Date(date);
 return Number.isNaN(value.getTime())?'':new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}).format(value);
}
function shurshCheckbox(name,label,checked){
 return '<label class="shursh-checkbox"><input type="checkbox" name="'+attr(name)+'"'+(checked?' checked':'')+'><span class="shursh-checkbox-mark" aria-hidden="true">'+ico('check',16)+'</span><span>'+esc(label)+'</span></label>';
}
let notificationModalItems=[];
let notificationModalTab='new',notificationModalMore=false,notificationModalUnread=0;
function mergeNotificationItems(first,older){const byId=new Map(older.map(n=>[n.id,n]));for(const n of first)byId.set(n.id,n);return [...byId.values()].sort((a,b)=>b.id-a.id);}
function notificationCategory(item){
 return ['friend_request','friend_accept','wishlist_new','wish_new','wish_request','santa_invitation','santa_joined'].includes(item.kind)?'friends':'system';
}
function renderNotificationModalTab(tab=notificationModalTab){
 const panel=modalRoot.querySelector('#notification-modal-list');if(!panel)return;
 notificationModalTab=tab;
 const chosen=Array.from(modalRoot.querySelectorAll('[data-notification-tab]')).find(button=>button.dataset.notificationTab===tab);
 if(chosen)syncSelection(chosen.closest('[role="tablist"]'),chosen,'aria-selected');
 const items=notificationModalItems.filter(item=>
  tab==='new'?!item.read_at:
  tab==='read'?!!item.read_at:
  notificationCategory(item)===tab);
 const next=panel.cloneNode(false);
 next.innerHTML=(items.length?items.map(item=>
  '<div class="notification-item'+(item.read_at?'':' unread')+'" data-notification-id="'+attr(item.id)+'">'+
  '<button class="notification-open" type="button" data-social-action="open-notification" data-id="'+item.id+'" data-path="'+attr(item.target_path)+'">'+
  '<strong>'+esc(item.message)+'</strong><small>'+esc(socialNotificationDate(item.created_at))+'</small></button>'+
  (!item.read_at?'<button class="btn btn-soft btn-small" type="button" data-social-action="read-notification" data-id="'+item.id+'">Прочитано</button>':'')+
  '</div>').join(''):'<p class="note">Здесь пока пусто</p>')+(notificationModalMore?'<button type="button" class="btn btn-soft btn-small" data-social-action="notification-older">Ранее</button>':'');
 patchOwnerNode(panel,next);
 const unread=notificationModalUnread;
 const all=modalRoot.querySelector('[data-social-action="read-all-notifications"]');if(all)all.disabled=!unread;
}
async function socialNotificationsModal(){
 if(!currentUser)return;
 const response=await api('/api/notifications');
 notificationModalItems=response.items||[];notificationModalMore=!!response.has_more;notificationModalUnread=response.unread||0;
 notificationModalTab='new';
 const tabs=[['new','Новое'],['friends','Друзья'],['system','Системные'],['read','Прочитано']];
 modal({title:'Уведомления',subtitle:'Новости друзей, подарков и игр',
  content:'<div class="notification-dialog"><div class="notification-dialog-toolbar"><div class="notification-tabs" role="tablist" aria-label="Фильтр уведомлений">'+
  tabs.map(([id,label])=>'<button type="button" role="tab" data-notification-tab="'+id+'" id="notification-tab-'+id+'" aria-controls="notification-modal-list" tabindex="'+(id==='new'?'0':'-1')+'" aria-selected="'+(id==='new'?'true':'false')+'" class="'+(id==='new'?'active':'')+'">'+label+'</button>').join('')+
  '</div><button type="button" class="notification-read-all" data-social-action="read-all-notifications" aria-label="Прочесть все" title="Прочесть все">'+ico('check')+'</button></div>'+
  '<div id="notification-modal-list" role="tabpanel" aria-labelledby="notification-tab-new" aria-live="polite"></div></div>'});
 const bell=document.querySelector('header .header-bell');
 if(bell)setAttrIfChanged(bell,'aria-expanded','true');
 const anchor=bell?.getBoundingClientRect();
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
 if(tab){event.preventDefault();if(tab.getAttribute('aria-selected')!=='true')renderNotificationModalTab(tab.dataset.notificationTab);}
});
function notificationPageItem(n){
 return '<div class="notification-item'+(n.read_at?'':' unread')+'" data-notification-id="'+attr(n.id)+'">'+
 '<button class="notification-open" data-social-action="open-notification" data-id="'+n.id+'" data-path="'+attr(n.target_path)+'"><strong>'+esc(n.message)+'</strong><small>'+esc(socialNotificationDate(n.created_at))+'</small></button>'+
 (!n.read_at?'<button class="btn btn-soft btn-small" type="button" data-social-action="read-notification" data-id="'+n.id+'">Прочитано</button>':'')+'</div>';
}
async function socialNotificationsPage(marker=lastRenderToken,snapshot=null){
 if(!currentUser){loginModal();return;}
 const res=snapshot||await api('/api/notifications');if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page"><div class="page-hero"><div><div class="section-label">Новости друзей и игр</div>'+
 '<h1>Уведомления</h1><p>Новые подарки, приглашения и события Тайного Санты</p></div></div>'+
 '<section class="panel notification-feed"><div data-notification-recent>'+(res.items.length?res.items.map(notificationPageItem).join(''):'<p class="note">Пока всё спокойно. Как только появятся новости, они будут здесь</p>')+
 '</div><div data-notification-history id="notification-page-history"></div><div data-notification-pagination>'+
 (res.has_more?'<button type="button" class="btn btn-soft btn-small" data-social-action="notification-older">Ранее</button>':'')+
 '</div></section></main>');
 if(!snapshot)socialRefreshBadge();
}
async function loadOlderNotifications(target){
 const epoch=ownerSessionEpoch,modalView=!!target.closest('.notification-dialog');
 const root=modalView?modalRoot.querySelector('.notification-dialog'):target.closest('.notification-feed');
 if(!root)return;
 const ids=modalView?notificationModalItems.map(n=>Number(n.id)):[...root.querySelectorAll('[data-notification-id]')].map(n=>Number(n.dataset.notificationId));
 if(!ids.length)return;
 const response=await api('/api/notifications?before='+Math.min(...ids));
 if(epoch!==ownerSessionEpoch||!root.isConnected)return;
 if(modalView){
  notificationModalItems=mergeNotificationItems(notificationModalItems,response.items||[]);
  notificationModalMore=!!response.has_more;notificationModalUnread=response.unread||0;
  renderNotificationModalTab();
 }else{
  const history=root.querySelector('[data-notification-history]');
  const seen=new Set([...root.querySelectorAll('[data-notification-id]')].map(n=>String(n.dataset.notificationId)));
  history.insertAdjacentHTML('beforeend',(response.items||[]).filter(n=>!seen.has(String(n.id))).map(notificationPageItem).join(''));
  root.querySelector('[data-notification-pagination]').dataset.loaded='true';
  if(!response.has_more)target.remove();
 }
}
function socialAdminVisitDate(date,now=new Date()){
 const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
 const yesterday=new Date(now.getFullYear(),now.getMonth(),now.getDate()-1);
 const day=new Date(date.getFullYear(),date.getMonth(),date.getDate());
 const time=date.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
 return +day===+today?'сегодня, '+time:+day===+yesterday?'вчера, '+time:
  date.toLocaleString('ru-RU',{dateStyle:'medium',timeStyle:'short'});
}
const ADMIN_PRESENCE_WINDOW=5*60*1000;
let adminServerClockOffset=0;
function syncAdminPresenceClock(page){const stamp=Date.parse(page.server_now);if(Number.isFinite(stamp))adminServerClockOffset=stamp-Date.now();}
function socialAdminPresenceOnline(u,now=Date.now()+adminServerClockOffset){
 const age=now-Date.parse(u.last_seen_at);
 return u.last_seen_source==='visit'&&Number.isFinite(age)&&age>=0&&age<ADMIN_PRESENCE_WINDOW;
}
function socialAdminVisitMarkup(u){
 if(!u.last_seen_at)return '<span class="muted">Нет данных</span>';
 const platforms={
  windows:['Windows','<path d="M2 4l9-1.3V11H2zm11-1.6L22 1v10h-9zM2 13h9v8.3L2 20zm11 0h9v10l-9-1.4z"/>'],
  macos:['Mac',null],
  linux:['Linux','<path d="M12 2c-3 0-4.5 2.4-4.5 5.5 0 3-3.5 6-3.5 10 0 1.6.8 3 2 3.4 1.6.5 3.7-.5 6-.5s4.4 1 6 .5c1.2-.4 2-1.8 2-3.4 0-4-3.5-7-3.5-10C16.5 4.4 15 2 12 2Z"/><ellipse cx="12" cy="15.5" rx="4.2" ry="4.6" fill="#fffefa"/><circle cx="10" cy="7" r=".9" fill="#fffefa"/><circle cx="14" cy="7" r=".9" fill="#fffefa"/><path d="m10 9 2 1.8L14 9l-2-.8z" fill="#fffefa"/>'],
  android:['Android','<path d="M3 16a9 9 0 0 1 18 0H3Z"/><path d="m6 8-2-3m14 3 2-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="12" r="1" fill="#fffefa"/><circle cx="16" cy="12" r="1" fill="#fffefa"/>'],
  ios:['iOS','<path d="M16.2 2c.2 2-1.4 4-3.5 4.4-.3-2 1.5-4 3.5-4.4ZM20 13.8c-.9-1.3-1.3-2.8-.6-4.2-2.1-2.7-4.2-2-6-1.3-1 .4-1.8.3-2.8-.1C7 6.5 3.6 9.5 4.2 14c.5 3.4 2.9 7.9 5 7.9 1 0 1.6-.7 3.2-.7 1.5 0 2.2.7 3.3.7 2.1 0 4.1-3.6 4.9-6.1-1.7-.7-2.6-1.9-2.6-2Z"/>']
 };
 const platform=Object.hasOwn(platforms,u.last_platform)?platforms[u.last_platform]:['Не определена','<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4m0 3v1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'];
 const date=new Date(u.last_seen_at);
 if(!Number.isFinite(date.getTime()))return '<span class="muted">Нет данных</span>';
 const symbol=platform[1]?'<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="'+attr(platform[0])+'" focusable="false"><title>'+esc(platform[0])+'</title>'+platform[1]+'</svg>':'<span aria-label="macOS" title="macOS">Mac</span>';
 const provenance=u.last_seen_source==='session'?'Последний известный вход по сессии; устройство не записано':'Последняя зафиксированная активность';
 const online=socialAdminPresenceOnline(u),status=online?'В сети: активность за последние 5 минут':'Нет недавней активности';
 return '<div class="admin-user-identity"><span class="admin-device-presence'+(online?' is-online':'')+'" data-presence-seen="'+attr(u.last_seen_at)+'" data-presence-source="'+attr(u.last_seen_source||'')+'" title="'+attr(status)+'">'+symbol+'<span class="sr-only" data-presence-status>'+esc(status)+'</span></span><span><time title="'+attr(provenance)+'" datetime="'+attr(u.last_seen_at)+'">'+esc(socialAdminVisitDate(date))+'</time></span></div>';
}
const adminCategories={wishlists:'Вишлисты',gifts:'Подарки',referrals:'Рефы',organized:'Свои Санты',joined:'Участие',discoverable:'В поиске'};
function adminCountCell(u,key,value){
 return '<td><button type="button" class="admin-count-button" data-social-action="admin-details" data-user-id="'+attr(u.id)+'" data-category="'+key+'" data-admin-count="'+key+'" aria-label="'+attr(adminCategories[key]+': '+u.name)+'">'+esc(value)+'</button></td>';
}
async function socialAdminDetails(uid,category,offset=0){
 const marker=lastRenderToken,epoch=ownerSessionEpoch;
 if(!Object.hasOwn(adminCategories,category))return;
 const data=await api('/api/admin/users/'+encodeURIComponent(uid)+'/'+category+'?offset='+offset,{method:'POST',body:{}});
 if(marker!==lastRenderToken||epoch!==ownerSessionEpoch)return;
 const title=adminCategories[category],p=data.profile;
 if(category==='discoverable'){
  modal({title:'Видимость в поиске',subtitle:p.name,content:shurshCheckbox('discoverable','Показывать в поиске',p.discoverable)+field('Пароль администратора','current_password','Текущий пароль','password','',true,'autocomplete="current-password" maxlength="200"')+'<p class="note">Действие будет записано в журнал</p>',submitLabel:'Подтвердить',onSubmit:async form=>{
   const password=form.elements.current_password.value;form.elements.current_password.value='';
   await api('/api/admin/users/'+encodeURIComponent(uid)+'/discoverable',{method:'PATCH',body:{current_password:password,discoverable:form.elements.discoverable.checked}});
   notice('Видимость обновлена');const root=document.querySelector('[data-admin-users-content]');if(root)await socialLoadAdminUsers(Number(root.dataset.adminOffset||0));
  }});return;
 }
 const list=data.items.map(x=>'<div class="admin-detail-row"><strong>'+esc(x.title)+'</strong><span class="note">'+esc([x.context,x.status, x.created_at?socialAdminVisitDate(new Date(x.created_at)):null].filter(Boolean).join(' · '))+'</span></div>').join('');
 const pager='<div class="btn-row admin-detail-pager">'+
  '<button type="button" class="btn btn-soft btn-small" data-social-action="admin-details" data-user-id="'+attr(uid)+'" data-category="'+category+'" data-offset="'+Math.max(0,offset-25)+'"'+(offset?'':' disabled')+'>Назад</button>'+
  '<button type="button" class="btn btn-soft btn-small" data-social-action="admin-details" data-user-id="'+attr(uid)+'" data-category="'+category+'" data-offset="'+(offset+25)+'"'+(data.more?'':' disabled')+'>Вперёд</button></div>';
 modal({title,subtitle:p.name,content:'<div class="admin-detail-list">'+(list||'<p class="note">Пока нет записей</p>')+'</div>',footer:pager});
}
const adminEventNames={'auth.sessions_revoked':'Завершены сеансы','auth.login':'Вход в аккаунт','auth.confirmed':'Подтверждён аккаунт','auth.logout':'Выход из аккаунта','wishlist.created':'Создан вишлист','wishlist.updated':'Изменён вишлист','wishlist.deleted':'Удалён вишлист','gift.created':'Добавлен подарок','gift.updated':'Изменён подарок','gift.deleted':'Удалён подарок','santa.created':'Создан Тайный Санта','santa.updated':'Изменена игра','santa.deleted':'Удалена игра','santa.drawn':'Проведена жеребьёвка','santa.finished':'Завершена игра','santa.photo_saved':'Сохранено фото','santa.photo_deleted':'Удалено фото','santa.joined':'Вступление в игру','profile.updated':'Изменён профиль','friend.requested':'Запрос в друзья','friend.updated':'Изменена заявка в друзья','friend.removed':'Удалён друг','feedback.created':'Создано обращение','feedback.updated':'Изменено обращение','invite.revoked':'Отозвано приглашение','admin.user_details':'Просмотр сведений пользователя','admin.visibility_changed':'Изменена видимость профиля','admin.visibility_rejected':'Неудачное подтверждение пароля'};
let adminAuditRequest=0;
async function socialLoadAudit(audience='admins',offset=0){
 const root=document.querySelector('[data-admin-audit-content]');if(!root)return;
 const request=++adminAuditRequest;root.setAttribute('aria-busy','true');
 try{
  const data=await api('/api/admin/audit?audience='+audience+'&offset='+offset);
  if(!root.isConnected||request!==adminAuditRequest)return;
  for(const tab of document.querySelectorAll('[data-audit-tab]')){const active=tab.dataset.auditTab===audience;tab.setAttribute('aria-selected',String(active));tab.classList.toggle('active',active);}
  root.innerHTML='<div class="admin-audit-list">'+(data.items.map(x=>'<button type="button" class="admin-audit-row" data-social-action="admin-audit-event" data-id="'+attr(x.id)+'"><span><strong>'+esc(adminEventNames[x.event]||x.event)+'</strong><small>'+esc(x.actor_name||'Удалённый пользователь')+'</small></span><span class="note">'+esc(socialAdminVisitDate(new Date(x.created_at)))+' · '+(x.success?'Успешно':'Отклонено')+'</span></button>').join('')||'<p class="note">Пока нет событий</p>')+'</div>'+
  '<div class="admin-users-pager"><span>Страница '+(Math.floor(offset/25)+1)+'</span><div class="btn-row"><button type="button" class="btn btn-soft btn-small" data-social-action="admin-audit-page" data-audience="'+audience+'" data-offset="'+Math.max(0,offset-25)+'"'+(offset?'':' disabled')+'>Назад</button><button type="button" class="btn btn-soft btn-small" data-social-action="admin-audit-page" data-audience="'+audience+'" data-offset="'+(offset+25)+'"'+(data.more?'':' disabled')+'>Вперёд</button></div></div>';
 }catch(error){if(root.isConnected&&request===adminAuditRequest)root.innerHTML='<p class="note">'+esc(error.message)+'</p>';}
 finally{if(root.isConnected&&request===adminAuditRequest)root.removeAttribute('aria-busy');}
}
async function socialAdminAuditPage(marker=lastRenderToken){
 if(!currentUser?.is_admin){errorView(new Error('Доступ только администратору'));return;}
 if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page admin-page"><div class="admin-section-back"><a href="/admin" data-nav="/admin" class="text-link">'+ico('back',18)+' Все разделы</a></div><div class="page-hero"><div><h1>Журнал событий</h1><p>Важные события за последние 90 дней</p></div></div><section class="panel"><div class="admin-audit-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" class="active" data-audit-tab="admins" data-social-action="admin-audit-page" data-audience="admins">Админы</button><button type="button" role="tab" aria-selected="false" data-audit-tab="users" data-social-action="admin-audit-page" data-audience="users">Пользователи</button></div><div data-admin-audit-content aria-live="polite"></div></section></main>');
 await socialLoadAudit();
}
async function socialAdminAuditEvent(id){
 const marker=lastRenderToken,epoch=ownerSessionEpoch;const {event:x}=await api('/api/admin/audit/'+encodeURIComponent(id));
 if(marker!==lastRenderToken||epoch!==ownerSessionEpoch)return;
 const rows=[['Событие',adminEventNames[x.event]||x.event],['Дата',new Date(x.created_at).toLocaleString('ru-RU')],['Инициатор',x.actor_name||'Удалённый пользователь'],['ID инициатора',x.actor_id],['Пользователь',x.target_name],['ID пользователя',x.target_id],['Категория',adminCategories[x.category]],['ID объекта',x.object_id],['Результат',x.success?'Успешно':'Отклонено'],['До',x.before_visible===null?null:x.before_visible?'Виден':'Скрыт'],['После',x.after_visible===null?null:x.after_visible?'Виден':'Скрыт']];
 modal({title:'Подробности события',content:rows.filter(([,v])=>v!==null&&v!==undefined).map(([k,v])=>'<div class="admin-detail-row"><small>'+esc(k)+'</small><strong>'+esc(v)+'</strong></div>').join(''),footer:'<button type="button" class="btn btn-soft" data-close>Закрыть</button>'});
}
function socialAdminUsersMarkup(page){
 syncAdminPresenceClock(page);
 const rows=(page.users||[]).map(u=>'<tr><td class="admin-user-cell"><a class="admin-user-identity admin-user-profile-link" href="/users/'+attr(u.id)+'" data-nav="/users/'+attr(u.id)+'" aria-label="Открыть профиль '+attr(u.name)+'"><span class="admin-user-emoji" aria-hidden="true">'+
   esc(u.avatar_emoji||'🎁')+'</span><span><strong>'+esc(u.name)+'</strong>'+
   '<small>ID: '+esc(String(u.id).slice(0,8))+'</small></span></a></td>'+
   '<td>'+(u.handle?'@'+esc(u.handle):'<span class="muted">—</span>')+'</td>'+
   '<td><time datetime="'+attr(u.created_at)+'">'+esc(new Date(u.created_at).toLocaleString('ru-RU',{dateStyle:'medium',timeStyle:'short'}))+'</time></td>'+
   '<td data-admin-visit-user="'+attr(u.id)+'">'+socialAdminVisitMarkup(u)+'</td>'+adminCountCell(u,'wishlists',Number(u.wishlists_count||0))+adminCountCell(u,'gifts',Number(u.gifts_count||0))+adminCountCell(u,'referrals',Number(u.referral_count||0))+adminCountCell(u,'organized',Number(u.organized_games||0))+adminCountCell(u,'joined',Number(u.joined_games||0))+adminCountCell(u,'discoverable',u.discoverable?'Виден':'Скрыт')+'</tr>').join('');
 const from=page.total?Number(page.offset)+1:0;
 const to=Math.min(Number(page.offset)+Number(page.limit),Number(page.total));
 return '<div class="admin-users-table-scroll"><table class="admin-users-table"><thead><tr>'+
   '<th>Игрок</th><th>Ник</th><th>Регистрация</th><th>Последний визит</th><th>Вишлисты</th><th>Подарки</th><th>Рефы</th>'+
   '<th>Свои Санты</th><th>Участие</th><th>В поиске</th></tr></thead><tbody>'+
   (rows||'<tr><td colspan="10" class="muted">Игроки не найдены</td></tr>')+'</tbody></table></div>'+
   '<div class="admin-users-pager"><span>'+from+'–'+to+' из '+Number(page.total)+'</span>'+
   '<div class="btn-row"><button type="button" class="btn btn-soft btn-small" data-social-action="admin-users-prev" data-offset="'+Math.max(0,page.offset-page.limit)+'"'+(page.offset===0?' disabled':'')+'>Назад</button>'+
   '<button type="button" class="btn btn-soft btn-small" data-social-action="admin-users-next" data-offset="'+(page.offset+page.limit)+'"'+(to>=page.total?' disabled':'')+'>Вперёд</button></div></div>';
}
let adminUsersSearchTimer=null;
let adminUsersRequestId=0;
async function socialLoadAdminUsers(offset=0){
 const root=document.querySelector('[data-admin-users-content]');
 const search=document.getElementById('admin-users-query');
 if(!root||!search)return;
 const query=search.value.trim(),requestId=++adminUsersRequestId;
 root.setAttribute('aria-busy','true');
 try{
  const page=await api('/api/admin/users?offset='+offset+'&q='+encodeURIComponent(query));
  if(requestId!==adminUsersRequestId||!root.isConnected||search.value.trim()!==query)return;
  root.innerHTML=socialAdminUsersMarkup(page);
  root.dataset.adminOffset=String(page.offset||0);root.dataset.adminQuery=query;
 }catch(error){
  if(requestId===adminUsersRequestId&&root.isConnected)notice(error.message,true);
 }finally{
  if(requestId===adminUsersRequestId&&root.isConnected)root.removeAttribute('aria-busy');
 }
}
let adminPresenceBusy=false;
async function socialRefreshAdminPresence(){
 if(document.hidden||!currentUser?.is_admin||currentPath()!=='/admin/users'||isPreview)return;
 const root=document.querySelector('[data-admin-users-content]');
 if(!root)return;
 // Expire stale indicators even if the next network read fails.
 for(const el of root.querySelectorAll('.admin-device-presence.is-online')){
  if(socialAdminPresenceOnline({last_seen_at:el.dataset.presenceSeen,last_seen_source:el.dataset.presenceSource}))continue;
  el.classList.remove('is-online');el.title='Нет недавней активности';
  el.querySelector('[data-presence-status]').textContent=el.title;
 }
 const search=document.getElementById('admin-users-query'),query=search?.value.trim()||'';
 if(adminPresenceBusy||root.hasAttribute('aria-busy')||query!==(root.dataset.adminQuery||''))return;
 const offset=Number(root.dataset.adminOffset||0),requestId=adminUsersRequestId,epoch=ownerSessionEpoch;
 adminPresenceBusy=true;
 try{
  const page=await api('/api/admin/users?offset='+offset+'&q='+encodeURIComponent(query));
  if(epoch!==ownerSessionEpoch||requestId!==adminUsersRequestId||!root.isConnected||document.hidden||search.value.trim()!==query||root.hasAttribute('aria-busy'))return;
  syncAdminPresenceClock(page);
  const users=new Map((page.users||[]).map(u=>[String(u.id),u]));
  for(const cell of root.querySelectorAll('[data-admin-visit-user]')){
   const user=users.get(cell.dataset.adminVisitUser);
   if(!user)continue;
   const next=cell.cloneNode(false);next.innerHTML=socialAdminVisitMarkup(user);patchOwnerNode(cell,next);
   const row=cell.closest('tr');for(const [key,value] of [['gifts',user.gifts_count],['referrals',user.referral_count]]){const count=row?.querySelector('[data-admin-count="'+key+'"]');if(count&&count.textContent!==String(Number(value||0)))count.textContent=String(Number(value||0));}
  }
 }catch{ /* Presence is advisory; leave existing data and expire stale indicators. */ }
 finally{adminPresenceBusy=false;}
}
setInterval(()=>{if(typeof currentUser!=='undefined')void socialRefreshAdminPresence();},30000);
async function socialAdminPage(marker=lastRenderToken){
 if(!currentUser?.is_admin){errorView(new Error('Доступ только администратору'));return;}
 const {stats}=await api('/api/admin/overview');
 if(marker!==lastRenderToken)return;
 shell('<main class="container page social-page admin-page"><div class="page-hero"><div><div class="section-label">Шурш! / управление</div>'+
  '<h1>Центр управления</h1><p>Работа с пользователями и обращениями. Личные переписки и секреты жеребьёвки сюда не попадают</p></div></div>'+
  '<div class="admin-hub-grid" aria-label="Разделы админки">'+
  '<a class="panel admin-hub-card admin-hub-users" href="/admin/users" data-nav="/admin/users">'+
  '<div class="admin-hub-card-top"><span class="admin-hub-icon">'+ico('users',25)+'</span><span class="admin-hub-arrow">'+ico('arrow')+'</span></div>'+
  '<strong>Пользователи</strong><p>Поиск, регистрации и активность участников</p><span class="admin-hub-metric">'+Number(stats.users||0)+' зарегистрировано</span>'+(stats.referrals!==undefined?'<p>'+Number(stats.referrals)+' зарегистрировано по приглашениям</p>':'')+'</a>'+
  '<a class="panel admin-hub-card admin-hub-feedback" href="/admin/feedback" data-nav="/admin/feedback">'+
  '<div class="admin-hub-card-top"><span class="admin-hub-icon">'+ico('mail',25)+'</span><span class="admin-hub-arrow">'+ico('arrow')+'</span></div>'+
  '<strong>Обращения</strong><p>Вопросы, ошибки и предложения пользователей</p><span class="admin-hub-metric">'+Number(stats.new_feedback||0)+' новых</span></a>'+
  '<a class="panel admin-hub-card admin-hub-audit" href="/admin/audit" data-nav="/admin/audit"><div class="admin-hub-card-top"><span class="admin-hub-icon">'+ico('info',25)+'</span><span class="admin-hub-arrow">'+ico('arrow')+'</span></div><strong>Журнал событий</strong><p>Действия администраторов и пользователей</p></a>'+
  '</div></main>');
}
async function socialAdminUsersPage(marker=lastRenderToken){
 if(!currentUser?.is_admin){errorView(new Error('Доступ только администратору'));return;}
 await socialRefreshBadge(true);
 if(marker!==lastRenderToken)return;
 const page=await api('/api/admin/users');
 if(marker!==lastRenderToken)return;
 ++adminUsersRequestId;
 if(adminUsersSearchTimer!==null){clearTimeout(adminUsersSearchTimer);adminUsersSearchTimer=null;}
 shell('<main class="container page social-page admin-page"><div class="admin-section-back"><a href="/admin" data-nav="/admin" class="text-link">'+ico('back',18)+' Все разделы</a></div>'+
   '<div class="page-hero"><div><div class="section-label">Администрирование / пользователи</div>'+
   '<h1>Пользователи</h1><p>Поиск по имени и никнейму. Без доступа к личным данным других разделов</p></div></div>'+
   '<section class="panel admin-users-panel"><div class="panel-heading-actions"><h2>Зарегистрированные игроки</h2></div>'+
   '<form id="admin-users-search" class="admin-users-search" role="search">'+
   '<label for="admin-users-query" class="sr-only">Поиск пользователей</label>'+
   '<input id="admin-users-query" class="input" type="search" placeholder="Имя или никнейм" maxlength="50" autocomplete="off" aria-controls="admin-users-content">'+
   '</form><div id="admin-users-content" data-admin-users-content aria-live="polite">'+socialAdminUsersMarkup(page)+'</div></section></main>');
 const search=document.getElementById('admin-users-query');
 search?.closest('form')?.addEventListener('submit',e=>e.preventDefault());
 search?.addEventListener('input',()=>{
   if(adminUsersSearchTimer!==null)clearTimeout(adminUsersSearchTimer);
   adminUsersSearchTimer=setTimeout(()=>{adminUsersSearchTimer=null;void socialLoadAdminUsers(0);},250);
 });
}
async function socialInviteFriendsModal(){
 if(!currentUser||!loadedSanta?.event||loadedSanta.event.status!=='open')return;
 const eventId=loadedSanta.event.id,marker=lastRenderToken;
 const {friends}=await api('/api/friends');
 if(marker!==lastRenderToken)return;
 if(!friends.length){notice('Сначала добавь друзей',true);nav('/friends');return;}
 modal({title:'Позвать друзей в игру',subtitle:'Друг получит приглашение в уведомлениях',
  content:selectField('Кого пригласить','friend_id',friends.map(x=>[x.id,x.name]),friends[0].id),
  submitLabel:'Отправить приглашение',onSubmit:async form=>{
   const uid=readForm(form).friend_id;
   await api('/api/santas/'+eventId+'/invite-friend/'+encodeURIComponent(uid),{method:'POST',body:{}});
   notice('Приглашение отправлено');
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
 const visibility=e.target.closest('[data-profile-visibility]');
 if(visibility){e.preventDefault();const input=visibility.parentElement.querySelector('input[type="hidden"]');if(!input)return;const visible=input.value!=='true';input.value=String(visible);visibility.setAttribute('aria-pressed',String(visible));const tip=(visible?'Скрыть ':'Показывать ')+(visibility.dataset.profileVisibility==='show_last_name'?'фамилию':'отчество');visibility.setAttribute('aria-label',tip);visibility.title=tip;visibility.innerHTML=ico(visible?'eye':'eye-off');return;}
 const picker=e.target.closest('[data-avatar-pick]');if(picker){e.preventDefault();const root=picker.closest('.emoji-grid');root?.querySelectorAll('[data-avatar-pick]').forEach(x=>{x.classList.toggle('selected',x===picker);x.setAttribute('aria-pressed',String(x===picker));});const input=modalRoot.querySelector('#social-avatar-value');if(input)input.value=picker.dataset.avatarPick;return;}
 const target=e.target.closest('[data-social-action]');if(!target)return;
 e.preventDefault();
 const action=target.dataset.socialAction,uid=target.dataset.userId,actionPath=currentPath();
 target.disabled=true;
 try{
  if(action==='santa-invite-qr'){await socialSantaInviteQr(target.dataset.code);return;}
  if(action==='personal-invite'){await socialPersonalInviteModal();return;}
  if(action==='copy-personal-invite'){await copyPersonalInvite(target);return;}
  if(action==='share-personal-invite'){await sharePersonalInvite(target);return;}
  if(action==='share-personal-qr'){await sharePersonalQr();return;}
  if(action==='revoke-personal-invite'){
   if(!window.confirm('Отозвать ссылку? Старые приглашения перестанут работать'))return;
   await api('/api/friend-invites/me',{method:'DELETE',body:{}});closeModal();notice('Приглашение отозвано');return;
  }
  if(action==='invite-add'){
   await api('/api/friend-invites/'+encodeURIComponent(target.dataset.code)+'/friend',{method:'POST',body:{}});
   if(currentPath()===actionPath){notice('Заявка обработана');await socialFriendInvitePage(target.dataset.code);}
   return;
  }
  if(action==='open-notifications'){await socialNotificationsModal();return;}
  if(action==='notification-older'){await loadOlderNotifications(target);return;}
  if(action==='read-all-notifications'){
   await api('/api/notifications/read-all',{method:'POST',body:{}});
   notificationModalUnread=0;const time=new Date().toISOString();notificationModalItems.forEach(x=>{if(!x.read_at)x.read_at=time;});
   renderNotificationModalTab();socialUnreadLast=0;void socialRefreshBadge(true);return;
  }
  if(action==='refresh-sessions'){
   dropOwnerRead('/api/profile/me');clearOwnerTabViews(['/profile']);
   if(currentPath()===actionPath)await socialOwnProfilePage();return;
  }
  if(action==='revoke-session'||action==='revoke-other-sessions'){
   if(!confirm(action==='revoke-session'?'Завершить этот сеанс?':'Завершить все сеансы, кроме текущего?'))return;
   await api('/api/sessions/'+(action==='revoke-session'?encodeURIComponent(target.dataset.sessionId):'others'),{method:'DELETE',body:{}});
   notice('Сеансы завершены');if(currentPath()===actionPath)await socialOwnProfilePage();return;
  }
  if(action==='edit-profile'){await socialEditProfileModal();return;}
  if(action==='edit-avatar'){await socialEditAvatarModal();return;}
  if(action==='admin-details'){await socialAdminDetails(uid,target.dataset.category,Number(target.dataset.offset)||0);return;}
  if(action==='admin-audit-page'){await socialLoadAudit(target.dataset.audience,Number(target.dataset.offset)||0);return;}
  if(action==='admin-audit-event'){await socialAdminAuditEvent(target.dataset.id);return;}
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
    if(item&&!item.read_at){item.read_at=new Date().toISOString();notificationModalUnread=Math.max(0,notificationModalUnread-1);}
    renderNotificationModalTab();void socialRefreshBadge(true);
   }else if(target.isConnected){const row=target.closest('[data-notification-id]');row?.classList.remove('unread');target.remove();void socialRefreshBadge(true);}
   return;
  }
  if(action==='add'||action==='accept'||action==='decline'||action==='unfriend'||action==='cancel'){
   const method=action==='add'?'POST':(action==='unfriend'||action==='cancel')?'DELETE':'PATCH';
   const payload=(action==='accept'||action==='decline')?{action:action==='accept'?'accept':'decline'}:{};
   await api('/api/friends/'+encodeURIComponent(uid),{method,body:payload});
   socialUnreadLast=0;
   notice(action==='add'?'Заявка в друзья отправлена':action==='accept'?'Теперь вы друзья':action==='decline'?'Заявка отклонена':action==='cancel'?'Заявка отменена':'Друг удалён');
   if(currentPath()!==actionPath)return;
   if(actionPath==='/friends')await refreshSocialFriendsAfterMutation();
   else if(actionPath==='/users/'+uid)await socialProfilePage(uid);
  }
 }catch(err){notice(err.message,true);}
 finally{if(target.isConnected)target.disabled=false;}
});

function syncSocialSearchRelationships(root,data){
 if(!root)return;
 const relationships=new Map();
 for(const [rows,state] of [[data.friends,'friends'],[data.outgoing,'outgoing'],[data.incoming,'incoming']])
  for(const u of rows)relationships.set(String(u.id),state);
 for(const row of root.querySelectorAll('#social-search-results [data-person-id]')){
  const id=row.dataset.personId,relationship=relationships.get(id)||'none';
  if(row.dataset.relationship===relationship)continue;
  const next=row.cloneNode(true);next.dataset.relationship=relationship;
  const identity=next.querySelector('.social-person-link');next.replaceChildren(identity);
  next.insertAdjacentHTML('beforeend',socialSearchAction({id,relationship}));
  patchOwnerNode(row,next);
 }
}
async function refreshSocialFriendsAfterMutation(){
 const root=app.querySelector('#page-view > main'),epoch=ownerSessionEpoch,marker=lastRenderToken;
 const data=await api('/api/friends');
 if(epoch!==ownerSessionEpoch||marker!==lastRenderToken||!root?.isConnected||currentPath()!=='/friends')return;
 let rendered;
 ownerPatchRoot=root;
 try{rendered=socialFriendsPage(marker,data);}finally{ownerPatchRoot=null;}
 await rendered;
 if(epoch===ownerSessionEpoch&&marker===lastRenderToken&&root.isConnected)renderedOwnerTab='/friends';
}
function inviteQrData(rows){
 if(!Array.isArray(rows)||!rows.length||rows.length>177||!rows.every(r=>typeof r==='string'&&r.length===rows.length&&/^[01]+$/.test(r)))throw new Error('Не удалось построить QR-код');
 const scale=10,canvas=document.createElement('canvas'),side=rows.length*scale,band=104;
 canvas.width=side;canvas.height=side+band;
 const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
 // Branding is outside the QR matrix and its four-module quiet zone.
 ctx.fillStyle='#f9e7a3';ctx.fillRect(0,0,side,band);
 ctx.textBaseline='middle';ctx.font='800 38px Unbounded, sans-serif';ctx.fillStyle='#27272b';ctx.fillText('шурш',24,band/2);
 ctx.fillStyle='#e58b67';ctx.fillText('!',24+ctx.measureText('шурш').width,band/2);
 const n=rows.length,center=(n-1)/2;
 const rounded=(x,y,w,h,r)=>{ctx.beginPath();ctx.moveTo(x+r,y);ctx.lineTo(x+w-r,y);ctx.quadraticCurveTo(x+w,y,x+w,y+r);ctx.lineTo(x+w,y+h-r);ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);ctx.lineTo(x+r,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-r);ctx.lineTo(x,y+r);ctx.quadraticCurveTo(x,y,x+r,y);ctx.closePath();ctx.fill();};
 const anchors=[[4,4],[n-11,4],[4,n-11]];
 const finder=(x,y)=>anchors.some(([a,b])=>x>=a&&x<a+7&&y>=b&&y<b+7);
 ctx.fillStyle='#000';
 rows.forEach((row,y)=>{for(let x=0;x<n;x++)if(row[x]==='1'&&!finder(x,y)){
  if(x===10||y===10){ctx.fillRect(x*scale,y*scale+band,scale,scale);continue;}
  // Connect touching modules and round only their exposed corners.
  const px=x*scale,py=y*scale+band,r=scale*.46,black=(a,b)=>rows[b]?.[a]==='1';
  const tl=black(x-1,y)||black(x,y-1)?0:r,tr=black(x+1,y)||black(x,y-1)?0:r,br=black(x+1,y)||black(x,y+1)?0:r,bl=black(x-1,y)||black(x,y+1)?0:r;
  ctx.beginPath();ctx.moveTo(px+tl,py);ctx.lineTo(px+scale-tr,py);ctx.quadraticCurveTo(px+scale,py,px+scale,py+tr);
  ctx.lineTo(px+scale,py+scale-br);ctx.quadraticCurveTo(px+scale,py+scale,px+scale-br,py+scale);
  ctx.lineTo(px+bl,py+scale);ctx.quadraticCurveTo(px,py+scale,px,py+scale-bl);
  ctx.lineTo(px,py+tl);ctx.quadraticCurveTo(px,py,px+tl,py);ctx.closePath();ctx.fill();
 }});
 for(const [x,y] of anchors){
  ctx.fillStyle='#000';rounded(x*scale,y*scale+band,7*scale,7*scale,scale*.45);
  ctx.fillStyle='#fff';rounded((x+1)*scale,(y+1)*scale+band,5*scale,5*scale,scale*.35);
  ctx.fillStyle='#000';rounded((x+2)*scale,(y+2)*scale+band,3*scale,3*scale,scale*.3);
 }
 const cx=(center+.5)*scale,cy=band+cx;
 ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(cx,cy,5.6*scale,0,Math.PI*2);ctx.fill();
 ctx.fillStyle='#e8dcf5';ctx.beginPath();ctx.arc(cx,cy,5.05*scale,0,Math.PI*2);ctx.fill();
 ctx.font='79px sans-serif';ctx.textAlign='center';ctx.fillText(currentUser?.avatar_emoji||'🎁',cx,cy+1);
 return canvas.toDataURL('image/png');
}
async function sharePersonalQr(){
 const image=modalRoot.querySelector('#personal-invite-qr');
 if(!image)return;
 const bytes=Uint8Array.from(atob(image.src.split(',')[1]),c=>c.charCodeAt(0));
 const file=new File([bytes],'shursh-invite.png',{type:'image/png'});
 if(navigator.share&&navigator.canShare?.({files:[file]})){
  try{await navigator.share({files:[file],title:'Шурш!'});return;}catch(e){if(e.name==='AbortError')return;}
 }
 if(navigator.clipboard?.write&&typeof ClipboardItem==='function'){
  try{await navigator.clipboard.write([new ClipboardItem({'image/png':file})]);notice('QR-код скопирован');return;}catch{}
 }
 await sharePersonalInvite();
}
// Brand marks rendered locally; no external image requests. Telegram and VK: Simple Icons.
// MAX filled speech-bubble mark from the publicly reproduced SVG (zaplata.ru/forum/scripts/skachat-gradient-fona-messendzhera-max); palette: go.max.ru/brandbook.
function inviteBrandIcon(brand){
 const paths={telegram:'M16.906 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z',vk:'M6.79 7.3H4.05c.13 6.24 3.25 9.99 8.72 9.99h.31v-3.57c2.01.2 3.53 1.67 4.14 3.57h2.84c-.78-2.84-2.83-4.41-4.11-5.01 1.28-.74 3.08-2.54 3.51-4.98h-2.58c-.56 1.98-2.22 3.78-3.8 3.95V7.3H10.5v6.92c-1.6-.4-3.62-2.34-3.71-6.92Z',max:'M508.211 878.328c-75.007 0-109.864-10.95-170.453-54.75-38.325 49.275-159.686 87.783-164.979 21.9 0-49.456-10.95-91.248-23.36-136.873-14.782-56.21-31.572-118.807-31.572-209.508 0-216.626 177.754-379.597 388.357-379.597 210.785 0 375.947 171.001 375.947 381.604.707 207.346-166.595 376.118-373.94 377.224m3.103-571.585c-102.564-5.292-182.499 65.7-200.201 177.024-14.6 92.162 11.315 204.398 33.397 210.238 10.585 2.555 37.23-18.98 53.837-35.587a189.8 189.8 0 0 0 92.71 33.032c106.273 5.112 197.08-75.794 204.215-181.95 4.154-106.382-77.67-196.486-183.958-202.574Z'};
 const views={telegram:'5 5 15 15',vk:'3 4 18 18',max:'100 100 800 800'};
 return '<svg aria-hidden="true" focusable="false" viewBox="'+views[brand]+'" fill="currentColor"><path fill-rule="evenodd" d="'+paths[brand]+'"/></svg>';
}
function inviteShareButtons(url,personal=false,code=''){
 const e=encodeURIComponent(url);
 return '<div class="personal-invite-social" role="group" aria-label="Поделиться приглашением">'+
 '<button class="btn btn-small" type="button" '+(personal?'id="personal-invite-link" data-invite-url="'+attr(url)+'" data-social-action="copy-personal-invite"':'data-action="copy" data-url="'+attr(url)+'"')+'>'+ico('copy')+' Ссылка</button>'+
 '<button class="btn btn-small" type="button" '+(personal?'data-social-action="share-personal-qr"':'data-social-action="santa-invite-qr" data-code="'+attr(code)+'"')+'>'+ico('qr')+' QR</button>'+
 '<a class="btn btn-small share-telegram" target="_blank" rel="noopener noreferrer" href="https://t.me/share/url?url='+e+'">'+inviteBrandIcon('telegram')+' Telegram</a>'+
 '<a class="btn btn-small share-vk" target="_blank" rel="noopener noreferrer" href="https://vk.com/share.php?url='+e+'">'+inviteBrandIcon('vk')+' VK</a>'+
 '<a class="btn btn-small share-max" target="_blank" rel="noopener noreferrer" href="https://max.ru/:share?text='+e+'">'+inviteBrandIcon('max')+' MAX</a></div>';
}
async function socialSantaInviteQr(code){
 const marker=lastRenderToken;
 if(isPreview){notice('QR доступен на сайте',true);return;}
 const data=await api('/api/invites/'+encodeURIComponent(code)+'/qr');
 if(marker!==lastRenderToken)return;
 modal({title:'Приглашение в игру',content:'<div class="personal-invite-card"><img id="personal-invite-qr" alt="QR-код приглашения в игру" src="'+attr(inviteQrData(data.qr))+'"></div>'});
 modalRoot.querySelector('.modal')?.classList.add('personal-invite-modal');
}
async function socialPersonalInviteModal(){
 if(!currentUser)return loginModal();
 const epoch=ownerSessionEpoch,marker=lastRenderToken;
 const data=await api('/api/friend-invites/me',{method:'POST',body:{}});
 if(epoch!==ownerSessionEpoch||marker!==lastRenderToken)return;
 const url=new URL(data.path,location.origin).href;
 if(url!==data.url)throw new Error('Адрес приглашения не совпадает с сайтом');
 modal({title:'Пригласить друга',content:'<div class="personal-invite-card"><img id="personal-invite-qr" alt="QR-код приглашения от '+attr(currentUser.name||'')+'" width="244" src="'+attr(inviteQrData(data.qr))+'"></div>'+inviteShareButtons(url,true),
 footer:'<div class="personal-invite-footer"><button class="text-link" type="button" data-social-action="revoke-personal-invite">Отозвать ссылку</button></div>'});
 modalRoot.querySelector('.modal')?.classList.add('personal-invite-modal');
}
async function copyPersonalInvite(){
 const button=modalRoot.querySelector('#personal-invite-link'),url=button?.dataset.inviteUrl;if(!url)return false;
 try{await navigator.clipboard.writeText(url);notice('Ссылка скопирована');return true;}catch{}
 const helper=document.createElement('textarea');helper.value=url;helper.setAttribute('readonly','');helper.style.cssText='position:fixed;top:0;left:0;opacity:0;width:1px;height:1px;pointer-events:none';
 modalRoot.append(helper);
 try{helper.select();if(document.execCommand('copy')){notice('Ссылка скопирована');return true;}}catch{}finally{helper.remove();button.focus({preventScroll:true});}
 notice('Не удалось скопировать ссылку',true);return false;
}
async function sharePersonalInvite(){
 const url=modalRoot.querySelector('#personal-invite-link')?.dataset.inviteUrl;if(!url)return;
 if(navigator.share){try{await navigator.share({title:'Шурш!',text:'Давай дружить в Шурш!',url});return;}catch(e){if(e.name==='AbortError')return;}}
 if(await copyPersonalInvite())notice('QR недоступен для отправки, ссылка скопирована');
}
async function socialFriendInvitePage(code,marker=lastRenderToken){
 const result=await api('/api/friend-invites/'+encodeURIComponent(code));
 if(marker!==lastRenderToken)return;
 const p=result.inviter,relation=result.relationship;
 let action='';
 if(relation==='guest')action='<div class="btn-row"><button class="btn btn-dark" data-open="register">Создать аккаунт</button><button class="btn btn-soft" data-open="login">Войти</button></div>';
 if(relation==='none'||relation==='incoming')action='<button class="btn btn-dark" data-social-action="invite-add" data-code="'+attr(code)+'">'+(relation==='incoming'?'Принять заявку':'Добавить в друзья')+'</button>';
 if(relation==='outgoing')action='<p class="note">Заявка уже отправлена</p>';
 if(relation==='friends')action='<p class="note">Вы уже друзья</p>';
 if(relation==='self')action='<p class="note">Это твоё приглашение</p>';
 shell('<main class="container page social-page"><section class="panel profile-main-card">'+socialAvatar(p,'profile-emoji')+
  '<h1>'+esc(p.name)+' приглашает тебя в Шурш!</h1>'+(p.handle?'<p class="profile-handle">@'+esc(p.handle)+'</p>':'')+
  '<p class="note">Делитесь желаниями и радуйте друг друга подарками</p>'+action+'</section></main>');
}
