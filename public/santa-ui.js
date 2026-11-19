/* Santa wishlist cards and scoped chats. Uses existing Shursh UI functions. */
'use strict';
function gameWishCard(w,source='own'){
 const mine=source==='own';
 const image=w.image_data?'<img src="'+attr(w.image_data)+'" alt="'+attr(w.title)+'" loading="lazy">':artFor(w);
 const detail=w.wanted||w.description||'Открой карточку, чтобы посмотреть пожелания';
 return '<article class="wish-card game-gift-card">'+
  '<button type="button" class="card-hitarea" data-action="show-game-gift" data-id="'+w.id+'" data-source="'+source+'" aria-label="Посмотреть подарок '+attr(w.title)+'"></button>'+
  '<div class="wish-image">'+image+'</div><div class="wish-content"><h3>'+esc(w.title)+'</h3>'+
  '<p class="wish-desc">'+esc(detail)+'</p><div class="wish-card-footer"><div class="wish-price">'+
  money(w.price_cents,w.currency)+'</div>'+(mine?'<div class="wish-controls"><button type="button" class="btn btn-soft" data-action="edit-game-gift" data-id="'+w.id+'" aria-label="Изменить подарок" title="Изменить подарок">'+ico('edit')+'</button><button type="button" class="btn btn-soft" data-action="delete-game-gift" data-id="'+w.id+'" aria-label="Удалить подарок" title="Удалить подарок">'+ico('trash')+'</button></div>':'')+'</div>'+
  (w.shop_url?'<a href="'+attr(w.shop_url)+'" target="_blank" rel="noopener noreferrer" class="text-link game-gift-store">В магазин '+ico('external')+'</a>':'')+
  '</div></article>';
}
function wishesMarkup(wishes,source='own'){
 return wishes?.length?'<div class="wishlist-grid game-wishes-grid">'+wishes.map(w=>gameWishCard(w,source)).join('')+'</div>':
  '<span class="muted note">Пока нет подарков. Добавь конкретные идеи и пожелания</span>';
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
     details('Что хотелось бы',gift.wanted)+details('Чего не хотелось бы',gift.unwanted)+
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
 modal({title:isEdit?'Изменить подарок':'Добавить подарок в игру',
   subtitle:'Опиши конкретную вещь, цвет, модель и то, чего лучше избегать. Информацию увидит твой даритель',
   content:field('Название подарка','title','Например, настольная игра','text',gift.title||'',true,'maxlength="130"')+
   textArea('Что хотелось бы','wanted','Модель, цвет, размер, важные детали',gift.wanted||'')+
   textArea('Чего не хотелось бы','unwanted','Аналоги, цвета, размеры, особенности',gift.unwanted||'')+
   textArea('Дополнительное описание','description','Любые детали',gift.description||'')+
   field('Ссылка на товар (необязательно)','shop_url','https://...','url',gift.shop_url||'')+
   '<div class="form-grid">'+field('Ориентировочная цена','price','Например, 1500','number',budget,false,'min="0" step="0.01"')+
   selectField('Валюта','currency',[['RUB','₽ Рубли'],['EUR','€ Евро'],['USD','$ Доллары']],gift.currency||'RUB')+'</div>'+
   '<div class="field"><label for="game-gift-photo">Фотография</label><input id="game-gift-photo" type="file" accept="image/png,image/jpeg,image/webp"><p class="field-hint">Фото автоматически уменьшается для экономии места</p></div>'+
   (isEdit&&gift.image_data?'<label class="switch-label"><input type="checkbox" id="game-gift-remove-photo"> Удалить фотографию</label>':''),
   submitLabel:isEdit?'Сохранить':'Добавить подарок',
   onSubmit:async form=>{
    const data=readForm(form);
    const file=form.querySelector('#game-gift-photo')?.files?.[0];
    data.image_data=file?await smallGamePhoto(file):
      form.querySelector('#game-gift-remove-photo')?.checked?null:(gift.image_data||null);
    const url=state.base+(state.base.startsWith('/api/santas/')?'/my-wishes':'/wishes')+(isEdit?'/'+gift.id:'');
    await api(url,{method:isEdit?'PATCH':'POST',body:data});
    notice(isEdit?'Подарок обновлён':'Подарок добавлен');
    await render();
   }});
}
function setupGameChat(state){
 const root=document.querySelector('#game-chat');if(!root)return;
 if(gameChatTimer){clearInterval(gameChatTimer);gameChatTimer=null;}
 let room='general',loading=false,pendingRefresh=false;
 const list=root.querySelector('.game-chat-messages');
 const apiRoom=()=>state.base+'/messages/'+room;
 const load=async()=>{
  if(!root.isConnected)return;
  if(loading){pendingRefresh=true;return;}
  loading=true;
  const requestedRoom=room;
  try{
   const result=await api(apiRoom());
   if(!root.isConnected||requestedRoom!==room||room!==result.room)return;
   list.innerHTML=result.messages.length?result.messages.map(m=>
    '<div class="chat-message '+(m.mine?'chat-mine':'')+'"><div class="chat-meta">'+
    esc(m.author)+'</div><p>'+esc(m.message)+'</p></div>').join(''):
    '<p class="note">Сообщений пока нет. Начни разговор!</p>';
   list.scrollTop=list.scrollHeight;
  }catch(err){if(root.isConnected&&requestedRoom===room)list.innerHTML='<p class="note" role="alert">'+esc(err.message)+'</p>';}
  finally{loading=false;if(pendingRefresh&&root.isConnected){pendingRefresh=false;load();}}
 };
 root.addEventListener('click',ev=>{
  const tab=ev.target.closest('[data-chat-room]');
  if(tab){room=tab.dataset.chatRoom;root.querySelectorAll('[data-chat-room]').forEach(b=>{
   const selected=b===tab;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));
  });list.innerHTML='<p class="note">Загружаем сообщения…</p>';load();}
  if(ev.target.closest('[data-chat-refresh]'))load();
 });
 root.querySelector('#game-chat-form').addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.currentTarget,button=form.querySelector('button');
  const data=readForm(form);
  if(!data.message?.trim())return;
  button.disabled=true;
  try{await api(apiRoom(),{method:'POST',body:data});form.reset();await load();}
  catch(err){notice(err.message,true);}finally{button.disabled=false;}
 });
 load();
 gameChatTimer=setInterval(()=>{
  if(!root.isConnected){clearInterval(gameChatTimer);gameChatTimer=null;return;}
  if(document.visibilityState==='visible')load();
 },20000);
}
