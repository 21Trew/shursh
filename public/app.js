/* Шурш! - UI application. Vanilla JS, no build step or third-party runtime. */
'use strict';
const app = document.getElementById('app');
const modalRoot = document.getElementById('modal-root');
let currentUser = null;
let isDemo = false;
let lastRenderToken = 0;
let toastTimeout;
const isPreview = window.location.protocol === 'file:' || window.location.pathname.endsWith('/shursh-preview.html');
const ico = (name, size=20) => `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${({
  plus:'<path d="M12 5v14M5 12h14"/>', arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  back:'<path d="m15 18-6-6 6-6M9 12h11"/>', copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  gift:'<rect x="3" y="9" width="18" height="12" rx="2"/><path d="M3 12h18M12 9v12M12 9c-6 0-6-6-2-6 2 0 2 3 2 6Zm0 0c6 0 6-6 2-6-2 0-2 3-2 6Z"/>',
  heart:'<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.3 1-1a5.5 5.5 0 0 0 0-7.8Z"/>',
  lock:'<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  eye:'<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  'eye-off':'<path d="M3 3l18 18M10.6 6.1A11 11 0 0 1 12 6c7 0 10 6 10 6a16 16 0 0 1-3.2 3.6M6.4 6.5C3.5 8.2 2 12 2 12s3.6 6 10 6c1.3 0 2.6-.2 3.7-.6"/><path d="M10 10a3 3 0 0 0 4 4"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 11a3 3 0 0 0 0-6M17 14a6 6 0 0 1 4 6"/>',
  edit:'<path d="m4 16 11-11 4 4L8 20H4v-4ZM13 7l4 4"/>',
  trash:'<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
  external:'<path d="M14 4h6v6M20 4l-9 9M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/>',
  check:'<path d="m5 12 5 5L20 7"/>', close:'<path d="M5 5l14 14M19 5 5 19"/>',
  spark:'<path d="M12 2c0 6-4 10-10 10 6 0 10 4 10 10 0-6 4-10 10-10-6 0-10-4-10-10Z"/>',
  ticket:'<path d="M3 7h18v4a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4V7ZM13 7v3m0 4v4"/>',
  tag:'<path d="M4 4h9l8 8-9 9-8-8V4Z"/><circle cx="9" cy="9" r="1"/>',
  star:'<path d="m12 2 2.9 6.3 7 .9-5.1 5 1.3 7L12 18l-6.1 3.2 1.3-7-5.1-5 7-.9L12 2Z"/>',
  shield:'<path d="m12 2 9 4v6c0 5-3 8-9 10-6-2-9-5-9-10V6l9-4Z"/><path d="m8 12 3 3 5-6"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 7 9-7"/>',
  info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6m0-10v1"/>',
  logout:'<path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5M14 16l4-4-4-4m4 4H9"/>',
  home:'<path d="m3 11 9-8 9 8v10H3V11ZM9 21v-7h6v7"/>'
})[name]||''}</svg>`;
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function attr(value){return esc(value);}
function money(cents,currency='RUB'){
 if(cents===null||cents===undefined||cents==='')return 'Без цены';
 return new Intl.NumberFormat('ru-RU',{style:'currency',currency:currency||'RUB',maximumFractionDigits:0}).format(cents/100);
}
function dateRu(value){if(!value)return 'Не указана';try{return new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'}).format(new Date(value+'T12:00:00'));}catch{return value}}
function currentPath(){return isPreview?(location.hash.slice(1)||'/'):location.pathname;}
function getLink(path){return isPreview?location.href.split('#')[0]+'#'+path:location.origin+path;}
/* Owner-only tabs preserve their live DOM between navigations.
   Capability/bearer URLs are deliberately excluded. */
const ownerTabViews=new Map();
const OWNER_VIEW_TTL=45000;
let renderedOwnerTab=null;
function ownerTab(path){return !!currentUser&&['/','/lists','/santas'].includes(path);}
function clearOwnerTabViews(paths=null){
 if(!paths){ownerTabViews.clear();return;}
 for(const path of paths)ownerTabViews.delete(path);
}
function rememberOwnerTab(){
 if(!ownerTab(renderedOwnerTab)||app.querySelector('.dashboard-skeleton'))return;
 const node=app.querySelector('#page-view > main');
 if(!node)return;
 node.remove();ownerTabViews.set(renderedOwnerTab,{node,expires:Date.now()+OWNER_VIEW_TTL});
}
function restoreOwnerTab(path){
 if(!ownerTab(path))return false;
 const saved=ownerTabViews.get(path);
 if(!saved||saved.expires<=Date.now()){ownerTabViews.delete(path);return false;}
 const view=app.querySelector('#page-view');if(!view)return false;
 ownerTabViews.delete(path);view.replaceChildren(saved.node);
 view.removeAttribute('aria-busy');app.classList.remove('route-loading');
 app.querySelectorAll('.site-header .nav [data-nav]').forEach(link=>{
  const href=link.dataset.nav;link.classList.toggle('active',href===path);
 });
 renderedOwnerTab=path;return true;
}

function nav(path,{force=false}={}){
 if(currentPath()===path&&!force)return;
 if(!force)rememberOwnerTab();else clearOwnerTabViews();
 if(isPreview){if(currentPath()===path)render();else location.hash=path;}
 else{
  if(currentPath()!==path)history.pushState(null,'',path);
  if(!force&&restoreOwnerTab(path))lastRenderToken++;
  else render();
 }
 window.scrollTo({top:0,behavior:'instant'});
}
// Cache only authenticated owner data in RAM, never public bearer-link data.
const ownerDataCache=new Map();
let ownerCacheVersion=0;
function ownerCacheTTL(path){return /^\/api\/(?:santas|lists)\/\d+/.test(path)?15000:45000;}
function cacheableOwnerRead(path){
 return !!currentUser&&(/^\/api\/(?:lists|santas|dashboard)$/.test(path)||
  /^\/api\/(?:lists|santas)\/\d+$/.test(path));
}
function clearOwnerDataCache(){ownerCacheVersion++;ownerDataCache.clear();clearOwnerTabViews();}
function invalidateOwnerDataForMutation(path){
 // Scoped invalidation: creating a wishlist does not change Santa games,
 // and changing a Santa event does not change owned wishlists.
 const listMutation=/^\/api\/(?:lists|wishes)(?:\/|$)/.test(path);
 const santaMutation=/^\/api\/santas(?:\/|$)/.test(path) ||
  /^\/api\/participant\/[^/]+\/wishes$/.test(path) ||
  /^\/api\/invites\/[^/]+\/join$/.test(path);
 if(!listMutation&&!santaMutation){clearOwnerDataCache();return;}
 const invalidTabs=['/'].concat(listMutation?['/lists']:[]).concat(santaMutation?['/santas']:[]);
 clearOwnerTabViews(invalidTabs);
 // The currently displayed page can be stale too: never put it back in RAM
 // after its successful write has invalidated the backing data.
 if(invalidTabs.includes(renderedOwnerTab))renderedOwnerTab=null;
 for(const key of ownerDataCache.keys()){
  if(key==='/api/dashboard' || (listMutation&&key.startsWith('/api/lists')) ||
      (santaMutation&&key.startsWith('/api/santas')))ownerDataCache.delete(key);
 }
}
function seedOwnerCache(path,value){
 if(!cacheableOwnerRead(path))return;
 ownerDataCache.set(path,{value,expires:Date.now()+ownerCacheTTL(path)});
 if(path==='/api/dashboard'&&value?.user){
  if(Array.isArray(value.lists))ownerDataCache.set('/api/lists',{value:{lists:value.lists},expires:Date.now()+ownerCacheTTL('/api/lists')});
  if(Array.isArray(value.events))ownerDataCache.set('/api/santas',{value:{events:value.events},expires:Date.now()+ownerCacheTTL('/api/santas')});
 }
}
function cachedOwnerValue(path){
 const entry=ownerDataCache.get(path);
 return entry&&entry.expires>Date.now()&&Object.hasOwn(entry,'value')?entry.value:null;
}
async function api(path,opts={}){
 if(isPreview)return window.previewApi(path,opts);
 const method=opts.method||'GET',cached=method==='GET'&&cacheableOwnerRead(path);
 if(cached){
  const entry=ownerDataCache.get(path);
  if(entry&&entry.expires>Date.now())return entry.promise||entry.value;
 }
 const version=ownerCacheVersion;
 const request=(async()=>{
  const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},
   credentials:'same-origin',body:opts.body?JSON.stringify(opts.body):undefined});
  const data=await response.json().catch(()=>({error:'Не удалось прочитать ответ сервера'}));
  if(!response.ok)throw new Error(data.error||'Произошла ошибка');
  if(method!=='GET')invalidateOwnerDataForMutation(path);
  return data;
 })();
 if(cached){
  ownerDataCache.set(path,{promise:request,expires:Date.now()+ownerCacheTTL(path)});
  request.then(value=>{
   if(ownerCacheVersion===version&&ownerDataCache.get(path)?.promise===request)seedOwnerCache(path,value);
  },()=>{
   if(ownerDataCache.get(path)?.promise===request)ownerDataCache.delete(path);
  });
 }
 return request;
}
function notice(message,error=false){const n=document.createElement('div');n.className='toast'+(error?' error':'');n.textContent=message;document.getElementById('toast-root').replaceChildren(n);clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>n.remove(),4500);}
async function clipboard(value){try{await navigator.clipboard.writeText(value);notice('Ссылка скопирована!');}catch{modal({title:'Скопируй ссылку',content:`<div class="field"><label>Ссылка</label><input class="input" autofocus readonly value="${attr(value)}" onclick="this.select()"></div>`});}}
function modal({title,subtitle='',content='',onSubmit=null,submitLabel='Сохранить',size='normal',footer=''}){
 closeUiSelect();
 modalRoot.innerHTML=`<div class="modal-backdrop" data-backdrop><div class="modal" role="dialog" aria-modal="true" aria-label="${attr(title)}"><button class="modal-close" type="button" data-close aria-label="Закрыть">×</button><div class="modal-scroll-area"><h2>${esc(title)}</h2>${subtitle?`<p class="modal-subtitle">${esc(subtitle)}</p>`:''}<form class="form" id="modal-form">${content}${onSubmit?`<div class="form-actions"><button type="button" class="btn btn-soft" data-close>Отмена</button><button type="submit" class="btn btn-dark">${esc(submitLabel)} ${ico('arrow')}</button></div>`:''}</form>${footer?`<div class="modal-foot">${footer}</div>`:''}</div></div></div>`;
 enhanceSelects(modalRoot);
 document.body.style.overflow='hidden';const bd=modalRoot.querySelector('[data-backdrop]');bd.addEventListener('click',e=>{if(e.target===bd)closeModal()});modalRoot.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',closeModal));
 if(onSubmit){modalRoot.querySelector('form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.currentTarget.querySelector('[type=submit]');btn.disabled=true;try{const submitted=e.currentTarget;await onSubmit(submitted);if(modalRoot.querySelector('form')===submitted)closeModal();}catch(err){notice(err.message,true)}finally{if(btn.isConnected)btn.disabled=false;}});}
 // No delayed autofocus: it can steal focus while the user types in the
 // password field, silently redirecting keystrokes to email after 10 ms.
 modalRoot.querySelector('input:not([type=hidden]),textarea,.ui-select-trigger,select:not(.ui-select-native)')?.focus({preventScroll:true});
}
function contactDeveloperModal(){
 modal({title:'Написать разработчику',subtitle:'Есть идея, вопрос или нашли ошибку? Напишите прямо здесь',
  content:field('Как к вам обращаться','name','Ваше имя','text',currentUser?.name||'',true,'maxlength="80"')+
   field('Почта для ответа','email','name@example.com','email',currentUser?.email||'',true,'maxlength="200"')+
   selectField('Тема','topic',[['idea','Предложение'],['bug','Ошибка'],['question','Вопрос'],['other','Другое']],'idea')+
   textArea('Сообщение','message','Расскажите подробнее…')+
   '<p class="field-hint">Сообщение поступит в кабинет администрации. Ответим на указанную почту.</p>',
  submitLabel:'Отправить',onSubmit:async form=>{
   await api('/api/feedback',{method:'POST',body:readForm(form)});
   notice('Обращение отправлено');
  }});
 const message=modalRoot.querySelector('#fld-message');if(message){message.required=true;message.minLength=5;message.maxLength=3000;}
}
function closeModal(){closeUiSelect();modalRoot.replaceChildren();document.body.style.overflow='';}
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(uiSelectOpen){e.preventDefault();closeUiSelect(true);}else closeModal();}});
function field(label,name,placeholder='',type='text',value='',required=false,extra=''){
 return `<div class="field"><label for="fld-${attr(name)}">${esc(label)}</label><input id="fld-${attr(name)}" name="${attr(name)}" type="${attr(type)}" placeholder="${attr(placeholder)}" value="${attr(value??'')}" ${required?'required':''} ${extra}></div>`;
}
function textArea(label,name,placeholder='',value=''){
 return `<div class="field"><label for="fld-${attr(name)}">${esc(label)}</label><textarea id="fld-${attr(name)}" name="${attr(name)}" placeholder="${attr(placeholder)}">${esc(value)}</textarea></div>`;
}

