/* Santa wishlist cards and scoped chats. Uses existing Shursh UI functions. */
'use strict';
function gameWishCard(w,source='own'){
 const mine=source==='own';
 const image=w.image_data?'<img src="'+attr(w.image_data)+'" alt="'+attr(w.title)+'" loading="lazy" decoding="async">': '<div class="game-gift-placeholder">'+artFor(w)+'</div>';
 const actions=mine?'<div class="game-gift-overlay-actions"><button type="button" class="btn btn-soft" data-action="edit-game-gift" data-id="'+w.id+'" aria-label="Изменить подарок" title="Изменить">'+ico('edit')+'</button>'+
  '<button type="button" class="btn btn-soft" data-action="delete-game-gift" data-id="'+w.id+'" aria-label="Удалить подарок" title="Удалить">'+ico('trash')+'</button></div>':'';
 return '<article class="wish-card game-gift-card">'+
  '<button type="button" class="card-hitarea game-gift-primary" data-action="show-game-gift" data-id="'+w.id+'" data-source="'+source+'" aria-label="Подробнее о подарке '+attr(w.title)+'">'+
  '<div class="wish-image">'+image+'</div>'+
  '<div class="wish-content"><h3>'+esc(w.title)+'</h3></div></button>'+
  actions+'</article>';
}
function wishesMarkup(wishes,source='own'){
 if(!wishes?.length)return '<span class="muted note">Пока нет подарков. Добавь конкретные идеи и пожелания</span>';
 return '<div class="game-gifts-carousel"><div class="game-gifts-toolbar"><span class="note">'+
  ruCount(wishes.length,'подарок','подарка','подарков')+'</span>'+
  (wishes.length>1?'<div class="game-gifts-arrows" hidden><button class="btn btn-soft btn-small" type="button" data-action="scroll-game-gifts" data-direction="prev" aria-label="Предыдущие подарки">'+ico('back')+'</button><button class="btn btn-soft btn-small" type="button" data-action="scroll-game-gifts" data-direction="next" aria-label="Следующие подарки">'+ico('arrow')+'</button></div>':'')+
  '</div><div class="game-gifts-track" tabindex="0" role="region" aria-label="Подарки — горизонтальная лента">'+
  wishes.map(w=>gameWishCard(w,source)).join('')+'</div></div>';
}
const gameGiftDisposers=new Map();
function disposeGameGiftOverflow(){for(const dispose of gameGiftDisposers.values())dispose();gameGiftDisposers.clear();}
function setupGameGiftOverflow(root=document){
 for(const [track,dispose] of gameGiftDisposers)if(!track.isConnected){dispose();gameGiftDisposers.delete(track);}
 root.querySelectorAll('.game-gifts-carousel').forEach(carousel=>{
  const track=carousel.querySelector('.game-gifts-track'),arrows=carousel.querySelector('.game-gifts-arrows');
  if(!track||!arrows||gameGiftDisposers.has(track))return;
  const update=()=>{
   if(!track.isConnected){observer?.disconnect();return;}
   const max=Math.max(0,track.scrollWidth-track.clientWidth);
   arrows.hidden=max<=3;
   const back=arrows.querySelector('[data-direction="prev"]'),next=arrows.querySelector('[data-direction="next"]');
   if(back)back.disabled=max<=3||track.scrollLeft<=2;
   if(next)next.disabled=max<=3||track.scrollLeft>=max-2;
  };
  const observer=typeof ResizeObserver==='function'?new ResizeObserver(update):null;
  observer?.observe(track);
  for(const card of track.children)observer?.observe(card);
  track.addEventListener('scroll',update,{passive:true});
  gameGiftDisposers.set(track,()=>{observer?.disconnect();track.removeEventListener('scroll',update);});
  requestAnimationFrame(update);
  if(document.fonts?.ready)void document.fonts.ready.then(update);
 });
}
async function refreshGameOwnWishes(state){
 if(!state||activeGameContext!==state)return;
 const root=document.querySelector('.my-wishes-list');
 if(!root)return;
 const result=await api(state.base+(state.base.startsWith('/api/santas/')?'/my-wishes':'/wishes'));
 if(!root.isConnected||activeGameContext!==state)return;
 const wishes=result.wishes||[];
 const scrollY=window.scrollY,trackX=root.querySelector('.game-gifts-track')?.scrollLeft||0;
 state.own=wishes;
 if(!state.memberView&&loadedSanta?.event.id===state.event.id)loadedSanta.my_wishes=wishes;
 root.innerHTML=wishesMarkup(wishes);
 setupGameGiftOverflow(root);
 const track=root.querySelector('.game-gifts-track');if(track)track.scrollLeft=trackX;
 if(Math.abs(window.scrollY-scrollY)>1)window.scrollTo({top:scrollY,behavior:'instant'});
}
function gameGiftDetailImage(gift){
 return gift.image_data?'<img class="gift-dialog-image" src="'+attr(gift.image_data)+'" alt="'+attr(gift.title)+'" draggable="false">':
  '<div class="gift-dialog-fallback" role="img" aria-label="Фото подарка не добавлено">'+artFor(gift)+'</div>';
}
function showGameWishDetails(el){
 const state=activeGameContext;if(!state)return;
 const source=el.dataset.source==='recipient'?'recipient':'own';
 const gifts=(source==='recipient'?state.recipient:state.own)||[];
 let index=gifts.findIndex(w=>Number(w.id)===Number(el.dataset.id));
 if(index<0)return;
 const mine=source==='own',count=gifts.length,multiple=count>1;
 const wrap=i=>(i+count)%count;
 function preview(dir){
  const g=gifts[wrap(index+dir)],direction=dir<0?'prev':'next';
  return '<button type="button" class="gift-gallery-peek gift-gallery-'+direction+'" data-gallery-step="'+dir+'" aria-label="'+(dir<0?'Предыдущий подарок: ':'Следующий подарок: ')+attr(g.title)+'"><span class="gift-gallery-preview-art" aria-hidden="true">'+gameGiftDetailImage(g)+'</span><span class="gift-gallery-arrow">'+ico(dir<0?'back':'arrow')+'</span></button>';
 }
 function content(){
  const gift=gifts[index],image='<div class="gift-dialog-media">'+gameGiftDetailImage(gift)+'</div>';
  const media=multiple?'<div class="gift-gallery" role="region" aria-label="Галерея подарков">'+preview(-1)+image+preview(1)+'<p class="gift-gallery-count" aria-live="polite">'+(index+1)+' / '+count+'</p></div>':image;
  const description=gift.description?'<div class="gift-dialog-description"><strong>Комментарий</strong><p>'+esc(gift.description)+'</p></div>':'';
  const store=gift.shop_url?'<a class="btn btn-soft" href="'+attr(gift.shop_url)+'" target="_blank" rel="noopener noreferrer">В магазин '+ico('external')+'</a>':'';
  const edit=mine?'<button type="button" class="gift-dialog-edit" data-action="edit-game-gift" data-id="'+gift.id+'" aria-label="Изменить подарок" data-tooltip="Изменить">'+ico('edit',20)+'</button>':'';
  return (multiple?'':edit)+media+'<div class="gift-dialog-copy">'+(multiple?edit:'')+'<div class="gift-dialog-price">'+money(gift.price_cents,gift.currency)+'</div>'+description+store+'</div>';
 }
 modal({title:gifts[index].title,content:'<div class="gift-dialog-layout'+(multiple?' gift-gallery-layout':'')+'">'+content()+'</div>',footer:'<div class="gift-dialog-footer"><button type="button" class="btn btn-dark" data-close>Закрыть</button></div>'});
 const dialog=modalRoot.querySelector('.modal');if(!dialog)return;
 dialog.classList.add('gift-details-modal');if(!multiple)return;
 dialog.classList.add('gift-deck-modal');
 const layout=dialog.querySelector('.gift-dialog-layout');
 function step(dir){
  if(activeGameContext!==state||!dialog.isConnected||dialog.closest('[inert]'))return;
  const focusInside=layout.contains(document.activeElement);
  const focused=document.activeElement?.closest('[data-gallery-step]')?.dataset.galleryStep;
  index=wrap(index+dir);
  const gift=gifts[index];dialog.setAttribute('aria-label',gift.title);
  dialog.querySelector('.modal-fixed-header h2').textContent=gift.title;
  layout.innerHTML=content();
  if(focused)layout.querySelector('[data-gallery-step="'+focused+'"]')?.focus({preventScroll:true});
  else if(focusInside)dialog.focus({preventScroll:true});
  const deck=layout.querySelector('.gift-dialog-media');
  if(!motionReduced()&&deck?.animate)deck.animate([{opacity:.65,transform:'translateX('+(dir*12)+'px)'},{opacity:1,transform:'translateX(0)'}],{duration:180,easing:'ease-out'});
 }
 let suppressClickUntil=0;
 function swipe(dx,dy){if(Math.abs(dx)<=50||Math.abs(dx)<=Math.abs(dy)*1.7)return false;suppressClickUntil=Date.now()+350;step(dx<0?1:-1);return true;}
 dialog.addEventListener('click',e=>{const button=e.target.closest('[data-gallery-step]');if(button){e.preventDefault();if(e.detail>0&&Date.now()<suppressClickUntil)return;step(Number(button.dataset.galleryStep));}});
 dialog.tabIndex=-1;dialog.focus({preventScroll:true});
 dialog.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){if(e.target.matches('input,textarea,select,[contenteditable]'))return;e.preventDefault();step(e.key==='ArrowLeft'?-1:1);}});
 let touch=null;
 dialog.addEventListener('touchstart',e=>{
  touch=null;if(e.touches.length!==1||!e.target.closest('.gift-gallery'))return;
  const t=e.touches[0];touch={id:t.identifier,x:t.clientX,y:t.clientY};
 },{passive:true});
 dialog.addEventListener('touchcancel',()=>{touch=null;},{passive:true});
 dialog.addEventListener('touchend',e=>{
  const start=touch;touch=null;if(!start)return;
  const t=[...e.changedTouches].find(t=>t.identifier===start.id);if(!t)return;
  const dx=t.clientX-start.x,dy=t.clientY-start.y;
  swipe(dx,dy);
 },{passive:true});
 let drag=null;
 dialog.addEventListener('pointerdown',e=>{
  if(e.pointerType==='touch'||e.button!==0||!e.isPrimary||!e.target.closest('.gift-gallery'))return;
  drag={id:e.pointerId,x:e.clientX,y:e.clientY};
 });
 dialog.addEventListener('pointercancel',()=>{drag=null;});
 dialog.addEventListener('pointerup',e=>{
  if(!drag||e.pointerId!==drag.id)return;
  const start=drag;drag=null;swipe(e.clientX-start.x,e.clientY-start.y);
 });
 dialog.addEventListener('pointerleave',()=>{drag=null;});
 let wheelTime=0,wheelDelta=0,wheelStepped=false;
 dialog.addEventListener('wheel',e=>{
  if(!e.target.closest('.gift-gallery')||e.ctrlKey||Math.abs(e.deltaX)<=Math.abs(e.deltaY)*1.7)return;
  e.preventDefault();
  const now=Date.now();if(now-wheelTime>220){wheelDelta=0;wheelStepped=false;}wheelTime=now;
  if(wheelStepped)return;
  wheelDelta+=e.deltaX*(e.deltaMode===1?16:e.deltaMode===2?innerWidth:1);
  if(Math.abs(wheelDelta)>50){wheelStepped=true;step(wheelDelta>0?1:-1);}
 },{passive:false});
}
async function smallGamePhoto(file){
 return compressToWebp(file,{maxDimension:780,maxBytes:235000,maxSourceBytes:12000000});
}
function gameGiftModal(edit=null){
 const state=activeGameContext;if(!state)return;
 const gift=edit||{},isEdit=!!edit;
 const budget=gift.price_cents==null?'':String(gift.price_cents/100);
 modal({title:isEdit?'Редактировать желание':'Добавить желание',
   subtitle:'Как в обычном вишлисте: добавь ссылку, фотографию, цену и уточни, какие подарки подойдут',
   content:field('Ссылка на товар (необязательно)','shop_url','https://...','url',gift.shop_url||'')+
   '<p class="field-hint">Сохраним ссылку, а название, цену и фото можно указать самостоятельно</p>'+
   field('Что хочется?','title','Например, настольная игра','text',gift.title||'',true,'maxlength="130"')+
   textArea('Комментарий','description','Размер, цвет, модель, особенности',gift.description||'')+
   field('Ориентировочная цена','price','Например, 1500','number',budget,false,'min="0" step="0.01"')+
   '<div class="field"><label for="game-gift-photo">Фотография (необязательно)</label>'+
   '<div class="file-picker"><input id="game-gift-photo" name="image" type="file" accept="image/png,image/jpeg,image/webp">'+
   '<div class="field-hint">JPG, PNG или WEBP до 12 МБ. Сожмём в WebP до 235 КБ</div></div></div>'+
   (isEdit&&gift.image_data?'<label class="switch-label"><input type="checkbox" id="game-gift-remove-photo"> Удалить фотографию</label>':''),
   submitLabel:isEdit?'Сохранить':'Добавить желание',
   onSubmit:async form=>{
    const data=readForm(form);
    delete data.image;
    const file=form.querySelector('#game-gift-photo')?.files?.[0];
    if(file)data.image_data=await smallGamePhoto(file);
    else if(form.querySelector('#game-gift-remove-photo')?.checked)data.image_data=null;
    else if(!isEdit)data.image_data=null;
    const url=state.base+(state.base.startsWith('/api/santas/')?'/my-wishes':'/wishes')+(isEdit?'/'+gift.id:'');
    await api(url,{method:isEdit?'PATCH':'POST',body:data});
    notice(isEdit?'Подарок обновлён':'Подарок добавлен');
    await refreshGameOwnWishes(state);
   }});
 fixWishModalLayout();
  const desc=modalRoot.querySelector('#fld-description');if(desc)desc.maxLength=800;
}
function setupGameChat(state){
 const root=document.querySelector('#game-chat');if(!root)return;
 let room='general',displayedRoom=null,displayedRevision=-1,disposed=false,delay=15000;
 const controller=new AbortController(),rooms=new Map(),inflight=new Map();
 const list=root.querySelector('.game-chat-messages'),tabs=[...root.querySelectorAll('[data-chat-room]')];
 const alive=()=>!disposed&&root.isConnected&&activeGameContext===state;
 const syncRoomTabs=()=>{for(const tab of tabs)setAttrIfChanged(tab,'aria-pressed',String(tab.dataset.chatRoom===room));};
 const markup=m=>'<div class="chat-message '+(m.mine?'chat-mine':'')+'" data-message-id="'+attr(m.id)+'"><div class="chat-meta">'+esc(m.author)+'</div><p>'+esc(m.message)+'</p></div>';
 const entryFor=name=>rooms.get(name);
 function merge(name,records,meta={}){
  const before=entryFor(name)||{messages:[],hasOlder:false,fetchedAt:0,revision:0};
  const merged=new Map(before.messages.map(m=>[m.id,m]));
  let changed=meta.hasOlder!==undefined&&meta.hasOlder!==before.hasOlder;
  for(const m of records){const previous=merged.get(m.id);if(!previous||previous.author!==m.author||previous.message!==m.message||previous.mine!==m.mine){merged.set(m.id,m);changed=true;}}
  const entry={...before,...meta,revision:before.revision+(changed?1:0),messages:changed?[...merged.values()].sort((a,b)=>a.id-b.id):before.messages};
  rooms.set(name,entry);return entry;
 }
 function showRoom(name,{bottom=false,prepend=false}={}){
  if(!alive()||name!==room)return;
  const entry=entryFor(name),same=displayedRoom===name;
  const top=list.scrollTop,oldHeight=list.scrollHeight,nearBottom=oldHeight-top-list.clientHeight<48;
  const revision=entry?.revision??-1;
  if(same&&displayedRevision===revision){if(bottom)list.scrollTop=list.scrollHeight;return;}
  if(!same||!entry||!list.querySelector('[data-message-id]')){
   list.innerHTML=entry?
    (entry.hasOlder?'<button type="button" class="btn btn-soft btn-small" data-chat-older>Ранее</button>':'')+
    (entry.messages.length?entry.messages.map(markup).join(''):'<p class="note">Сообщений пока нет. Начни разговор!</p>'):
    '<div class="chat-loading" role="status"><span class="skeleton-bar"></span><span class="skeleton-bar"></span></div>';
  }else{
   // Existing messages keep identity. Only build elements for new/changed IDs.
   let older=list.querySelector('[data-chat-older]');
   if(entry.hasOlder&&!older){older=document.createElement('button');older.type='button';older.className='btn btn-soft btn-small';older.dataset.chatOlder='';older.textContent='Ранее';list.prepend(older);}
   else if(!entry.hasOlder&&older){older.remove();older=null;}
   const existing=new Map([...list.querySelectorAll('[data-message-id]')].map(n=>[n.dataset.messageId,n]));
   let cursor=older?older.nextSibling:list.firstChild;
   for(const m of entry.messages){
    const key=String(m.id);let node=existing.get(key);existing.delete(key);
    if(!node){const template=document.createElement('template');template.innerHTML=markup(m);node=template.content.firstElementChild;}
    else{
     const author=node.querySelector('.chat-meta'),body=node.querySelector('p');
     if(author.textContent!==m.author)author.textContent=m.author;
     if(body.textContent!==m.message)body.textContent=m.message;
     if(node.classList.contains('chat-mine')!==!!m.mine)node.classList.toggle('chat-mine',!!m.mine);
    }
    if(node!==cursor)list.insertBefore(node,cursor);
    cursor=node.nextSibling;
   }
   for(const node of existing.values())node.remove();
  }
  displayedRoom=name;displayedRevision=revision;
  if(entry){
   if(prepend&&same)list.scrollTop=top+list.scrollHeight-oldHeight;
   else if(bottom||!same||nearBottom)list.scrollTop=list.scrollHeight;
  }
 }
 function schedule(){
  if(!alive())return;
  clearTimeout(gameChatTimer);gameChatTimer=null;
  if(!document.hidden)gameChatTimer=setTimeout(async()=>{await load({force:true});schedule();},delay);
 }
 function load({force=false,older=false}={}){
  if(!alive())return Promise.resolve();
  const name=room,existing=entryFor(name);
  if(!force&&!older&&existing&&Date.now()-existing.fetchedAt<12000)return Promise.resolve();
  if(older&&!existing?.hasOlder)return Promise.resolve();
  // An older-page request is not equivalent to a delta poll. Keep one
  // in-flight request per room AND direction, then merge by message ID.
  const requestKey=name+(older?':older':':new');
  if(inflight.has(requestKey))return inflight.get(requestKey);
  const request=(async()=>{
   try{
    const cursor=older?existing?.messages[0]?.id:existing?.cursor;
    const suffix=!isPreview&&cursor?'?'+(older?'before':'after')+'='+cursor:'';
    const result=await api(state.base+'/messages/'+name+suffix,{signal:controller.signal});
    if(!alive()||result.room!==name)return;
    const records=Array.isArray(result.messages)?result.messages:[];
    const latest=entryFor(name);
    const initial=!existing||!suffix;
    const oldCursor=latest?.cursor||0;
    const meta=older?{hasOlder:!!result.has_more}:{
     fetchedAt:Date.now(),cursor:Math.max(oldCursor,...records.map(m=>m.id),0),
     ...(initial?{hasOlder:!!result.has_more}:{}),moreNew:!initial&&!!result.has_more};
    merge(name,records,meta);
    if(name===room){
     showRoom(name,{prepend:older});
     if(!older)delay=records.length?15000:Math.min(60000,delay*2);
    }
   }catch(err){
    if(!alive()||err.name==='AbortError')return;
    delay=Math.min(60000,delay*2);
    if(room===name&&!entryFor(name)){list.innerHTML='<p class="note">Не удалось загрузить сообщения</p><button type="button" class="btn btn-soft btn-small" data-chat-refresh>Повторить</button>';}
   }
  })();
  inflight.set(requestKey,request);
  void request.finally(()=>{
   if(inflight.get(requestKey)===request)inflight.delete(requestKey);
   if(!older&&alive()&&room===name&&entryFor(name)?.moreNew){entryFor(name).moreNew=false;void load({force:true});}
  });
  return request;
 }
 const visibility=()=>{if(!alive())return;if(document.hidden){clearTimeout(gameChatTimer);gameChatTimer=null;}else{delay=15000;void load({force:true}).finally(schedule);}};
 document.addEventListener('visibilitychange',visibility);
 gameLifecycleCleanup.push(()=>{disposed=true;controller.abort();document.removeEventListener('visibilitychange',visibility);rooms.clear();inflight.clear();});
 root.addEventListener('click',ev=>{
  const tab=ev.target.closest('[data-chat-room]');
  if(tab&&tabs.includes(tab)){
   const next=tab.dataset.chatRoom;if(next===room)return;
   room=next;delay=15000;syncRoomTabs();showRoom(room);void load().finally(schedule);
  }
  if(ev.target.closest('[data-chat-refresh]'))void load({force:true}).finally(schedule);
  if(ev.target.closest('[data-chat-older]'))void load({older:true});
 });
 root.querySelector('#game-chat-form').addEventListener('submit',async ev=>{
  ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('button'),data=readForm(form);
  if(!data.message?.trim())return;
  const name=room;button.disabled=true;
  try{
   const sent=await api(state.base+'/messages/'+name,{method:'POST',body:data,signal:controller.signal});
   if(!alive())return;
   form.reset();
   if(sent.message){
    // Do not advance the polling cursor on a local acknowledgement: a
    // concurrent message could have arrived between the GET and POST.
    merge(name,[sent.message]);
    if(room===name)showRoom(name,{bottom:true});
   }
   delay=15000;schedule();
  }catch(err){if(alive()&&err.name!=='AbortError')notice(err.message,true);}
  finally{button.disabled=false;}
 });
 syncRoomTabs();showRoom(room);void load().finally(schedule);
}

