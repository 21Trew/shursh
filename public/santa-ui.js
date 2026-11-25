/* Santa wishlist cards and scoped chats. Uses existing Shursh UI functions. */
'use strict';
function gameWishCard(w,source='own'){
 const mine=source==='own';
 const image=w.image_data?'<img src="'+attr(w.image_data)+'" alt="'+attr(w.title)+'" loading="lazy" decoding="async">': '<div class="game-gift-placeholder">'+fallbackArt('gift')+'</div>';
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
function setupGameGiftOverflow(root=document){
 root.querySelectorAll('.game-gifts-carousel').forEach(carousel=>{
  const track=carousel.querySelector('.game-gifts-track'),arrows=carousel.querySelector('.game-gifts-arrows');
  if(!track||!arrows)return;
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
function showGameWishDetails(el){
 const state=activeGameContext;if(!state)return;
 const source=el.dataset.source||'own';
 const gift=(source==='recipient'?state.recipient:state.own)?.find(w=>Number(w.id)===Number(el.dataset.id));
 if(!gift)return;
 const mine=source!=='recipient';
 const image=gift.image_data?'<img class="gift-dialog-image" src="'+attr(gift.image_data)+'" alt="'+attr(gift.title)+'">':
   '<div class="gift-dialog-fallback" role="img" aria-label="Фото подарка не добавлено">'+fallbackArt('gift')+'</div>';
 const description=gift.description?'<div class="gift-dialog-description"><strong>Комментарий</strong><p>'+esc(gift.description)+'</p></div>':'';
 const store=gift.shop_url?'<a class="btn btn-soft" href="'+attr(gift.shop_url)+'" target="_blank" rel="noopener noreferrer">В магазин '+ico('external')+'</a>':'';
 const footer='<button type="button" class="btn btn-dark" data-close>Закрыть</button>';
 const edit=mine?'<button type="button" class="gift-dialog-edit" data-action="edit-game-gift" data-id="'+gift.id+'" aria-label="Изменить подарок" data-tooltip="Изменить">'+ico('edit',20)+'</button>':'';
 modal({title:gift.title,content:'<div class="gift-dialog-layout">'+edit+'<div class="gift-dialog-media">'+image+'</div>'+
  '<div class="gift-dialog-copy"><div class="gift-dialog-price">'+money(gift.price_cents,gift.currency)+'</div>'+
  description+store+'</div></div>',
  footer:'<div class="gift-dialog-footer">'+footer+'</div>'});
 modalRoot.querySelector('.modal')?.classList.add('gift-details-modal');
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
 if(gameChatTimer){clearInterval(gameChatTimer);gameChatTimer=null;}
 let room='general',renderedKey='';
 const tabs=Array.from(root.querySelectorAll('button[data-chat-room]'));
 // The room is the sole selection state. Never use hover or a second
 // active class as an independent indicator of the visible conversation.
 const syncRoomTabs=()=>{
  for(const tab of tabs){
   const pressed=String(tab.dataset.chatRoom===room);
   if(tab.getAttribute('aria-pressed')!==pressed)tab.setAttribute('aria-pressed',pressed);
  }
 };
 const roomCache=new Map(),inflight=new Map();
 const list=root.querySelector('.game-chat-messages');
 const markup=m=>'<div class="chat-message '+(m.mine?'chat-mine':'')+'"><div class="chat-meta">'+
   esc(m.author)+'</div><p>'+esc(m.message)+'</p></div>';
 const showRoom=(name)=>{
  const entry=roomCache.get(name);
  const key=name+':'+(entry?.signature||'pending');
  if(renderedKey===key)return;
  renderedKey=key;
  list.innerHTML=entry?(entry.messages.length?entry.messages.map(markup).join(''):
   '<p class="note">Сообщений пока нет. Начни разговор!</p>'):
   '<div class="chat-loading" role="status"><span class="skeleton-bar"></span><span class="skeleton-bar"></span></div>';
  if(entry)list.scrollTop=list.scrollHeight;
 };
 const load=({force=false}={})=>{
  if(!root.isConnected)return Promise.resolve();
  const requestedRoom=room,existing=roomCache.get(requestedRoom);
  // Room switching must never wait for a different room's slow request.
  // A warm room reopens synchronously from its own memory snapshot.
  if(!force&&existing&&Date.now()-existing.fetchedAt<12000)return Promise.resolve();
  if(inflight.has(requestedRoom))return inflight.get(requestedRoom);
  const request=(async()=>{
   try{
    const result=await api(state.base+'/messages/'+requestedRoom);
    if(!root.isConnected||result.room!==requestedRoom)return;
    const messages=Array.isArray(result.messages)?result.messages:[];
    const signature=JSON.stringify(messages.map(m=>[m.id,m.author,m.message,m.mine]));
    roomCache.set(requestedRoom,{messages,signature,fetchedAt:Date.now()});
    if(room===requestedRoom)showRoom(room);
   }catch(err){
    if(root.isConnected&&room===requestedRoom&&!roomCache.has(requestedRoom)){
     list.innerHTML='<p class="note">Не удалось загрузить сообщения. Попробуй обновить чат</p>';
     notice(err.message,true);
    }
   }
  })();
  inflight.set(requestedRoom,request);
  void request.finally(()=>{if(inflight.get(requestedRoom)===request)inflight.delete(requestedRoom);});
  return request;
 };
 root.addEventListener('click',ev=>{
  const tab=ev.target.closest('[data-chat-room]');
  if(tab&&tabs.includes(tab)){
   const next=tab.dataset.chatRoom;
   if(next===room)return;
   room=next;
   syncRoomTabs();
   showRoom(room);void load();
  }
  if(ev.target.closest('[data-chat-refresh]'))void load({force:true});
 });
 root.querySelector('#game-chat-form').addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.currentTarget,button=form.querySelector('button'),data=readForm(form);
  if(!data.message?.trim())return;
  const targetRoom=room;
  button.disabled=true;
  try{
   const sent=await api(state.base+'/messages/'+targetRoom,{method:'POST',body:data});
   form.reset();
   if(root.isConnected&&sent.message){
    const before=roomCache.get(targetRoom)?.messages||[];
    if(!before.some(m=>m.id===sent.message.id)){
     const messages=[...before,sent.message].slice(-60);
     roomCache.set(targetRoom,{messages,signature:JSON.stringify(messages.map(m=>[m.id,m.author,m.message,m.mine])),fetchedAt:Date.now()});
    }
    if(room===targetRoom)showRoom(room);
   }else if(root.isConnected)void load({force:true});
  }catch(err){notice(err.message,true)}
  finally{button.disabled=false;}
 });
 syncRoomTabs();showRoom(room);void load();
 gameChatTimer=setInterval(()=>{
  if(!root.isConnected){clearInterval(gameChatTimer);gameChatTimer=null;return;}
  if(document.visibilityState==='visible')void load({force:true});
 },15000);
}

/* Small read-only poll: update the roster without reloading game details or
   fetching the private wishlist/image payload. All access is server-checked. */
function santaRosterPerson(p,state){
 const organizer=!!p.is_organizer||(!state.memberView&&p.user_id===state.currentUserId);
 const mine=state.memberView&&p.id===state.memberId;
 const adminActions=!state.memberView&&state.event.status==='open'&&!organizer;
 const profile=!!currentUser&&!!p.user_id;
 return '<div class="person-row"'+(profile?' data-santa-profile="'+attr(p.user_id)+'" role="link" tabindex="0" aria-label="Открыть профиль участника '+attr(p.name)+'"':'')+'><div class="avatar">'+esc(p.name.slice(0,1).toUpperCase())+
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
 if(gameRosterTimer){clearInterval(gameRosterTimer);gameRosterTimer=null;}
 const route=state.base+'/roster';
 let running=false,previous=JSON.stringify((state.participants||[]).map(p=>[p.id,p.name,p.wish_count,p.is_organizer,p.user_id])),failures=0;
 const update=async()=>{
  if(!root.isConnected){clearInterval(gameRosterTimer);gameRosterTimer=null;return;}
  if(document.visibilityState==='hidden'||running)return;
  running=true;
  try{
   const info=await api(route);
   if(!root.isConnected||activeGameContext!==state)return;
   failures=0;
   if(info.status!==state.event.status){
    if(state.base.startsWith('/api/santas/'))ownerDataCache.delete(state.base);
    await render();
    return;
   }
   const signature=JSON.stringify(info.participants.map(p=>[p.id,p.name,p.wish_count,p.is_organizer,p.user_id]));
   if(signature===previous)return;
   previous=signature;
   root.innerHTML=info.participants.map(p=>santaRosterPerson(p,state)).join('');
   document.querySelectorAll('[data-santa-roster-count], [data-santa-event-count]').forEach(node=>{
    node.textContent=String(info.participants.length);
   });
   // An organizer who opened the page alone must be able to draw as soon
   // as the third participant arrives, without refreshing the page.
   const draw=document.querySelector('button[data-action="draw"]');
   if(draw&&info.status==='open')draw.disabled=info.participants.length<3;
   if(!state.memberView&&loadedSanta)loadedSanta.participants=info.participants;
  }catch(err){
   failures++;
   // Polling failure never hides the existing list. Manual actions still work.
   if(failures===3)console.warn('Santa roster refresh unavailable');
  }finally{running=false;}
 };
 gameRosterTimer=setInterval(update,15000);
}

document.addEventListener('click',event=>{const row=event.target.closest('[data-santa-profile]');if(!row||event.target.closest('button,a,input,select,textarea'))return;event.preventDefault();nav('/users/'+row.dataset.santaProfile);});
document.addEventListener('keydown',event=>{if((event.key!=='Enter'&&event.key!==' ')||!event.target.matches('[data-santa-profile]'))return;event.preventDefault();nav('/users/'+event.target.dataset.santaProfile);});