/* Custom desktop selects with keyboard support; keep the real form select.
   On touch screens the native OS picker remains available and accessible. */
let uiSelectOpen=null;
let uiSelectSerial=0;
function closeUiSelect(focus=false){
 const open=uiSelectOpen;if(!open)return;
 uiSelectOpen=null;open.menu.remove();
 open.button.setAttribute('aria-expanded','false');
 open.button.removeAttribute('aria-activedescendant');
 if(focus&&open.button.isConnected)open.button.focus({preventScroll:true});
}
function openUiSelect(select,button){
 if(uiSelectOpen?.select===select){closeUiSelect();return;}
 closeUiSelect();
 const opts=[...select.options];
 const list=document.createElement('div');
 list.id='ui-select-list-'+(++uiSelectSerial);
 list.className='ui-select-menu';
 list.setAttribute('role','listbox');
 list.setAttribute('aria-label',select.labels?.[0]?.textContent?.trim()||'Выбрать вариант');
 list.innerHTML=opts.map((o,i)=>
  '<button type="button" role="option" tabindex="-1" data-ui-index="'+i+'" id="'+list.id+'-opt-'+i+'"'+
  (o.disabled?' disabled':'')+' aria-selected="'+(o.selected?'true':'false')+'">'+esc(o.textContent)+'</button>').join('');
 const portal=select.closest('.modal')||document.body;
 portal.appendChild(list);
 const r=button.getBoundingClientRect(),height=window.innerHeight,width=window.innerWidth;
 const below=Math.max(0,height-r.bottom-12),above=Math.max(0,r.top-12);
 const useAbove=below<Math.min(190,opts.length*44)&&above>below;
 const maxHeight=Math.max(58,Math.min(244,useAbove?above:below));
 list.style.width=Math.min(r.width,width-20)+'px';
 list.style.maxHeight=maxHeight+'px';
 list.style.left=Math.max(10,Math.min(r.left,width-r.width-10))+'px';
 list.style.top=Math.max(8,useAbove?r.top-6-maxHeight:r.bottom+6)+'px';
 let highlighted=Math.max(0,select.selectedIndex);
 const mark=(i)=>{
  if(!opts.length)return;
  highlighted=(i+opts.length)%opts.length;
  list.querySelectorAll('[data-ui-index]').forEach(el=>{
   const active=Number(el.dataset.uiIndex)===highlighted;
   el.classList.toggle('is-highlighted',active);
   el.setAttribute('aria-selected',String(Number(el.dataset.uiIndex)===select.selectedIndex));
  });
  button.setAttribute('aria-activedescendant',list.id+'-opt-'+highlighted);
  const target=list.querySelector('[data-ui-index="'+highlighted+'"]');
  target?.scrollIntoView({block:'nearest'});
 };
 const choose=(i)=>{
  if(!opts[i]||opts[i].disabled)return;
  select.selectedIndex=i;
  select.dispatchEvent(new Event('change',{bubbles:true}));
  closeUiSelect(true);
 };
 uiSelectOpen={select,button,menu:list,choose,mark,get highlighted(){return highlighted;}};
 button.setAttribute('aria-controls',list.id);
 button.setAttribute('aria-expanded','true');
 list.addEventListener('pointerdown',e=>e.preventDefault());
 list.addEventListener('click',e=>{
  const option=e.target.closest('[data-ui-index]');
  if(option)choose(Number(option.dataset.uiIndex));
 });
 mark(highlighted);
}
function enhanceSelects(root){
 if(window.matchMedia?.('(pointer:coarse)').matches)return;
 root.querySelectorAll('select:not([data-ui-enhanced])').forEach(select=>{
  select.dataset.uiEnhanced='true';
  const shell=document.createElement('div');shell.className='ui-select';
  select.parentNode.insertBefore(shell,select);shell.appendChild(select);
  select.classList.add('ui-select-native');
  select.tabIndex=-1;select.setAttribute('aria-hidden','true');
  const button=document.createElement('button');
  button.type='button';button.className='ui-select-trigger';
  button.dataset.selectId=select.id;
  button.setAttribute('role','combobox');
  button.setAttribute('aria-haspopup','listbox');
  button.setAttribute('aria-expanded','false');
  button.disabled=select.disabled;
  const update=()=>{
   const text=select.selectedOptions[0]?.textContent||'Выбрать';
   const label=select.labels?.[0]?.textContent?.trim()||'Вариант';
   button.textContent=text;
   button.setAttribute('aria-label',label+': '+text);
  };
  update();select.addEventListener('change',update);
  button.addEventListener('click',()=>openUiSelect(select,button));
  button.addEventListener('keydown',e=>{
   if(e.key==='Escape'&&uiSelectOpen?.select===select){
    e.preventDefault();e.stopPropagation();closeUiSelect(true);return;
   }
   if(e.key==='Tab'){if(uiSelectOpen?.select===select)closeUiSelect();return;}
   if(!['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(e.key))return;
   e.preventDefault();
   if(!uiSelectOpen||uiSelectOpen.select!==select)openUiSelect(select,button);
   const state=uiSelectOpen;
   if(!state)return;
   if(e.key==='ArrowDown')state.mark(state.highlighted+1);
   else if(e.key==='ArrowUp')state.mark(state.highlighted-1);
   else if(e.key==='Home')state.mark(0);
   else if(e.key==='End')state.mark(select.options.length-1);
   else if(e.key==='Enter'||e.key===' ')state.choose(state.highlighted);
  });
  shell.appendChild(button);
  select.labels?.[0]?.addEventListener('click',e=>{e.preventDefault();button.focus({preventScroll:true});});
 });
}
document.addEventListener('pointerdown',e=>{
 if(uiSelectOpen&&!uiSelectOpen.button.contains(e.target)&&!uiSelectOpen.menu.contains(e.target))closeUiSelect();
});
document.addEventListener('scroll',e=>{
 if(uiSelectOpen&&!uiSelectOpen.menu.contains(e.target))closeUiSelect();
},true);
window.addEventListener('resize',()=>closeUiSelect());

function selectField(label,name,options,selected){return `<div class="field"><label for="fld-${name}">${esc(label)}</label><select id="fld-${name}" name="${name}">${options.map(([value,text])=>`<option value="${attr(value)}" ${String(value)===String(selected)?'selected':''}>${esc(text)}</option>`).join('')}</select></div>`;}
function readForm(form){return Object.fromEntries(new FormData(form).entries());}
function fallbackArt(type='gift'){
 const out={
  'gift':`<path d="M37 72h94v64H37z" fill="#e6b7df" stroke="#302b34" stroke-width="3"/><path d="M30 63h107v20H30z" fill="#f6c4a9" stroke="#302b34" stroke-width="3"/><path d="M75 64v72m0-53h19" fill="none" stroke="#302b34" stroke-width="3"/><path d="M77 63c-13-3-25-13-19-24s25 1 19 24Zm1 0c13-3 25-13 19-24S72 52 78 63Z" fill="#f8e7a3" stroke="#302b34" stroke-width="3"/>`,
  'camera':`<rect x="20" y="53" width="125" height="80" rx="14" fill="#f0aa80" stroke="#29272b" stroke-width="3"/><rect x="42" y="42" width="44" height="14" rx="5" fill="#f2cb91" stroke="#29272b" stroke-width="3"/><circle cx="89" cy="91" r="29" fill="#f6ecd9" stroke="#29272b" stroke-width="3"/><circle cx="89" cy="91" r="19" fill="#87a2af" stroke="#29272b" stroke-width="3"/><circle cx="37" cy="72" r="5" fill="#f7e5a8"/>`,
  'cup':`<path d="M42 53h81v44c0 26-17 40-40 40S42 120 42 97V53Z" fill="#d9c9ed" stroke="#29272b" stroke-width="3"/><path d="M124 65c38-7 34 43-1 42" fill="none" stroke="#29272b" stroke-width="9"/><path d="M65 41c-10-12 9-20-1-29m27 29c-10-12 9-20-1-29" stroke="#947e98" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M60 88c15-8 30-8 45 0" stroke="#7c638f" stroke-width="3" fill="none"/>`,
  'ticket':`<path d="M22 61 131 39l17 79-108 22-7-27c11-4 9-20-5-18Z" fill="#f4b6a8" stroke="#29272b" stroke-width="3"/><path d="m91 52 13 66" stroke="#29272b" stroke-dasharray="5 6" stroke-width="2"/><path d="m62 79 9 8 14-16" stroke="#29272b" stroke-width="3" fill="none"/>`,
  'book':`<path d="M33 46c22-8 43-3 53 7v83c-17-10-37-12-53-5V46Z" fill="#f2c69a" stroke="#29272b" stroke-width="3"/><path d="M86 53c19-11 39-12 56-4v84c-20-7-40-6-56 3V53Z" fill="#d6c7ec" stroke="#29272b" stroke-width="3"/><path d="m48 67 20 5m-20 11 20 5m35-17 21-6m-21 20 21-6" stroke="#928485" stroke-width="2"/>`,
  'plant':`<path d="M54 93h63l-8 43H62Z" fill="#e7a18b" stroke="#29272b" stroke-width="3"/><path d="M86 94c-5-32-5-57 0-75" stroke="#29272b" stroke-width="3" fill="none"/><path d="M86 76c-38-4-35-41-16-41 12 1 15 25 16 41Zm0-18c30-5 39-34 24-37-20-3-25 21-24 37Z" fill="#91c8a5" stroke="#29272b" stroke-width="3"/>`
 };
 return `<svg viewBox="0 0 170 160" aria-hidden="true">${out[type]||out.gift}</svg>`;
}
function artFor(w){const t=(w.title||'').toLowerCase();if(w.kind==='experience'||/билет|театр|концерт|поездк|настол/.test(t))return fallbackArt('ticket');if(/камер|фотоаппарат|плён/.test(t))return fallbackArt('camera');if(/чаш|кофе|чай/.test(t))return fallbackArt('cup');if(/книг|издани|пазл/.test(t))return fallbackArt('book');if(/растен|цвет|карандаш/.test(t))return fallbackArt('plant');return fallbackArt('gift')}
function envelopeArt(){return `<svg class="envelope-svg" viewBox="0 0 210 175" fill="none" aria-hidden="true"><g transform="rotate(-7 105 90)"><rect x="20" y="32" width="169" height="119" rx="13" fill="#f8c8a8" stroke="#302c31" stroke-width="3"/><path d="m21 43 84 65 82-65" fill="#fbe3bb" stroke="#302c31" stroke-width="3"/><path d="m22 143 62-50m104 50-61-50" stroke="#302c31" stroke-width="3"/><circle cx="105" cy="105" r="17" fill="#e18d79" stroke="#302c31" stroke-width="3"/><path d="M99 101c2-3 6-3 8 0 2-3 7-3 9 0 0 5-5 7-9 11-5-4-8-6-8-11Z" fill="#fff"/></g><path d="M10 15v18M1 24h18M179 9v27m-13-13h26" stroke="#efad65" stroke-width="3" stroke-linecap="round"/></svg>`;}
function heroArt(){return `<svg viewBox="0 0 570 535" aria-hidden="true" role="presentation">
 <path d="M79 167c2-73 65-113 144-99 65 12 83 50 154 41 88-11 142 68 116 159-27 100-77 153-192 170-99 14-236-38-251-132-7-44 27-84 29-139Z" fill="#f7e5d4"/>
 <g class="float-one" transform="rotate(-15 118 164)"><rect x="48" y="113" width="133" height="99" rx="7" fill="#d6c5f3" stroke="#28282b" stroke-width="3"/><path d="M48 113 113 72l68 41-68 45Z" fill="#eee3fa" stroke="#28282b" stroke-width="3"/><path d="m49 212 63-53 69 53" stroke="#28282b" stroke-width="3" fill="none"/><path d="m104 105 8 6 8-6" stroke="#28282b" stroke-width="3" stroke-linecap="round"/></g>
 <g class="float-two" transform="rotate(10 408 136)"><path d="M363 73h105v130H363z" fill="#f2aa78" stroke="#28282b" stroke-width="3"/><path d="M351 64h130v25H351z" fill="#fccd95" stroke="#28282b" stroke-width="3"/><path d="M410 65v138" stroke="#28282b" stroke-width="3"/><path d="M411 64c-22-26-40-19-36-5 3 11 22 9 36 5Zm0 0c22-26 40-19 36-5-3 11-22 9-36 5Z" fill="#f6e5b0" stroke="#28282b" stroke-width="3"/></g>
 <g class="wobble"><path d="M237 337c-20 44-31 72-13 84 23 15 40-16 54-57M335 336c15 45 32 77 52 65 19-12-1-46-16-76" stroke="#29292c" stroke-width="13" fill="none" stroke-linecap="round"/><path d="M206 253c-25 11-39 28-38 43 0 15 19 17 43 7m162-50c30 9 39 25 37 36-2 15-19 14-40 12" stroke="#29292c" stroke-width="12" fill="none" stroke-linecap="round"/>
 <path d="M210 215c-3-30 20-50 50-52l78-5c31-2 55 17 56 47l6 129c2 34-21 54-52 56l-80 5c-31 2-56-17-57-50Z" fill="#f7b7a3" stroke="#29292c" stroke-width="4"/><path d="M212 227 302 296l93-87" fill="#ffd7b9" stroke="#29292c" stroke-width="4" stroke-linejoin="round"/><path d="m215 344 66-76m117 63-74-68" stroke="#29292c" stroke-width="3" fill="none"/>
 <ellipse cx="273" cy="316" rx="5" ry="7" fill="#29292c"/><ellipse cx="334" cy="316" rx="5" ry="7" fill="#29292c"/><path d="M292 337c6 7 16 8 23 0" stroke="#29292c" stroke-width="3" fill="none" stroke-linecap="round"/><ellipse cx="252" cy="332" rx="14" ry="7" fill="#eb9f94"/><ellipse cx="357" cy="332" rx="14" ry="7" fill="#eb9f94"/>
 <path d="M260 164c-11-37 8-60 35-57 27 4 32 25 17 55" fill="#f3e49a" stroke="#29292c" stroke-width="4"/><path d="m285 114 1-21m-14 31-17-9m53 13 19-11" stroke="#29292c" stroke-width="3" stroke-linecap="round"/>
 </g><g fill="#edc76c" stroke="#29292c" stroke-width="2"><path d="m161 343 7 19 20 6-20 7-7 20-7-20-20-7 20-6Z"/><path d="m444 310 6 14 14 6-14 6-6 15-5-15-15-6 15-6Z"/></g><path d="M130 252c-12-24-4-36 10-29 8 4 9 13 9 13s12-13 23-4c13 14-5 27-23 40Z" fill="#e98e86"/><path d="m460 212 13-3m-9-15 11-9" stroke="#27272b" stroke-width="3" stroke-linecap="round"/></svg>`;}
function santaArt(){return `<svg viewBox="0 0 600 430" aria-hidden="true"><path d="M5 210c70-180 229-206 353-138s202 176 220 266v92H0Z" fill="#f3d1c2"/><g transform="translate(60 70) rotate(-12 110 145)"><rect x="25" y="32" width="195" height="232" rx="17" fill="#f5e8ce" stroke="#2c292b" stroke-width="4"/><path d="M45 72h150m-150 31h105m-105 31h130" stroke="#d5baa5" stroke-width="6" stroke-linecap="round"/><circle cx="122" cy="195" r="33" fill="#eeb5a0" stroke="#2c292b" stroke-width="3"/><path d="m106 197 12 12 24-26" stroke="#2c292b" stroke-width="5" fill="none"/></g><g transform="translate(310 91) rotate(13 110 125)"><rect x="18" y="25" width="202" height="230" rx="17" fill="#d4c5ef" stroke="#2c292b" stroke-width="4"/><path d="M19 45 119 139 219 45M19 250l71-91m129 91-72-91" stroke="#2c292b" stroke-width="4" fill="none"/><circle cx="118" cy="150" r="33" fill="#f8c18a" stroke="#2c292b" stroke-width="4"/><path d="M107 152c0-9 7-12 11-4 4-8 12-5 11 4-2 7-11 12-11 12s-11-5-11-12" fill="#fff"/></g><path d="M277 47v29m-14-14h29m204 217 7 17 17 8-17 7-7 17-8-17-17-7 17-8Z" stroke="#2c292b" stroke-width="3" fill="#f2d990"/></svg>`;}
function stepArt(num){if(num===1)return `<svg viewBox="0 0 130 112">${fallbackArt('book').replace(/viewBox="[^"]*"/,'viewBox="0 0 170 160"')}</svg>`;if(num===2)return `<svg viewBox="0 0 130 112"><rect x="13" y="28" width="104" height="67" rx="10" fill="#fff" stroke="#29292b" stroke-width="3"/><path d="m15 40 50 38 50-38" stroke="#29292b" stroke-width="3" fill="none"/><circle cx="67" cy="73" r="15" fill="#e5bcf0" stroke="#29292b" stroke-width="2"/><path d="M62 72c1-5 5-5 6-1 4-6 9-2 7 3l-7 7Z" fill="#e27f9a"/></svg>`;return `<svg viewBox="0 0 130 112"><rect x="23" y="36" width="86" height="65" fill="#f1b0ac" stroke="#29292b" stroke-width="3"/><rect x="16" y="27" width="100" height="18" fill="#ffdc98" stroke="#29292b" stroke-width="3"/><path d="M65 28v72M65 28c-27 1-25-24-12-23 10 1 12 20 12 23Zm0 0c25-1 24-24 11-23-9 1-11 20-11 23Z" fill="#e5d1f4" stroke="#29292b" stroke-width="3"/></svg>`;}
function header(){const path=currentPath();return `<header class="site-header"><div class="container topbar"><a class="logo" href="/" data-nav="/" aria-label="Шурш! Главная">шурш<span>!</span></a><nav class="nav" aria-label="Главная навигация"><a href="/" data-nav="/" class="${path==='/'?'active':''}">${currentUser?'Кабинет':'Главная'}</a><a href="/lists" data-nav="/lists" class="${path.startsWith('/lists')||path.startsWith('/list/')?'active':''}">Вишлисты</a><a href="/santas" data-nav="/santas" class="${path.startsWith('/santas')||path.startsWith('/santa/')?'active':''}">Тайный Санта</a></nav><div class="header-actions">${currentUser?`<span class="user-name">Привет, ${esc(currentUser.name)}!</span><button class="btn btn-ghost" data-action="logout" title="Выйти">${ico('logout')} Выйти</button>`:`<button class="btn btn-ghost" data-open="login">Войти</button>`}</div></div></header>${isPreview?`<div class="preview-ribbon"><div class="container">Интерактивное демо · данные хранятся только в этом браузере · ссылки не работают на других устройствах <button type="button" data-action="reset-preview">Сбросить демо</button></div></div>`:''}`;}
function footer(){return `<footer class="container footer"><div><a class="logo" data-nav="/" href="/">шурш<span>!</span></a><small>Место для хотелок и сюрпризов</small></div><nav><a data-nav="/lists" href="/lists">Вишлисты</a><a data-nav="/santas" href="/santas">Тайный Санта</a></nav><p class="footer-credit">Сделано с заботой о сюрпризах <span aria-hidden="true">·</span> <button class="footer-developer" type="button" data-action="contact-developer">L-code</button></p></footer>`;}
let shellUserSignature='';
function shell(body){
 const identity=(currentUser?.id??'guest')+':'+(currentUser?.name??'')+':'+isDemo+':'+isPreview;
 let view=app.querySelector('#page-view');
 if(!view){
  app.innerHTML=header()+'<div id="page-view"></div>'+footer();
  view=app.querySelector('#page-view');shellUserSignature=identity;
 }else if(shellUserSignature!==identity){
  const head=app.querySelector('.site-header');
  if(head)head.outerHTML=header();
  shellUserSignature=identity;
 }else{
  const path=currentPath();
  app.querySelectorAll('.site-header .nav [data-nav]').forEach(link=>{
   const href=link.dataset.nav;
   link.classList.toggle('active',href==='/'?path==='/':
    href==='/lists'?(path==='/lists'||path.startsWith('/list/')):
    (path==='/santas'||path.startsWith('/santa/')));
  });
 }
 closeUiSelect();view.innerHTML=body;enhanceSelects(view);view.removeAttribute('aria-busy');app.classList.remove('route-loading');
 renderedOwnerTab=ownerTab(currentPath())?currentPath():null;
 document.title='Шурш! - вишлисты и Тайный Санта';
}

function dashboardContent(data){
 const lists=Array.isArray(data.lists)?data.lists:[];
 const events=Array.isArray(data.events)?data.events:[];
 const name=esc((currentUser.name||'Друг').trim().split(/\s+/)[0]);
 const recentLists=lists.slice(0,3).map(listCard).join('');
 const recentEvents=events.slice(0,3).map(e=>
  '<article class="dashboard-santa-card"><a class="card-hitarea" href="/santa/'+e.id+'" data-nav="/santa/'+e.id+'" aria-label="Открыть игру '+attr(e.title)+'"></a><div class="dashboard-santa-symbol">'+ico('gift',30)+'</div>'+
  '<div class="section-label">'+(e.status==='drawn'?'Жеребьёвка проведена':'Собираем участников')+'</div>'+
  '<h3>'+esc(e.title)+'</h3><p>'+esc(e.description||'Праздник уже на горизонте!')+'</p>'+
  '<div class="dashboard-card-footer"><span>'+Number(e.participant_count||0)+' '+plural(e.participant_count||0,'участник','участника','участников')+'</span>'+
  '<button class="text-link" data-nav="/santa/'+e.id+'">Открыть '+ico('arrow')+'</button></div></article>'
 ).join('');
 shell('<main class="container dashboard-page">'+
  '<section class="dashboard-welcome"><div><div class="section-label">Твоё пространство</div><h1>С возвращением, <em>'+name+'!</em></h1>'+
  '<p>Хорошие сюрпризы начинаются здесь. Что будем делать сегодня?</p>'+
  '<div class="btn-row"><button class="btn btn-dark" data-open="list">Новый вишлист '+ico('plus')+'</button>'+
  '<button class="btn btn-peach" data-open="santa">Создать Тайного Санту '+ico('gift')+'</button></div></div>'+
  '<div class="dashboard-welcome-art" aria-hidden="true">'+fallbackArt('gift')+'</div></section>'+
  '<section class="dashboard-metrics" aria-label="Твоя активность">'+
  '<div><strong>'+lists.length+'</strong><span>'+plural(lists.length,'вишлист','вишлиста','вишлистов')+'</span></div>'+
  '<div><strong>'+lists.reduce((sum,l)=>sum+Number(l.wish_count||0),0)+'</strong><span>желаний в списках</span></div>'+
  '<div><strong>'+events.length+'</strong><span>'+plural(events.length,'игра','игры','игр')+' в Тайного Санту</span></div></section>'+
  '<section class="dashboard-section"><div class="dashboard-section-head"><div><div class="section-label">01 / Вишлисты</div>'+
  '<h2>Твои желания</h2></div><button class="text-link" data-nav="/lists">Все списки '+ico('arrow')+'</button></div>'+
  (lists.length?'<div class="cards-grid">'+recentLists+'</div>':
   '<div class="dashboard-empty"><div class="dashboard-empty-art">'+fallbackArt('cup')+'</div>'+
   '<div><h3>Пока ни одного списка</h3><p>Начни с первого желания - остальные подтянутся</p>'+
   '<button class="btn btn-soft btn-small" data-open="list">Создать вишлист '+ico('plus')+'</button></div></div>')+'</section>'+
  '<section class="dashboard-section"><div class="dashboard-section-head"><div><div class="section-label">02 / Тайный Санта</div>'+
  '<h2>Твои игры</h2></div><button class="text-link" data-nav="/santas">Все игры '+ico('arrow')+'</button></div>'+
  (events.length?'<div class="dashboard-santa-grid">'+recentEvents+'</div>':
   '<div class="dashboard-empty dashboard-empty-lilac"><div class="dashboard-empty-art">'+envelopeArt()+'</div>'+
   '<div><h3>Пока без секретов</h3><p>Собери компанию и устрой первый обмен подарками</p>'+
   '<button class="btn btn-soft btn-small" data-open="santa">Создать игру '+ico('plus')+'</button></div></div>')+'</section></main>');
}
function dashboardLoading(){
 const name=esc((currentUser?.name||'Друг').trim().split(/\s+/)[0]);
 shell('<main class="container dashboard-page"><section class="dashboard-welcome"><div>'+
  '<div class="section-label">Твоё пространство</div><h1>С возвращением, <em>'+name+'!</em></h1>'+
  '<p>Хорошие сюрпризы начинаются здесь</p>'+
  '<div class="btn-row"><button class="btn btn-dark" data-open="list">Новый вишлист '+ico('plus')+'</button>'+
  '<button class="btn btn-peach" data-open="santa">Создать Тайного Санту '+ico('gift')+'</button></div></div>'+
  '<div class="dashboard-welcome-art" aria-hidden="true">'+fallbackArt('gift')+'</div></section>'+
  '<section class="dashboard-skeleton" role="status" aria-live="polite">Загружаем твои списки и игры…</section></main>');
}
async function dashboardPage(marker=lastRenderToken){
 if(!currentUser){home();return;}
 const data=isPreview?await Promise.all([api('/api/lists'),api('/api/santas')]).then(([a,b])=>({user:currentUser,lists:a.lists,events:b.events})):await api('/api/dashboard');
 if(marker!==lastRenderToken)return;
 if(!isPreview&&!data.user){clearOwnerDataCache();currentUser=null;home();return;}
 if(!isPreview)seedOwnerCache('/api/dashboard',data);
 dashboardContent(data);
}
function home(){shell(`<main><section class="container hero"><div class="hero-copy"><div class="eyebrow">${ico('spark')} Сервис хороших сюрпризов</div><h1>Подарки, о которых <em>не нужно</em> догадываться</h1><p class="hero-description">Собирай желания, делись ими с близкими и устраивай Тайного Санту без бумажек и путаницы</p><div class="btn-row"><button class="btn btn-dark" data-open="list">Создать вишлист ${ico('arrow')}</button><button class="btn btn-peach" data-open="santa">Играть в Тайного Санту ${ico('gift')}</button></div></div><div class="hero-visual">${heroArt()}<div class="tiny-bubble bubble-heart">${ico('heart')} кое-кто уже мечтает</div><div class="tiny-bubble bubble-gift">сюрприз на подходе</div></div></section>
 <div class="marquee-line"><div class="marquee-inner"><span>Меньше «что подарить?»</span><span>Больше «как ты угадал!»</span><span>Сюрпризы без спойлеров</span><span>Повод найдётся всегда</span></div></div>
 <section class="container section" id="how"><div class="section-intro"><div><div class="section-label">01 / Очень просто</div><h2>Три шага до<br>«вау, это же оно!»</h2></div><p>Никаких таблиц, бесконечных переписок и загадочных намёков</p></div><div class="steps">${[['Собери желания','Добавляй вещи, идеи и впечатления. С ценой или без неё'],['Поделись ссылкой','Отправь список кому хочешь - даже тем, кто здесь впервые'],['Получай сюрпризы','Друзья договорятся о подарках. А ты ничего не узнаешь раньше времени']].map((x,i)=>`<div class="step"><span class="step-number">0${i+1} / 03</span><div class="step-art">${stepArt(i+1)}</div><h3>${x[0]}</h3><p>${x[1]}</p></div>`).join('')}</div></section>
 <section class="container"><div class="showcase"><div class="blob"></div><div class="showcase-copy"><div class="section-label">02 / Выглядит как мечта</div><h2>Списки, которыми хочется делиться</h2><p>Красивое место для маленьких и больших желаний. От керамической чашки до поездки на край света</p><button class="btn btn-dark" data-action="sample-list">${isDemo?'Посмотреть пример':'Создать свой список'} ${ico('arrow')}</button></div><div class="showcase-mock"><div class="mock-top"><h3>Сашин день рождения ♡</h3><span class="chip chip-peach">4 желания</span></div><div class="mock-items">${[['camera','Плёночный фотоаппарат','8 900 ₽'],['cup','Керамическая чашка','2 500 ₽'],['ticket','Билеты в театр','Впечатление']].map((a,i)=>`<div class="mock-item"><div class="mock-art" style="background:${['#f4e7dd','#e9e2f5','#e4f0e4'][i]}">${fallbackArt(a[0])}</div><div class="mock-copy"><strong>${a[1]}</strong><small>${a[2]}</small></div></div>`).join('')}</div></div></div></section>
 <section class="container section"><div class="santa-feature"><div class="santa-art">${santaArt()}</div><div class="santa-copy"><div class="section-label">03 / Немного волшебства</div><h2>Тайный Санта без бумажек и хитростей</h2><p>Зови компанию, задавай бюджет и правила. Мы честно перемешаем имена и сохраним интригу</p><div class="feature-tick">${ico('check')} Никто не вытянет сам себя</div><div class="feature-tick">${ico('check')} Можно исключать неудобные пары</div><div class="feature-tick">${ico('check')} Каждый видит только свой секрет</div><button class="btn btn-dark" style="margin-top:25px" data-open="santa">Организовать игру ${ico('arrow')}</button></div></div></section>
 <section class="container"><div class="privacy-strip"><div class="privacy-illustration">${envelopeArt()}</div><div><div class="section-label">04 / Тс-с, секрет!</div><h2>Бронируй подарок. Не выдавай сюрприз</h2><p>Друг выбрал подарок? Он отметит его занятым, чтобы никто не купил такой же. Владелец списка не увидит бронирование в своём кабинете. Даритель получит отдельную ссылку для отмены</p></div></div></section>
 <section class="container section"><div class="section-intro"><div><div class="section-label">05 / Дарить без повода - тоже повод</div><h2>Для всех ваших<br>«хочу порадовать»</h2></div></div><div class="occasions">${[['gift','День рождения'],['heart','Годовщина'],['home','Новоселье'],['spark','Просто так'],['users','Свадьба'],['star','Любой праздник']].map(a=>`<span class="occasion-chip">${ico(a[0])} ${a[1]}</span>`).join('')}</div></section>
 <section class="container"><div class="final-cta"><div><h2>Пусть хорошие подарки случаются чаще</h2><p>Первый список можно собрать прямо сейчас</p></div><button class="btn btn-dark" data-open="list">Создать свой список ${ico('arrow')}</button></div></section></main>`);}
function loading(){
 renderedOwnerTab=null;
 const view=app.querySelector('#page-view');
 if(view&&renderStarted){
  app.classList.add('route-loading');view.setAttribute('aria-busy','true');return;
 }
 app.innerHTML=header()+'<div class="loading-screen"><div class="loading-mark">шурш<span>!</span></div><div class="loading-line"></div></div>';
}
function errorView(err,title='Что-то пошло не так'){shell(`<main class="container page"><div class="error-page">${envelopeArt()}<h1>${esc(title)}</h1><p>${esc(err?.message||'Не удалось загрузить страницу')}</p><button class="btn btn-dark" data-nav="/">На главную ${ico('arrow')}</button></div></main>`);}
function emptyState(title,desc,button,open){return `<div class="blank-state"><div class="blank-illustration">${fallbackArt('gift')}</div><h3>${esc(title)}</h3><p>${esc(desc)}</p><button class="btn btn-dark" data-open="${attr(open)}">${esc(button)} ${ico('plus')}</button></div>`;}
async function listsPage(marker=lastRenderToken){if(!currentUser){shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Твой уголок</div><h1>Мои вишлисты</h1><p>Здесь будут все твои желания. Для начала нужно войти</p></div><button class="btn btn-dark" data-open="login">Войти ${ico('arrow')}</button></div>${emptyState('Всё начинается с одного желания','Войди или создай аккаунт, чтобы хранить списки','Создать аккаунт','register')}</main>`);return;}
 const {lists}=await api('/api/lists');if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Коллекция желаний</div><h1>Твои вишлисты ${isDemo?'<span class="demo-banner">ДЕМО-ДАННЫЕ</span>':''}</h1><p>Хочешь - по поводу, хочешь - просто потому что</p></div><div class="btn-row"><button class="btn btn-dark" data-open="list">Новый список ${ico('plus')}</button></div></div>${lists.length?`<div class="cards-grid">${lists.map(l=>listCard(l)).join('')}</div>`:emptyState('Здесь пока тихо','Создай первый список и добавь пару желаний','Создать список','list')}</main>`);}
function listCard(l){return `<article class="list-card"><a class="card-hitarea" href="/list/${l.id}" data-nav="/list/${l.id}" aria-label="Открыть вишлист ${attr(l.title)}"></a><div class="list-cover cover-${attr(l.theme)}"><span class="cover-stamp">${esc(l.occasion)}</span>${fallbackArt('gift')}</div><div class="list-info"><h3>${esc(l.title)}</h3><p>${esc(l.description||'Место для твоих желаний')}</p><div class="list-bottom"><span>${l.wish_count} ${plural(l.wish_count,'желание','желания','желаний')}</span><button class="text-link" data-nav="/list/${l.id}">Открыть ${ico('arrow')}</button></div></div></article>`;}
function plural(n,a,b,c){const k=Number(n)%100,d=k%10;return k>=11&&k<=14?c:d===1?a:d>=2&&d<=4?b:c;}
function wishCard(w,mode='owner',shareKey=''){
 const reserved=w.reserved===true;
 const cardActions=mode==='owner'?`<div class="wish-controls"><button class="btn btn-soft" data-action="edit-wish" data-id="${w.id}" title="Редактировать">${ico('edit')}</button><button class="btn btn-soft" data-action="delete-wish" data-id="${w.id}" title="Удалить">${ico('trash')}</button></div>`:'';
 const footer=mode==='guest'?`<button class="btn ${reserved?'btn-soft':'btn-dark'} wish-action" ${reserved?'disabled':''} data-action="reserve" data-id="${w.id}" data-key="${attr(shareKey)}">${reserved?`${ico('check')} Уже забронировано`:`${ico('gift')} Забронировать подарок`}</button>`:'';
 return `<article class="wish-card"><button type="button" class="card-hitarea" data-action="show-wish" data-id="${w.id}" data-mode="${attr(mode)}" data-key="${attr(shareKey)}" aria-label="Подробнее о желании ${attr(w.title)}"></button><div class="wish-image">${w.image_path?`<img src="${attr(w.image_path)}" alt="${attr(w.title)}" loading="lazy">`:artFor(w)}${w.priority==='love'?`<span class="wish-priority chip chip-peach">${ico('heart')} Очень хочу</span>`:''}</div><div class="wish-content"><h3>${esc(w.title)}</h3><p class="wish-desc">${esc(w.description|| (w.kind==='experience'?'Впечатление или хорошая идея':'Подарок без комментария'))}</p><div class="wish-card-footer"><div class="wish-price">${money(w.price_cents,w.currency)}</div>${cardActions}</div>${w.shop_url?`<a href="${attr(w.shop_url)}" target="_blank" rel="noopener noreferrer" class="text-link" style="margin-top:12px;font-size:12px">В магазин ${ico('external')}</a>`:''}${footer}</div></article>`;
}
function showWishDetails(el){
 const id=Number(el.dataset.id), mode=el.dataset.mode, key=el.dataset.key||'';
 const wish=(mode==='owner'?loadedList?.wishes:loadedPublicWishes)?.find(w=>Number(w.id)===id);
 if(!wish)return;
 const image=wish.image_path?'<img class="wish-detail-image" src="'+attr(wish.image_path)+'" alt="'+attr(wish.title)+'">':
   '<div class="wish-detail-art">'+artFor(wish)+'</div>';
 const actions=mode==='owner'?'<button class="btn btn-soft" data-action="edit-wish" data-id="'+id+'">'+ico('edit')+' Редактировать</button>':
   mode==='guest'&&!wish.reserved?'<button class="btn btn-dark" data-action="reserve" data-id="'+id+'" data-key="'+attr(key)+'">'+ico('gift')+' Забронировать</button>':'';
 const store=wish.shop_url?'<a class="btn btn-soft" href="'+attr(wish.shop_url)+'" target="_blank" rel="noopener noreferrer">В магазин '+ico('external')+'</a>':'';
 modal({title:wish.title,subtitle:money(wish.price_cents,wish.currency),
   content:'<div class="wish-detail">'+image+
     (wish.description?'<p>'+esc(wish.description)+'</p>':'')+
     '<div class="wish-detail-actions">'+store+actions+'</div></div>'});
}
let loadedList = null;
async function ownerListPage(id,marker=lastRenderToken){if(!currentUser)throw new Error('Войди, чтобы открыть список');const d=await api(`/api/lists/${id}`);if(marker!==lastRenderToken)return;loadedList=d;
 const l=d.list;const url=getLink(`/w/${l.share_key}`);shell(`<main class="container page"><div class="guest-topline"><button class="text-link" data-nav="/lists">${ico('back')} Мои вишлисты</button> <span>/</span> <span>${esc(l.title)}</span></div><div class="detail-top cover-${attr(l.theme)}"><div><span class="chip">${ico('gift')} ${esc(l.occasion)}</span><h1>${esc(l.title)}</h1><p>${esc(l.description||'Список маленьких и больших мечтаний')}</p></div><div class="detail-art">${fallbackArt('gift')}</div></div><div class="detail-actions"><div><h2>Желания <span class="chip">${d.wishes.length}</span></h2><p class="note">Брони друзей здесь никогда не отображаются</p></div><div class="btn-row"><button class="btn btn-soft btn-small" data-action="edit-list">${ico('edit')} Настройки</button><button class="btn btn-soft btn-small" data-action="copy" data-url="${attr(url)}" ${l.visibility==='private'?'disabled title="Сначала открой доступ по ссылке"':''}>${ico('copy')} Ссылка</button><button class="btn btn-dark btn-small" data-open="wish">Добавить желание ${ico('plus')}</button></div></div>${l.visibility==='private'?`<div class="alert">${ico('lock')} Список приватный. Доступ по ссылке выключен в настройках</div>`:''}${d.wishes.length?`<div class="wishlist-grid">${d.wishes.map(w=>wishCard(w)).join('')}</div>`:emptyState('Пока ни одного желания','Вдохновение начинается с первой идеи','Добавить желание','wish')}<div class="divider-line"></div><button class="btn btn-ghost btn-small" data-action="delete-list">${ico('trash')} Удалить весь список</button></main>`);}
let loadedPublicWishes=[];
async function publicListPage(key,marker=lastRenderToken){const {list:l,wishes,owner_view}=await api(`/api/public/${key}`);if(marker!==lastRenderToken)return;loadedPublicWishes=wishes;shell(`<main class="container page"><div class="guest-topline">${ico('gift')} <span>Вишлист по ссылке</span><span>/</span><strong>от ${esc(l.owner_name)}</strong></div><div class="detail-top cover-${attr(l.theme)}"><div><span class="chip">${ico('heart')} ${esc(l.occasion)}</span><h1>${esc(l.title)}</h1><p>${esc(l.description)}</p></div><div class="detail-art">${fallbackArt('gift')}</div></div><div class="guest-banner">${ico('lock')} ${owner_view?'Это твой список - статус бронирования для владельца скрыт':'Можешь забронировать понравившийся подарок. Владелец списка не увидит, что выбрано. После брони сохрани приватную ссылку для управления'}</div><div class="detail-actions"><h2>Желания <span class="chip">${wishes.length}</span></h2></div>${wishes.length?`<div class="wishlist-grid">${wishes.map(w=>wishCard(w,owner_view?'view':'guest',key)).join('')}</div>`:emptyState('В этом списке пока пусто','Загляни позже - здесь скоро появятся желания','На главную','login')}</main>`);}
async function reservationPage(key,marker=lastRenderToken){const {reservation:r}=await api(`/api/reservations/${key}`);if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="invite-card"><div class="invite-icon">${envelopeArt()}</div><h1>${r.cancelled_at?'Бронь отменена':'Подарок ждёт своего часа!'}</h1><p>${r.cancelled_at?'Этот подарок снова доступен другим дарителям':'Твоя бронь сохранена. Эта ссылка - личный ключ для отмены, береги её'}</p><div class="details-box"><p><strong>Подарок:</strong> ${esc(r.wish_title)}</p><p><strong>Вишлист:</strong> ${esc(r.list_title)}</p><p><strong>Даритель:</strong> ${esc(r.guest_name)}</p></div>${!r.cancelled_at?`<div class="share-field"><input class="input" readonly value="${attr(getLink(`/r/${key}`))}" aria-label="Ссылка управления бронью"><button class="btn btn-dark btn-small" data-action="copy" data-url="${attr(getLink(`/r/${key}`))}">${ico('copy')} Копировать</button></div><button class="btn btn-danger btn-small" data-action="cancel-reservation" data-token="${attr(key)}">Отменить мою бронь</button>`:''}</div></main>`);}
async function adminFeedbackPage(marker=lastRenderToken){
 const {items}=await api('/api/admin/feedback');
 if(marker!==lastRenderToken)return;
 const topic={idea:'Предложение',bug:'Ошибка',question:'Вопрос',other:'Другое'};
 shell('<main class="container page"><div class="page-hero"><div><div class="section-label">Администрирование</div><h1>Обращения пользователей</h1><p>Последние 100 обращений. Только для администратора.</p></div></div>'+
  (items.length?'<div class="feedback-inbox">'+items.map(item=>
   '<article class="panel feedback-entry"><div class="panel-heading-actions"><h2>'+esc(topic[item.topic]||item.topic)+
   '</h2><span class="chip">'+(item.status==='resolved'?'Закрыто':'Новое')+'</span></div>'+
   '<p><strong>'+esc(item.name)+'</strong> · <a href="mailto:'+attr(item.email)+'">'+esc(item.email)+'</a></p>'+
   '<p class="feedback-message">'+esc(item.message)+'</p>'+
   '<div class="panel-heading-actions"><small>'+esc(item.created_at)+'</small>'+
   '<button type="button" class="btn btn-soft btn-small" data-action="admin-feedback-status" data-id="'+item.id+
   '" data-status="'+(item.status==='resolved'?'new':'resolved')+'">'+(item.status==='resolved'?'Вернуть в новые':'Отметить решённым')+'</button></div></article>'
  ).join('')+'</div>':'<div class="panel"><p>Сообщений пока нет.</p></div>')+'</main>');
}
async function santasPage(marker=lastRenderToken){if(!currentUser){shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Под прикрытием</div><h1>Тайный Санта</h1><p>Чтобы организовать игру, нужно войти. Участникам регистрация не требуется</p></div><button class="btn btn-dark" data-open="login">Войти ${ico('arrow')}</button></div>${emptyState('Собери компанию','Укажите бюджет, зовите друзей и проведите честную жеребьёвку','Создать игру','santa')}</main>`);return;}
 const {events}=await api('/api/santas');if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Секретная служба подарков</div><h1>Тайный Санта</h1><p>Здесь живут все твои секретные обмены подарками</p></div><div class="btn-row"><button class="btn btn-dark" data-open="santa">Новая игра ${ico('plus')}</button></div></div>${events.length?`<div class="santa-grid">${events.map(e=>`<div class="santa-list-card"><a class="card-hitarea" href="/santa/${e.id}" data-nav="/santa/${e.id}" aria-label="Открыть игру ${attr(e.title)}"></a><span class="sparkle-deco">✳</span><div class="section-label">${e.status==='drawn'?'Жеребьёвка проведена':'Собираем компанию'}</div><h3>${esc(e.title)}</h3><p>${esc(e.description||'Собираем друзей для хороших сюрпризов')}</p><div class="list-bottom"><span>${ico('users')} ${e.participant_count} участников · ${dateRu(e.exchange_date)}</span><button class="text-link" data-nav="/santa/${e.id}">Открыть ${ico('arrow')}</button></div></div>`).join('')}</div>`:emptyState('Пока без секретов','Первую игру создать проще, чем выбрать подарочную бумагу','Создать игру','santa')}</main>`);}
let loadedSanta=null;
let activeGameContext=null;
let gameChatTimer=null;
let gameRosterTimer=null;
async function santaAdminPage(id,marker=lastRenderToken){return santaGamePage(id,marker);}
async function santaGamePage(id,marker=lastRenderToken,participantToken=null){
 const memberView=participantToken!==null;
 if(!memberView&&!currentUser)throw new Error('Для управления игрой нужно войти');
 const d=await api(memberView?`/api/participant/${participantToken}`:`/api/santas/${id}`);
 if(marker!==lastRenderToken)return;
 if(!memberView)loadedSanta=d;
 const e=d.event;
 if(memberView)id=e.id;
 const gameWishes=memberView?d.wishes:(d.my_wishes||[]);
  const myPrefs=memberView?d.preferences:d.my_preferences;
 activeGameContext={base:memberView?'/api/participant/'+participantToken:'/api/santas/'+id,
  event:e,richEnabled:d.rich_enabled!==false,own:gameWishes,memberView,memberId:memberView?d.participant.id:null,currentUserId:currentUser?.id,recipient:e.status==='drawn'?(memberView?d.assignment?.wish_cards:d.my_assignment?.wish_cards)||[]:[]};
 const people=d.participants;
 const selects=(id,label)=>selectField(label,id,people.map(p=>[p.id,p.name]),null);
 shell(`<main class="container page"><div class="guest-topline">${memberView? `${ico('lock')} Личный кабинет участника <span>/</span> <strong>${esc(d.participant.name)}</strong>`:`<button class="text-link" data-nav="/santas">${ico('back')} Все игры</button> <span>/</span> <span>${esc(e.title)}</span>`}</div><div class="page-hero"><div><div class="section-label">${e.status==='drawn'?'Жеребьёвка проведена':'Приглашаем участников'}</div><h1>${esc(e.title)}</h1><p>${esc(e.description||'Праздник начинается с маленькой тайны')}</p></div><span class="chip ${e.status==='drawn'?'chip-green':'chip-lilac'}">${ico(e.status==='drawn'?'check':'users')} ${e.status==='drawn'?'Игра началась':'Приём открыт'}</span></div><div class="santa-detail-layout"><div>
 <div class="panel"><div class="panel-heading-actions"><h2>Участники <span class="chip" data-santa-roster-count>${people.length}</span></h2>${!memberView&&e.status==='open'?'<button class="btn btn-soft btn-small" data-action="add-player">'+ico('plus')+' Добавить участника</button>':''}</div><div class="person-list" data-santa-roster>${people.map(p=>santaRosterPerson(p,activeGameContext)).join('')}</div>${e.status==='open'?`<div class="divider-line"></div><p class="note">Пригласи друзей по общей ссылке. Каждый сможет присоединиться без регистрации и получит собственную личную ссылку</p><div class="share-field"><input class="input" aria-label="Ссылка-приглашение" readonly value="${attr(getLink(`/join/${e.invite_key}`))}"><button class="btn btn-dark btn-small" data-action="copy" data-url="${attr(getLink(`/join/${e.invite_key}`))}">${ico('copy')} Копировать</button></div>`:''}</div>
 <div class="panel"><div class="panel-heading-actions"><h2>Мои пожелания</h2>${!memberView||currentUser?`<button class="btn btn-soft btn-small" data-action="import-own-wishes" ${memberView?`data-key="${attr(participantToken)}"`:`data-id="${id}"`}>${ico('plus')} Из вишлиста</button>`:''}</div><p class="note">Твои пожелания увидит только тот, кому выпадет тебя одаривать</p>
  <form class="form participant-preferences" id="santa-preferences-form">
    ${textArea('Что хотелось бы','wanted','Любимые цвета, увлечения, идеи',myPrefs?.wanted||'')}
    ${textArea('Чего не хотелось бы','unwanted','Что точно не подходит',myPrefs?.unwanted||'')}
    <button type="submit" class="btn btn-soft btn-small">Сохранить пожелания</button>
  </form><div class="my-wishes-list">${wishesMarkup(gameWishes)}</div>
 ${d.rich_enabled!==false?`<button class="btn btn-dark btn-small" type="button" data-action="add-game-gift">${ico('plus')} Добавить подарок</button>`:
 `<form class="form" id="legacy-santa-wish-form"><div class="share-field"><input class="input" name="title" required maxlength="130" placeholder="Название подарка"><button class="btn btn-dark btn-small" type="submit">Добавить ${ico('plus')}</button></div></form><p class="note">Подробные карточки появятся после обновления игры</p>`}</div>
 ${!memberView&&e.status==='open'?`<div class="panel"><h2>Исключения</h2><p class="note">Укажи пары, которые не должны выпадать друг другу. Ограничения работают направленно: «А → Б» означает, что А не может дарить Б</p><div class="rules-list" style="margin:17px 0">${d.exclusions.length?d.exclusions.map(r=>`<span class="rule-chip">${esc(people.find(p=>p.id===r.giver_id)?.name||'?')} → ${esc(people.find(p=>p.id===r.receiver_id)?.name||'?')} <button title="Убрать ограничение" data-action="remove-rule" data-from="${r.giver_id}" data-to="${r.receiver_id}">×</button></span>`).join(''):'<span class="muted">Пока нет исключений</span>'}</div><form class="form" id="rule-form"><div class="form-grid">${selects('giver_id','Кто дарит')}${selects('receiver_id','Кому нельзя дарить')}</div><button class="btn btn-soft btn-small" type="submit">${ico('plus')} Добавить ограничение</button></form></div>`:''}
 </div><div><div class="panel"><div class="panel-heading-actions"><h2>О событии</h2>${!memberView?`<button class="btn btn-soft btn-small" data-action="edit-santa">${ico('edit')} Изменить</button>`:''}</div><div class="details-box"><p>${ico('calendar')} <strong>Дата:</strong> ${dateRu(e.exchange_date)}</p><p>${ico('gift')} <strong>Бюджет:</strong> ${money(e.budget_cents,e.currency)}</p><p>${ico('users')} <strong>Участников:</strong> <span data-santa-event-count>${people.length}</span></p>${e.rules?`<div class="divider-line"></div><strong>Правила:</strong><p>${esc(e.rules)}</p>`:''}</div></div>
 ${!memberView&&e.status==='open'?`<div class="panel"><h2>Время раскрыть карты?</h2><p class="note">После жеребьёвки приглашения, состав и исключения будут заморожены. Каждый увидит только своего получателя</p><div class="alert">${ico('info')} Понадобится минимум 3 участника. Желательно, чтобы все успели присоединиться</div><button class="btn btn-dark" style="width:100%" data-action="draw" ${people.length<3?'disabled':''}>Провести жеребьёвку ${ico('spark')}</button></div>`:`<div class="panel"><h2>Кому ты даришь</h2>${e.status==='drawn'?secretCard(memberView?d.assignment:d.my_assignment,!memberView,memberView?participantToken:id):`<div class="secret-card">${envelopeArt()}<h2>Пока храним интригу</h2><p>Организатор ещё собирает всех участников. После жеребьёвки здесь появится конверт с твоим получателем</p></div>`}</div>`}
 ${memberView?`<div class="panel"><h2>Твоя личная ссылка</h2><p class="note">Не пересылай никому: по ней открывается твой секрет. Сохрани в закладки</p><div class="share-field"><input class="input" readonly value="${attr(getLink(`/p/${participantToken}`))}" aria-label="Личная ссылка"><button class="btn btn-dark btn-small" data-action="copy" data-url="${attr(getLink(`/p/${participantToken}`))}">${ico('copy')} Копировать</button></div></div>`:''}
 </div></div>
 ${d.rich_enabled!==false?`<section class="panel game-chat-panel" id="game-chat" aria-label="Чаты игры">
 <div class="panel-heading-actions"><h2>Чаты игры</h2><span class="chip">${ico('users')} Только участники</span></div>
 <p class="note">Общий чат открыт всем участникам. После жеребьёвки появятся личные переписки. Личность тайного дарителя не раскрывается</p>
 <div class="game-chat-tabs" role="group" aria-label="Выбрать чат">
 <button class="btn btn-soft btn-small active" type="button" data-chat-room="general" aria-pressed="true">Общий чат</button>
 ${e.status==='drawn'?'<button class="btn btn-soft btn-small" type="button" data-chat-room="to-recipient" aria-pressed="false">Моему получателю</button><button class="btn btn-soft btn-small" type="button" data-chat-room="from-santa" aria-pressed="false">Моему дарителю</button>':''}
 </div>
 <div class="game-chat-messages" role="log" aria-live="polite"><p class="note">Загружаем сообщения…</p></div>
 <form id="game-chat-form" class="game-chat-form"><label for="game-chat-input" class="sr-only">Текст сообщения</label><input id="game-chat-input" class="input" name="message" placeholder="Напиши сообщение" maxlength="500" autocomplete="off" required><button class="btn btn-dark btn-small" type="submit">Отправить ${ico('arrow')}</button></form>
 <button class="text-link game-chat-refresh" type="button" data-chat-refresh>Обновить сообщения</button>
 </section>`:`<section class="panel"><h2>Чаты игры</h2><p class="note">Чаты появятся после обновления игры. Остальные возможности доступны</p></section>`}</main>`);
 document.getElementById('santa-preferences-form')?.addEventListener('submit',async ev=>{
   ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('button');
   button.disabled=true;
   try{await api(activeGameContext.base+'/preferences',{method:'PATCH',body:readForm(form)});
    notice('Пожелания сохранены');
   }catch(err){notice(err.message,true)}finally{button.disabled=false;}
  });
  document.getElementById('rule-form')?.addEventListener('submit',async ev=>{ev.preventDefault();try{await api(`/api/santas/${id}/exclusions`,{method:'POST',body:readForm(ev.currentTarget)});notice('Исключение добавлено');await render();}catch(err){notice(err.message,true)}});
 setupGameChat(activeGameContext);
 setupSantaRoster(activeGameContext);
 document.getElementById('legacy-santa-wish-form')?.addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.currentTarget,button=form.querySelector('button');
  button.disabled=true;
  try{await api(activeGameContext.base+(memberView?'/wishes':'/my-wishes'),
         {method:'POST',body:readForm(form)});
      notice('Желание добавлено');await render();}
  catch(err){notice(err.message,true);button.disabled=false;}
 });
}
async function myWishesForAdmin(id){const res=await api(`/api/santas/${id}/my-wishes`);return wishesMarkup(res.wishes);}
function secretCard(assignment,organizer,identifier){if(!assignment||!assignment.revealed)return `<div class="secret-card">${envelopeArt()}<h2>Твой получатель ждёт внутри</h2><p>Никто, кроме тебя, не увидит это имя</p><button class="btn btn-dark" data-action="reveal" data-mode="${organizer?'owner':'participant'}" data-key="${attr(identifier)}">Узнать, кому я дарю ${ico('spark')}</button></div>`;
 return `<div class="secret-card revealed"><div class="recipient-summary">${ico('check')}<div><div class="recipient-eyebrow">Твой получатель</div><div class="recipient">${esc(assignment.receiver_name)}</div></div></div><div class="recipient-wishes">
  ${preferenceSummary(assignment.preferences)}
  <strong>Подарки получателя</strong>${assignment.wish_cards?.length?wishesMarkup(assignment.wish_cards,'recipient'):'<p class="recipient-empty">Пока без пожеланий - можно придумать сюрприз самому</p>'}</div></div>`;}
function preferenceSummary(preferences){
 const text=(label,value)=>value?'<div class="game-gift-note"><strong>'+label+'</strong><p>'+esc(value)+'</p></div>':'';
 return '<div class="participant-preferences-summary">'+
  (text('Что хотелось бы',preferences?.wanted)+text('Чего не хотелось бы',preferences?.unwanted)||
   '<p class="note">Получатель пока не оставил общих пожеланий</p>')+'</div>';
}
async function invitePage(key,marker=lastRenderToken){const {event:e,already_joined}=await api(`/api/invites/${key}`);if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="invite-card"><div class="invite-icon">${envelopeArt()}</div><div class="section-label" style="text-align:center">Тебя зовут в игру!</div><h1>${esc(e.title)}</h1><p>${esc(e.description||'Кто-то хочет устроить вам небольшой праздник')}</p><div class="invite-info"><div class="info-tile"><small>Когда обмениваемся</small><strong>${dateRu(e.exchange_date)}</strong></div><div class="info-tile"><small>Бюджет</small><strong>${money(e.budget_cents,e.currency)}</strong></div></div>${e.rules?`<div class="details-box"><strong>Правила от организатора</strong><p>${esc(e.rules)}</p></div>`:''}${already_joined?'<div class="alert">Ты уже участвуешь в этой игре. Повторное вступление не требуется</div>':e.status==='open'?`<form class="invite-form" id="join-form"><h3>Как тебя зовут?</h3><div class="field"><label for="join-name">Твоё имя</label><input id="join-name" name="name" maxlength="50" required placeholder="Например, Маша"></div><button class="btn btn-dark" type="submit">Присоединиться ${ico('arrow')}</button><p class="note" style="margin-top:15px">После вступления получишь личную ссылку - сохрани её, чтобы вернуться в игру</p></form>`:`<div class="alert">Жеребьёвка уже состоялась. Новые участники присоединиться не могут</div>`}</div></main>`);
 document.getElementById('join-form')?.addEventListener('submit',async ev=>{ev.preventDefault();const btn=ev.currentTarget.querySelector('button');btn.disabled=true;try{const r=await api(`/api/invites/${key}/join`,{method:'POST',body:readForm(ev.currentTarget)});nav(`/p/${r.participant_token}`);notice('Ты в игре! Сохрани личную ссылку');}catch(err){notice(err.message,true);btn.disabled=false;}});
}
async function participantPage(key,marker=lastRenderToken){return santaGamePage(null,marker,key);}

