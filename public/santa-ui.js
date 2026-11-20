/* Santa wishlist cards and scoped chats. Uses existing Shursh UI functions. */
'use strict';
function gameWishCard(w,source='own'){
 const mine=source==='own';
 const image=w.image_data?'<img src="'+attr(w.image_data)+'" alt="'+attr(w.title)+'" loading="lazy" decoding="async">':artFor(w);
 const detail=w.description||'Нажми, чтобы посмотреть детали';
 return '<article class="wish-card game-gift-card">'+
  '<button type="button" class="card-hitarea" data-action="show-game-gift" data-id="'+w.id+'" data-source="'+source+'" aria-label="Посмотреть подарок '+attr(w.title)+'"></button>'+
  '<div class="wish-image">'+image+'</div><div class="wish-content"><h3>'+esc(w.title)+'</h3>'+
  '<p class="wish-desc">'+esc(detail)+'</p><div class="wish-card-footer"><div class="wish-price">'+
  money(w.price_cents,w.currency)+'</div>'+(mine?'<div class="wish-controls"><button type="button" class="btn btn-soft" data-action="edit-game-gift" data-id="'+w.id+'" aria-label="Изменить подарок" title="Изменить подарок">'+ico('edit')+'</button><button type="button" class="btn btn-soft" data-action="delete-game-gift" data-id="'+w.id+'" aria-label="Удалить подарок" title="Удалить подарок">'+ico('trash')+'</button></div>':'')+'</div>'+
  (w.shop_url?'<a href="'+attr(w.shop_url)+'" target="_blank" rel="noopener noreferrer" class="text-link game-gift-store">В магазин '+ico('external')+'</a>':'')+
  '</div></article>';
}
function wishesMarkup(wishes,source='own'){
 if(!wishes?.length)return '<span class="muted note">Пока нет подарков. Добавь конкретные идеи и пожелания</span>';
 return '<div class="game-gifts-carousel"><div class="game-gifts-toolbar"><span class="note">'+
  wishes.length+' '+plural(wishes.length,'подарок','подарка','подарков')+'</span>'+
  (wishes.length>1?'<div class="game-gifts-arrows"><button class="btn btn-soft btn-small" type="button" data-action="scroll-game-gifts" data-direction="prev" aria-label="Предыдущие подарки">'+ico('back')+'</button><button class="btn btn-soft btn-small" type="button" data-action="scroll-game-gifts" data-direction="next" aria-label="Следующие подарки">'+ico('arrow')+'</button></div>':'')+
  '</div><div class="game-gifts-track" tabindex="0" role="region" aria-label="Подарки — горизонтальная лента">'+
  wishes.map(w=>gameWishCard(w,source)).join('')+'</div></div>';
}
function showGameWishDetails(el){
 const state=activeGameContext;if(!state)return;
 const gift=(el.dataset.source==='recipient'?state.recipient:state.own)?.find(w=>Number(w.id)===Number(el.dataset.id));
 if(!gift)return;
 const own=el.dataset.source!=='recipient';
 const image=gift.image_data?'<img class="wish-detail-image" src="'+attr(gift.image_data)+'" alt="'+attr(gift.title)+'">':
   '<div class="wish-detail-art">'+artFor(gift)+'</div>';
 const details=(label,value)=>value?'<div class="game-gift-note"><strong>'+label+'</strong><p>'+esc(value)+'</p></div>':'';
 const store=gift.shop_url?'<a class="btn btn-soft" href="'+attr(gift.shop_url)+'" target="_blank" rel="noopener noreferrer">В магазин '+ico('external')+'</a>':'';
 const actions=own?'<button class="btn btn-soft" data-action="edit-game-gift" data-id="'+gift.id+'">'+ico('edit')+' Изменить</button>':'';
 modal({title:gift.title,subtitle:money(gift.price_cents,gift.currency),
   content:'<div class="wish-detail">'+image+details('Описание',gift.description)+
     
     '<div class="wish-detail-actions">'+store+actions+'</div></div>'});
}
async function smallGamePhoto(file){
 if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Нужно фото JPG, PNG или WEBP');
 if(file.size>10_000_000)throw new Error('Исходное фото слишком большое (максимум 10 МБ)');
 const image=await createImageBitmap(file);
 const canvas=document.createElement('canvas');
 let ratio=Math.min(1,700/Math.max(image.width,image.height));
 for(let step=0;step<6;step++){
  canvas.width=Math.max(1,Math.round(image.width*ratio));
  canvas.height=Math.max(1,Math.round(image.height*ratio));
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(image,0,0,canvas.width,canvas.height);
  const result=canvas.toDataURL('image/jpeg',.72);
  if(result.length<335000){image.close?.();return result;}
  ratio*=.7;
 }
 image.close?.();throw new Error('Фото не удалось уменьшить до 250 КБ');
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
   '<div class="form-grid">'+
   field('Ориентировочная цена','price','Например, 1500','number',budget,false,'min="0" step="0.01"')+
   selectField('Валюта','currency',[['RUB','₽ Рубли'],['EUR','€ Евро'],['USD','$ Доллары']],gift.currency||'RUB')+'</div>'+
   '<div class="field"><label for="game-gift-photo">Фотография (необязательно)</label>'+
   '<div class="file-picker"><input id="game-gift-photo" name="image" type="file" accept="image/png,image/jpeg,image/webp">'+
   '<div class="field-hint">JPG, PNG или WEBP до 10 МБ. Фото сожмём до 250 КБ</div></div></div>'+
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
    await render();
   }});
 const desc=modalRoot.querySelector('#fld-description');if(desc)desc.maxLength=800;
}
function setupGameChat(state){
 const root=document.querySelector('#game-chat');if(!root)return;
 if(gameChatTimer){clearInterval(gameChatTimer);gameChatTimer=null;}
 let room='general',loading=false,pendingRefresh=false,lastContent='',messages=[];
 const list=root.querySelector('.game-chat-messages');
 const apiRoom=()=>state.base+'/messages/'+room;
 const markup=m=>'<div class="chat-message '+(m.mine?'chat-mine':'')+'"><div class="chat-meta">'+
   esc(m.author)+'</div><p>'+esc(m.message)+'</p></div>';
 const paint=()=>{
  list.innerHTML=messages.length?messages.map(markup).join(''):'<p class="note">Сообщений пока нет. Начни разговор!</p>';
  list.scrollTop=list.scrollHeight;
 };
 const load=async()=>{
  if(!root.isConnected)return;
  if(loading){pendingRefresh=true;return;}
  loading=true;const requestedRoom=room;
  try{
   const result=await api(apiRoom());
   if(!root.isConnected||requestedRoom!==room||room!==result.room)return;
   const signature=JSON.stringify(result.messages.map(m=>m.id));
   if(signature!==lastContent){messages=result.messages;lastContent=signature;paint();}
  }catch(err){
   if(root.isConnected&&requestedRoom===room)notice(err.message,true);
  }finally{
   loading=false;
   if(pendingRefresh&&root.isConnected){pendingRefresh=false;load();}
  }
 };
 root.addEventListener('click',ev=>{
  const tab=ev.target.closest('[data-chat-room]');
  if(tab){
   room=tab.dataset.chatRoom;lastContent='';messages=[];
   root.querySelectorAll('[data-chat-room]').forEach(b=>{
    const selected=b===tab;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));
   });
   list.innerHTML='<p class="note">Загружаем сообщения…</p>';load();
  }
  if(ev.target.closest('[data-chat-refresh]'))load();
 });
 root.querySelector('#game-chat-form').addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.currentTarget,button=form.querySelector('button'),data=readForm(form);
  if(!data.message?.trim())return;
  const targetRoom=room;
  button.disabled=true;
  try{
   const sent=await api(apiRoom(),{method:'POST',body:data});
   form.reset();
   if(root.isConnected&&room===targetRoom&&sent.message){
    if(!messages.some(m=>m.id===sent.message.id)){
     messages=[...messages,sent.message].slice(-60);
     lastContent=JSON.stringify(messages.map(m=>m.id));paint();
    }
   }else if(root.isConnected)load();
  }catch(err){notice(err.message,true)}
  finally{button.disabled=false;}
 });
 load();
 gameChatTimer=setInterval(()=>{
  if(!root.isConnected){clearInterval(gameChatTimer);gameChatTimer=null;return;}
  if(document.visibilityState==='visible')load();
 },15000);
}

