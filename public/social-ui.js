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
  const data=await api('/api/notifications/unread');
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

const socialEmojiChoices=["🎁","🎄","🐱","🦊","🐻","🐼","🐸","🦄","🐰","🧸","✨","🌸","🌼","🌙","⭐","🎮","🎨","📚","🎵","🚀","☕","🍓","💚"];
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
 (p.handle?'<span class="profile-handle">@'+esc(p.handle)+'</span>':'')+
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
async function socialProfilePage(uid,marker=lastRenderToken){
 if(!currentUser){loginModal();return;}
 const data=await api('/api/users/'+encodeURIComponent(uid));if(marker!==lastRenderToken)return;
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
  (data.invites_enabled?'<section class="panel"><h2>Приглашённые друзья</h2><p class="note">'+Number(data.referral_count||0)+' подтверждённых регистраций по твоей ссылке</p>'+socialInviteButton()+'</section>':'')+
  '<section class="panel profile-security"><div><h2>Вход и безопасность</h2><p class="note">Почта не отображается в публичном профиле</p><div class="account-email">'+esc(p.email||'')+'</div></div>'+
  '<div class="profile-actions"><button class="btn btn-soft btn-small" data-social-action="change-email">Изменить почту</button>'+
  '<button class="btn btn-soft btn-small" data-social-action="change-password">Изменить пароль</button></div></section>'+
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
async function socialEditProfileModal(){
 const d=await api('/api/profile/me'),p=d.profile;
 const choices=socialEmojiChoices.map(emoji=>
  '<button type="button" class="emoji-choice'+(emoji===(p.avatar_emoji||'🎁')?' selected':'')+
  '" data-avatar-pick="'+attr(emoji)+'" aria-pressed="'+String(emoji===(p.avatar_emoji||'🎁'))+'">'+esc(emoji)+'</button>').join('');
 modal({title:'Редактировать профиль',subtitle:'Настрой, как тебя видят друзья',
  content:'<div class="field"><label>Твой аватар — только эмодзи</label><div class="emoji-grid" role="group" aria-label="Выбрать эмодзи">'+choices+'</div>'+
   '<input type="hidden" name="avatar_emoji" id="social-avatar-value" value="'+attr(p.avatar_emoji||'🎁')+'"></div>'+
   field('Имя','name','Как к тебе обращаться','text',p.name,true,'maxlength="40"')+
   (d.invites_enabled?field('Фамилия (необязательно)','last_name','Твоя фамилия','text',p.last_name||'',false,'maxlength="60" autocomplete="family-name"')+field('Отчество (необязательно)','patronymic','Твоё отчество','text',p.patronymic||'',false,'maxlength="60"')+shurshCheckbox('show_full_name','Показывать фамилию и отчество другим пользователям',p.show_full_name)+shurshCheckbox('allow_friend_invites','Разрешать приглашения даже при скрытом профиле',p.allow_friend_invites):'')+
   field('Никнейм (@)','handle','Например, shursh_friend','text',p.handle||'',false,'maxlength="20" autocomplete="username"')+
   field('Город (необязательно)','city','Например, Санкт-Петербург','text',p.city||'',false,'maxlength="60"')+
   textArea('О себе','bio','Что любишь, чем увлекаешься и что тебя радует',p.bio||'')+
   shurshCheckbox('discoverable','Показывать мой профиль в поиске',p.discoverable),
  submitLabel:'Сохранить профиль',onSubmit:async form=>{
   const data=readForm(form);data.discoverable=form.elements.discoverable.checked;
   if(d.invites_enabled){data.show_full_name=form.elements.show_full_name.checked;data.allow_friend_invites=form.elements.allow_friend_invites.checked;}
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
 const provenance=u.last_seen_source==='session'?'Последний известный вход по сессии; устройство не записано':'Последний зафиксированный визит';
 return '<div class="admin-user-identity">'+symbol+'<span><time title="'+attr(provenance)+'" datetime="'+attr(u.last_seen_at)+'">'+esc(socialAdminVisitDate(date))+'</time></span></div>';
}
function socialAdminUsersMarkup(page){
 const rows=(page.users||[]).map(u=>'<tr><td class="admin-user-cell"><a class="admin-user-identity admin-user-profile-link" href="/users/'+attr(u.id)+'" data-nav="/users/'+attr(u.id)+'" aria-label="Открыть профиль '+attr(u.name)+'"><span class="admin-user-emoji" aria-hidden="true">'+
   esc(u.avatar_emoji||'🎁')+'</span><span><strong>'+esc(u.name)+'</strong>'+
   '<small>ID: '+esc(String(u.id).slice(0,8))+'</small></span></a></td>'+
   '<td>'+(u.handle?'@'+esc(u.handle):'<span class="muted">—</span>')+'</td>'+
   '<td><time datetime="'+attr(u.created_at)+'">'+esc(new Date(u.created_at).toLocaleString('ru-RU',{dateStyle:'medium',timeStyle:'short'}))+'</time></td>'+
   '<td>'+socialAdminVisitMarkup(u)+'</td><td>'+Number(u.wishlists_count||0)+'</td><td>'+Number(u.organized_games||0)+'</td>'+
   '<td>'+Number(u.joined_games||0)+'</td><td>'+(u.discoverable?'Виден':'Скрыт')+'</td></tr>').join('');
 const from=page.total?Number(page.offset)+1:0;
 const to=Math.min(Number(page.offset)+Number(page.limit),Number(page.total));
 return '<div class="admin-users-table-scroll"><table class="admin-users-table"><thead><tr>'+
   '<th>Игрок</th><th>Ник</th><th>Регистрация</th><th>Последний визит</th><th>Вишлисты</th>'+
   '<th>Свои Санты</th><th>Участие</th><th>В поиске</th></tr></thead><tbody>'+
   (rows||'<tr><td colspan="8" class="muted">Игроки не найдены</td></tr>')+'</tbody></table></div>'+
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
 }catch(error){
  if(requestId===adminUsersRequestId&&root.isConnected)notice(error.message,true);
 }finally{
  if(requestId===adminUsersRequestId&&root.isConnected)root.removeAttribute('aria-busy');
 }
}
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
  '</div></main>');
}
async function socialAdminUsersPage(marker=lastRenderToken){
 if(!currentUser?.is_admin){errorView(new Error('Доступ только администратору'));return;}
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
 const picker=e.target.closest('[data-avatar-pick]');if(picker){e.preventDefault();const root=picker.closest('.emoji-grid');root?.querySelectorAll('[data-avatar-pick]').forEach(x=>{x.classList.toggle('selected',x===picker);x.setAttribute('aria-pressed',String(x===picker));});const input=modalRoot.querySelector('#social-avatar-value');if(input)input.value=picker.dataset.avatarPick;return;}
 const target=e.target.closest('[data-social-action]');if(!target)return;
 e.preventDefault();
 const action=target.dataset.socialAction,uid=target.dataset.userId,actionPath=currentPath();
 target.disabled=true;
 try{
  if(action==='personal-invite'){await socialPersonalInviteModal();return;}
  if(action==='enable-hidden-personal-invite'){await api('/api/profile/me',{method:'PATCH',body:{allow_friend_invites:true}});clearOwnerTabViews(['/profile']);await socialPersonalInviteModal();return;}
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
 ctx.fillStyle='#fffefa';ctx.beginPath();ctx.arc(side-52,band/2,35,0,Math.PI*2);ctx.fill();
 ctx.font='36px sans-serif';ctx.textAlign='center';ctx.fillText(currentUser?.avatar_emoji||'🎁',side-52,band/2+2);
 ctx.fillStyle='#000';rows.forEach((r,y)=>{for(let x=0;x<r.length;x++)if(r[x]==='1')ctx.fillRect(x*scale,y*scale+band,scale,scale);});
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
 modalRoot.querySelector('[download="shursh-invite.png"]')?.click();
}
async function socialPersonalInviteModal(){
 if(!currentUser)return loginModal();
 const epoch=ownerSessionEpoch,marker=lastRenderToken;
 let data;
 try{data=await api('/api/friend-invites/me',{method:'POST',body:{}});}
 catch(err){
  if(epoch!==ownerSessionEpoch||marker!==lastRenderToken)return;
  if(err.status!==403||err.message!=='Разреши приглашения в настройках профиля')throw err;
  modal({title:'Пригласить друга',content:'<p>Твой профиль скрыт из поиска. Можно создать личную ссылку: тебя увидят только те, кому она доступна</p><p class="note">Профиль останется скрытым из поиска. Приглашения можно отключить в настройках профиля или отозвать ссылку</p>',footer:'<div class="form-actions"><button type="button" class="btn btn-dark" data-social-action="enable-hidden-personal-invite">Создать ссылку</button></div>'});
  return;
 }
 if(epoch!==ownerSessionEpoch||marker!==lastRenderToken)return;
 const url=new URL(data.path,location.origin).href;
 if(url!==data.url)throw new Error('Адрес приглашения не совпадает с сайтом');
 const qr=inviteQrData(data.qr);
 modal({title:'Пригласить друга',content:
  '<div class="personal-invite-card">'+
  '<img id="personal-invite-qr" alt="QR-код приглашения от '+attr(currentUser.name||'')+'" width="208" src="'+attr(qr)+'">'+
  '<div class="personal-invite-download"><a class="btn btn-soft btn-small" download="shursh-invite.png" href="'+attr(qr)+'">Скачать QR</a><button class="btn btn-soft btn-small" type="button" data-social-action="share-personal-qr">Поделиться QR</button></div></div>'+
  '<div class="field"><label for="personal-invite-link">Твоя ссылка</label><div class="share-field invite-link-row"><input class="input" aria-label="Персональная ссылка" id="personal-invite-link" readonly value="'+attr(url)+'"><button class="btn btn-soft btn-small" type="button" data-social-action="copy-personal-invite" aria-label="Копировать ссылку">'+ico('copy')+'</button></div></div>'+
  '<div class="personal-invite-social"><a class="btn btn-soft btn-small" target="_blank" rel="noopener noreferrer" href="https://t.me/share/url?url='+encodeURIComponent(url)+'">Telegram</a>'+
  '<a class="btn btn-soft btn-small" target="_blank" rel="noopener noreferrer" href="https://vk.com/share.php?url='+encodeURIComponent(url)+'">VK</a></div>'+
  '<p class="note">Дружба только по согласию. Новая подтверждённая регистрация засчитывается один раз</p>',
  footer:'<div class="personal-invite-footer"><button class="text-link" type="button" data-social-action="revoke-personal-invite">Отозвать ссылку</button><button class="btn btn-dark" type="button" data-social-action="share-personal-invite">Поделиться ссылкой '+ico('arrow')+'</button></div>'});
 modalRoot.querySelector('.modal')?.classList.add('personal-invite-modal');
}
async function copyPersonalInvite(){
 const input=modalRoot.querySelector('#personal-invite-link');if(!input)return;
 try{await navigator.clipboard.writeText(input.value);notice('Ссылка скопирована');}
 catch{input.focus();input.select();notice('Скопируй выделенную ссылку');}
}
async function sharePersonalInvite(){
 const input=modalRoot.querySelector('#personal-invite-link');if(!input)return;
 if(navigator.share){try{await navigator.share({title:'Шурш!',text:'Давай дружить в Шурш!',url:input.value});return;}catch(e){if(e.name==='AbortError')return;}}
 await copyPersonalInvite();
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