function passwordField(register){
 const generator=register?'<button type="button" class="password-generate" data-password-generate>'+ico('spark')+' Сгенерировать пароль</button>':'';
 return '<div class="field password-field"><div class="password-label-row"><label for="fld-password">Пароль (минимум 8 символов)</label>'+generator+'</div>'+
  '<div class="password-input-row"><input id="fld-password" name="password" type="password" placeholder="Не менее 8 символов" required minlength="8" maxlength="200" autocomplete="'+(register?'new-password':'current-password')+'">'+
  '<button type="button" class="password-visibility" data-password-visibility aria-label="Показать пароль" aria-pressed="false">'+ico('eye')+'</button></div>'+
  (register?'<p class="password-hint" id="password-hint">Используй уникальный пароль и сохрани его в менеджере паролей</p>':'')+'</div>';
}
function securePassword(){
 if(!window.crypto || !crypto.getRandomValues)throw new Error('Для генерации пароля нужно защищённое HTTPS-соединение');
 const groups=['ABCDEFGHJKLMNPQRSTUVWXYZ','abcdefghijkmnopqrstuvwxyz','23456789','!@#$%&*'];
 const alphabet=groups.join(''),random=new Uint32Array(1);
 const pick=chars=>{const limit=Math.floor(4294967296/chars.length)*chars.length;let n;do{crypto.getRandomValues(random);n=random[0];}while(n>=limit);return chars[n%chars.length];};
 const chars=groups.map(pick);
 while(chars.length<20)chars.push(pick(alphabet));
 for(let i=chars.length-1;i>0;i--){const j=Math.floor(crypto.getRandomValues(new Uint32Array(1))[0]*(i+1)/4294967296);[chars[i],chars[j]]=[chars[j],chars[i]];}
 return chars.join('');
}
function confirmationModal(email){
 modal({title:'Проверь почту 💌',subtitle:'Ещё один маленький шаг - и все желания будут под рукой',
  content:'<div class="auth-confirm-card" role="status"><span class="auth-confirm-symbol" aria-hidden="true">'+ico('mail',28)+'</span><div class="auth-confirm-message"><strong>Письмо с подтверждением отправлено!</strong><p>Загляни в <b>'+esc(email)+'</b> и перейди по ссылке из письма</p></div></div>'+
   '<p class="auth-confirm-help">Не видишь письмо? Проверь «Спам» и подожди немного! Повторная регистрация сразу после отправки не ускорит доставку</p>',
  footer:'Уже подтвердил адрес? <button type="button" data-open="login">Войти в аккаунт</button>'});
}
function loginModal(mode='login'){
 const register=mode==='register';
 modal({title:register?'Давай знакомиться!':'С возвращением!',
  subtitle:register?'Создай аккаунт, чтобы хранить свои списки и организовывать игры':'Твои желания уже соскучились',
  content:(register?field('Как тебя зовут?','name','Например, Саша','text','',true,'maxlength="40"'):'')+
   field('Почта','email','you@example.com','email','',true,'autocomplete="email"')+passwordField(register),
  submitLabel:register?'Создать аккаунт':'Войти',
  onSubmit:async form=>{
   const payload=readForm(form);
   const result=await api(register?'/api/register':'/api/login',{method:'POST',body:payload});
   if(result.pending_confirmation){confirmationModal(payload.email);return;}
   currentUser=result.user;broadcastSessionChange();notice(register?'Аккаунт создан!':'С возвращением!');nav('/',{force:true});
  },
  footer:(register?'Уже есть аккаунт?':'Нет аккаунта?')+
   ' <button type="button" data-open="'+(register?'login':'register')+'">'+(register?'Войти':'Зарегистрироваться')+'</button>'+
   (!register&&isDemo?'<p style="margin-top:12px"><button type="button" data-action="demo-login">Войти в демонстрационный аккаунт →</button></p>':'')
 });
}
function listModal(edit=null){if(!currentUser){loginModal('register');return;}
 const selected=edit||{};modal({title:edit?'Настройки вишлиста':'Новый вишлист',subtitle:edit?'Меняй оформление и доступ, когда захочешь':'Как назовём твою маленькую коллекцию желаний?',content:`${field('Название','title','Например, День рождения, ура!','text',selected.title||'',true,'maxlength="90"')}${textArea('Пара слов о списке','description','Что важно знать дарителям?',selected.description||'')}<div class="form-grid">${selectField('Повод','occasion',['Просто так','День рождения','Годовщина','Новоселье','Свадьба','Новый год','Другое'].map(v=>[v,v]),selected.occasion||'День рождения')}${selectField('Оформление','theme',[['peach','Персиковое'],['lilac','Лавандовое'],['mint','Мятное'],['yellow','Солнечное']],selected.theme||'peach')}</div>${selectField('Доступ к списку','visibility',[['link','По ссылке'],['private','Только мне']],selected.visibility||'link')}`,submitLabel:edit?'Сохранить':'Создать список',onSubmit:async form=>{const payload=readForm(form);if(edit){await api(`/api/lists/${edit.id}`,{method:'PATCH',body:payload});notice('Настройки сохранены');await render();}else{const r=await api('/api/lists',{method:'POST',body:payload});notice('Список создан!');nav(`/list/${r.id}`);}}});}