/* Small read-only poll: update the roster without reloading game details or
   fetching the private wishlist/image payload. All access is server-checked. */
function santaRosterPerson(p,state){
 const organizer=!!p.is_organizer||(!state.memberView&&p.user_id===state.currentUserId);
 const mine=state.memberView&&p.id===state.memberId;
 const adminActions=!state.memberView&&state.event.status==='open'&&!organizer;
 return '<div class="person-row"><div class="avatar">'+esc(p.name.slice(0,1).toUpperCase())+
  '</div><div class="person-main"><strong>'+esc(p.name)+' '+
  (organizer?'<span class="chip chip-peach">Организатор</span>':'')+
  (mine?'<span class="chip">Ты</span>':'')+'</strong><small>'+
  p.wish_count+' '+plural(p.wish_count,'желание','желания','желаний')+'</small></div>'+
  (adminActions?'<div class="person-actions"><button class="btn btn-soft btn-small" title="Выдать новую личную ссылку" data-action="new-player-link" data-id="'+p.id+'">'+ico('link')+'</button>'+
  '<button class="btn btn-soft btn-small" title="Убрать участника" data-action="remove-player" data-id="'+p.id+'">'+ico('trash')+'</button></div>':'')+
  '</div>';
}
function setupSantaRoster(state){
 const root=document.querySelector('[data-santa-roster]');if(!root)return;
 if(gameRosterTimer){clearInterval(gameRosterTimer);gameRosterTimer=null;}
 const route=state.base+'/roster';
 let running=false,previous=null,failures=0;
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
   const signature=JSON.stringify(info.participants.map(p=>[p.id,p.name,p.wish_count,p.is_organizer]));
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