/* Small read-only poll: update the roster without reloading game details or
   fetching the private wishlist/image payload. All access is server-checked. */
function santaRosterPerson(p,state){
 const organizer=!!p.is_organizer||(!state.memberView&&p.user_id===state.currentUserId);
 const mine=state.memberView&&p.id===state.memberId;
 const adminActions=!state.memberView&&state.event.status==='open'&&!organizer;
 const profile=!!currentUser&&!!p.user_id;
 return '<div class="person-row" data-person-id="'+attr(p.id)+'"'+(profile?' data-santa-profile="'+attr(p.user_id)+'" role="link" tabindex="0" aria-label="Открыть профиль участника '+attr(p.name)+'"':'')+'><div class="avatar">'+esc(p.name.slice(0,1).toUpperCase())+
  '</div><div class="person-main"><div class="person-topline"><strong class="person-name">'+esc(p.name)+'</strong>'+
  (mine?'<span class="chip">Ты</span>':'')+
  (organizer?'<span class="chip chip-peach organizer-label">Организатор</span>':'')+'</div><small>'+
  ruCount(p.wish_count,'желание','желания','желаний')+'</small></div>'+
  (adminActions?'<div class="person-actions"><button type="button" class="btn btn-soft btn-small" aria-label="Выдать новую личную ссылку" data-tooltip="Выдать новую личную ссылку" data-action="new-player-link" data-id="'+p.id+'">'+ico('link')+'</button>'+
  '<button type="button" class="btn btn-soft btn-small" aria-label="Убрать участника" data-tooltip="Убрать участника" data-action="remove-player" data-id="'+p.id+'">'+ico('trash')+'</button></div>':'')+
  '</div>';
}
function setupSantaRoster(state){
 const root=document.querySelector('[data-santa-roster]');if(!root)return;
 if(gameRosterTimer){clearTimeout(gameRosterTimer);gameRosterTimer=null;}
 const route=state.base+'/roster',controller=new AbortController();
 // Detail and polling projections encode organizer differently. Compare the
 // visible semantics, not the presence of an optional field.
 const rosterSignature=people=>JSON.stringify(people.map(p=>[
  p.id,p.name,p.wish_count,!!p.is_organizer||(!state.memberView&&p.user_id===state.currentUserId),p.user_id??null
 ]));
 let disposed=false,delay=15000,running=false,previous=rosterSignature(state.participants||[]),failures=0;
 const update=async()=>{
  if(disposed||!root.isConnected)return;
  if(document.visibilityState==='hidden'||running)return;
  running=true;
  try{
   const info=await api(route,{signal:controller.signal});
   if(disposed||!root.isConnected||activeGameContext!==state)return;
   failures=0;
   if(info.status!==state.event.status){
    if(state.base.startsWith('/api/santas/'))dropOwnerRead(state.base);
    await render();
    return;
   }
   const signature=rosterSignature(info.participants);
   if(signature===previous){delay=Math.min(60000,delay*2);return;}
   delay=15000;previous=signature;
   const next=root.cloneNode(false);next.innerHTML=info.participants.map(p=>santaRosterPerson(p,state)).join('');patchOwnerNode(root,next);
   document.querySelectorAll('[data-santa-roster-count], [data-santa-event-count]').forEach(node=>{
    node.textContent=String(info.participants.length);
   });
   // An organizer who opened the page alone must be able to draw as soon
   // as the third participant arrives, without refreshing the page.
   const draw=document.querySelector('button[data-action="draw"]');
   if(draw&&info.status==='open')draw.disabled=info.participants.length<3;
   if(!state.memberView&&loadedSanta)loadedSanta.participants=info.participants;
  }catch(err){
   if(disposed||err.name==='AbortError')return;
   failures++;delay=Math.min(60000,delay*2);
   // Polling failure never hides the existing list. Manual actions still work.
   if(failures===3)console.warn('Santa roster refresh unavailable');
  }finally{running=false;}
 };
 const schedule=()=>{if(disposed||!root.isConnected)return;clearTimeout(gameRosterTimer);gameRosterTimer=null;if(!document.hidden)gameRosterTimer=setTimeout(async()=>{await update();schedule();},delay);};
 const visibility=()=>{if(disposed)return;if(document.hidden){clearTimeout(gameRosterTimer);gameRosterTimer=null;}else{delay=15000;void update().finally(schedule);}};
 document.addEventListener('visibilitychange',visibility);
 gameLifecycleCleanup.push(()=>{disposed=true;controller.abort();document.removeEventListener('visibilitychange',visibility);});
 schedule();
}

document.addEventListener('click',event=>{const row=event.target.closest('[data-santa-profile]');if(!row||event.target.closest('button,a,input,select,textarea'))return;event.preventDefault();nav('/users/'+row.dataset.santaProfile);});
document.addEventListener('keydown',event=>{if((event.key!=='Enter'&&event.key!==' ')||!event.target.matches('[data-santa-profile]'))return;event.preventDefault();nav('/users/'+event.target.dataset.santaProfile);});