function wishModal(edit=null){
 if(!currentUser||!loadedList){notice('Сначала открой список',true);return;}
 const w=edit||{};
 modal({
  title:edit?'Редактировать желание':'Добавить желание',
  subtitle:'Можно добавить конкретную вещь или просто идею. Ссылка на магазин необязательна',
  content:
   field('Ссылка на товар (необязательно)','shop_url','https://...', 'url',w.shop_url||'')+
   '<p class="field-hint">Сохраним ссылку, а название, цену и фото ты добавишь самостоятельно</p>'+
   field('Что хочется?','title','Например, керамическая чашка','text',w.title||'',true,'maxlength="130"')+
   textArea('Комментарий','description','Цвет, размер, пожелания или настроение',w.description||'')+
   '<div class="form-grid">'+
   field('Ориентировочная цена','price','Например, 2500','number',w.price_cents!=null?w.price_cents/100:'',false,'min="0" step="0.01"')+
   selectField('Валюта','currency',[['RUB','₽ Рубли'],['EUR','€ Евро'],['USD','$ Доллары']],w.currency||'RUB')+
   '</div><div class="form-grid">'+
   selectField('Тип','kind',[['item','Конкретный подарок'],['experience','Идея / впечатление']],w.kind||'item')+
   selectField('Приоритет','priority',[['nice','Было бы здорово'],['love','Очень хочу!']],w.priority||'nice')+
   '</div>'+
   '<div class="field"><label for="wish-file">Фотография (необязательно)</label>'+
   '<div class="file-picker"><input id="wish-file" name="image" type="file" accept="image/png,image/jpeg,image/webp">'+
   '<div class="field-hint">JPG, PNG или WEBP до 2 МБ. Без фото покажем иллюстрацию</div></div></div>',
  submitLabel:edit?'Сохранить':'Добавить в список',
  onSubmit:async form=>{
   const data=readForm(form);
   delete data.image;
   const file=form.elements.image.files[0];
   if(file){
    if(file.size>2_000_000)throw new Error('Изображение должно быть меньше 2 МБ');
    data.image_data=await fileToData(file);
   }
   if(edit){
    await api('/api/wishes/'+edit.id,{method:'PATCH',body:data});
    notice('Желание обновлено');
   }else{
    await api('/api/lists/'+loadedList.list.id+'/wishes',{method:'POST',body:data});
    notice('Желание добавлено!');
   }
   await render();
  }
 });

}
function fileToData(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('Не получилось прочитать файл'));r.readAsDataURL(file)});}
function santaModal(){if(!currentUser){loginModal('register');return;}modal({title:'Создать Тайного Санту',subtitle:'Праздничный заговор начинается здесь. Ты автоматически станешь первым участником',content:`${field('Название игры','title','Например, Санта в нашем офисе','text','',true,'maxlength="100"')}${textArea('Описание','description','Кого зовём и что задумали?')}<div class="form-grid">${field('Дата обмена','exchange_date','','date')}${field('Бюджет','budget','Например, 2500','number','','','min="0" step="0.01"')}</div>${selectField('Валюта','currency',[['RUB','₽ Рубли'],['EUR','€ Евро'],['USD','$ Доллары']],'RUB')}${textArea('Дополнительные правила','rules','Что стоит учесть каждому?')}`,submitLabel:'Создать игру',onSubmit:async form=>{const r=await api('/api/santas',{method:'POST',body:readForm(form)});notice('Игра создана! Зови участников');nav(`/santa/${r.id}`);}});}

function showParticipantLink(token,name){
 const url=getLink('/p/'+token);
 modal({title:'Личная ссылка участника',subtitle:'Передай ссылку только участнику '+name+'. Кто откроет её, получит доступ к его пожеланиям и секрету',
   content:'<div class="share-field"><input class="input" readonly aria-label="Личная ссылка участника" value="'+attr(url)+'">'+
     '<button type="button" class="btn btn-dark btn-small" data-action="copy" data-url="'+attr(url)+'">'+ico('copy')+' Копировать</button></div>'+
     '<p class="note">Ссылка показывается сейчас. Позже организатор может выпустить новую, но старая перестанет работать</p>'});
}
function addPlayerModal(){
 const event=loadedSanta?.event;
 if(!event||event.status!=='open')return;
 modal({title:'Добавить участника',subtitle:'Добавь человека в игру и отправь ему персональную ссылку. Регистрация не нужна',
   content:field('Имя участника','name','Например, Маша','text','',true,'maxlength="50"'),
   submitLabel:'Добавить',onSubmit:async form=>{
     const data=readForm(form);
     const result=await api('/api/santas/'+event.id+'/participants',{method:'POST',body:data});
     await render();
     showParticipantLink(result.participant_token,data.name);
   }});
}
function santaSettingsModal(){
 const event=loadedSanta?.event;
 if(!event)return;
 const budget=event.budget_cents==null?'':String(Number(event.budget_cents)/100);
 modal({title:'Настройки игры',subtitle:'Бюджет и дату можно изменить и после жеребьёвки. Состав участников останется прежним',
   content:field('Дата обмена','exchange_date','','date',event.exchange_date||'')+
     field('Бюджет подарка','budget','Например, 2000','number',budget,false,'min="0" max="100000000" step="0.01"')+
     '<p class="field-hint">Бюджет ориентировочный и виден всем участникам</p>',
   submitLabel:'Сохранить',onSubmit:async form=>{
     await api('/api/santas/'+event.id,{method:'PATCH',body:readForm(form)});
     notice('Настройки игры обновлены');
     await render();
   }});
}
async function importOwnWishesModal(el){
 if(!currentUser){loginModal();return;}
 // One server call fetches only safe list/gift titles (no bulky image blobs).
 const collection=await api('/api/santa/library');
 const lists=collection.lists||[];
 if(!lists.length){notice('Сначала создай собственный вишлист',true);return;}
 const endpoint=el.dataset.key?'/api/participant/'+el.dataset.key+'/wishes/import':
   '/api/santas/'+el.dataset.id+'/my-wishes/import';
 const options=lists.map(l=>'<option value="'+l.id+'">'+esc(l.title)+'</option>').join('');
 modal({title:'Добавить из вишлиста',subtitle:'Выбери список и подарки. Копируются название, описание, цена, ссылка и доступное фото',
   content:'<div class="field"><label for="import-list">Вишлист</label><select id="import-list" name="list_id">'+options+'</select></div>'+
     '<div id="import-wish-choices" class="import-wish-choices" role="group" aria-label="Выбрать подарки"></div>',
   submitLabel:'Добавить выбранное',onSubmit:async form=>{
     const list_id=Number(form.querySelector('#import-list').value);
     const wish_ids=[...form.querySelectorAll('[name="wish_ids"]:checked')].map(input=>Number(input.value));
     if(!wish_ids.length)throw new Error('Выбери хотя бы один подарок');
     const result=await api(endpoint,{method:'POST',body:{list_id,wish_ids}});
     notice(result.added?'Добавлено подарков: '+result.added:'Эти подарки уже добавлены');
     await render();
   }});
 const select=modalRoot.querySelector('#import-list');
 const choices=modalRoot.querySelector('#import-wish-choices');
 const byId=new Map(lists.map(l=>[String(l.id),l.wishes||[]]));
 const show=()=>{
   if(!choices.isConnected)return;
   const gifts=byId.get(select.value)||[];
   choices.innerHTML=gifts.length?gifts.map(w=>
     '<label class="import-wish-choice"><input type="checkbox" name="wish_ids" value="'+w.id+'" checked><span>'+esc(w.title)+'</span></label>').join(''):
     '<p class="note">В этом вишлисте пока нет подарков</p>';
 };
 select.addEventListener('change',show);
 show();
}
function reserveModal(id,key){modal({title:'Забронировать подарок',subtitle:'Владелец списка не узнает, что ты выбрал. Сохрани приватную ссылку для отмены',content:`${field('Как тебя зовут?','guest_name','Например, Маша','text','',true,'maxlength="50"')}`,submitLabel:'Забронировать',onSubmit:async form=>{const r=await api(`/api/public/${key}/reserve/${id}`,{method:'POST',body:readForm(form)});nav(`/r/${r.manage_token}`);notice('Подарок за тобой!');}});}
async function confirmAction(title,subtitle,handler,label='Удалить'){modal({title,subtitle,content:'<div class="alert alert-error">Это действие нельзя отменить</div>',submitLabel:label,onSubmit:handler});}
async function dispatch(action,el){try{
 if(action==='reset-preview'){window.SHURSH_PREVIEW_RESET?.();return;}
 if(action==='logout'){await api('/api/logout',{method:'POST',body:{}});currentUser=null;broadcastSessionChange();notice('Ты вышел из аккаунта');nav('/',{force:true});}
 if(action==='demo-login'){const r=await api('/api/demo-login',{method:'POST',body:{}});currentUser=r.user;closeModal();notice('Демо-аккаунт открыт');nav('/lists');}
 if(action==='sample-list'){if(!isDemo){listModal();return;}if(!currentUser){const r=await api('/api/demo-login',{method:'POST',body:{}});currentUser=r.user;}const {lists}=await api('/api/lists');if(lists.length)nav(`/w/${lists[lists.length-1].share_key}`);else nav('/lists');}
 if(action==='copy')await clipboard(el.dataset.url);
 if(action==='contact-developer')contactDeveloperModal();
  if(action==='admin-feedback-status'){
   await api('/api/admin/feedback/'+el.dataset.id,{method:'PATCH',body:{status:el.dataset.status}});
   await adminFeedbackPage();return;
  }
 if(action==='scroll-game-gifts'){const track=el.closest('.game-gifts-carousel')?.querySelector('.game-gifts-track');if(track)track.scrollBy({left:(el.dataset.direction==='prev'?-1:1)*Math.max(180,track.clientWidth*.7),behavior:'smooth'});}
 if(action==='edit-list')listModal(loadedList.list);
 if(action==='add-game-gift')gameGiftModal();
 if(action==='show-game-gift')showGameWishDetails(el);
 if(action==='edit-game-gift'){
  const gift=activeGameContext?.own?.find(w=>Number(w.id)===Number(el.dataset.id));
  if(gift)gameGiftModal(gift);
 }
 if(action==='delete-game-gift'){
  const gift=activeGameContext?.own?.find(w=>Number(w.id)===Number(el.dataset.id));
  if(gift)confirmAction('Удалить подарок?','Подарок и его пожелания исчезнут из игры',async()=>{
   const base=activeGameContext.base;
   await api(base+(base.startsWith('/api/santas/')?'/my-wishes':'/wishes')+'/'+gift.id,{method:'DELETE'});
   notice('Подарок удалён');await render();
  });
 }
 if(action==='show-wish')showWishDetails(el);
 if(action==='edit-santa')santaSettingsModal();
 if(action==='add-player')addPlayerModal();
 if(action==='import-own-wishes')await importOwnWishesModal(el);
 if(action==='new-player-link')confirmAction('Выдать новую личную ссылку?','Старая ссылка перестанет работать. Участнику потребуется новая',async()=>{
   const player=loadedSanta.participants.find(p=>p.id===Number(el.dataset.id));
   const result=await api('/api/santas/'+loadedSanta.event.id+'/participants/'+el.dataset.id+'/new-link',{method:'POST',body:{}});
   showParticipantLink(result.participant_token,player?.name||'');
 },'Обновить ссылку');
 if(action==='edit-wish')wishModal(loadedList.wishes.find(w=>w.id===Number(el.dataset.id)));
 if(action==='delete-wish')confirmAction('Удалить это желание?','Подарок пропадёт из списка. Активная бронь тоже будет удалена',async()=>{await api(`/api/wishes/${el.dataset.id}`,{method:'DELETE'});notice('Желание удалено');await render();});
 if(action==='delete-list')confirmAction('Удалить весь вишлист?','Все желания, ссылки и связанные брони будут удалены',async()=>{await api(`/api/lists/${loadedList.list.id}`,{method:'DELETE'});notice('Список удалён');nav('/lists');});
 if(action==='reserve')reserveModal(el.dataset.id,el.dataset.key);
 if(action==='cancel-reservation')confirmAction('Отменить бронирование?','Подарок снова станет доступен другим дарителям',async()=>{await api(`/api/reservations/${el.dataset.token}`,{method:'DELETE'});notice('Бронь отменена');await render();},'Отменить бронь');
 if(action==='remove-player')confirmAction('Убрать участника?','Его приватная ссылка перестанет работать, и он не будет участвовать в жеребьёвке',async()=>{await api(`/api/santas/${loadedSanta.event.id}/participants/${el.dataset.id}`,{method:'DELETE'});notice('Участник удалён');await render();});
 if(action==='remove-rule'){await api(`/api/santas/${loadedSanta.event.id}/exclusions/${el.dataset.from}/${el.dataset.to}`,{method:'DELETE'});notice('Ограничение снято');await render();}
 if(action==='draw')modal({title:'Провести жеребьёвку?',subtitle:'После этого изменить участников и исключения уже нельзя. Имена распределятся случайно и останутся в секрете',content:`<div class="alert">Сейчас участвуют: ${loadedSanta.participants.map(p=>esc(p.name)).join(', ')}.</div>`,submitLabel:'Провести жеребьёвку',onSubmit:async()=>{await api(`/api/santas/${loadedSanta.event.id}/draw`,{method:'POST',body:{}});notice('Готово! Все подарки нашли своего дарителя');await render();}});
 if(action==='reveal'){const path=el.dataset.mode==='owner'?`/api/santas/${el.dataset.key}/reveal`:`/api/participant/${el.dataset.key}/reveal`;await api(path,{method:'POST',body:{}});notice('Секрет раскрыт!');await render();}
 }catch(err){notice(err.message,true)}}
// Invalidate sensitive owner RAM cache across browser tabs after sign-in/out.
const sessionChannel=(!isPreview&&'BroadcastChannel' in window)?
 new BroadcastChannel('shursh-session-changed'):null;
function broadcastSessionChange(){sessionChannel?.postMessage('changed');}
sessionChannel?.addEventListener('message',event=>{
 if(event.data!=='changed')return;
 clearOwnerDataCache();currentUser=null;renderStarted=false;render();
});
let renderStarted=false;
let authReturnNotice = null;
let authReturnError = false;
const authFragment=new URLSearchParams(location.hash.slice(1));
if(!isPreview && ['access_token','refresh_token','error','error_code','error_description']
    .some(key=>authFragment.has(key))){
 const params=authFragment;
 authReturnError=params.has('error')||params.has('error_code')||params.has('error_description');
 authReturnNotice=authReturnError?'Ссылка подтверждения недействительна или истекла. Попробуй зарегистрироваться снова':'Адрес электронной почты подтверждён. Теперь войди с паролем';
 // Remove provider tokens *before* any async fetch or UI rendering. The
 // application creates its own HttpOnly session cookie on password login.
 history.replaceState(null,'',location.pathname+location.search);
}
async function render(){const marker=++lastRenderToken;try{
 const path=currentPath();
 if(!renderStarted&&path==='/'&&!isPreview){
  const data=await api('/api/dashboard');
  if(marker!==lastRenderToken)return;
  currentUser=data.user;isDemo=data.demo;renderStarted=true;
  if(currentUser){seedOwnerCache('/api/dashboard',data);dashboardContent(data);}else home();
  return;
 }
 if(!renderStarted){
  const r=await api('/api/me');
  if(marker!==lastRenderToken)return;
  currentUser=r.user;isDemo=r.demo;renderStarted=true;
 }
 if(path==='/'){
  if(currentUser){if(!cachedOwnerValue('/api/dashboard'))dashboardLoading();await dashboardPage(marker);}else home();
  return;
 }
 if(!((path==='/lists'&&cachedOwnerValue('/api/lists')) || (path==='/santas'&&cachedOwnerValue('/api/santas'))))loading();
 if(path==='/lists')await listsPage();else if(/^\/list\/\d+$/.test(path))await ownerListPage(path.split('/')[2]);else if(/^\/w\/[A-Za-z0-9_-]+$/.test(path))await publicListPage(path.split('/')[2]);else if(/^\/r\/[A-Za-z0-9_-]+$/.test(path))await reservationPage(path.split('/')[2]);else if(path==='/santas')await santasPage();else if(path==='/admin/feedback')await adminFeedbackPage();else if(/^\/santa\/\d+$/.test(path))await santaAdminPage(path.split('/')[2]);else if(/^\/join\/[A-Za-z0-9_-]+$/.test(path))await invitePage(path.split('/')[2]);else if(/^\/p\/[A-Za-z0-9_-]+$/.test(path))await participantPage(path.split('/')[2]);else errorView(new Error('Похоже, такой страницы ещё нет'),'Страница потерялась');
 }catch(err){if(marker===lastRenderToken)errorView(err,err.message?.includes('404')?'Не найдена':'Страница не загрузилась');}}
document.addEventListener('click',async ev=>{
 const reveal=ev.target.closest('[data-password-visibility]');
 if(reveal){
  ev.preventDefault();
  const input=reveal.closest('.password-field')?.querySelector('input[name="password"]');
  if(!input)return;
  const visible=input.type==='password';input.type=visible?'text':'password';
  reveal.setAttribute('aria-pressed',String(visible));
  reveal.setAttribute('aria-label',visible?'Скрыть пароль':'Показать пароль');
  reveal.innerHTML=ico(visible?'eye-off':'eye');
  input.focus({preventScroll:true});return;
 }
 const generator=ev.target.closest('[data-password-generate]');
 if(generator){
  ev.preventDefault();
  try{
   const field=generator.closest('.password-field'),input=field?.querySelector('input[name="password"]');
   if(!input)return;
   input.value=securePassword();input.type='text';
   input.dispatchEvent(new Event('input',{bubbles:true}));
   const toggle=field.querySelector('[data-password-visibility]');
   toggle.setAttribute('aria-pressed','true');toggle.setAttribute('aria-label','Скрыть пароль');toggle.innerHTML=ico('eye-off');
   const hint=field.querySelector('#password-hint');
   if(hint)hint.textContent='Новый пароль создан. Сохрани его в менеджере паролей перед регистрацией';
   input.focus({preventScroll:true});
  }catch(err){notice(err.message,true)}
  return;
 }
 const n=ev.target.closest('[data-nav]');if(n){ev.preventDefault();nav(n.dataset.nav);return;}const op=ev.target.closest('[data-open]');if(op){ev.preventDefault();const key=op.dataset.open;if(key==='login'||key==='register')loginModal(key);if(key==='list')listModal();if(key==='wish')wishModal();if(key==='santa')santaModal();return;}const a=ev.target.closest('[data-action]');if(a){ev.preventDefault();await dispatch(a.dataset.action,a);}});
window.addEventListener('popstate',()=>{rememberOwnerTab();if(restoreOwnerTab(currentPath()))lastRenderToken++;else render();});window.addEventListener('hashchange',()=>{if(isPreview)render();});
if(!isPreview)render().then(()=>{if(authReturnNotice)notice(authReturnNotice,authReturnError);});
