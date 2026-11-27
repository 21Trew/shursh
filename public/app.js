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
  link:'<path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.7 1.7M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.7-1.7"/>',
   gift:'<rect x="3" y="9" width="18" height="12" rx="2"/><path d="M3 12h18M12 9v12M12 9c-6 0-6-6-2-6 2 0 2 3 2 6Zm0 0c6 0 6-6 2-6-2 0-2 3-2 6Z"/>',
  heart:'<path d="M20.8 4.9a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.3 1-1a5.5 5.5 0 0 0 0-7.8Z"/>',
  lock:'<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  qr:'<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM21 14v3h-4v4M21 21h-2"/>',
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
  home:'<path d="m3 11 9-8 9 8v10H3V11ZM9 21v-7h6v7"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>'
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
// Kept until an explicitly relevant mutation or the authenticated session ends.
const OWNER_VIEW_TTL=Number.POSITIVE_INFINITY;
const OWNER_VIEW_LIMIT=6;
let renderedOwnerTab=null;
function ownerTab(path){return !!currentUser&&['/','/lists','/santas','/friends','/profile','/notifications'].includes(path);}
function clearOwnerTabViews(paths=null){
 if(!paths){ownerTabViews.clear();return;}
 for(const path of paths)ownerTabViews.delete(path);
}
function rememberOwnerTab(){
 if(!ownerTab(renderedOwnerTab)||app.querySelector('.dashboard-skeleton, .route-skeleton'))return;
 const node=app.querySelector('#page-view > main');
 if(!node)return;
 node.remove();ownerTabViews.delete(renderedOwnerTab);ownerTabViews.set(renderedOwnerTab,{node,expires:Date.now()+OWNER_VIEW_TTL});
 while(ownerTabViews.size>OWNER_VIEW_LIMIT)ownerTabViews.delete(ownerTabViews.keys().next().value);
}
function restoreOwnerTab(path){
 if(!ownerTab(path))return false;
 const saved=ownerTabViews.get(path);
 if(!saved){ownerTabViews.delete(path);return false;}
 const view=app.querySelector('#page-view');if(!view)return false;
 ownerTabViews.delete(path);view.replaceChildren(saved.node);
 view.removeAttribute('aria-busy');app.classList.remove('route-loading');
 syncNavigationSelection(path);
 renderedOwnerTab=path;consumeSwipeArrival();
 const refreshPath=ownerApiForTab(path);
 const stale=refreshPath&&ownerEntry(refreshPath);
 if(stale&&stale.expires<=Date.now())void revalidateOwnerRead(refreshPath,stale);
 if(path==='/lists'&&view.querySelector('[data-wishlist-view="friends"][aria-selected="true"]')){
  const friends=ownerEntry('/api/friends/wishlists');
  if(friends&&friends.expires<=Date.now())void revalidateOwnerRead('/api/friends/wishlists',friends);
 }
 return true;
}

// Touch only. Native vertical scrolling and horizontally scrollable controls
// always win; never intercept OS back gestures at screen edges.
let pageSwipe=null,swipeClickUntil=0,swipeArrival=null;
function animateSwipeArrival(node,dir){
 if(!node||motionReduced()||!node.animate)return;
 node.animate([{opacity:.88,transform:'translateX('+(dir*22)+'px)'},{opacity:1,transform:'translateX(0)'}],{duration:260,easing:'cubic-bezier(.2,.7,.2,1)'});
}
function consumeSwipeArrival(){
 if(!swipeArrival)return;
 const pending=swipeArrival;swipeArrival=null;
 if(pending.path===currentPath())animateSwipeArrival(app.querySelector('#page-view > main'),pending.dir);
}
const swipeExcluded='input,textarea,select,button,a:not(.card-hitarea),[contenteditable], [role="slider"],.ui-select,.ui-calendar-popover,.game-gifts-track,.gift-gallery,.game-chat-messages,.admin-users-table-scroll,.nav,.cookie-notice';
function swipeScrollable(node,limit){
 for(let el=node;el&&el!==limit;el=el.parentElement){
  if(el.scrollWidth>el.clientWidth+3&&/auto|scroll/.test(getComputedStyle(el).overflowX))return true;
 }
 return false;
}
document.addEventListener('touchstart',event=>{
 pageSwipe=null;swipeClickUntil=0;
 if(event.touches.length!==1||!matchMedia('(max-width:760px)').matches||!currentUser)return;
 const t=event.touches[0],target=event.target instanceof Element?event.target:null;
 if(!target||target.closest(swipeExcluded)||t.clientX<24||t.clientX>innerWidth-24)return;
 const dialog=target.closest('.modal');
 if(modalRoot.firstElementChild&&!dialog)return;
 const surface=dialog||target.closest('#page-view > main');
 if(!surface||swipeScrollable(target,surface))return;
 const groups=[...surface.querySelectorAll('.wishlist-view-tabs,.santa-state-tabs,.notification-tabs,.game-chat-tabs')];
 let local=null;
 for(const group of groups){
  const active=group.querySelector('[aria-selected="true"],[aria-pressed="true"]');
  const panel=active?.getAttribute('aria-controls');
  if(group.contains(target)||(panel&&document.getElementById(panel)?.contains(target))||
     (group.matches('.game-chat-tabs')&&target.closest('#game-chat'))){local=group;break;}
 }
 if(dialog&&!local)return;
 pageSwipe={x:t.clientX,y:t.clientY,id:t.identifier,start:performance.now(),surface,local,path:currentPath(),cancelled:false};
},{passive:true});
document.addEventListener('touchmove',event=>{
 if(!pageSwipe)return;
 const t=[...event.touches].find(v=>v.identifier===pageSwipe.id);
 if(!t||event.touches.length!==1||Math.abs(t.clientY-pageSwipe.y)>Math.abs(t.clientX-pageSwipe.x)*.85+12){pageSwipe.cancelled=true;return;}
 // Claim only a clearly horizontal eligible gesture before Chromium starts
 // native gesture handling (which can swallow the following independent tap).
 // Keep vertical scrolling, edge gestures, multitouch and small moves native.
 if(!pageSwipe.cancelled&&Math.abs(t.clientX-pageSwipe.x)>14&&Math.abs(t.clientX-pageSwipe.x)>Math.abs(t.clientY-pageSwipe.y)*1.7&&event.cancelable)event.preventDefault();
},{passive:false});
document.addEventListener('touchcancel',()=>{pageSwipe=null;},{passive:true});
document.addEventListener('touchend',event=>{
 const s=pageSwipe;pageSwipe=null;
 if(!s||s.cancelled||!s.surface.isConnected||s.path!==currentPath()||performance.now()-s.start>850)return;
 const t=[...event.changedTouches].find(v=>v.identifier===s.id);if(!t)return;
 const dx=t.clientX-s.x,dy=t.clientY-s.y;
 if(Math.abs(dx)<65||Math.abs(dx)<Math.abs(dy)*1.7)return;
 const dir=dx<0?1:-1;
 if(s.local){
  const tabs=[...s.local.querySelectorAll('button[aria-selected],button[aria-pressed]')].filter(b=>!b.disabled&&!b.hidden);
  const i=tabs.findIndex(b=>b.getAttribute('aria-selected')==='true'||b.getAttribute('aria-pressed')==='true');
  if(i>=0&&tabs[i+dir]){swipeClickUntil=performance.now()+300;tabs[i+dir].click();const panel=document.getElementById(tabs[i+dir].getAttribute('aria-controls')||'')||s.local.parentElement;animateSwipeArrival(panel,dir);}
  return;
 }
 if(!ownerTab(s.path)||s.path==='/notifications')return;
 const links=[...app.querySelectorAll('.site-header .nav a[data-nav]')];
 const i=links.findIndex(a=>a.dataset.nav===s.path);
 if(i<0||!links[i+dir])return;
 swipeClickUntil=performance.now()+300;swipeArrival={path:links[i+dir].dataset.nav,dir};nav(links[i+dir].dataset.nav);
},{passive:true});
// Suppress only a compatibility click belonging to the completed swipe. A new
// touch resets the deadline; programmatic tab clicks and keyboard activation pass.
document.addEventListener('click',event=>{if(swipeClickUntil>performance.now()&&event.detail>0){event.preventDefault();event.stopImmediatePropagation();swipeClickUntil=0;}},true);

function nav(path,{force=false}={}){
 if(currentPath()===path&&!force)return;
 if(currentPath()!==path)beginToastRoute(path);
 closeCalendar();
 stopGameLifecycle();
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
const OWNER_DATA_LIMIT=32;
const OWNER_DETAIL_RETENTION=10*60*1000;
const OWNER_DETAIL_BYTES=8*1024*1024;
const ownerPending=new Map();
const apiReadPending=new Map(),apiReadControllers=new Set();
let apiReadGeneration=0;
const API_READ_TIMEOUT=15000,API_WRITE_TIMEOUT=60000;
// Bound the complete request including response body consumption. A caller's
// cancellation is independent of the deadline and never cancels another caller.
async function withApiDeadline(method,opts,task){
 const controller=new AbortController(),external=opts.signal;
 const read=method==='GET';
 if(external?.aborted)throw sessionChangedError();
 let timer,onAbort,onExternal;
 const timeout=opts.timeoutMs??(read?API_READ_TIMEOUT:API_WRITE_TIMEOUT);
 const timeoutError=new Error(read?'Сервер не ответил вовремя. Попробуй ещё раз':'Сервер не ответил вовремя. Проверь, сохранились ли изменения, прежде чем повторить');
 timeoutError.name='TimeoutError';
 let failure=sessionChangedError();
 const cancelled=new Promise((_,reject)=>{
  onAbort=()=>reject(failure);
  controller.signal.addEventListener('abort',onAbort,{once:true});
 });
 onExternal=()=>controller.abort();
 external?.addEventListener('abort',onExternal,{once:true});
 if(read)apiReadControllers.add(controller);
 timer=setTimeout(()=>{failure=timeoutError;controller.abort();},timeout);
 try{return await Promise.race([cancelled,task(controller.signal)]);}
 catch(error){if(controller.signal.aborted)throw failure;throw error;}
 finally{clearTimeout(timer);controller.signal.removeEventListener('abort',onAbort);external?.removeEventListener('abort',onExternal);apiReadControllers.delete(controller);}
}
let ownerSessionEpoch=0;
function ownerPinned(path){return !/^\/api\/(?:lists|santas)\/\d+$/.test(path);}
function pruneOwnerData(){
 const now=Date.now();
 for(const [key,entry] of ownerDataCache)
  if(!ownerPinned(key)&&!entry.promise&&entry.retainUntil<=now)ownerDataCache.delete(key);
 let detailBytes=[...ownerDataCache].reduce((sum,[key,entry])=>sum+(ownerPinned(key)?0:entry.bytes||0),0);
 while(ownerDataCache.size>OWNER_DATA_LIMIT||detailBytes>OWNER_DETAIL_BYTES){
  const key=[...ownerDataCache.keys()].find(key=>!ownerPinned(key));
  if(!key)break;
  detailBytes-=ownerDataCache.get(key)?.bytes||0;ownerDataCache.delete(key);
 }
}
function ownerEntry(path){
 pruneOwnerData();
 const entry=ownerDataCache.get(path);
 if(entry){ownerDataCache.delete(path);ownerDataCache.set(path,entry);}
 return entry;
}
function putOwnerEntry(path,entry){
 ownerDataCache.delete(path);
 ownerDataCache.set(path,{...entry,bytes:ownerPinned(path)?0:JSON.stringify(entry.value).length*2,retainUntil:Date.now()+OWNER_DETAIL_RETENTION});
 pruneOwnerData();
 return ownerDataCache.get(path);
}
function sessionChangedError(){const error=new Error('Сессия изменилась');error.name='AbortError';return error;}
let ownerCacheVersion=0;
function ownerCacheTTL(path){return /^\/api\/(?:santas|lists)\/\d+/.test(path)?30000:45000;}
function cacheableOwnerRead(path){
 return !!currentUser&&(path==='/api/friends/wishlists'||/^\/api\/(?:lists|santas|dashboard|friends|notifications)$/.test(path)||
  path==='/api/profile/me'||
  /^\/api\/(?:lists|santas)\/\d+$/.test(path));
}
function resetOwnerSession(){
 clearOwnerDataCache();currentUser=null;renderStarted=false;closeModal({immediate:true});loading();void render();
}
function verifyOwnerViewer(response,identity){
 // Local standalone server does not supply the cloud UI/version header.
 if(!identity||!response.headers.has('X-Shursh-UI-Version'))return true;
 return response.headers.get('X-Shursh-Viewer')===String(identity);
}
function dropOwnerRead(path){
 ownerDataCache.delete(path);ownerPending.delete(path);ownerRevalidating.delete(path);
}
function clearOwnerDataCache(){
 for(const controller of apiReadControllers)controller.abort();
 apiReadPending.clear();apiReadGeneration++;
 if(typeof cancelAdminUserReads==='function')cancelAdminUserReads();
 ownerCacheVersion++;ownerSessionEpoch++;ownerDataCache.clear();clearOwnerTabViews();ownerRevalidating.clear();ownerPending.clear();renderedOwnerTab=null;wishlistTabGeneration++;
 ownerWarmupIdentity=null;ownerWarmupReady=false;ownerWarmupPromise=null;
 currentOwnedWishlists=[];loadedList=null;loadedSanta=null;activeGameContext=null;wishlistCoverSlots.clear();
 if(typeof notificationModalItems!=='undefined'){notificationModalItems=[];notificationModalMore=false;notificationModalUnread=0;}
 if(typeof resetSocialBadge==='function')resetSocialBadge();
 stopGameLifecycle();
}
function invalidateOwnerDataForMutation(path){
 // A social write may change one section, but must not discard unrelated views.
 const isFriendWrite=/^\/api\/friends\//.test(path)||/^\/api\/friend-invites\/[A-Za-z0-9_-]{24}\/friend$/.test(path);
 if(path==='/api/friend-invites/me')return;
 const isNotificationWrite=/^\/api\/notifications\/(?:\d+\/read|read-all)$/.test(path);
 const isAccountWrite=path==='/api/profile/me'||path.startsWith('/api/sessions/')||/^\/api\/account\/(?:email|password)$/.test(path);
 if(isFriendWrite||isNotificationWrite||isAccountWrite){
  const tabs=isFriendWrite?['/friends','/notifications']:isNotificationWrite?['/notifications']:['/profile'];
  if(isFriendWrite){const lists=ownerTabViews.get('/lists')?.node;if(lists?.querySelector('[data-wishlist-view="friends"][aria-selected="true"]'))tabs.push('/lists');}
  clearOwnerTabViews(tabs);
  for(const endpoint of isFriendWrite?['/api/friends','/api/friends/wishlists','/api/notifications']:
    isNotificationWrite?['/api/notifications']:['/api/profile/me']){
   dropOwnerRead(endpoint);
  }
  ownerCacheVersion++;
  if(tabs.includes(renderedOwnerTab))renderedOwnerTab=null;
  return;
 }
 // Chat, reservations and support do not affect owner tab snapshots.
 if(/^\/api\/(?:santas\/\d+|member\/\d+|participant\/[^/]+)\/messages\//.test(path)
    ||/^\/api\/(?:public\/[^/]+\/reserve\/\d+|reservations\/[^/]+)$/.test(path)
    ||path==='/api/feedback'||path==='/api/incidents'||/^\/api\/admin\/feedback(?:\/|$)/.test(path))return;
 // Own gift/pref/reveal writes change one game detail, not the global game list.
 const detailMutation=path.match(/^\/api\/(santas\/\d+|member\/\d+|participant\/[^/]+)\/(?:my-wishes(?:\/|$)|wishes(?:\/|$)|preferences$|reveal$|invite-friend\/)/);
 if(detailMutation){
  if(detailMutation[1].startsWith('santas/')){ownerCacheVersion++;dropOwnerRead('/api/'+detailMutation[1]);}
  return;
 }
 // Scoped invalidation: creating a wishlist does not change Santa games,
 // and changing a Santa event does not change owned wishlists.
 const listMutation=/^\/api\/(?:lists|wishes)(?:\/|$)/.test(path);
 const santaMutation=/^\/api\/santas(?:\/|$)/.test(path) ||
  /^\/api\/(?:member\/\d+|participant\/[^/]+)\/(?:wishes(?:\/|$)|claim$|reveal$)/.test(path) ||
  /^\/api\/invites\/[^/]+\/join$/.test(path);
 if(!listMutation&&!santaMutation){ownerCacheVersion++;ownerDataCache.clear();clearOwnerTabViews();ownerRevalidating.clear();ownerPending.clear();renderedOwnerTab=null;return;}
 ownerCacheVersion++;
 const invalidTabs=['/'].concat(listMutation?['/lists']:[]).concat(santaMutation?['/santas']:[]);
 clearOwnerTabViews(invalidTabs);
 // The currently displayed page can be stale too: never put it back in RAM
 // after its successful write has invalidated the backing data.
 if(invalidTabs.includes(renderedOwnerTab))renderedOwnerTab=null;
 for(const key of new Set([...ownerDataCache.keys(),...ownerPending.keys(),...ownerRevalidating.keys()])){
  if(key==='/api/dashboard' || (listMutation&&key.startsWith('/api/lists')) ||
      (santaMutation&&key.startsWith('/api/santas')))dropOwnerRead(key);
 }
}
function seedOwnerCache(path,value,{derive=true}={}){
 if(!cacheableOwnerRead(path))return;
 putOwnerEntry(path,{value,expires:Date.now()+ownerCacheTTL(path)});
 if(derive&&path==='/api/dashboard'&&value?.user){
  if(Array.isArray(value.lists)&&!ownerDataCache.has('/api/lists'))putOwnerEntry('/api/lists',{value:{lists:value.lists},expires:Date.now()+ownerCacheTTL('/api/lists')});
  if(Array.isArray(value.events)&&!ownerDataCache.has('/api/santas'))putOwnerEntry('/api/santas',{value:{events:value.events,invitations:value.invitations||[]},expires:Date.now()+ownerCacheTTL('/api/santas')});
 }
}
function cachedOwnerValue(path){
 const entry=ownerEntry(path);
 return entry&&Object.hasOwn(entry,'value')?entry.value:null;
}
function ownerApiForTab(path){
 return ({'/':'/api/dashboard','/lists':'/api/lists','/santas':'/api/santas',
  '/friends':'/api/friends','/profile':'/api/profile/me',
  '/notifications':'/api/notifications'})[path]||null;
}
// Patch the existing tree, not the shell. Equal subtrees and live form
// controls survive; route-specific renderers supply trusted escaped markup.
let ownerPatchRoot=null;
function patchOwnerNode(old,next){
 if(old.isEqualNode(next))return;
 if(old.nodeType!==next.nodeType||old.nodeName!==next.nodeName){
  old.replaceWith(next.cloneNode(true));return;
 }
 if(old.nodeType!==1){old.nodeValue=next.nodeValue;return;}
 if(old.matches('form#social-search-form,#social-search-results,[data-notification-history],[data-notification-pagination][data-loaded]'))return;
 if(old.matches('input,textarea,select')){
  if(old.type==='checkbox'&&old.checked===old.defaultChecked){old.checked=next.checked;old.defaultChecked=next.defaultChecked;}
  return;
 }
 for(const a of [...old.attributes])if(!next.hasAttribute(a.name)&&!(a.name==='data-keyboard-focus'&&old===document.activeElement))old.removeAttribute(a.name);
 for(const a of next.attributes)if(old.getAttribute(a.name)!==a.value)old.setAttribute(a.name,a.value);
 const key=n=>n.nodeType===1?(n.getAttribute('data-render-key')||n.id||n.getAttribute('data-nav')||n.getAttribute('data-wishlist-filter')||n.getAttribute('data-santa-state')||n.getAttribute('data-message-id')||n.getAttribute('data-notification-id')||n.getAttribute('data-person-id')||n.querySelector(':scope > [data-nav]')?.getAttribute('data-nav')||(n.matches('section.panel')?n.querySelector(':scope > h2')?.firstChild?.textContent:null)||null):null;
 // Remove obsolete keyed siblings first. Otherwise deleting the first
 // card moves every surviving card before it, causing avoidable DOM mutations.
 const nextKeys=new Set([...next.childNodes].map(key).filter(Boolean));
 for(const child of [...old.childNodes]){const k=key(child);if(k&&!nextKeys.has(k))child.remove();}
 let cursor=old.firstChild;
 for(const child of [...next.childNodes]){
  const k=key(child);
  let match=null;
  if(k){for(let candidate=cursor;candidate;candidate=candidate.nextSibling){if(key(candidate)===k){match=candidate;break;}}}
  else if(cursor&&!key(cursor))match=cursor;
  if(!match){old.insertBefore(child.cloneNode(true),cursor);continue;}
  if(match!==cursor)old.insertBefore(match,cursor);
  const after=match.nextSibling;
  patchOwnerNode(match,child);cursor=after;
 }
 while(cursor){const after=cursor.nextSibling;cursor.remove();cursor=after;}
}
// Patch trusted, escaped renderer output, preserving a moved live control.
function patchRenderedMarkup(root,markup,prepare){
 const next=root.cloneNode(false);next.innerHTML=markup;
 if(prepare)prepare(next);
 if(root.isEqualNode(next))return false;
 const focused=root.contains(document.activeElement)?document.activeElement:null;
 patchOwnerNode(root,next);
 if(focused?.isConnected&&root.contains(focused)&&document.activeElement===document.body&&!focused.disabled)focused.focus({preventScroll:true});
 return true;
}
function refreshOwnerWishlistPanel(root,lists,mode){
 const panel=root.querySelector('#wishlist-view-content');if(!panel)return;
 const selected=panel.querySelector('[data-wishlist-filter][aria-pressed="true"]')?.dataset.wishlistFilter||'Все';
 const next=panel.cloneNode(false);
 next.innerHTML=mode==='friends'?friendWishlistTiles(lists):ownWishlistTiles(lists);
 const filter=[...next.querySelectorAll('[data-wishlist-filter]')].find(n=>n.dataset.wishlistFilter===selected)||next.querySelector('[data-wishlist-filter]');
 if(filter){
  for(const b of next.querySelectorAll('[data-wishlist-filter]')){b.classList.toggle('active',b===filter);b.setAttribute('aria-pressed',String(b===filter));}
  for(const tile of next.querySelectorAll('[data-occasion]'))tile.hidden=filter.dataset.wishlistFilter!=='Все'&&tile.dataset.occasion!==filter.dataset.wishlistFilter;
  for(const stack of next.querySelectorAll('[data-friend-stack]'))stack.hidden=![...stack.querySelectorAll('[data-occasion]')].some(tile=>!tile.hidden);
 }
 patchOwnerNode(panel,next);
}
function updateOwnerView(path,value){
 const tab=path==='/api/friends/wishlists'?'/lists':['/','/lists','/santas','/friends','/profile','/notifications'].find(t=>ownerApiForTab(t)===path);
 if(!tab)return;
 const root=renderedOwnerTab===tab&&currentPath()===tab?app.querySelector('#page-view > main'):ownerTabViews.get(tab)?.node;
 if(path==='/api/notifications'){
  const amount=Number(value.unread||0),label=amount?String(Math.min(99,amount)):'';
  for(const el of document.querySelectorAll('[data-notification-count]')){if(el.textContent!==label)el.textContent=label;if(el.hidden!==!amount)el.hidden=!amount;}
 }
 if(path==='/api/notifications'&&modalRoot.querySelector('.notification-dialog')){
  const recent=value.items||[];
  const oldest=recent.at(-1)?.id??0;
  const older=notificationModalItems.filter(n=>n.id<oldest);
  notificationModalItems=mergeNotificationItems(recent,older);
  if(!older.length)notificationModalMore=!!value.has_more;
  notificationModalUnread=value.unread||0;renderNotificationModalTab(notificationModalTab);
 }
 if(tab==='/lists'&&path==='/api/lists')currentOwnedWishlists=value.lists||[];
 if(!root)return;
 if(tab==='/notifications'){
  const history=root.querySelector('[data-notification-history]'),recent=root.querySelector('[data-notification-recent]');
  const pagination=root.querySelector('[data-notification-pagination]');
  if(history&&recent&&pagination?.dataset.loaded){
   const ids=new Set((value.items||[]).map(n=>String(n.id)));
   const boundary=value.items?.at(-1)?.id??0;
   // Keep rows that slid out of the recent window, but never duplicate rows
   // that returned to the recent window. Preserve explicitly loaded history.
   for(const n of [...history.querySelectorAll('[data-notification-id]')])if(ids.has(n.dataset.notificationId))n.remove();
   for(const n of [...recent.querySelectorAll('[data-notification-id]')].reverse())if(!ids.has(n.dataset.notificationId)&&Number(n.dataset.notificationId)<boundary)history.prepend(n);
  }
 }
 if(tab==='/lists'){
  const mode=root.querySelector('[data-wishlist-view][aria-selected="true"]')?.dataset.wishlistView;
  if(mode===(path==='/api/lists'?'mine':'friends'))refreshOwnerWishlistPanel(root,value.lists||[],mode);
  return;
 }
 // Render only the affected owner page using the response already in RAM.
 // shell() intercepts the markup and patches the existing main.
 const renderers={'/':()=>dashboardContent(value),'/santas':()=>santasPage(lastRenderToken,value),
  '/friends':()=>socialFriendsPage(lastRenderToken,value),'/profile':()=>socialOwnProfilePage(lastRenderToken,value),
  '/notifications':()=>socialNotificationsPage(lastRenderToken,value)};
 ownerPatchRoot=root;
 try{const result=renderers[tab]?.();if(result?.catch)void result.catch(()=>clearOwnerTabViews([tab]));}finally{ownerPatchRoot=null;}
}
const ownerRevalidating=new Map();
function revalidateOwnerRead(path,entry){
 if(!currentUser||isPreview||!entry||ownerDataCache.get(path)!==entry)return Promise.resolve();
 if(ownerRevalidating.has(path))return ownerRevalidating.get(path);
 const epoch=ownerSessionEpoch,identity=currentUser.id;
 const job=(async()=>{
  try{
   const {response,value}=await withApiDeadline('GET',{},async signal=>{
    const response=await fetch(path,{credentials:'same-origin',headers:{Accept:'application/json'},signal});
    return {response,value:response.ok?await response.json():null};
   });
   if(!response.ok){
    if((response.status===401||response.status===403||response.status===404)&&epoch===ownerSessionEpoch&&ownerDataCache.get(path)===entry){
     dropOwnerRead(path);
     if(response.status===401){resetOwnerSession();return;}
     if(!ownerPinned(path))return;
     const tab=['/','/lists','/santas','/friends','/profile','/notifications'].find(t=>ownerApiForTab(t)===path);
     if(tab)clearOwnerTabViews([tab]);
    }
    return;
   }
   if(epoch!==ownerSessionEpoch||currentUser?.id!==identity||ownerDataCache.get(path)!==entry)return;
   if(!verifyOwnerViewer(response,identity)){resetOwnerSession();return;}
   if(path==='/api/dashboard'&&value.user?.id!==identity){
    if(epoch===ownerSessionEpoch&&currentUser?.id===identity)resetOwnerSession();
    return;
   }
   if(epoch!==ownerSessionEpoch||currentUser?.id!==identity||ownerDataCache.get(path)!==entry)return;
   const changed=JSON.stringify(value)!==JSON.stringify(entry.value);
   seedOwnerCache(path,value,{derive:false});
   if(changed)updateOwnerView(path,value);
  }catch{
   // A network outage must not destroy a previously rendered private page.
  }
 })();
 ownerRevalidating.set(path,job);
 void job.finally(()=>{if(ownerRevalidating.get(path)===job)ownerRevalidating.delete(path);});
 return job;
}
let ownerWarmupIdentity=null,ownerWarmupReady=false,ownerWarmupPromise=null;
function scheduleOwnerWarmup(){
 if(isPreview||!currentUser||ownerWarmupIdentity===currentUser.id)return;
 const identity=currentUser.id,epoch=ownerSessionEpoch;
 ownerWarmupIdentity=identity;ownerWarmupReady=false;
 // Do not block the first paint. The initial dashboard already seeds lists/Santa.
 setTimeout(()=>{
  if(currentUser?.id!==identity||epoch!==ownerSessionEpoch)return;
  ownerWarmupPromise=Promise.allSettled(
   ['/api/friends','/api/profile/me','/api/notifications'].map(path=>api(path))
  ).finally(()=>{if(currentUser?.id===identity&&epoch===ownerSessionEpoch)ownerWarmupReady=true;});
 },0);
}
async function api(path,opts={}){
 if(isPreview)return window.previewApi(path,opts);
 const method=opts.method||'GET',cached=method==='GET'&&!opts.signal&&!opts.visit&&opts.timeoutMs==null&&cacheableOwnerRead(path);
 const dedup=method==='GET'&&!cached&&!opts.signal&&!opts.visit&&opts.timeoutMs==null&&!opts.body;
 const readKey=dedup?ownerSessionEpoch+':'+apiReadGeneration+':'+path:null;
 if(readKey&&apiReadPending.has(readKey))return apiReadPending.get(readKey);
 const epoch=ownerSessionEpoch,identity=currentUser?.id;
 if(cached){
  const pending=ownerPending.get(path);
  if(pending?.epoch===epoch)return pending.request;
  const entry=ownerEntry(path);
  if(entry&&Object.hasOwn(entry,'value')){
   if(entry.expires<=Date.now()){
    if(!ownerPinned(path)){
     await revalidateOwnerRead(path,entry);
     if(epoch!==ownerSessionEpoch||currentUser?.id!==identity)throw sessionChangedError();
     const refreshed=ownerDataCache.get(path);
     if(refreshed)return refreshed.value;
     return api(path,opts);
    }
    void revalidateOwnerRead(path,entry);
   }
   return entry.value;
  }
 }
 const version=ownerCacheVersion;
 const request=(async()=>{
  const headers={'Content-Type':'application/json'};
  if(opts.visit)headers['X-Shursh-Visit']='1';
  // iPadOS sometimes identifies as macOS. Only the coarse OS hint is sent.
  if((opts.visit||['/api/login','/api/register','/api/auth/complete'].includes(path))&&navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1)headers['X-Shursh-Platform']='ios';
  const {response,data}=await withApiDeadline(method,opts,async signal=>{
   const response=await fetch(path,{method,headers,credentials:'same-origin',body:opts.body?JSON.stringify(opts.body):undefined,signal});
   const data=await response.json().catch(error=>{if(signal.aborted)throw error;return {error:'Не удалось прочитать ответ сервера'};});
   return {response,data};
  });
  if(epoch!==ownerSessionEpoch||currentUser?.id!==identity)throw sessionChangedError();
  if(cached&&ownerPending.get(path)?.request!==request)return api(path,opts);
  if(cached&&((response.ok&&!verifyOwnerViewer(response,identity))||response.status===401)){resetOwnerSession();throw sessionChangedError();}
  if(!response.ok){const err=new Error(data.error||'Произошла ошибка');err.status=response.status;err.apiPath=path;err.requestId=response.headers.get('x-vercel-id')||'';err.uiVersion=response.headers.get('x-shursh-ui-version')||'';throw err;}
  if(epoch!==ownerSessionEpoch||currentUser?.id!==identity)throw sessionChangedError();
  if(cached&&ownerPending.get(path)?.request!==request)return api(path,opts);
  if(method!=='GET'){apiReadGeneration++;invalidateOwnerDataForMutation(path);}
  return data;
 })();
 if(cached){
  const pending={request,version,epoch};ownerPending.set(path,pending);
  request.then(value=>{
   if(ownerSessionEpoch===epoch&&currentUser?.id===identity&&ownerPending.get(path)===pending)seedOwnerCache(path,value,{derive:ownerCacheVersion===version});
  },()=>{}).finally(()=>{if(ownerPending.get(path)===pending)ownerPending.delete(path);});
 }
 if(readKey){
  apiReadPending.set(readKey,request);
  const cleanup=()=>{if(apiReadPending.get(readKey)===request)apiReadPending.delete(readKey);};
  void request.then(cleanup,cleanup);
 }
 return request;
}
function refreshVisibleOwner(){
 pruneOwnerData();
 if(isPreview||!currentUser||document.hidden)return;
 const path=ownerApiForTab(currentPath());
 const paths=path?[path]:[];
 if(currentPath()==='/lists'&&document.querySelector('[data-wishlist-view="friends"][aria-selected="true"]'))paths.push('/api/friends/wishlists');
 if(modalRoot.querySelector('.notification-dialog'))paths.push('/api/notifications');
 for(const key of new Set(paths)){
  const entry=ownerEntry(key);
  if(entry&&entry.expires<=Date.now())void revalidateOwnerRead(key,entry);
 }
}
setInterval(refreshVisibleOwner,45000);
document.addEventListener('visibilitychange',refreshVisibleOwner);
async function startupApi(path){
 try{return await api(path,{timeoutMs:9000,visit:true});}
 catch(error){if(error.name==='TimeoutError')throw new Error('Не удалось дождаться ответа сервера. Проверь соединение и попробуй ещё раз');throw error;}
}
// Page feedback belongs to one route. Modal errors belong to their dialog.
const pageToastRoot=document.getElementById('toast-root');
let toastRoute=currentPath(),toastRouteEpoch=0;
function toastRail(dialog=modalRoot.querySelector('.modal')){
 return dialog?.querySelector(':scope > .modal-toast-rail')||null;
}
function parkPageToast(){
 if(pageToastRoot.parentElement!==document.body)document.body.append(pageToastRoot);
}
function placePageToast(){parkPageToast();}
function clearNotice(){
 clearTimeout(toastTimeout);toastTimeout=undefined;
 pageToastRoot.replaceChildren();toastRail()?.replaceChildren();parkPageToast();
}
function beginToastRoute(path=currentPath()){
 if(path===toastRoute)return;
 toastRoute=path;toastRouteEpoch++;clearNotice();
 if(typeof cancelAdminUserReads==='function')cancelAdminUserReads();
 if(modalRoot.firstElementChild)closeModal({immediate:true});
}
function restorePageToast(){
 const n=toastRail()?.firstElementChild;
 if(!n)return;
 if(n.classList.contains('error')){n.remove();clearTimeout(toastTimeout);toastTimeout=undefined;return;}
 pageToastRoot.replaceChildren(n);placePageToast();
}
function syncToastPlacement(){
 const rail=toastRail();
 if(!rail||modalExit)return;
 if(pageToastRoot.firstElementChild){rail.replaceChildren(pageToastRoot.firstElementChild);parkPageToast();}
}
function notice(message,error=false){
 beginToastRoute();
 const n=document.createElement('div');
 n.className='toast'+(error?' error':'');
 n.setAttribute('role',error?'alert':'status');
 n.setAttribute('aria-atomic','true');
 n.textContent=error?localizedError(message):message;
 const rail=toastRail();
 pageToastRoot.replaceChildren();rail?.replaceChildren();
 if(rail&&!modalExit){rail.append(n);parkPageToast();}
 else{pageToastRoot.append(n);placePageToast();}
 clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>{n.remove();parkPageToast();},4500);
}
async function clipboard(value){const epoch=toastRouteEpoch;try{await navigator.clipboard.writeText(value);if(epoch===toastRouteEpoch)notice('Ссылка скопирована!');}catch{if(epoch!==toastRouteEpoch)return;modal({title:'Скопируй ссылку',content:`<div class="field"><label>Ссылка</label><input class="input" autofocus readonly value="${attr(value)}" onclick="this.select()"></div>`});}}
let modalContentObserver=null,authModalMotion=null,authModalFrame=0;
let modalEntrance=[],modalExit=null;
const motionReduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function cancelModalEntrance(){for(const a of modalEntrance.splice(0))a.cancel();}
function finishModalExit(){
 if(!modalExit)return;
 const exit=modalExit;modalExit=null;
 for(const a of exit.animations)a.cancel();
 if(exit.backdrop.isConnected){restorePageToast();exit.backdrop.remove();}
 if(!modalRoot.firstElementChild)document.body.style.overflow='';
}
function animateModalEntrance(backdrop,dialog){
 if(motionReduced()||!dialog.animate)return;
 const mobile=matchMedia('(max-width:760px)').matches;
 modalEntrance=[
  backdrop.animate([{opacity:0},{opacity:1}],{duration:200,easing:'ease-out'}),
  dialog.animate([{transform:mobile?'translateY(100%)':'translateY(12px) scale(.985)'},{transform:'none'}],
    {duration:280,easing:'cubic-bezier(.2,.75,.2,1)'})
 ];
 const batch=modalEntrance;
 Promise.allSettled(batch.map(a=>a.finished)).then(()=>{if(modalEntrance===batch)modalEntrance=[];});
}
// Breakpoint and keyboard resizing are geometry changes, not content animation.
window.addEventListener('resize',()=>{
 if(!modalRoot.firstElementChild)return;
 cancelModalEntrance();stopAuthModalMotion();
 if(modalExit)finishModalExit();
 else syncToastPlacement();
},{passive:true});
function stopAuthModalMotion(){
 if(authModalFrame)cancelAnimationFrame(authModalFrame);
 authModalFrame=0;
 if(authModalMotion){
  const {dialog,animation}=authModalMotion;authModalMotion=null;
  animation.cancel();dialog.classList.remove('auth-height-motion');
  dialog.style.removeProperty('--auth-dialog-height');
 }
}
function animateAuthModalHeight(dialog,from){
 if(!dialog.isConnected||dialog.classList.contains('gift-deck-modal'))return;
 const current=authModalMotion?.dialog===dialog?authModalMotion:null;
 if(current)dialog.classList.remove('auth-height-motion');
 const target=dialog.offsetHeight;
 if(current)dialog.classList.add('auth-height-motion');
 if(current&&Math.abs(target-current.target)<1)return;
 stopAuthModalMotion();
 if(!from||Math.abs(target-from)<1||matchMedia('(prefers-reduced-motion: reduce)').matches||!dialog.animate)return;
 dialog.style.setProperty('--auth-dialog-height',from+'px');
 dialog.classList.add('auth-height-motion');
 const animation=dialog.animate(
  [{'--auth-dialog-height':from+'px'},{'--auth-dialog-height':target+'px'}],
  {duration:280,easing:'cubic-bezier(.22,.68,.28,1)',fill:'both'});
 const motion={dialog,animation,target};authModalMotion=motion;
 animation.onfinish=()=>{if(authModalMotion===motion)stopAuthModalMotion();};
}
function modal({title,subtitle='',content='',onSubmit=null,onError=null,submitLabel='Сохранить',size='normal',footer='',authScreen='',nativeSubmit=false }){
 finishModalExit();cancelModalEntrance();restorePageToast();
 const priorDialog=modalRoot.querySelector('.modal');
 if(modalRoot.querySelector('.notification-dialog')){
  const bell=app.querySelector('.header-bell');if(bell)setAttrIfChanged(bell,'aria-expanded','false');
 }
 const reuseAuth=!!(authScreen&&priorDialog?.dataset.authScreen);
 const oldHeight=priorDialog?.offsetHeight||0;
 const restoreDialogFocus=reuseAuth&&priorDialog.contains(document.activeElement);
 stopAuthModalMotion();
 for(const input of modalRoot.querySelectorAll('input'))suggestionObservers.get(input)?.disconnect();

 modalContentObserver?.disconnect();modalContentObserver=null;
 closeCalendar();closeUiSelect();
 const markup=`<div class="modal-backdrop" data-backdrop><div class="modal${size==='gift-deck'?' gift-deck-modal':''}" role="dialog" aria-modal="true" aria-label="${attr(title)}"><button class="modal-close" type="button" data-close aria-label="Закрыть">×</button><div class="modal-scroll-area"><h2>${esc(title)}</h2>${subtitle?`<p class="modal-subtitle">${esc(subtitle)}</p>`:''}<form class="form" id="modal-form">${content}${onSubmit?`<div class="form-actions"><button type="button" class="btn btn-soft" data-close>Отмена</button><button type="submit" class="btn btn-dark">${esc(submitLabel)} ${ico('arrow')}</button></div>`:''}</form>${footer?`<div class="modal-foot">${footer}</div>`:''}</div></div></div>`;
 if(reuseAuth){
  const template=document.createElement('template');template.innerHTML=markup;
  const fresh=template.content.querySelector('.modal');
  priorDialog.replaceChildren(...fresh.childNodes);
  priorDialog.setAttribute('aria-label',title);
 }else modalRoot.innerHTML=markup;
 const scroller=modalRoot.querySelector('.modal-scroll-area');
 const dialog=modalRoot.querySelector('.modal');
 if(authScreen){dialog.dataset.authScreen=authScreen;dialog.tabIndex=-1;}

 const titleNode=scroller.querySelector(':scope > h2');
 if(titleNode){
  const headerRail=document.createElement('div');headerRail.className='modal-fixed-header';
  headerRail.append(titleNode,dialog.querySelector('.modal-close'));dialog.insertBefore(headerRail,scroller);
 }
 const rail=document.createElement('div');rail.className='modal-toast-rail';
 dialog.insertBefore(rail,scroller);syncToastPlacement();
 const actionRow=scroller.querySelector('#modal-form > .form-actions');
 const extra=scroller.querySelector(':scope > .modal-foot');
 if(actionRow||extra){
  const footerRail=document.createElement('div');footerRail.className='modal-fixed-footer';
  if(actionRow){actionRow.querySelector('[type=submit]')?.setAttribute('form','modal-form');footerRail.append(actionRow);}
  if(extra)footerRail.append(extra);
  dialog.append(footerRail);
 }
 enhanceSelects(modalRoot);enhanceCalendars(modalRoot);enhancePhotoPickers(modalRoot);
 // The same bounded height animation serves every dialog, not only Auth.
 if(reuseAuth){
  if(!motionReduced()&&dialog.animate){
   for(const region of dialog.querySelectorAll('.modal-fixed-header,.modal-scroll-area,.modal-fixed-footer'))
    region.animate([{opacity:.55,transform:'translateY(4px)'},{opacity:1,transform:'translateY(0)'}],
     {duration:200,easing:'ease-out'});
  }
  if(restoreDialogFocus)dialog.focus({preventScroll:true});
 }
 if(oldHeight)animateAuthModalHeight(dialog,oldHeight);
 let lastNatural=authModalMotion?.dialog===dialog?authModalMotion.target:dialog.getBoundingClientRect().height;
 let viewport=innerWidth+':'+innerHeight;
 if(typeof ResizeObserver==='function'){
  modalContentObserver=new ResizeObserver(()=>{
   if(!scroller.isConnected||authModalFrame)return;
   authModalFrame=requestAnimationFrame(()=>{
    authModalFrame=0;if(!dialog.isConnected||!scroller.isConnected||modalExit)return;
    const nextViewport=innerWidth+':'+innerHeight;
    if(nextViewport!==viewport){viewport=nextViewport;stopAuthModalMotion();lastNatural=dialog.getBoundingClientRect().height;return;}
    const from=authModalMotion?.dialog===dialog?dialog.offsetHeight:lastNatural;
    animateAuthModalHeight(dialog,from);
    lastNatural=authModalMotion?.dialog===dialog?authModalMotion.target:dialog.getBoundingClientRect().height;
   });
  });
  for(const region of dialog.querySelectorAll('.modal-fixed-header,.modal-fixed-footer,.modal-toast-rail,.modal-subtitle,#modal-form'))modalContentObserver.observe(region);
 }
 if(!priorDialog)animateModalEntrance(dialog.parentElement,dialog);
 document.body.style.overflow='hidden';const bd=modalRoot.querySelector('[data-backdrop]');if(!reuseAuth)bd.addEventListener('click',e=>{if(e.target===bd)closeModal()});modalRoot.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',closeModal));
 if(onSubmit){modalRoot.querySelector('form').addEventListener('submit',async e=>{if(nativeSubmit){if(e.defaultPrevented)return;const password=e.currentTarget.elements.password;if(password)password.type='password';return;}e.preventDefault();const btn=e.currentTarget.querySelector('[type=submit]')||modalRoot.querySelector('.modal-fixed-footer [type=submit]');if(btn.disabled)return;btn.disabled=true;const submitted=e.currentTarget,epoch=toastRouteEpoch;try{await onSubmit(submitted);if(modalRoot.querySelector('form')===submitted)closeModal();}catch(err){if(submitted.isConnected&&!modalExit&&epoch===toastRouteEpoch){if(onError)onError(err,submitted);else notice(err.message,true);}}finally{if(btn.isConnected)btn.disabled=false;}});}
 // No delayed autofocus: it can steal focus while the user types in the
 // password field, silently redirecting keystrokes to email after 10 ms.
 // Fields focus on the first intentional click; avoid noisy autofocus rings.
}
function contactDeveloperModal(){
 const path=currentPath(),route=/^\/(?:list|santa)\/[0-9]{1,10}$/.test(path)?path:incidentRoute();
 modal({title:'Написать разработчику',subtitle:'Есть идея, вопрос или найдена ошибка? Пиши прямо здесь',
  content:field('Как к тебе обращаться','name','Твоё имя','text',currentUser?.name||'',true,'maxlength="80"')+
   field('Почта для ответа','email','name@example.com','email',currentUser?.email||'',true,'maxlength="200"')+
   selectField('Тема','topic',[['idea','💡 Предложение'],['bug','🐞 Ошибка'],['question','❓ Вопрос'],['thanks','💛 Благодарность'],['other','💬 Другое']],'idea')+
   textArea('Сообщение','message','Расскажи подробнее…')+
   '<div class="feedback-options">'+shurshCheckbox('reply_email','Ответить на почту',true)+(currentUser?shurshCheckbox('notify_site','Уведомить на сайте',false):'')+'</div>',
  submitLabel:'Отправить',onSubmit:async form=>{
   const data=readForm(form);data.reply_email=form.elements.reply_email.checked;data.notify_site=!!form.elements.notify_site?.checked;data.source_route=route;
   if(!data.reply_email)data.email='';
   await api('/api/feedback',{method:'POST',body:data});notice('Обращение отправлено');
  }});
 const message=modalRoot.querySelector('#fld-message');if(message){message.required=true;message.minLength=5;message.maxLength=3000;}
 const reply=modalRoot.querySelector('[name="reply_email"]'),email=modalRoot.querySelector('#fld-email');
 const sync=()=>{email.required=reply.checked;email.disabled=!reply.checked;const field=email.closest('.field');field.hidden=!reply.checked;field.classList.toggle('hide',!reply.checked);};
 reply.addEventListener('change',sync);sync();
}
function closeModal({immediate=false}={}){
 if(modalExit){if(immediate)finishModalExit();return;}
 const backdrop=modalRoot.querySelector('.modal-backdrop'),dialog=backdrop?.querySelector('.modal');
 if(!backdrop)return;
 const wasNotifications=!!modalRoot.querySelector('.notification-dialog');
 if(wasNotifications){notificationModalItems=[];notificationModalMore=false;notificationModalUnread=0;}
 const transform=dialog?getComputedStyle(dialog).transform:'none';
 const opacity=getComputedStyle(backdrop).opacity;
 const height=dialog?.offsetHeight;
 cancelModalEntrance();stopAuthModalMotion();
 for(const input of modalRoot.querySelectorAll('input'))suggestionObservers.get(input)?.disconnect();
 modalContentObserver?.disconnect();modalContentObserver=null;closeCalendar();closeUiSelect();
 if(wasNotifications){const bell=app.querySelector('.header-bell');if(bell){setAttrIfChanged(bell,'aria-expanded','false');bell.focus({preventScroll:true});}}
 if(immediate||motionReduced()||!dialog?.animate){restorePageToast();backdrop.remove();document.body.style.overflow='';return;}
 // Do not leave controls or credentials interactive during a closing transition.
 backdrop.inert=true;backdrop.setAttribute('aria-hidden','true');
 dialog.style.setProperty('--auth-dialog-height',height+'px');dialog.classList.add('auth-height-motion');
 const mobile=matchMedia('(max-width:760px)').matches;
 const animations=[
  backdrop.animate([{opacity},{opacity:0}],{duration:210,easing:'ease-in',fill:'both'}),
  dialog.animate([{transform},{transform:mobile?'translateY(100%)':'translateY(12px) scale(.985)'}],{duration:230,easing:'cubic-bezier(.4,0,.8,.4)',fill:'both'})
 ];
 const exit={backdrop,animations};modalExit=exit;
 Promise.allSettled(animations.map(a=>a.finished)).then(()=>{if(modalExit===exit)finishModalExit();});
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(activeCalendar){e.preventDefault();closeCalendar(true);}else if(uiSelectOpen){e.preventDefault();closeUiSelect(true);}else closeModal();}});

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
 const portal=document.body;
 portal.appendChild(list);
 const r=button.getBoundingClientRect(),height=window.innerHeight,width=window.innerWidth;
 // Position the popup using its actual content height, not the maximum
 // scrolling height (which detached two-option menus from their triggers).
 const desiredHeight=Math.min(244,opts.length*44+14);
 const below=Math.max(0,height-r.bottom-12),above=Math.max(0,r.top-12);
 const useAbove=below<desiredHeight&&above>below;
 const available=useAbove?above:below;
 const menuHeight=Math.max(0,Math.min(desiredHeight,available));
 const menuWidth=Math.min(r.width,width-20);
 list.style.width=menuWidth+'px';
 list.style.maxHeight=menuHeight+'px';
 list.style.left=Math.max(10,Math.min(r.left,width-menuWidth-10))+'px';
 list.style.top=Math.max(8,Math.min(height-menuHeight-8,useAbove?r.top-6-menuHeight:r.bottom+6))+'px';
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
  // Scroll only the portal menu, never the modal behind it: outer
  // scrolling would trigger the document scroll listener and close the menu.
  if(target){
   const top=target.offsetTop,bottom=top+target.offsetHeight;
   if(top<list.scrollTop)list.scrollTop=top;
   else if(bottom>list.scrollTop+list.clientHeight)list.scrollTop=bottom-list.clientHeight;
  }
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
// Close on intentional scrolling, not layout/auto-scroll while clicking a portal
// option: the latter detached the option before Playwright and users could click.
const closeOnScrollIntent=e=>{
 if(uiSelectOpen&&!uiSelectOpen.menu.contains(e.target))closeUiSelect();
};
document.addEventListener('wheel',closeOnScrollIntent,{passive:true,capture:true});
document.addEventListener('touchmove',closeOnScrollIntent,{passive:true,capture:true});
window.addEventListener('resize',()=>closeUiSelect());


/* Shared date picker; native input retains the value for FormData. */
let activeCalendar=null;
function closeCalendar(refocus=false){
 if(!activeCalendar)return;
 const {popup,button}=activeCalendar;activeCalendar=null;popup.remove();
 button.setAttribute('aria-expanded','false');
 if(refocus&&button.isConnected)button.focus({preventScroll:true});
}
function enhanceCalendars(root){
 root.querySelectorAll('input[type="date"]:not([data-ui-calendar])').forEach(input=>{
  input.dataset.uiCalendar='true';input.classList.add('ui-calendar-native');if(input.hasAttribute('data-santa-date-input'))input.classList.add('hide');input.tabIndex=-1;input.setAttribute('aria-hidden','true');
  const button=document.createElement('button');button.type='button';button.className='ui-calendar-trigger';
  button.setAttribute('aria-label',input.closest('.field')?.querySelector('label')?.textContent||'Дата');
  button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-expanded','false');
  input.insertAdjacentElement('afterend',button);
  const iso=date=>[date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');
  const parse=value=>{
   if(!/^\d{4}-\d\d-\d\d$/.test(value||''))return null;
   const [y,m,d]=value.split('-').map(Number),dt=new Date(y,m-1,d,12);
   return dt.getFullYear()===y&&dt.getMonth()+1===m&&dt.getDate()===d?dt:null;
  };
  const sync=()=>{
   const date=parse(input.value);
   button.innerHTML='<span>'+(date?(input.hasAttribute('data-santa-date-input')?dateRu(input.value):new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'}).format(date)):'Выбери дату')+'</span>'+(input.hasAttribute('data-santa-date-input')?'':ico('calendar'));
  };
  input.addEventListener('change',sync);
  button.addEventListener('click',()=>{
   if(activeCalendar?.button===button){closeCalendar();return;}
   closeCalendar();const date=parse(input.value)||new Date();
   const popup=document.createElement('div');popup.className='ui-calendar-popover';
   popup.setAttribute('role','dialog');popup.setAttribute('aria-label','Календарь');
   const inline=input.hasAttribute('data-santa-date-input');
   const state={popup,button,inline,year:date.getFullYear(),month:date.getMonth()};activeCalendar=state;
   button.setAttribute('aria-expanded','true');(inline?document.body:modalRoot).append(popup);
   const choose=value=>{
    if(!value&&input.hasAttribute('data-santa-date-input'))return;
    if(value&&((input.min&&value<input.min)||(input.max&&value>input.max)))return;
    input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}));closeCalendar(true);
   };
   const draw=()=>{
    const first=new Date(state.year,state.month,1,12);
    const days=new Date(state.year,state.month+1,0).getDate(),skip=(first.getDay()+6)%7;
    let cells='<span></span>'.repeat(skip);
    for(let day=1;day<=days;day++){
     const value=iso(new Date(state.year,state.month,day,12));
     const disabled=(input.min&&value<input.min)||(input.max&&value>input.max);
     cells+='<button type="button" class="ui-calendar-day" data-date="'+value+'"'+(input.value===value?' aria-selected="true"':'')+(value===iso(new Date())?' data-today="true"':'')+(disabled?' disabled':'')+'>'+day+'</button>';
    }
    popup.innerHTML='<div class="ui-calendar-toolbar"><button type="button" data-shift="-1" aria-label="Предыдущий месяц">‹</button><strong>'+
     esc(new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric'}).format(first))+
     '</strong><button type="button" data-shift="1" aria-label="Следующий месяц">›</button></div>'+
     '<div class="ui-calendar-days">'+['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map(d=>'<span>'+d+'</span>').join('')+'</div>'+
     '<div class="ui-calendar-grid">'+cells+'</div><div class="ui-calendar-actions"><button type="button" data-clear>Очистить</button><button type="button" data-today>Сегодня</button></div>';
    position();
   };
   const position=()=>{
    const r=button.getBoundingClientRect(),h=popup.getBoundingClientRect().height;
    popup.style.left=Math.max(8,Math.min(r.left,innerWidth-popup.getBoundingClientRect().width-8))+'px';
    popup.style.top=Math.max(8,Math.min(r.bottom+h+8<innerHeight?r.bottom+6:r.top-h-6,innerHeight-h-8))+'px';
   };
   state.position=position;
   popup.addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.shift){const next=new Date(state.year,state.month+Number(b.dataset.shift),1,12);state.year=next.getFullYear();state.month=next.getMonth();draw();}
    else if(b.dataset.date)choose(b.dataset.date);
    else if(b.hasAttribute('data-clear'))choose('');
    else if(b.hasAttribute('data-today'))choose(iso(new Date()));
   });
   draw();
  });sync();
 });
}
document.addEventListener('pointerdown',event=>{if(activeCalendar&&!activeCalendar.popup.contains(event.target)&&!activeCalendar.button.contains(event.target))closeCalendar();});
document.addEventListener('scroll',event=>{const state=activeCalendar;if(!state||state.popup.contains(event.target))return;if(state.inline&&state.button.isConnected){state.position();}else closeCalendar();},{capture:true,passive:true});
window.addEventListener('resize',()=>closeCalendar());

function selectField(label,name,options,selected){return `<div class="field"><label for="fld-${name}">${esc(label)}</label><select id="fld-${name}" name="${name}">${options.map(([value,text])=>`<option value="${attr(value)}" ${String(value)===String(selected)?'selected':''}>${esc(text)}</option>`).join('')}</select></div>`;}
function readForm(form){return Object.fromEntries(new FormData(form).entries());}
// Use the approved crayon collection throughout the service.
function serviceArt(name,classes=''){
 const [width,height]=landingArtSizes[name];
 return `<img alt="" aria-hidden="true" class="service-art ${classes}" data-service-art="${name}" width="${width}" height="${height}" src="${landingArtPrefix}${name}.webp" loading="lazy" decoding="async" draggable="false">`;
}
function fallbackArt(type='gift'){
 return serviceArt(({gift:'step-gift',camera:'camera',cup:'cup',ticket:'ticket',book:'step-list',plant:'hero-gift'})[type]||'step-gift');
}
function artFor(w){const t=(w.title||'').toLowerCase();if(w.kind==='experience'||/билет|театр|концерт|поездк|настол/.test(t))return fallbackArt('ticket');if(/камер|фотоаппарат|плён/.test(t))return fallbackArt('camera');if(/чаш|кофе|чай/.test(t))return fallbackArt('cup');if(/книг|издани|пазл/.test(t))return fallbackArt('book');if(/растен|цвет|карандаш/.test(t))return fallbackArt('plant');return fallbackArt('gift')}
function envelopeArt(){return serviceArt('hero-mail','envelope-art');}
// Approved crayon artwork shared by the landing page and service. The script's
// release prefix also fingerprints the image bytes; the local server uses
// the same assets through its unversioned public directory.
const landingArtPrefix = (new URL(document.currentScript?.src || '/app.js',location.href).pathname.match(/^\/ui\/[a-f0-9]{20}\//)?.[0] || '/') + 'art/crayon/';
const landingArtSizes = Object.freeze({
 'hero-accents':[650,481],
 'hero-mail':[400,312],
 'hero-gift':[389,440],
 'hero-mascot':[540,611],
 'step-list':[360,310],
 'step-share':[360,310],
 'step-gift':[360,310],
 'camera':[360,310],
 'cup':[360,310],
 'ticket':[360,310],
 'santa':[800,578],
 'privacy':[480,360]
});
function landingArt(name, classes=''){
 const [width,height]=landingArtSizes[name];
 const hero=name.startsWith('hero-');
 return `<img alt="" data-art="${name}" class="${classes}" width="${width}" height="${height}" src="${landingArtPrefix}${name}.webp" decoding="async"${hero?(name==='hero-mascot'?' fetchpriority="high"':''):' loading="lazy"'}>`;
}
// Stable default art with collision-free allocation in each rendered collection.
// Each primary illustration and every companion must belong to the occasion.
const wishlistOccasionArt=Object.freeze({
 'День рождения':['step-gift','hero-gift'],
 'Годовщина':['privacy','step-share','hero-mail'],
 'Новоселье':['cup','step-gift','hero-gift'],
 'Свадьба':['step-share','privacy','hero-mail','hero-gift'],
 'Новый год':['santa','hero-gift','step-gift'],
 'Просто так':['camera','ticket','cup','step-list','step-gift','hero-gift','step-share','hero-mail','hero-mascot','privacy'],
 'Другое':['step-share','camera','hero-mascot','hero-mail','cup','ticket','step-list','step-gift','hero-gift','privacy']
});
// Require a recognizable primary motif even when the set includes gift accents.
const wishlistOccasionPrimary=Object.freeze({
 'Новоселье':['cup'],
 'Свадьба':['step-share','privacy','hero-mail'],
 'Новый год':['santa']
});
function wishlistOccasion(list){
 const occasion=typeof list.occasion==='string'?list.occasion.trim():'';
 return Object.hasOwn(wishlistOccasionArt,occasion)?occasion:'Другое';
}
const wishlistCoverSlots=new Map();
function wishlistCoverKey(list){return String(list.id??list.share_key??'')+'|'+wishlistOccasion(list);}
function wishlistCoverSeed(list){
 const key=String(list.id??list.share_key??'');
 if(/^\d+$/.test(key))return Number(BigInt(key)%100n);
 let h=0;for(const ch of key)h=(Math.imul(h,31)+ch.charCodeAt(0))>>>0;return h%100;
}
function wishlistCoverParts(list,slot){
 const occasion=wishlistOccasion(list),pool=wishlistOccasionArt[occasion];
 const primary=wishlistOccasionPrimary[occasion]||pool;
 const parts=[primary[slot%primary.length]],n=pool.length;
 let remaining=Math.floor(slot/primary.length)-1;
 while(remaining>=0){parts.push(pool[remaining%n]);remaining=Math.floor(remaining/n)-1;}
 return parts;
}
function assignWishlistCovers(lists){
 const used=new Set(),ordered=[...lists].sort((x,y)=>wishlistCoverKey(x).localeCompare(wishlistCoverKey(y),'en',{numeric:true}));
 const result=new Map();
 for(const list of ordered){
  const key=wishlistCoverKey(list);if(result.has(key))continue;
  let slot=wishlistCoverSlots.get(key)??wishlistCoverSeed(list)%4;
  if(used.has(wishlistCoverParts(list,slot).join('|'))){
   slot=0;while(used.has(wishlistCoverParts(list,slot).join('|')))slot++;
  }
  used.add(wishlistCoverParts(list,slot).join('|'));result.set(key,slot);wishlistCoverSlots.set(key,slot);
 }
 return result;
}
function wishlistCover(list,assignments){
 if(list.cover_path)return '<span class="wishlist-cover-art custom-wishlist-cover"><img loading="lazy" decoding="async" alt="" src="'+attr(list.cover_path)+'"></span>';
 const key=wishlistCoverKey(list),slot=assignments?.get(key)??wishlistCoverSlots.get(key)??wishlistCoverSeed(list)%4;
 const [primary,...companions]=wishlistCoverParts(list,slot);
 const mirrored=companions.length&&[primary,...companions].every(name=>['step-gift','hero-gift'].includes(name));
 return `<span class="wishlist-cover-art${companions.length?' wishlist-cover-paired':''}${mirrored?' wishlist-cover-gifts-reversed':''}" data-cover-variant="${attr(wishlistOccasion(list)+':'+slot)}">${serviceArt(primary)}${companions.length?`<span class="cover-companions">${companions.map(name=>serviceArt(name)).join('')}</span>`:''}</span>`;
}
function heroArt(){return `<div class="hero-stage" aria-hidden="true">${landingArt('hero-accents','hero-layer')}${landingArt('hero-mail','hero-layer float-one')}${landingArt('hero-gift','hero-layer float-two')}${landingArt('hero-mascot','hero-layer wobble')}</div>`;}
function santaArt(){return landingArt('santa');}
function stepArt(num){return landingArt(['step-list','step-share','step-gift'][num-1]);}
function navigationSection(path){
 if(path==='/lists'||path.startsWith('/list/'))return '/lists';
 if(path==='/santas'||path.startsWith('/santa/'))return '/santas';
 if(path==='/profile'||path.startsWith('/users/')||path.startsWith('/u/'))return '/profile';
 if(path==='/friends')return '/friends';
 if(path==='/admin'||path.startsWith('/admin/'))return '/admin';
 return path==='/'?'/':null;
}
function setAttrIfChanged(node,key,value){
 if(node.getAttribute(key)!==value)node.setAttribute(key,value);
}
function syncNavigationSelection(path=currentPath()){
 const section=navigationSection(path);
 for(const link of app.querySelectorAll('.site-header .nav [data-nav]')){
  const href=link.dataset.nav,selected=href===section;
  if(link.classList.contains('active')!==selected)link.classList.toggle('active',selected);
  if(selected)setAttrIfChanged(link,'aria-current',href===path?'page':'location');
  else if(link.hasAttribute('aria-current'))link.removeAttribute('aria-current');
 }
 const active=app.querySelector('.site-header .nav [aria-current]');
 const rail=active?.parentElement;
 if(rail&&matchMedia('(max-width:760px)').matches){const x=active.offsetLeft-rail.offsetLeft; if(x<rail.scrollLeft||x+active.offsetWidth>rail.scrollLeft+rail.clientWidth)rail.scrollLeft=Math.max(0,x-(rail.clientWidth-active.offsetWidth)/2);}
 const bell=app.querySelector('.header-bell');
 if(bell&&bell.classList.contains('active')!==(path==='/notifications'))bell.classList.toggle('active',path==='/notifications');
}
function syncSelection(group,chosen,attribute){
 const buttons=group.querySelectorAll(attribute==='aria-selected'?'[role="tab"]':'button[aria-pressed]');
 for(const b of buttons){
  const selected=b===chosen;
  if(b.classList.contains('active')!==selected)b.classList.toggle('active',selected);
  setAttrIfChanged(b,attribute,String(selected));
  if(attribute==='aria-selected'&&b.tabIndex!==(selected?0:-1))b.tabIndex=selected?0:-1;
 }
 if(attribute==='aria-selected'){
  const panel=chosen.getAttribute('aria-controls');
  const region=panel&&document.getElementById(panel);
  if(region)setAttrIfChanged(region,'aria-labelledby',chosen.id);
 }
}
// Automatic activation for the existing local tablists; native links retain
// their browser keyboard semantics. Focus is separate from selected paint.
document.addEventListener('keydown',event=>{
 const tab=event.target.closest('[role="tab"]');
 const group=tab?.closest('[role="tablist"]');
 if(!group||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
 const buttons=[...group.querySelectorAll('[role="tab"]:not(:disabled)')],index=buttons.indexOf(tab);
 if(index<0)return;
 const key=event.key;
 const next=key==='Home'?0:key==='End'?buttons.length-1:key==='ArrowRight'?(index+1)%buttons.length:key==='ArrowLeft'?(index+buttons.length-1)%buttons.length:-1;
 if(next<0)return;
 event.preventDefault();
 const target=buttons[next];
 // Preserve keyboard modality through synthetic activation, including WebKit.
 if(!target.hasAttribute('data-keyboard-focus'))target.setAttribute('data-keyboard-focus','');
 target.focus();target.click();
});
document.addEventListener('focusout',event=>{
 if(event.target instanceof Element)event.target.removeAttribute('data-keyboard-focus');
});
document.addEventListener('pointerdown',()=>{
 const focused=document.activeElement;
 if(focused?.hasAttribute('data-keyboard-focus'))focused.removeAttribute('data-keyboard-focus');
},true);
function header(){const path=currentPath();return `<header class="site-header"><div class="container topbar"><a class="logo" href="/" data-nav="/" aria-label="Шурш! Главная">шурш<span>!</span></a>${currentUser?`<nav class="nav" aria-label="Главная навигация"><a href="/" data-nav="/" class="${navigationSection(path)==='/'?'active':''}"${navigationSection(path)==='/'?' aria-current="'+(path==='/'?'page':'location')+'"':''}>${currentUser?'Кабинет':'Главная'}</a><a href="/lists" data-nav="/lists" class="${navigationSection(path)==='/lists'?'active':''}"${navigationSection(path)==='/lists'?' aria-current="'+(path==='/lists'?'page':'location')+'"':''}>Вишлисты</a><a href="/santas" data-nav="/santas" class="${navigationSection(path)==='/santas'?'active':''}"${navigationSection(path)==='/santas'?' aria-current="'+(path==='/santas'?'page':'location')+'"':''}>Тайный Санта</a>${!isPreview?`<a href="/friends" data-nav="/friends" class="${navigationSection(path)==='/friends'?'active':''}"${navigationSection(path)==='/friends'?' aria-current="'+(path==='/friends'?'page':'location')+'"':''}>Друзья</a><a href="/profile" data-nav="/profile" class="${navigationSection(path)==='/profile'?'active':''}"${navigationSection(path)==='/profile'?' aria-current="'+(path==='/profile'?'page':'location')+'"':''}>Профиль</a>${currentUser.is_admin?`<a href="/admin" data-nav="/admin" class="${navigationSection(path)==='/admin'?'active':''}"${navigationSection(path)==='/admin'?' aria-current="'+(path==='/admin'?'page':'location')+'"':''}>Админка</a>`:''}`:''}</nav>`:""}<div class="header-actions">${currentUser?`<button class="header-bell ${path==='/notifications'?'active':''}" type="button" data-social-action="open-notifications" aria-haspopup="dialog" aria-expanded="false" title="Уведомления" aria-label="Уведомления">${ico('bell',21)}<span class="nav-unread" data-notification-count hidden></span></button><button class="header-avatar" type="button" data-nav="/profile" aria-label="Открыть профиль" title="Открыть профиль">${esc(currentUser.avatar_emoji||"🎁")}</button><button class="btn btn-ghost" data-action="logout" title="Выйти">${ico('logout')} Выйти</button>`:`<button class="btn btn-ghost" data-open="login">Войти</button>`}</div></div></header>${isPreview?`<div class="preview-ribbon"><div class="container">Интерактивное демо · данные хранятся только в этом браузере · ссылки не работают на других устройствах <button type="button" data-action="reset-preview">Сбросить демо</button></div></div>`:''}`;}
function footer(){return `<footer class="container footer"><div><a class="logo" data-nav="/" href="/">шурш<span>!</span></a><small>Место для хотелок и сюрпризов</small></div><p class="footer-credit">Сделано с заботой о сюрпризах <span aria-hidden="true">·</span> <button class="footer-developer" type="button" data-action="contact-developer">L-code</button></p></footer>`;}
let shellUserSignature='';
let headerScrollQueued=false;
let headerIsCondensed=false;
function updateScrollTopButton(){
 const btn=document.getElementById('scroll-to-top');
 if(btn){const visible=scrollY>440;if(btn.classList.contains('is-visible')!==visible)btn.classList.toggle('is-visible',visible);if(btn.tabIndex!==(visible?0:-1))btn.tabIndex=visible?0:-1;setAttrIfChanged(btn,'aria-hidden',String(!visible));}
}
// A fixed overlay cannot change document scroll height. Hysteresis prevents
// flip-flopping near the collapse threshold without any extra DOM reads.
function syncHeaderDensity(){
 const next=headerIsCondensed?scrollY>36:scrollY>100;
 if(next===headerIsCondensed)return;
 headerIsCondensed=next;
 document.querySelector('.site-header')?.classList.toggle('is-condensed',next);
}
window.addEventListener('scroll',()=>{
 updateScrollTopButton();
 if(headerScrollQueued)return;
 headerScrollQueued=true;
 requestAnimationFrame(()=>{
  headerScrollQueued=false;syncHeaderDensity();
 });
},{passive:true});

// Existing mobile nav gets passive scroll cues; no new elements or fetches.
let navigationCueNode=null;
let navigationCueObserver=null;
function attachNavigationScrollCue(){
 const nav=app.querySelector('.site-header .nav');
 if(nav===navigationCueNode)return;
 navigationCueObserver?.disconnect();
 navigationCueObserver=null;
 navigationCueNode=nav;
 if(!nav)return;
 let scheduled=false;
 const sync=()=>{
  const remaining=Math.max(0,nav.scrollWidth-nav.clientWidth);
  const right=remaining>2&&nav.scrollLeft<remaining-2,left=remaining>2&&nav.scrollLeft>2;
  if(nav.classList.contains('nav-scroll-more-right')!==right)nav.classList.toggle('nav-scroll-more-right',right);
  if(nav.classList.contains('nav-scroll-more-left')!==left)nav.classList.toggle('nav-scroll-more-left',left);
 };
 const schedule=()=>{
  if(scheduled)return;
  scheduled=true;
  requestAnimationFrame(()=>{scheduled=false;if(nav.isConnected)sync();});
 };
 nav.addEventListener('scroll',schedule,{passive:true});
 if(typeof ResizeObserver==='function'){
  navigationCueObserver=new ResizeObserver(schedule);
  navigationCueObserver.observe(nav);
  nav.querySelectorAll('a').forEach(link=>navigationCueObserver.observe(link));
 }
 requestAnimationFrame(sync);
 if(document.fonts?.ready)void document.fonts.ready.then(schedule);
}
function ensureCookieNotice(){
 if(document.querySelector('.cookie-notice'))return;
 try{if(localStorage.getItem('shursh-cookie-notice-v1')==='yes')return;}catch{}
 const node=document.createElement('div');node.className='cookie-notice';node.setAttribute('role','status');
 node.innerHTML='<span class="cookie-message"><span>Используем необходимые cookie</span><span>для входа и работы сайта</span></span><button type="button" data-action="cookie-ack" aria-label="Понятно">Понятно</button>';
 app.querySelector('#page-view').before(node);
}
function shell(body){
 const hadPageToast=!!pageToastRoot.firstElementChild;
 parkPageToast();
 if(ownerPatchRoot){
  const template=document.createElement('template');template.innerHTML=body;
  const next=template.content.firstElementChild;
  if(next){
   const santaState=ownerPatchRoot.querySelector('[data-santa-state][aria-selected="true"]')?.dataset.santaState;
   if(santaState==='finished'){
    for(const tab of next.querySelectorAll('[data-santa-state]')){
     const active=tab.dataset.santaState===santaState;
     tab.classList.toggle('active',active);tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
    }
    const panel=next.querySelector('#santa-state-panel');if(panel)panel.setAttribute('aria-labelledby','santa-tab-finished');
    for(const card of next.querySelectorAll('[data-santa-card-state]'))card.hidden=card.dataset.santaCardState!==santaState;
    const empty=next.querySelector('.santa-state-empty');if(empty){empty.hidden=!!next.querySelector('[data-santa-card-state="finished"]');empty.innerHTML='<h3>Пока нет завершённых игр</h3><p>Законченные игры появятся здесь</p>';}
   }
   patchOwnerNode(ownerPatchRoot,next);
  }
  if(hadPageToast)placePageToast();
  return;
 }
 const identity=(currentUser?.id??'guest')+':'+(currentUser?.name??'')+':'+(currentUser?.avatar_emoji??'')+':'+!!currentUser?.is_admin+':'+isDemo+':'+isPreview;
 let view=app.querySelector('#page-view');
 if(!view){
  document.body.append(pageToastRoot);
   app.innerHTML=header()+'<div id="page-view"></div>'+footer();
  if(!document.getElementById('scroll-to-top')){
   const top=document.createElement('button');
   top.id='scroll-to-top';top.type='button';top.className='scroll-to-top';top.setAttribute('aria-label','Наверх');
   top.innerHTML=ico('back',22);
   top.addEventListener('click',()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));
   document.body.append(top);
   updateScrollTopButton();
  }
  view=app.querySelector('#page-view');shellUserSignature=identity;
 }else if(shellUserSignature!==identity){
  const head=app.querySelector('.site-header');
  if(head)head.outerHTML=header();
  app.querySelector('.site-header')?.classList.toggle('is-condensed',headerIsCondensed);
  shellUserSignature=identity;
 }
 ensureCookieNotice();
 syncNavigationSelection();
 attachNavigationScrollCue();
  closeUiSelect();view.innerHTML=body;enhanceSelects(view);view.removeAttribute('aria-busy');app.classList.remove('route-loading');
   if(hadPageToast)placePageToast();else parkPageToast();
 renderedOwnerTab=ownerTab(currentPath())?currentPath():null;consumeSwipeArrival();
 document.title='Шурш! - вишлисты и Тайный Санта';
 if(currentUser&&!isPreview){
  if(typeof socialRefreshBadge==='function')void socialRefreshBadge();
  scheduleOwnerWarmup();
 }
}

function santaTone(id){
 return ['apricot','lilac','mint','butter'][Math.abs(Number(id)||0)%4];
}
function santaCardArt(id){const motifs=['santa','step-gift','hero-gift','hero-mail'];return motifs[Math.abs(Number(id)||0)%motifs.length];}
function santaGameCard(game,{shared=false}={}){
 const status=game.status==='finished'?'Игра завершена':game.status==='drawn'?'Жеребьёвка проведена':'Собираем участников';
 const detail=shared?(dateRu(game.exchange_date)+' · '+status):(game.description||'Праздник уже на горизонте!');
 const meta=shared?dateRu(game.exchange_date):ruCount(game.participant_count||0,'участник','участника','участников');
 return '<article class="dashboard-santa-card santa-tone-'+santaTone(game.id)+'">'+
  '<a class="card-hitarea" href="/santa/'+game.id+'" data-nav="/santa/'+game.id+'" aria-label="Открыть игру '+attr(game.title)+'"></a>'+
  '<div class="dashboard-santa-symbol">'+serviceArt(santaCardArt(game.id))+'</div>'+
  '<div class="section-label">'+status+'</div><h3>'+esc(game.title)+'</h3><p>'+esc(detail)+'</p>'+
  '<div class="dashboard-card-footer"><span>'+esc(meta)+'</span>'+
  '<button class="text-link" type="button" data-nav="/santa/'+game.id+'">Открыть '+ico('arrow')+'</button></div></article>';
}
function dashboardContent(data){
 const lists=Array.isArray(data.lists)?data.lists:[];
 const events=Array.isArray(data.events)?data.events:[];
 const name=esc((currentUser.name||'Друг').trim().split(/\s+/)[0]);
 const coverAssignments=assignWishlistCovers(lists);
 const recentLists=lists.slice(0,3).map(l=>listCard(l,coverAssignments)).join('');
 const recentEvents=events.slice(0,3).map(e=>santaGameCard(e)).join('');
 shell('<main class="container dashboard-page">'+
  '<section class="dashboard-welcome"><div><h1><span class="welcome-intro">С возвращением,</span> <em class="welcome-name'+(name.length>14?' welcome-name-long':'')+'">'+name+'!</em></h1>'+
  '<p>Хорошие сюрпризы начинаются здесь. Есть новые идеи подарков?</p>'+
  '<div class="btn-row"><button class="btn btn-peach dashboard-new-list" data-open="list">Новый вишлист '+ico('plus')+'</button>'+
  '<button class="btn btn-lilac santa-create-cta" data-open="santa">Тайный Санта '+ico('plus')+'</button></div></div>'+
  '<div class="dashboard-welcome-art" aria-hidden="true">'+fallbackArt('gift')+'</div></section>'+
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
  '<h1><span class="welcome-intro">С возвращением,</span> <em class="welcome-name'+(name.length>14?' welcome-name-long':'')+'">'+name+'!</em></h1>'+
  '<p>Хорошие сюрпризы начинаются здесь</p>'+
  '<div class="btn-row"><button class="btn btn-peach dashboard-new-list" data-open="list">Новый вишлист '+ico('plus')+'</button>'+
  '<button class="btn btn-lilac santa-create-cta" data-open="santa">Тайный Санта '+ico('plus')+'</button></div></div>'+
  '<div class="dashboard-welcome-art" aria-hidden="true">'+fallbackArt('gift')+'</div></section>'+
  '<section class="dashboard-skeleton" role="status" aria-label="Загружаем списки и игры"><div class="skeleton-cards"><div class="skeleton-card"></div><div class="skeleton-card"></div></div></section></main>');
}
async function dashboardPage(marker=lastRenderToken){
 if(!currentUser){home();return;}
 const data=isPreview?await Promise.all([api('/api/lists'),api('/api/santas')]).then(([a,b])=>({user:currentUser,lists:a.lists,events:b.events})):await api('/api/dashboard');
 if(marker!==lastRenderToken)return;
 if(!isPreview&&!data.user){clearOwnerDataCache();currentUser=null;home();return;}
 dashboardContent(data);
}
function home(){shell(`<main><section class="container hero"><div class="hero-copy"><div class="eyebrow">${ico('spark')} Сервис хороших сюрпризов</div><h1>Подарки, о которых <em>не нужно</em> догадываться</h1><p class="hero-description">Собирай желания, делись ими с близкими и устраивай Тайного Санту без бумажек и путаницы</p><div class="btn-row"><button class="btn btn-dark" data-open="list">Создать вишлист ${ico('arrow')}</button><button class="btn btn-peach" data-open="santa">Играть в Тайного Санту ${ico('gift')}</button></div></div><div class="hero-visual"><div class="tiny-bubble bubble-heart">${ico('heart')} кое-кто уже мечтает</div>${heroArt()}<div class="tiny-bubble bubble-gift">сюрприз на подходе</div></div></section>
 <div class="marquee-line"><div class="marquee-inner"><span>Меньше «что подарить?»</span><span>Больше «как ты угадал!»</span><span>Сюрпризы без спойлеров</span><span>Повод найдётся всегда</span></div></div>
 <section class="container section" id="how"><div class="section-intro"><div><div class="section-label">01 / Очень просто</div><h2>Три шага до<br>«вау, это же оно!»</h2></div><p>Никаких таблиц, бесконечных переписок и загадочных намёков</p></div><div class="steps">${[['Собери желания','Добавляй вещи, идеи и впечатления. С ценой или без неё'],['Поделись ссылкой','Отправь список кому хочешь - даже тем, кто здесь впервые'],['Получай сюрпризы','Друзья договорятся о подарках. А ты ничего не узнаешь раньше времени']].map((x,i)=>`<div class="step"><span class="step-number">0${i+1} / 03</span><div class="step-art">${stepArt(i+1)}</div><h3>${x[0]}</h3><p>${x[1]}</p></div>`).join('')}</div></section>
 <section class="container"><div class="showcase"><div class="blob"></div><div class="showcase-copy"><div class="section-label">02 / Выглядит как мечта</div><h2>Списки, которыми хочется делиться</h2><p>Красивое место для маленьких и больших желаний. От керамической чашки до поездки на край света</p><button class="btn btn-dark" data-action="sample-list">${isDemo?'Посмотреть пример':'Создать свой список'} ${ico('arrow')}</button></div><div class="showcase-mock"><div class="mock-top"><h3>Сашин день рождения ♡</h3><span class="chip chip-peach">4 желания</span></div><div class="mock-items">${[['camera','Плёночный фотоаппарат','8 900 ₽'],['cup','Керамическая чашка','2 500 ₽'],['ticket','Билеты в театр','Впечатление']].map((a,i)=>`<div class="mock-item"><div class="mock-art" style="background:${['#f4e7dd','#e9e2f5','#e4f0e4'][i]}">${landingArt(a[0])}</div><div class="mock-copy"><strong>${a[1]}</strong><small>${a[2]}</small></div></div>`).join('')}</div></div></div></section>
 <section class="container section"><div class="santa-feature"><div class="santa-art">${santaArt()}</div><div class="santa-copy"><div class="section-label">03 / Немного волшебства</div><h2>Тайный Санта без бумажек и хитростей</h2><p>Зови компанию, задавай бюджет и правила. Мы честно перемешаем имена и сохраним интригу</p><div class="feature-tick">${ico('check')} Никто не вытянет сам себя</div><div class="feature-tick">${ico('check')} Можно исключать неудобные пары</div><div class="feature-tick">${ico('check')} Каждый видит только свой секрет</div><button class="btn btn-dark" style="margin-top:25px" data-open="santa">Организовать игру ${ico('arrow')}</button></div></div></section>
 <section class="container"><div class="privacy-strip"><div class="privacy-illustration">${landingArt('privacy')}</div><div><div class="section-label">04 / Тс-с, секрет!</div><h2>Бронируй подарок. Не выдавай сюрприз</h2><p>Друг выбрал подарок? Он отметит его занятым, чтобы никто не купил такой же. Владелец списка не увидит бронирование в своём кабинете. Даритель получит отдельную ссылку для отмены</p></div></div></section>
 <section class="container section"><div class="section-intro"><div><div class="section-label">05 / Дарить без повода - тоже повод</div><h2>Для всех ваших<br>«хочу порадовать»</h2></div></div><div class="occasions">${[['gift','День рождения'],['heart','Годовщина'],['home','Новоселье'],['spark','Просто так'],['users','Свадьба'],['star','Любой праздник']].map(a=>`<span class="occasion-chip">${ico(a[0])} ${a[1]}</span>`).join('')}</div></section>
 <section class="container"><div class="final-cta"><div><h2>Пусть хорошие подарки случаются чаще</h2><p>Первый список можно собрать прямо сейчас</p></div><button class="btn btn-dark" data-open="list">Создать свой список ${ico('arrow')}</button></div></section></main>`);}
const loadingHelpMarkup='<div class="loading-help"><p>Загрузка занимает больше времени, чем обычно</p><a class="btn btn-soft" href="/">Повторить загрузку</a></div>';
function loading(){
 parkPageToast();
 renderedOwnerTab=null;
 const view=app.querySelector('#page-view');
 if(view&&renderStarted){
  // The old view has been detached. Render a lightweight loading skeleton
  // rather than leaving a blank screen for the duration of the API call.
  syncNavigationSelection();
  app.classList.add('route-loading');
  view.setAttribute('aria-busy','true');
  view.innerHTML='<main class="container page route-skeleton" role="status" aria-label="Загружаем страницу">'+
    '<div class="skeleton-bar skeleton-kicker"></div>'+
    '<div class="skeleton-bar skeleton-title"></div>'+
    '<div class="skeleton-bar skeleton-subtitle"></div>'+
    '<div class="skeleton-cards"><div class="skeleton-card"></div><div class="skeleton-card"></div></div>'+
    '</main>';
  return;
 }
 document.body.append(pageToastRoot);
 app.innerHTML=header()+'<div class="loading-screen"><div class="loading-mark">шурш<span>!</span></div><div class="loading-line"></div>'+loadingHelpMarkup+'</div>';
}
function localizedError(value){
 const message=typeof value==='string'?value:value?.message;
 if(typeof message==='string'&&/[А-Яа-яЁё]/.test(message)&&!/[<>]/.test(message))return message;
 return 'Не получилось выполнить действие. Попробуй ещё раз';
}
function incidentType(err){
 if(err?.name==='ReferenceError'||err?.name==='SyntaxError')return 'module';
 if(err?.status===404)return 'not_found';
 if([401,403].includes(err?.status))return 'access';
 if(err?.status>=500)return 'server';
 if(err?.name==='TypeError'||err?.name==='AbortError')return 'network';
 return 'unknown';
}
function incidentRoute(){
 const path=currentPath();
 if(['/','/lists','/santas','/friends','/profile','/notifications','/admin','/admin/users','/admin/feedback','/admin/audit'].includes(path))return path;
 if(/^\/(?:list|santa|users|u|w|r|i|join|p)\//.test(path))return '/'+path.split('/')[1]+'/*';
 return 'other';
}
function incidentApiRoute(path){
 if(typeof path!=='string')return '';
 const clean=path.split('?')[0];
 if(/^\/api\/(?:me|dashboard|lists|santas|friends|profile\/me|notifications|notifications\/unread|admin\/users|admin\/overview|admin\/feedback|admin\/audit)$/.test(clean))return clean;
 const m=clean.match(/^\/api\/(lists|santas|users|u|public|invites|member|participant|friend-invites|reservations|personal-invites)\//);
 return m?'/api/'+m[1]+'/*':'other';
}
let visibleIncident=null;
function errorView(err,title='Что-то пошло не так'){
 const kind=incidentType(err),route=incidentRoute();
 const notFound={'/list/*':'Вишлист не найден','/w/*':'Вишлист не найден','/santa/*':'Игра не найдена','/users/*':'Пользователь не найден','/u/*':'Пользователь не найден','/join/*':'Приглашение не найдено','/i/*':'Приглашение не найдено','/p/*':'Личная ссылка недействительна','/r/*':'Бронь не найдена'};
 const heading=kind==='not_found'?(notFound[route]||'Страница не найдена'):title==='Страница потерялась'?'Страница не найдена':kind==='module'?'Не удалось загрузить интерфейс':kind==='access'?'Нет доступа':title;
 const status=Number.isInteger(err?.status)?err.status:null;
 const id=currentPath().match(/^\/(?:list|santa)\/(\d{1,10})$/)?.[1]||'';
 const uiVersion=err?.uiVersion||landingArtPrefix.match(/\/ui\/([a-f0-9]{20})\//)?.[1]||'';
 const moduleName=kind==='module'&&typeof err?.message==='string'?err.message.match(/\b(socialAdminUsersPage|socialAdminAuditPage|socialAdminPage|socialOwnProfilePage|socialProfilePage|socialFriendsPage|santaGamePage|santasPage|ownerListPage|dashboardPage|santaRosterPerson|inviteShareButtons)\b/)?.[1]||'':'';
 visibleIncident={kind:kind==='unknown'&&title==='Страница потерялась'?'not_found':kind,route,status,api_route:incidentApiRoute(err?.apiPath),object_id:id,ui_version:uiVersion,request_id:err?.requestId||'',module_name:moduleName,context:true};
 shell(`<main class="container page"><div class="error-page"><div class="error-approved-art">${serviceArt('santa')}</div><h1>${esc(heading)}</h1><div class="error-page-actions">${kind==='not_found'||title==='Страница потерялась'?'':'<button class="btn btn-dark" data-action="retry-error">Попробовать снова</button>'}<button class="btn btn-soft" data-action="report-incident">Сообщить об ошибке</button><button class="text-link" data-nav="/">На главную ${ico('arrow')}</button></div><p class="note" data-incident-result role="status"></p></div></main>`);
}
function emptyState(title,desc,button,open){return `<div class="blank-state"><div class="blank-illustration">${fallbackArt('gift')}</div><h3>${esc(title)}</h3><p>${esc(desc)}</p><button class="btn btn-dark" data-open="${attr(open)}">${esc(button)} ${ico('plus')}</button></div>`;}
let wishlistTabGeneration=0;
let currentOwnedWishlists=[];
function wishlistCategoryFilter(lists){
 const categories=[...new Set(lists.map(x=>x.occasion?.trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru'));
 return '<div class="wishlist-filters" role="group" aria-label="Фильтр категорий">'+['Все',...categories].map((x,i)=>
  '<button type="button" class="filter-chip'+(i===0?' active':'')+'" aria-pressed="'+(i===0)+'" data-wishlist-filter="'+attr(x)+'">'+esc(x)+'</button>').join('')+'</div>';
}
function ownWishlistTiles(lists){
 const coverAssignments=assignWishlistCovers(lists);
 return lists.length?wishlistCategoryFilter(lists)+
  '<div class="cards-grid">'+lists.map(l=>listCard(l,coverAssignments).replace('<article class="list-card">','<article class="list-card" data-occasion="'+attr(l.occasion?.trim()||'')+'">')).join('')+'</div>':
  emptyState('Здесь пока тихо','Создай первый список и добавь пару желаний','Создать список','list');
}
function friendWishlistTiles(lists){
 if(!lists.length)return '<div class="blank-state"><h3>Пока нет доступных вишлистов друзей</h3><p>Добавь друзей, которые открыли свои списки по ссылке</p><button class="btn btn-soft" data-nav="/friends">Мои друзья</button></div>';
 const coverAssignments=assignWishlistCovers(lists);
 const groups=new Map();
 for(const l of lists){
  const id=String(l.owner_id||l.owner_name);
  if(!groups.has(id))groups.set(id,{name:l.owner_name,avatar:l.avatar_emoji||'🎁',id:l.owner_id,lists:[]});
  groups.get(id).lists.push(l);
 }
 const cards=[...groups.values()].map(friend=>{
  const name=esc(friend.name);
  const tiles=friend.lists.map(l=>
   '<article class="list-card friend-stack-list" data-occasion="'+attr(l.occasion?.trim()||'')+'">'+
   '<a class="card-hitarea" href="/w/'+attr(l.share_key)+'" data-nav="/w/'+attr(l.share_key)+'" aria-label="Открыть вишлист '+attr(l.title)+'"></a>'+
   '<div class="list-cover cover-'+attr(l.theme)+'">'+wishlistCover(l,coverAssignments)+'</div>'+
   '<div class="list-info"><h3>'+esc(l.title)+'</h3><p>'+esc(l.description||l.occasion||'Список подарков')+'</p>'+
   '<div class="list-bottom"><span>'+ruCount(l.wish_count,'желание','желания','желаний')+'</span><button class="text-link" data-nav="/w/'+attr(l.share_key)+'">Открыть '+ico('arrow')+'</button></div></div></article>').join('');
  return '<section class="friend-wishlist-stack" data-friend-stack>'+(friend.id?'<a class="friend-stack-heading" href="/users/'+attr(friend.id)+'" data-nav="/users/'+attr(friend.id)+'" aria-label="Открыть профиль '+attr(friend.name)+'">':'<div class="friend-stack-heading">')+'<span class="friend-stack-avatar">'+esc(friend.avatar)+'</span><div><strong>'+name+'</strong><span>'+ruCount(friend.lists.length,'вишлист','вишлиста','вишлистов')+'</span></div>'+
   (friend.id?'<span class="text-link">Профиль '+ico('arrow')+'</span>':'')+(friend.id?'</a>':'</div>')+'<div class="friend-stack-cards">'+tiles+'</div></section>';
 }).join('');
 return wishlistCategoryFilter(lists)+'<div class="friend-stack-grid">'+cards+'</div>';
}
async function listsPage(marker=lastRenderToken){
 if(!currentUser){
  // A restored private tab is not a useful anonymous entrypoint.
  if(!isPreview&&currentPath()==='/lists')history.replaceState(null,'','/');
  home();return;
 }
 const {lists}=await api('/api/lists');if(marker!==lastRenderToken)return;
 currentOwnedWishlists=lists;wishlistTabGeneration++;
 shell('<main class="container page wishlists-page"><div class="page-hero"><div><div class="section-label">Коллекция желаний</div><h1>Вишлисты</h1><p>Мои желания и открытые списки друзей</p></div><div class="btn-row"><button class="btn btn-dark" data-open="list">Новый список '+ico('plus')+'</button></div></div>'+
 '<div class="wishlist-view-tabs" role="tablist" aria-label="Вишлисты"><button type="button" role="tab" id="wishlist-tab-mine" aria-controls="wishlist-view-content" aria-selected="true" tabindex="0" class="active" data-wishlist-view="mine">Мои вишлисты</button><button type="button" role="tab" id="wishlist-tab-friends" aria-controls="wishlist-view-content" aria-selected="false" tabindex="-1" data-wishlist-view="friends">Вишлисты друзей</button></div>'+
 '<div id="wishlist-view-content" role="tabpanel" aria-labelledby="wishlist-tab-mine">'+
 ownWishlistTiles(lists)+
 '</div></main>');
}
document.addEventListener('click',async event=>{
 const tab=event.target.closest('[data-wishlist-view]');
 if(tab){
  event.preventDefault();const tabs=tab.closest('[role="tablist"]');
  if(tab.getAttribute('aria-selected')==='true')return;
  syncSelection(tabs,tab,'aria-selected');
  const region=document.getElementById('wishlist-view-content');
  if(!region)return;
  const generation=++wishlistTabGeneration;
  if(tab.dataset.wishlistView==='mine'){
   patchRenderedMarkup(region,ownWishlistTiles(currentOwnedWishlists));
   return;
  }
  const cachedFriends=cachedOwnerValue('/api/friends/wishlists');
  if(cachedFriends)patchRenderedMarkup(region,friendWishlistTiles(cachedFriends.lists||[]));
  else patchRenderedMarkup(region,'<p class="note" role="status">Загружаем вишлисты друзей…</p>');
  try{
   const result=await api('/api/friends/wishlists');
   if(generation!==wishlistTabGeneration||(!region.isConnected&&!ownerTabViews.get('/lists')?.node.contains(region)))return;
   if(!cachedFriends)patchRenderedMarkup(region,friendWishlistTiles(result.lists||[]));
  }catch(err){if(generation===wishlistTabGeneration)region.innerHTML='<p class="note">'+esc(err.message)+'</p>';}
  return;
 }
 const filter=event.target.closest('[data-wishlist-filter]');
 if(filter){
  event.preventDefault();
  const panel=filter.closest('#wishlist-view-content');if(!panel)return;
  if(filter.getAttribute('aria-pressed')==='true')return;
  syncSelection(filter.closest('.wishlist-filters'),filter,'aria-pressed');
  for(const tile of panel.querySelectorAll('[data-occasion]')){
   const hidden=filter.dataset.wishlistFilter!=='Все'&&tile.dataset.occasion!==filter.dataset.wishlistFilter;
   if(tile.hidden!==hidden)tile.hidden=hidden;
  }
  for(const stack of panel.querySelectorAll('[data-friend-stack]')){
   const hidden=![...stack.querySelectorAll('[data-occasion]')].some(tile=>!tile.hidden);
   if(stack.hidden!==hidden)stack.hidden=hidden;
  }
 }
});
function listCard(l,coverAssignments){return `<article class="list-card"><a class="card-hitarea" href="/list/${l.id}" data-nav="/list/${l.id}" aria-label="Открыть вишлист ${attr(l.title)}"></a><div class="list-cover cover-${attr(l.theme)}"><span class="cover-stamp">${esc(l.occasion)}</span>${wishlistCover(l,coverAssignments)}</div><div class="list-info"><h3>${esc(l.title)}</h3><p>${esc(l.description||'Место для твоих желаний')}</p><div class="list-bottom"><span>${ruCount(l.wish_count,'желание','желания','желаний')}</span><button class="text-link" data-nav="/list/${l.id}">Открыть ${ico('arrow')}</button></div></div></article>`;}
function plural(n,a,b,c){
 const value=Math.abs(Math.trunc(Number(n)||0)),k=value%100,d=k%10;
 return k>=11&&k<=14?c:d===1?a:d>=2&&d<=4?b:c;
}
function ruCount(n,one,few,many){
 const value=Math.max(0,Math.trunc(Number(n)||0));
 return value+' '+plural(value,one,few,many);
}
// Account ownership is authoritative on the server. Legacy reservation links
// created before login-only booking remain cancellable from their old browser.
const legacyReservations=new Map();
function reservationKey(listKey,wishId){return 'shursh-reservation-v2:'+listKey+':'+wishId;}
function ownReservation(listKey,wishId){
 const key=reservationKey(listKey,wishId);
 if(legacyReservations.has(key))return legacyReservations.get(key);
 try{const saved=localStorage.getItem(key);if(saved&&/^[A-Za-z0-9_-]{43}$/.test(saved)){legacyReservations.set(key,saved);return saved;}}catch{}
 return null;
}
function forgetReservation(listKey,wishId){
 const key=reservationKey(listKey,wishId);
 legacyReservations.delete(key);
 try{localStorage.removeItem(key);}catch{}
}
async function toggleGiftReservation(wishId,listKey){
 if(!currentUser){loginModal('register');return;}
 const marker=lastRenderToken;
 const actionButton=[...document.querySelectorAll('.wishlist-grid [data-action="reserve"]')].find(b=>Number(b.dataset.id)===Number(wishId));
 const card=actionButton?.closest('.wish-card');
 const wish=loadedPublicWishes.find(w=>Number(w.id)===Number(wishId));
 if(!wish)throw new Error('Подарок не найден');
 const token=ownReservation(listKey,wishId);
 if(wish.reserved){
  if(wish.reserved_by_me){
   await api('/api/public/'+encodeURIComponent(listKey)+'/reserve/'+wishId,{method:'DELETE'});
   notice('Бронь отменена');
  }else if(token){
   // Preserve legacy bookings for their original browser only.
   try{await api('/api/reservations/'+encodeURIComponent(token),{method:'DELETE'});}
   catch(err){if(err.status!==404&&err.status!==409)throw err;}
   forgetReservation(listKey,wishId);
   notice('Бронь отменена');
  }else throw new Error('Этот подарок уже забронирован другим человеком');
 }else{
  if(token)forgetReservation(listKey,wishId);
  await api('/api/public/'+encodeURIComponent(listKey)+'/reserve/'+wishId,{method:'POST',body:{}});
  notice('Подарок забронирован!');
 }
 if(marker!==lastRenderToken||currentPath()!=='/w/'+listKey)return;
 closeModal();
 // A successful reservation mutation affects only this gift. Re-read only
 // when the legacy bearer cancellation may have raced another reservation.
 if(wish.reserved&&!wish.reserved_by_me&&token){
  const result=await api('/api/public/'+encodeURIComponent(listKey));
  if(marker!==lastRenderToken||!card?.isConnected)return;
  const fresh=result.wishes.find(w=>Number(w.id)===Number(wishId));
  if(!fresh){await publicListPage(listKey,marker);return;}
  Object.assign(wish,fresh);
 }else{
  wish.reserved=!wish.reserved;wish.reserved_by_me=wish.reserved;
 }
 if(card?.isConnected){
  const next=document.createElement('template');next.innerHTML=wishCard(wish,'guest',listKey);
  patchOwnerNode(card,next.content.firstElementChild);
 }
}
function wishCard(w,mode='owner',shareKey=''){
 const reserved=w.reserved===true;
 const cardActions=mode==='owner'?`<div class="wish-controls"><button class="btn btn-soft" data-action="edit-wish" data-id="${w.id}" title="Редактировать">${ico('edit')}</button><button class="btn btn-soft" data-action="delete-wish" data-id="${w.id}" title="Удалить">${ico('trash')}</button></div>`:'';
 const own=reserved&&!!currentUser&&(w.reserved_by_me||!!ownReservation(shareKey,w.id));
 const footer=mode==='guest'?`<button type="button" class="btn ${own?'btn-soft':reserved?'btn-soft':'btn-dark'} wish-action" ${reserved&&!own?'disabled':''} data-action="reserve" data-id="${w.id}" data-key="${attr(shareKey)}">${own?`${ico('check')} Отменить бронь`:reserved?`${ico('lock')} Уже забронировано`:currentUser?`${ico('gift')} Забронировать`:`${ico('lock')} Войти и забронировать`}</button>`:'';
 return `<article class="wish-card" data-render-key="wish:${attr(mode)}:${attr(w.id)}"><button type="button" class="card-hitarea" data-action="show-wish" data-id="${w.id}" data-mode="${attr(mode)}" data-key="${attr(shareKey)}" aria-label="Подробнее о желании ${attr(w.title)}"></button><div class="wish-image">${w.image_path?`<img src="${attr(w.image_path)}" alt="${attr(w.title)}" loading="lazy">`:artFor(w)}${w.priority==='love'?`<span class="wish-priority chip chip-peach">${ico('heart')} Очень хочу</span>`:`<span class="wish-priority chip priority-nice">Было бы здорово</span>`}</div><div class="wish-content"><h3>${esc(w.title)}</h3><p class="wish-desc">${esc(w.description|| (w.kind==='experience'?'Впечатление или хорошая идея':'Подарок без комментария'))}</p><div class="wish-card-footer"><div class="wish-price">${money(w.price_cents,w.currency)}</div>${cardActions}</div>${w.shop_url?`<a href="${attr(w.shop_url)}" target="_blank" rel="noopener noreferrer" class="text-link" style="margin-top:12px;font-size:12px">В магазин ${ico('external')}</a>`:''}${footer}</div></article>`;
}
function showWishDetails(el){
 const id=Number(el.dataset.id), mode=el.dataset.mode, key=el.dataset.key||'';
 const wish=(mode==='owner'?loadedList?.wishes:loadedPublicWishes)?.find(w=>Number(w.id)===id);
 if(!wish)return;
 const image=wish.image_path?'<img class="wish-detail-image" src="'+attr(wish.image_path)+'" alt="'+attr(wish.title)+'">':
   '<div class="wish-detail-art">'+artFor(wish)+'</div>';
 const actions=mode==='owner'?'<button class="btn btn-soft" data-action="edit-wish" data-id="'+id+'">'+ico('edit')+' Редактировать</button>'+(isPreview?'':'<button class="btn btn-soft" data-social-action="ask-gift" data-wish-id="'+id+'">'+ico('heart')+' Попросить друга</button>'):
   mode==='guest'&&(!wish.reserved||(currentUser&&(wish.reserved_by_me||ownReservation(key,id))))?'<button class="btn btn-dark" data-action="reserve" data-id="'+id+'" data-key="'+attr(key)+'">'+ico(wish.reserved?'check':'gift')+' '+(wish.reserved?'Отменить бронь':currentUser?'Забронировать':'Войти и забронировать')+'</button>':'';
 const store=wish.shop_url?'<a class="btn btn-soft" href="'+attr(wish.shop_url)+'" target="_blank" rel="noopener noreferrer">В магазин '+ico('external')+'</a>':'';
 modal({title:wish.title,subtitle:money(wish.price_cents,wish.currency),
   content:'<div class="wish-detail">'+image+
     (wish.description?'<p>'+esc(wish.description)+'</p>':'')+
     '<div class="wish-detail-actions">'+store+actions+'</div></div>'});
 const photo=modalRoot.querySelector('.wish-detail > .wish-detail-image, .wish-detail > .wish-detail-art');
 const heading=modalRoot.querySelector('.modal-scroll-area h2');
 if(photo&&heading)heading.before(photo);
 modalRoot.querySelector('.modal')?.classList.add('gift-details-modal');
}
let loadedList = null;
async function ownerListPage(id,marker=lastRenderToken){if(!currentUser)throw new Error('Войди, чтобы открыть список');const d=await api(`/api/lists/${id}`);if(marker!==lastRenderToken)return;loadedList=d;
 const l=d.list;const url=getLink(`/w/${l.share_key}`);shell(`<main class="container page"><div class="guest-topline"><button class="text-link" data-nav="/lists">${ico('back')} Мои вишлисты</button> <span>/</span> <span>${esc(l.title)}</span></div><div class="detail-top cover-${attr(l.theme)}"><div><span class="chip">${ico('gift')} ${esc(l.occasion)}</span><h1>${esc(l.title)}</h1><p>${esc(l.description||'Список маленьких и больших мечтаний')}</p></div><div class="detail-art">${wishlistCover(l)}</div></div><div class="detail-actions"><div><h2>Желания <span class="chip" data-owner-wish-count>${d.wishes.length}</span></h2><p class="note">Брони друзей здесь никогда не отображаются</p></div><div class="btn-row"><button class="btn btn-soft btn-small" data-action="edit-list">${ico('edit')} Настройки</button><button class="btn btn-soft btn-small" data-action="copy" data-url="${attr(url)}" ${l.visibility==='private'?'disabled title="Сначала открой доступ по ссылке"':''}>${ico('copy')} Ссылка</button><button class="btn btn-dark btn-small" data-open="wish">Добавить желание ${ico('plus')}</button></div></div>${l.visibility==='private'?`<div class="alert">${ico('lock')} Список приватный. Доступ по ссылке выключен в настройках</div>`:''}<div data-owner-wishes>${ownerWishesMarkup(d.wishes)}</div><div class="divider-line"></div><button class="btn btn-ghost btn-small" data-action="delete-list">${ico('trash')} Удалить весь список</button></main>`);}
function ownerWishesMarkup(wishes){
 return wishes.length?'<div class="wishlist-grid">'+wishes.map(w=>wishCard(w)).join('')+'</div>':
  emptyState('Пока ни одного желания','Вдохновение начинается с первой идеи','Добавить желание','wish');
}
async function refreshOwnerWishes(id){
 const root=document.querySelector('[data-owner-wishes]'),marker=lastRenderToken;
 if(!root||currentPath()!=='/list/'+id)return;
 const data=await api('/api/lists/'+id);
 if(marker!==lastRenderToken||!root.isConnected)return;
 loadedList=data;
 const scrollY=window.scrollY;
 patchRenderedMarkup(root,ownerWishesMarkup(data.wishes));
 const count=document.querySelector('[data-owner-wish-count]'),label=String(data.wishes.length);
 if(count&&count.textContent!==label)count.textContent=label;
 if(Math.abs(window.scrollY-scrollY)>1)window.scrollTo({top:scrollY,behavior:'instant'});
}
let loadedPublicWishes=[];
async function publicListPage(key,marker=lastRenderToken){const {list:l,wishes,owner_view}=await api(`/api/public/${key}`);if(marker!==lastRenderToken)return;loadedPublicWishes=wishes;shell(`<main class="container page"><div class="guest-topline">${ico('gift')} <span>Вишлист по ссылке</span><span>/</span><strong>от ${esc(l.owner_name)}</strong></div><div class="detail-top cover-${attr(l.theme)}"><div><span class="chip">${ico('heart')} ${esc(l.occasion)}</span><h1>${esc(l.title)}</h1><p>${esc(l.description)}</p></div><div class="detail-art">${wishlistCover(l)}</div></div><div class="guest-banner">${owner_view?'Это твой список - статус бронирования для владельца скрыт':'Можешь забронировать понравившийся подарок. Владелец списка не увидит, что выбрано. Для брони войди в аккаунт. Нажми «Забронировать», чтобы занять подарок, или ту же кнопку, чтобы снять свою бронь с любого устройства'}</div><div class="detail-actions"><h2>Желания <span class="chip">${wishes.length}</span></h2></div>${wishes.length?`<div class="wishlist-grid">${wishes.map(w=>wishCard(w,owner_view?'view':'guest',key)).join('')}</div>`:emptyState('В этом списке пока пусто','Загляни позже - здесь скоро появятся желания','На главную','login')}</main>`);}
async function reservationPage(key,marker=lastRenderToken){const {reservation:r}=await api(`/api/reservations/${key}`);if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="invite-card"><div class="invite-icon">${envelopeArt()}</div><h1>${r.cancelled_at?'Бронь отменена':'Подарок ждёт своего часа!'}</h1><p>${r.cancelled_at?'Этот подарок снова доступен другим дарителям':'Твоя бронь сохранена. Эта ссылка - личный ключ для отмены, береги её'}</p><div class="details-box"><p><strong>Подарок:</strong> ${esc(r.wish_title)}</p><p><strong>Вишлист:</strong> ${esc(r.list_title)}</p></div>${!r.cancelled_at?`<div class="share-field"><input class="input" readonly value="${attr(getLink(`/r/${key}`))}" aria-label="Ссылка управления бронью"><button class="btn btn-dark btn-small" data-action="copy" data-url="${attr(getLink(`/r/${key}`))}">${ico('copy')} Копировать</button></div><button class="btn btn-danger btn-small" data-action="cancel-reservation" data-token="${attr(key)}">Отменить мою бронь</button>`:''}</div></main>`);}
async function adminFeedbackPage(marker=lastRenderToken){
 const {items}=await api('/api/admin/feedback');
 if(marker!==lastRenderToken)return;
 const topic={idea:'Предложение',bug:'Ошибка',question:'Вопрос',thanks:'Благодарность',other:'Другое'};
 shell('<main class="container page admin-feedback-page"><div class="admin-section-back"><a href="/admin" data-nav="/admin" class="text-link">'+ico('back',18)+' Все разделы</a></div><div class="page-hero"><div><div class="section-label">Администрирование</div><h1>Обращения пользователей</h1><p>Последние 100 обращений. Только для администратора</p></div></div>'+
  (items.length?'<div class="feedback-inbox">'+items.map(item=>
   '<article class="panel feedback-entry"><div class="panel-heading-actions"><h2>'+esc(topic[item.topic]||item.topic)+
   '</h2><span class="chip">'+(item.status==='resolved'?'Закрыто':'Новое')+'</span></div>'+
   '<p><strong>'+esc(item.name)+'</strong>'+(item.email?' · <a href="mailto:'+attr(item.email)+'">'+esc(item.email)+'</a>':'')+'</p>'+
   '<p class="feedback-message">'+esc(item.message)+'</p>'+ (item.source_route&&item.name!=='Системный инцидент'?'<p class="note">Раздел: '+esc(item.source_route)+' · Ответ на почту: '+(item.reply_email?'да':'нет')+' · Уведомление: '+(item.notify_site?'да':'нет')+'</p>':'')+
   '<div class="panel-heading-actions"><small>'+esc(item.created_at)+'</small>'+
   '<button type="button" class="btn btn-soft btn-small" data-action="admin-feedback-status" data-id="'+item.id+
   '" data-status="'+(item.status==='resolved'?'new':'resolved')+'">'+(item.status==='resolved'?'Вернуть в новые':'Отметить решённым')+'</button></div></article>'
  ).join('')+'</div>':'<div class="panel"><p>Сообщений пока нет</p></div>')+'</main>');
}
async function santasPage(marker=lastRenderToken,snapshot=null){if(!currentUser){shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Под прикрытием</div><h1>Тайный Санта</h1><p>Чтобы организовать игру, нужно войти. Участникам тоже потребуется зарегистрироваться</p></div><button class="btn btn-dark" data-open="login">Войти ${ico('arrow')}</button></div>${emptyState('Собери компанию','Укажи бюджет, зови друзей и проведи честную жеребьёвку','Создать игру','santa')}</main>`);return;}
 const {events,invitations=[]}=snapshot||await api('/api/santas');if(marker!==lastRenderToken)return;
 const currentEvents=events.filter(e=>e.status!=='finished');
 const finishedEvents=events.filter(e=>e.status==='finished');
 const pending=invitations.length?'<section class="panel santa-pending"><h2>Приглашения <span class="chip">'+invitations.length+'</span></h2>'+
  invitations.map(i=>'<article class="santa-pending-row"><div><strong>'+esc(i.title)+'</strong><p class="note">'+dateRu(i.exchange_date)+' · '+money(i.budget_cents,i.currency)+'</p></div><button type="button" class="btn btn-peach btn-small" data-action="accept-santa-invite" data-key="'+attr(i.invite_key)+'">Присоединиться</button></article>').join('')+'</section>':'';
 shell(`<main class="container page"><div class="page-hero"><div><div class="section-label">Секретная служба подарков</div><h1>Тайный Санта</h1><p>Здесь живут все твои секретные обмены подарками</p></div><div class="btn-row santa-actions-row"><button class="btn btn-soft" data-action="connect-game">Привязать игру по ссылке</button><button class="btn btn-peach" data-open="santa">Новая игра ${ico('plus')}</button></div></div>${pending}
 <div class="santa-state-tabs" role="tablist" aria-label="Статус игр"><button type="button" role="tab" id="santa-tab-current" aria-controls="santa-state-panel" aria-selected="true" tabindex="0" class="active" data-santa-state="current">Текущие <span class="tab-count">${currentEvents.length}</span></button>
 <button type="button" role="tab" id="santa-tab-finished" aria-controls="santa-state-panel" aria-selected="false" tabindex="-1" data-santa-state="finished">Завершённые <span class="tab-count">${finishedEvents.length}</span></button></div>
 <div id="santa-state-panel" role="tabpanel" aria-labelledby="santa-tab-current"><div class="santa-grid">${events.map(e=>`<div class="santa-list-card santa-tone-${santaTone(e.id)}" data-santa-card-state="${e.status==='finished'?'finished':'current'}" ${e.status==='finished'?'hidden':''}><a class="card-hitarea" href="/santa/${e.id}" data-nav="/santa/${e.id}" aria-label="Открыть игру ${attr(e.title)}"></a><span class="sparkle-deco" aria-hidden="true">${ico("spark",72)}</span><div class="section-label">${e.status==='finished'?'Игра завершена':e.status==='drawn'?'Жеребьёвка проведена':'Собираем компанию'}</div><h3>${esc(e.title)}</h3><p>${esc(e.description||'Собираем друзей для хороших сюрпризов')}</p><div class="list-bottom"><span>${ico('users')} ${ruCount(e.participant_count,'участник','участника','участников')} · ${dateRu(e.exchange_date)}</span><button class="text-link" data-nav="/santa/${e.id}">Открыть ${ico('arrow')}</button></div></div>`).join('')}</div>
 <div class="santa-state-empty" ${currentEvents.length?'hidden':''}><h3>Пока нет текущих игр</h3><p>Создай игру или загляни в завершённые</p></div>
 </div></main>`);
}
document.addEventListener('click',event=>{
 const tab=event.target.closest('[data-santa-state]');
 if(!tab)return;
 event.preventDefault();
 const panel=document.getElementById('santa-state-panel');if(!panel)return;
 const state=tab.dataset.santaState;
 if(tab.getAttribute('aria-selected')==='true')return;
 syncSelection(tab.closest('[role="tablist"]'),tab,'aria-selected');
 let visible=0;
 for(const card of panel.querySelectorAll('[data-santa-card-state]')){
  const match=card.dataset.santaCardState===state;
  if(card.hidden===match)card.hidden=!match;if(match)visible++;
 }
 const empty=panel.querySelector('.santa-state-empty');
 if(empty){
  if(empty.hidden!==(visible>0))empty.hidden=visible>0;
  empty.innerHTML=state==='finished'?'<h3>Пока нет завершённых игр</h3><p>Законченные игры появятся здесь</p>':
   '<h3>Пока нет текущих игр</h3><p>Создай игру или загляни в завершённые</p>';
 }
});

let loadedSanta=null;
let activeGameContext=null;
let gameChatTimer=null;
let gameRosterTimer=null;
let gameLifecycleCleanup=[];
function stopGameLifecycle(){
 clearTimeout(gameChatTimer);clearTimeout(gameRosterTimer);gameChatTimer=null;gameRosterTimer=null;
 for(const cleanup of gameLifecycleCleanup.splice(0))cleanup();
 if(typeof disposeGameGiftOverflow==='function')disposeGameGiftOverflow();
}
// Prefer WebP, but do not require Safari to provide its encoder or createImageBitmap.
function photoDataURL(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не удалось прочитать фотографию'));reader.readAsDataURL(file);});}
async function compressToWebp(file,{maxDimension=1280,maxBytes=800000,maxSourceBytes=12000000}={}){
 const accepted=['image/jpeg','image/png','image/webp','image/heic','image/heif'];
 const type=(file?.type||'').toLowerCase(),ext=file?.name?.split('.').pop()?.toLowerCase();
 if(!file||(!accepted.includes(type)&&!(type===''&&['jpg','jpeg','png','webp','heic','heif'].includes(ext))))throw new Error('Выбери фотографию JPG, PNG, WebP или HEIC');
 if(file.size>maxSourceBytes)throw new Error('Фотография слишком большая для загрузки');
 let bitmap=null,canvas=null,original=null;
 try{
  if(typeof createImageBitmap==='function')try{bitmap=await createImageBitmap(file);}catch{}
  if(!bitmap){
   original=await photoDataURL(file);
   bitmap=await new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('Не удалось открыть фотографию. Для HEIC попробуй сохранить снимок в JPG'));image.src=original;});
  }
  const width=bitmap.naturalWidth||bitmap.width,height=bitmap.naturalHeight||bitmap.height;
  if(!width||!height)throw new Error('Не удалось открыть фотографию');
  canvas=document.createElement('canvas');
  let scale=Math.min(1,maxDimension/Math.max(width,height));
  for(let i=0;i<10;i++){
   canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
   const ctx=canvas.getContext('2d',{alpha:false});if(!ctx)break;
   ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
   for(const mime of ['image/webp','image/jpeg']){
    let result;try{result=canvas.toDataURL(mime,Math.max(.58,.82-.035*i));}catch{continue;}
    if(result.startsWith('data:'+mime+';base64,')&&result.length<=Math.floor(maxBytes*4/3)+24)return result;
   }
   scale*=.82;
  }
  if(['image/jpeg','image/png','image/webp'].includes(type)&&file.size<=maxBytes)return original||await photoDataURL(file);
  throw new Error('Не удалось уменьшить фотографию. Выбери файл меньшего размера');
 }finally{bitmap?.close?.();if(canvas){canvas.width=1;canvas.height=1;}}
}
function enhancePhotoPickers(root){
 for(const input of root.querySelectorAll('.file-picker input[type=file]')){
  if(input.closest('.localized-file-input'))continue;
  const wrap=document.createElement('div');wrap.className='localized-file-input';input.before(wrap);wrap.append(input);
  const label=document.createElement('span');label.className='localized-file-button';label.textContent='Выбери файл';label.setAttribute('aria-hidden','true');wrap.append(label);
  const name=document.createElement('span');name.className='localized-file-name';name.textContent='Файл не выбран';name.setAttribute('aria-live','polite');wrap.append(name);
  input.addEventListener('change',()=>{name.textContent=input.files?.[0]?.name||'Файл не выбран';});
 }
}
async function compressSantaMemory(file){
 return compressToWebp(file,{maxDimension:1600,maxBytes:850000});
}
function openSantaMemory(state,source,canEdit){
 if(activeGameContext!==state)return;
 modal({title:'Фото на память',content:'<img class="santa-memory-full" src="'+attr(source)+'" alt="Общая фотография участников и подарков">',
 footer:canEdit?'<div class="btn-row santa-memory-modal-actions"><button type="button" class="btn btn-soft btn-square" data-memory-action="replace" aria-label="Заменить" title="Заменить">'+ico('edit')+'</button><button type="button" class="btn btn-soft btn-square" data-memory-action="delete" aria-label="Удалить" title="Удалить">'+ico('trash')+'</button></div>':''});
 modalRoot.querySelector('.modal')?.classList.add('santa-memory-modal');
}
document.addEventListener('click',async event=>{
 for(const menu of document.querySelectorAll('.santa-memory-menu[open]'))if(!menu.contains(event.target)||event.target.closest('[data-memory-action]'))menu.open=false;
 const button=event.target.closest('[data-memory-action]');if(!button)return;
 const state=activeGameContext;if(!state)return;
 const action=button.dataset.memoryAction,photo=document.querySelector('.santa-memory-photo');
 if(action==='view'&&photo){openSantaMemory(state,photo.src,!state.memberView);return;}
 if(action==='replace'&&!state.memberView){document.getElementById('santa-memory-input')?.click();return;}
 if(action==='delete'&&!state.memberView&&confirm('Удалить общее фото?')){
  button.disabled=true;
  try{await api(state.base+'/memory',{method:'DELETE',body:{}});closeModal();await loadSantaMemory(state);notice('Фотография удалена');}catch(error){notice(error.message,true);}finally{button.disabled=false;}
 }
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')for(const menu of document.querySelectorAll('.santa-memory-menu[open]')){menu.open=false;menu.querySelector('summary')?.focus();}});
async function loadSantaMemory(state){
 const panel=document.getElementById('santa-memory-content');if(!panel)return;
 try{
  const response=await api(state.base+'/memory');
  if(!panel.isConnected||activeGameContext!==state)return;
  const memory=response.memory,canEdit=response.can_edit===true&&!state.memberView;
  panel.innerHTML=memory?
    '<div class="santa-memory-wrap"><button type="button" class="santa-memory-view" data-memory-action="view" aria-label="Посмотреть фотографию"><img class="santa-memory-photo" src="'+attr(memory.image_data)+'" alt="Общая фотография участников и подарков"></button>'+
    (canEdit?'<details class="santa-memory-menu"><summary aria-label="Действия с фотографией">⋮</summary><div><button type="button" data-memory-action="view">Посмотреть</button><button type="button" data-memory-action="replace">Заменить</button><button type="button" data-memory-action="delete">Удалить</button></div></details>':'')+'</div>':
    '<div class="santa-memory-empty">'+ico('gift',28)+'<p>Пока без фотографии. Организатор может добавить один общий снимок</p></div>';
  const upload=document.querySelector('.santa-memory-upload');if(upload)upload.classList.toggle('hide',!!memory);
 }catch(err){if(panel.isConnected&&activeGameContext===state)panel.innerHTML='<p class="note">'+esc(err.message)+'</p>';}
}
function santaMemorySection(event,memberView){
 if(event.status==='open')return '';
 if(event.status!=='finished')return '<section class="panel santa-memory-panel"><h2>Фото на память</h2><p class="note">Фото можно добавить после завершения игры</p></section>';
 return '<section class="panel santa-memory-panel" aria-label="Общее фото на память">'+
  '<div class="panel-heading-actions"><div><h2>Фото на память</h2><p class="note">Один общий снимок участников с подарками, доступный только участникам этой игры</p></div>'+
  (!memberView?'<label class="btn btn-soft btn-small santa-memory-upload"><span data-santa-memory-label>Добавить фотографию</span><input id="santa-memory-input" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" aria-label="Загрузить общее фото"></label>':'')+
  '</div><div id="santa-memory-content"><p class="note">Загружаем фотографию…</p></div></section>';
}
async function santaAdminPage(id,marker=lastRenderToken){return santaGamePage(id,marker);}
async function santaGamePage(id,marker=lastRenderToken,participantToken=null){
 let memberView=participantToken!==null,memberBase=null,d;
 if(!memberView&&!currentUser)throw new Error('Для управления игрой нужно войти');
 if(memberView)d=await api(`/api/participant/${participantToken}`);
 else{
  try{d=await api(`/api/santas/${id}`);}
  catch(err){
   if(err.status!==404||isPreview)throw err;
   memberView=true;memberBase='/api/member/'+id;
   d=await api(memberBase);
  }
 }
 if(marker!==lastRenderToken)return;
 if(!memberView)loadedSanta=d;else loadedSanta=null;
 const e=d.event;
 const drawPerformed=e.status==='drawn'||(e.status==='finished'&&!!(memberView?d.assignment:d.my_assignment));
 if(memberView)id=e.id;
 const gameWishes=memberView?d.wishes:(d.my_wishes||[]);
  const myPrefs=memberView?d.preferences:d.my_preferences;
 activeGameContext={base:memberView?(memberBase||'/api/participant/'+participantToken):'/api/santas/'+id,
  event:e,richEnabled:d.rich_enabled!==false,own:gameWishes,memberView,memberId:memberView?d.participant.id:null,currentUserId:currentUser?.id,recipient:e.status!=='open'?(memberView?d.assignment?.wish_cards:d.my_assignment?.wish_cards)||[]:[],participants:d.participants};
 const people=d.participants;
 const selects=(id,label)=>selectField(label,id,people.map(p=>[p.id,p.name]),null);
 shell(`<main class="container page"><div class="guest-topline">${memberView? `${ico('lock')} Личный кабинет участника <span>/</span> <strong>${esc(d.participant.name)}</strong>`:`<button class="text-link" data-nav="/santas">${ico('back')} Все игры</button> <span>/</span> <span>${esc(e.title)}</span>`}</div><div class="page-hero"><div><div class="section-label">${e.status==='finished'?'Игра завершена':e.status==='drawn'?'Жеребьёвка проведена':'Приглашаем участников'}</div><h1>${memberView?esc(e.title):`<button type="button" class="santa-inline-field santa-inline-title" data-action="edit-santa-title" title="Изменить название" data-santa-field="title">${esc(e.title)}</button>`}</h1><p>${memberView?esc(e.description||'Праздник начинается с маленькой тайны'):`<button type="button" class="santa-inline-field santa-inline-description" data-action="edit-santa-description" title="Изменить описание" data-santa-field="description">${esc(e.description||'Праздник начинается с маленькой тайны')}</button>`}</p></div><div class="santa-game-status">${!memberView?'<button type="button" class="btn btn-soft btn-small" data-action="delete-santa">'+ico('trash')+' Удалить игру</button>':''}${!memberView&&e.status!=='finished'?'<button type="button" class="btn btn-soft btn-small" data-action="finish-santa">Завершить игру '+ico('check')+'</button>':''}<span class="chip ${e.status!=='open'?'chip-green':'chip-lilac'}">${ico(e.status!=='open'?'check':'users')} ${e.status==='finished'?'Игра завершена':e.status==='drawn'?'Игра началась':'Приём открыт'}</span></div></div><div class="santa-detail-layout"><div>
 <div class="panel"><div class="panel-heading-actions"><h2>Участники <span class="chip" data-santa-roster-count>${people.length}</span></h2>${!memberView&&e.status==='open'?'<div class="santa-player-actions"><button class="btn btn-soft btn-small" data-action="add-player">'+ico('plus')+' Личная ссылка</button>'+(isPreview?'':'<button class="btn btn-soft btn-small santa-invite-action" data-social-action="invite-friends">Пригласить друзей</button>')+'</div>':''}</div><div class="person-list" data-santa-roster>${people.map(p=>santaRosterPerson(p,activeGameContext)).join('')}</div>${e.status==='open'?`<div class="santa-share"><p class="note">Общая ссылка для всех: любой зарегистрированный пользователь сможет выбрать имя и присоединиться к игре</p>${inviteShareButtons(getLink('/join/'+e.invite_key),false,e.invite_key)}</div>`:''}</div>
 <div class="panel"><div class="panel-heading-actions"><h2>Мои пожелания</h2>${!memberView||currentUser?`<button class="btn btn-soft btn-small" data-action="import-own-wishes" ${memberView?`data-key="${attr(participantToken||'')}"`:`data-id="${id}"`}>${ico('plus')} Из вишлиста</button>`:''}</div><p class="note">Твои пожелания увидит только твой тайный Санта</p>
  <div class="santa-preferences-display" id="santa-preferences-display">
    <div data-preferences-summary>${preferenceSummary(myPrefs,true)}</div>
   </div>
   <form class="form participant-preferences" id="santa-preferences-form" hidden>
     ${textArea('Что хотелось бы','wanted','Любимые цвета, увлечения, идеи',myPrefs?.wanted||'')}
     ${textArea('Чего не хотелось бы','unwanted','Что точно не подходит',myPrefs?.unwanted||'')}
     <div class="btn-row"><button type="button" class="btn btn-soft btn-small" data-action="cancel-santa-preferences">Отмена</button><button type="submit" class="btn btn-dark btn-small">Сохранить пожелания</button></div>
   </form><div class="my-wishes-list">${wishesMarkup(gameWishes)}</div>
 ${d.rich_enabled!==false?`<button class="btn btn-dark btn-small" type="button" data-action="add-game-gift">${ico('plus')} Добавить подарок</button>`:
 `<form class="form" id="legacy-santa-wish-form"><div class="share-field"><input class="input" name="title" required maxlength="130" placeholder="Название подарка"><button class="btn btn-dark btn-small" type="submit">Добавить ${ico('plus')}</button></div></form><p class="note">Подробные карточки появятся после обновления игры</p>`}</div>

 </div><div><div class="panel"><div class="panel-heading-actions"><h2>О событии</h2></div><div class="details-box santa-event-details"><p>${ico('calendar')} <strong>Дата:</strong> ${memberView?dateRu(e.exchange_date):`<span class="santa-date-inline"><input type="date" data-santa-date-input value="${attr(e.exchange_date||'')}" aria-label="Изменить дату обмена"></span>`}</p><p>${ico('gift')} <strong>Бюджет:</strong> ${memberView?money(e.budget_cents,e.currency):`<button type="button" class="santa-inline-field santa-inline-value" data-action="edit-santa-budget" data-santa-field="budget" aria-label="Изменить бюджет">${money(e.budget_cents,e.currency)}</button>`}</p><p>${ico('users')} <strong>Участники:</strong> <span data-santa-event-count>${people.length}</span></p>${e.rules?`<div class="divider-line"></div><strong>Правила:</strong><p>${esc(e.rules)}</p>`:''}</div></div>
 ${!memberView&&e.status==='open'?`<div class="panel"><h2>Исключения</h2><p class="note">Укажи пары, которые не должны выпадать друг другу. Ограничения работают направленно: «А → Б» означает, что А не может дарить Б</p><div class="rules-list" id="santa-rules-list" style="margin:17px 0">${santaRuleMarkup(d.exclusions,people)}</div><button type="button" class="btn btn-soft btn-small santa-rule-toggle" data-action="toggle-santa-rule-form">${ico('plus')} Добавить ограничение</button><form class="form santa-rule-editor" id="rule-form" hidden><div class="form-grid">${selects('giver_id','Кто дарит')}${selects('receiver_id','Кому нельзя дарить')}</div><div class="btn-row"><button class="btn btn-soft btn-small" type="button" data-action="toggle-santa-rule-form">Отмена</button><button class="btn btn-dark btn-small" type="submit">Сохранить ограничение</button></div></form></div>`:''}
 ${santaMemorySection(e,memberView)}
 ${!memberView&&e.status==='open'?`<div class="panel"><h2>Время раскрыть карты?</h2><p class="note">После жеребьёвки приглашения, состав и исключения будут заморожены. Каждый увидит только своего получателя</p><div class="alert santa-draw-hint"><span class="santa-draw-hint-icon">${ico('info')}</span><span>Понадобится минимум 3 участника. А то вдвоём играть неинтересно :D</span></div><button class="btn btn-dark" style="width:100%" data-action="draw" ${people.length<3?'disabled':''}>Провести жеребьёвку ${ico('spark')}</button></div>`:`<div class="panel"><h2>Кому ты даришь</h2>${drawPerformed?secretCard(memberView?d.assignment:d.my_assignment):`<div class="secret-card">${envelopeArt()}<h2>${e.status==='finished'?'Игра завершена без жеребьёвки':'Пока храним интригу'}</h2><p>${e.status==='finished'?'Получатели не назначались':'Организатор ещё собирает всех участников. После жеребьёвки здесь появится конверт с твоим получателем'}</p></div>`}</div>`}
 ${memberView&&participantToken&&!d.participant.user_id?`<div class="panel"><h2>Твоя личная ссылка</h2><p class="note">Эта гостевая ссылка даёт доступ к твоей игре без аккаунта. Не пересылай её другим</p>${!d.participant.user_id&&!isPreview?`<div class="game-save-account"><p>Привяжи это гостевое место к своему аккаунту, чтобы больше не пользоваться ссылкой</p><button class="btn btn-dark btn-small" type="button" data-action="claim-game" data-token="${attr(participantToken)}">${ico("check")} Сохранить игру в аккаунте</button></div>`:""}<div class="share-field"><input class="input" readonly value="${attr(getLink(`/p/${participantToken}`))}" aria-label="Личная ссылка"><button class="btn btn-dark btn-small" data-action="copy" data-url="${attr(getLink(`/p/${participantToken}`))}">${ico('copy')} Копировать</button></div></div>`:''}
 </div></div>
 ${d.rich_enabled!==false?`<section class="panel game-chat-panel" id="game-chat" aria-label="Чаты игры">
 <div class="panel-heading-actions"><h2>Чаты игры</h2></div>
 <p class="note">Общий чат открыт всем участникам. После жеребьёвки появятся личные переписки. Личность тайного дарителя не раскрывается</p>
 <div class="game-chat-tabs" role="group" aria-label="Выбрать чат">
 <button class="btn btn-soft btn-small" type="button" data-chat-room="general" aria-pressed="true">Общий чат</button>
 ${drawPerformed?'<button class="btn btn-soft btn-small" type="button" data-chat-room="to-recipient" aria-pressed="false">Моему получателю</button><button class="btn btn-soft btn-small" type="button" data-chat-room="from-santa" aria-pressed="false">Моему дарителю</button>':''}
 </div>
 <div class="game-chat-messages" role="log" aria-live="polite"><p class="note">Загружаем сообщения…</p></div>
 <form id="game-chat-form" class="game-chat-form"><label for="game-chat-input" class="sr-only">Текст сообщения</label><input id="game-chat-input" class="input" name="message" placeholder="Сообщение…" maxlength="500" autocomplete="off" required><button class="btn btn-dark btn-small game-chat-send" type="submit" aria-label="Отправить сообщение" title="Отправить">${ico('arrow',22)}</button></form>
 
 </section>`:`<section class="panel"><h2>Чаты игры</h2><p class="note">Чаты появятся после обновления игры. Остальные возможности доступны</p></section>`}</main>`);
 setupGameGiftOverflow();
 const dateInput=document.querySelector('[data-santa-date-input]');
 if(dateInput){enhanceCalendars(dateInput.parentElement);const trigger=dateInput.nextElementSibling;trigger.setAttribute('aria-label','Изменить дату обмена');trigger.classList.add('santa-inline-field');dateInput.addEventListener('change',async()=>{const old=e.exchange_date||'';if(!dateInput.value){if(old){dateInput.value=old;dateInput.dispatchEvent(new Event('change'));}return;}if(dateInput.value===old)return;trigger.disabled=true;try{await api('/api/santas/'+e.id,{method:'PATCH',body:{exchange_date:dateInput.value}});e.exchange_date=dateInput.value;notice('Изменения сохранены');}catch(err){dateInput.value=old;dateInput.dispatchEvent(new Event('change'));notice(err.message,true);}finally{trigger.disabled=false;}});}
 document.getElementById('santa-preferences-form')?.addEventListener('submit',async ev=>{
   ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('[type=submit]');
   button.disabled=true;
   try{await api(activeGameContext.base+'/preferences',{method:'PATCH',body:readForm(form)});
    if(form.isConnected){const summary=document.querySelector('#santa-preferences-display');if(summary){const values=readForm(form);summary.querySelector('[data-preferences-summary]').innerHTML=preferenceSummary(values,true);form.querySelectorAll('textarea').forEach(t=>t.defaultValue=t.value);summary.hidden=false;}form.hidden=true;}
    notice('Пожелания сохранены');
   }catch(err){notice(err.message,true)}finally{button.disabled=false;}
  });
  document.getElementById('rule-form')?.addEventListener('submit',async ev=>{
   ev.preventDefault();const form=ev.currentTarget,button=form.querySelector('[type="submit"]'),data=readForm(form);button.disabled=true;
   try{
    await api('/api/santas/'+id+'/exclusions',{method:'POST',body:data});
    const giver_id=Number(data.giver_id),receiver_id=Number(data.receiver_id);
    if(!loadedSanta.exclusions.some(rule=>rule.giver_id===giver_id&&rule.receiver_id===receiver_id))loadedSanta.exclusions.push({giver_id,receiver_id});
    refreshSantaRules();form.hidden=true;document.querySelector('.santa-rule-toggle')?.removeAttribute('hidden');
    notice('Исключение добавлено');
   }catch(err){notice(err.message,true)}finally{button.disabled=false;}
  });
 setupSantaChatLayout();
 setupGameChat(activeGameContext);
 setupSantaRoster(activeGameContext);
 if(e.status==='finished'){
  const state=activeGameContext;
  void loadSantaMemory(state);
  document.getElementById('santa-memory-input')?.addEventListener('change',async event=>{
   const file=event.target.files?.[0];if(!file)return;
   const input=event.target;
   input.disabled=true;
   try{
    const image_data=await compressSantaMemory(file);
    await api('/api/santas/'+e.id+'/memory',{method:'PUT',body:{image_data}});
    notice('Общая фотография сохранена');
    if(modalRoot.querySelector('.santa-memory-modal'))closeModal();
    await loadSantaMemory(state);
   }catch(err){notice(err.message,true);}
   finally{if(input.isConnected){input.value='';input.disabled=false;}}
  });
 }
 document.getElementById('legacy-santa-wish-form')?.addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.currentTarget,button=form.querySelector('button'),state=activeGameContext;
  button.disabled=true;
  try{await api(state.base+(memberView?'/wishes':'/my-wishes'),
         {method:'POST',body:readForm(form)});
      form.reset();notice('Желание добавлено');await refreshGameOwnWishes(state);}
  catch(err){notice(err.message,true);}finally{if(button.isConnected)button.disabled=false;}
 });
}
async function myWishesForAdmin(id){const res=await api(`/api/santas/${id}/my-wishes`);return wishesMarkup(res.wishes);}
function secretCard(assignment){if(!assignment||!assignment.revealed)return `<div class="secret-card">${envelopeArt()}<h2>Твой получатель ждёт внутри</h2><p>Никто, кроме тебя, не увидит это имя</p><button class="btn btn-dark" type="button" data-action="reveal">Узнать, кому я дарю ${ico('spark')}</button></div>`;
 return `<div class="secret-card revealed"><div class="recipient-summary">${socialAvatar({avatar_emoji:assignment.receiver_avatar_emoji},'recipient-avatar')}<div><div class="recipient">${esc(assignment.receiver_name)}</div>${assignment.receiver_user_id?`<button class="text-link recipient-profile-link" data-nav="/users/${attr(assignment.receiver_user_id)}">Профиль получателя ${ico('arrow')}</button>`:""}</div></div><div class="recipient-wishes">
  ${preferenceSummary(assignment.preferences,false)}
  <strong>Подарки получателя</strong>${assignment.wish_cards?.length?wishesMarkup(assignment.wish_cards,'recipient'):'<p class="recipient-empty">Пока без пожеланий - можно придумать сюрприз самому</p>'}</div></div>`;}
function santaRuleMarkup(exclusions,people){
 return exclusions.length?exclusions.map(r=>'<span class="rule-chip">'+esc(people.find(p=>p.id===r.giver_id)?.name||'?')+' → '+esc(people.find(p=>p.id===r.receiver_id)?.name||'?')+' <button type="button" title="Убрать ограничение" aria-label="Убрать ограничение" data-action="remove-rule" data-from="'+r.giver_id+'" data-to="'+r.receiver_id+'">×</button></span>').join(''):'<span class="muted">Пока нет исключений</span>';
}
function refreshSantaRules(){const root=document.getElementById('santa-rules-list');if(root&&loadedSanta)root.innerHTML=santaRuleMarkup(loadedSanta.exclusions,loadedSanta.participants);}
function editSantaIdentity(fieldName){
 const event=loadedSanta?.event,control=document.querySelector('[data-santa-field="'+fieldName+'"]');
 if(!event||!control||control.tagName!=='BUTTON')return;
 const budget=fieldName==='budget',date=fieldName==='exchange_date',description=fieldName==='description';
 const old=budget?(event.budget_cents==null?'':String(event.budget_cents/100)):String(event[fieldName]||'');
 if(date){
  modal({title:'Дата обмена',content:field('Дата обмена','exchange_date','','date',old,true),submitLabel:'Сохранить',onSubmit:async form=>{
   const value=form.elements.exchange_date.value;if(!value)throw new Error('Выбери дату');
   await api('/api/santas/'+event.id,{method:'PATCH',body:{exchange_date:value}});
   event.exchange_date=value;control.textContent=dateRu(value);notice('Изменения сохранены');
  }});return;
 }
 const editor=document.createElement(description?'textarea':'input');
 editor.className='santa-inline-editor santa-inline-editor-'+fieldName;
 if(!description)editor.type=budget?'number':'text';
 if(budget){editor.min='0';editor.max='100000000';editor.step='0.01';}
 if(description)editor.maxLength=800;
 if(fieldName==='title')editor.maxLength=90;
 editor.value=old;
 editor.setAttribute('aria-label',({title:'Название игры',description:'Описание игры',exchange_date:'Дата обмена',budget:'Бюджет подарка'})[fieldName]);
 let settled=false;
 const restore=()=>{if(editor.isConnected)editor.replaceWith(control);};
 const save=async()=>{
  if(settled)return;settled=true;
  const value=editor.value.trim();
  if(value===old.trim()){restore();return;}
  if((fieldName==='title'||date)&&!value){restore();notice('Заполни поле',true);return;}
  if(budget&&(!Number.isFinite(Number(value))||Number(value)<0||Number(value)>100000000)){restore();notice('Некорректный бюджет',true);return;}
  editor.disabled=true;
  try{
   await api('/api/santas/'+event.id,{method:'PATCH',body:{[fieldName]:value}});
   if(budget)event.budget_cents=value===''?null:Math.round(Number(value)*100);else event[fieldName]=value;
   control.textContent=budget?money(event.budget_cents,event.currency):date?dateRu(value):value||(description?'Праздник начинается с маленькой тайны':'');
   restore();notice('Изменения сохранены');
  }catch(error){editor.disabled=false;restore();notice(error.message,true);}
 };
 editor.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();settled=true;restore();control.focus({preventScroll:true});}else if(e.key==='Enter'&&(!description||!e.shiftKey)){e.preventDefault();void save();}});
 editor.addEventListener('blur',()=>{void save();},{once:true});
 control.replaceWith(editor);editor.focus({preventScroll:true});
 if(!budget&&!date)editor.select();
}
function preferenceSummary(preferences,editable=true){
 const row=(title,value,key)=>(editable?'<button type="button" class="game-gift-note santa-pref-row" data-action="edit-santa-preferences" data-pref="'+key+'">':'<div class="game-gift-note santa-pref-row">')+'<strong>'+title+'</strong><p>'+(value?esc(value):'<span class="muted">Не указано</span>')+'</p>'+(editable?'</button>':'</div>');
 return '<div class="participant-preferences-summary">'+
 row('Что хотелось бы',preferences?.wanted,'wanted')+row('Чего не хотелось бы',preferences?.unwanted,'unwanted')+'</div>';
}
async function invitePage(key,marker=lastRenderToken,personal=false){const base=personal?'/api/personal-invites/':'/api/invites/';const {event:e,already_joined,used}=await api(base+key);if(marker!==lastRenderToken)return;shell(`<main class="container page"><div class="invite-card"><div class="invite-icon">${envelopeArt()}</div><div class="section-label" style="text-align:center">Тебя зовут в игру!</div><h1>${esc(e.title)}</h1><p>${esc(e.description||'Кто-то хочет устроить вам небольшой праздник')}</p><div class="invite-info"><div class="info-tile"><small>Когда обмениваемся</small><strong>${dateRu(e.exchange_date)}</strong></div><div class="info-tile"><small>Бюджет</small><strong>${money(e.budget_cents,e.currency)}</strong></div></div>${e.rules?`<div class="details-box"><strong>Правила от организатора</strong><p>${esc(e.rules)}</p></div>`:''}${already_joined?'<div class="alert">Ты уже участвуешь в этой игре. Повторное вступление не требуется</div>':used?'<div class="alert">Личная ссылка уже использована. Попроси организатора прислать новое приглашение</div>':!currentUser?'<div class="invite-auth-gate"><p>Присоединиться могут только зарегистрированные участники. Войди или создай аккаунт, а затем выбери имя в игре</p><div class="btn-row"><button class="btn btn-dark" data-open="login">Войти</button><button class="btn btn-soft" data-open="register">Зарегистрироваться</button></div></div>':e.status==='open'?`<form class="invite-form" id="join-form"><h3>Как тебя зовут?</h3><div class="field"><label for="join-name">Твоё имя</label><input id="join-name" name="name" maxlength="50" required placeholder="Например, Маша"></div><button class="btn btn-dark" type="submit">Присоединиться ${ico('arrow')}</button><p class="note" style="margin-top:15px">После вступления игра появится в твоём аккаунте. Дополнительные ссылки не понадобятся</p></form>`:`<div class="alert">Жеребьёвка уже состоялась. Новые участники присоединиться не могут</div>`}</div></main>`);
 document.getElementById('join-form')?.addEventListener('submit',async ev=>{ev.preventDefault();const btn=ev.currentTarget.querySelector('button');btn.disabled=true;try{const r=await api(base+key+'/join',{method:'POST',body:readForm(ev.currentTarget)});nav('/santa/'+r.event_id,{force:true});notice('Ты в игре!');}catch(err){notice(err.message,true);btn.disabled=false;}});
}
async function participantPage(key,marker=lastRenderToken){
 // Simply viewing a personal link must not silently claim a membership.
 return santaGamePage(null,marker,key);
}

function passwordField(register,name='password',label='Пароль'){
 const generator=register?'<button type="button" class="password-generate" data-password-generate>'+ico('spark')+' Сгенерировать пароль</button>':'';
 return '<div class="field password-field"><div class="password-label-row"><label for="fld-'+attr(name)+'">'+esc(label)+'</label>'+generator+'</div>'+
  '<div class="password-input-row"><input id="fld-'+attr(name)+'" name="'+attr(name)+'" type="password" placeholder="'+(register?'От 8 символов':'Твой пароль')+'" required minlength="8" maxlength="200" autocomplete="'+(register?'new-password':'current-password')+'"'+(register?' aria-describedby="password-hint"':'')+'>'+
  '<button type="button" class="password-visibility" data-password-visibility aria-label="Показать пароль" aria-pressed="false">'+ico('eye')+'</button></div>'+
  (register?'<div class="password-strength" data-password-strength data-level="0" hidden><p data-password-strength-label role="status" aria-live="polite" aria-label="Надёжность пароля"></p><div class="password-strength-bars" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div><p class="password-hint" id="password-hint" hidden aria-live="polite"></p><div class="password-suggestions" data-password-suggestions role="group" aria-label="Более надёжные варианты пароля" hidden></div>':'')+'</div>';
}
function confirmPasswordField(){
 return '<div class="field password-field"><label for="fld-confirm_password">Повтори пароль</label>'+
  '<div class="password-input-row"><input id="fld-confirm_password" name="confirm_password" type="password" placeholder="Тот же пароль" required minlength="8" maxlength="200" autocomplete="new-password">'+
  '<button type="button" class="password-visibility" data-password-visibility aria-label="Показать повтор пароля" aria-pressed="false">'+ico('eye')+'</button></div></div>';
}
function newPasswordIssue(value){
 if(!value)return 'Введи пароль';
 if(/[А-Яа-яЁё]/.test(value))return 'Убери русские буквы из пароля';
 if(Array.from(value).length<8)return passwordLengthIssue(value);
 if(/[\u0000-\u001f\u007f]/.test(value)||Array.from(value).some(c=>c.length===1&&/[\ud800-\udfff]/.test(c)))return 'В пароле есть недопустимые символы';
 if(new TextEncoder().encode(value).length>72)return 'Пароль слишком длинный. Сократи его';
 return '';
}
function passwordLengthIssue(value){
 const count=8-Array.from(value).length;
 if(count<=0)return '';
 const word=count===1?'символ':count<=4?'символа':'символов';
 return 'Добавь ещё '+count+' '+word;
}
function passwordAdvice(value,score=null,reason=''){
 if(!value)return '';
 const issue=newPasswordIssue(value);
 // Mandatory errors block submission, never the help for replacing the password.
 if(issue){
  if(/[А-Яа-яЁё]/.test(value))return 'Варианты без русских букв';
  if(new TextEncoder().encode(value).length>72)return 'Более короткие варианты';
  if(Array.from(value).length<8)return 'Подходящие варианты от 8 символов';
  return 'Варианты без недопустимых символов';
 }
 const missing=[];
 if(!/[a-z]/.test(value))missing.push('1 строчную латинскую букву');
 if(!/[A-Z]/.test(value))missing.push('1 заглавную латинскую букву');
 if(!/[0-9]/.test(value))missing.push('1 цифру');
 if(!/[^\p{L}\p{N}\s]/u.test(value))missing.push('1 спецсимвол');
 if(missing.length){
  const items=missing.length===1?missing[0]:missing.slice(0,-1).join(', ')+' и '+missing.at(-1);
  return 'Добавь хотя бы '+items+', чтобы усилить пароль';
 }
 if(!Number.isInteger(score)||score>1)return '';
 const advice={
  sequence:'Замени последовательности букв или цифр случайными символами',
  repeat:'Замени повторяющиеся символы случайными',
  dictionary:'Замени распространённые слова и комбинации случайными символами',
  spatial:'Избегай последовательностей клавиш на клавиатуре',
  date:'Замени даты и годы случайными цифрами',
  short:'Добавь несколько случайных символов, чтобы усложнить подбор'
 };
 return advice[reason]||'Добавь несколько случайных символов, чтобы усложнить подбор';
}
function setPasswordHint(hint,message){
 if(!hint)return;
 if(hint.textContent!==message)hint.textContent=message;
 hint.hidden=!message;
}
// Use the input's length and missing classes to shape independent examples.
// Never retain its literal characters, dictionary fragments or numeric patterns.
const passwordSuggestions=new WeakMap();
const suggestionObservers=new WeakMap();
function suggestedPassword(value,index){
 const groups=['abcdefghijkmnopqrstuvwxyz','ABCDEFGHJKLMNPQRSTUVWXYZ','23456789','!@#$%&*'];
 const tests=[/[a-z]/,/[A-Z]/,/[0-9]/,/[^\p{L}\p{N}\s]/u];
 const source=Array.from(value);
 const counts=tests.map(test=>source.filter(c=>test.test(c)).length);
 const missing=counts.filter(n=>n===0).length;
 const length=Math.max(12,Math.min(32,source.length+Math.max(2,missing)+(index%3)));
 const random=new Uint32Array(1);
 const number=max=>{const limit=Math.floor(4294967296/max)*max;let n;do{crypto.getRandomValues(random);n=random[0];}while(n>=limit);return n%max;};
 const pick=group=>group[number(group.length)];
 const chars=groups.map(pick);
 // Keep a modest bias toward the user's character mix while ensuring at
 // least one of every class, and enough diversity for numeric-only input.
 const weights=counts.map(n=>1+Math.min(3,Math.floor(4*n/Math.max(1,source.length))));
 const weighted=groups.flatMap((group,i)=>Array(weights[i]).fill(group));
 while(chars.length<length)chars.push(pick(weighted[number(weighted.length)]));
 for(let i=chars.length-1;i>0;i--){const j=number(i+1);[chars[i],chars[j]]=[chars[j],chars[i]];}
 return chars.join('');
}
function renderPasswordSuggestions(input,show=false){
 const panel=input.closest('.password-field')?.querySelector('[data-password-suggestions]');
 if(!panel)return false;
 const previous=suggestionObservers.get(input);
 const hint=input.closest('.password-field')?.querySelector('#password-hint');
 const visibility=input.type==='text'?'visible':'masked';
 if(show&&passwordSuggestions.has(input)&&!panel.hidden&&panel.dataset.visibility===visibility&&panel.firstChild){
  const shown=!!panel.querySelector('button:not([hidden])');
  const advice=hint?.textContent?.replace(/, например:$/,'')||'';
  if(advice)setPasswordHint(hint,advice+(shown?', например:':''));
  return shown;
 }
 if(previous){previous.disconnect();suggestionObservers.delete(input);}
 if(!show||!window.crypto?.getRandomValues){
  passwordSuggestions.delete(input);panel.replaceChildren();panel.hidden=true;return false;
 }
 let values=passwordSuggestions.get(input);
 if(!values){
  values=Array.from({length:6},(_,i)=>suggestedPassword(input.value,i));
  passwordSuggestions.set(input,values);
 }
 const buttons=values.map((value,index)=>{
  const button=document.createElement('button');button.type='button';
  button.dataset.passwordSuggestion=String(index);
  button.textContent=input.type==='text'?value:'Вариант '+(index+1);
  return button;
 });
 panel.replaceChildren(...buttons);panel.dataset.visibility=visibility;panel.hidden=false;
 let lastWidth=-1;
 const fit=()=>{
  if(!input.isConnected){previous?.disconnect();suggestionObservers.get(input)?.disconnect();suggestionObservers.delete(input);return;}
  const width=panel.clientWidth;
  if(width===lastWidth)return;
  lastWidth=width;
  for(const button of buttons)button.hidden=false;
  const gap=parseFloat(getComputedStyle(panel).columnGap)||0;
  let used=0,shown=0;
  const measured=buttons.map(button=>({button,width:button.getBoundingClientRect().width}));
  measured.sort((a,b)=>a.width-b.width);
  for(const item of measured){
   const next=item.width+(shown?gap:0);
   if(used+next<=width+.1){used+=next;shown++;}
   else item.button.hidden=true;
  }
  const advice=hint?.textContent?.replace(/, например:$/,'')||'';
  if(advice)setPasswordHint(hint,advice+(shown?', например:':''));
 };
 fit();
 if(typeof ResizeObserver==='function'){
  const observer=new ResizeObserver(fit);observer.observe(panel);suggestionObservers.set(input,observer);
 }
 document.fonts?.ready.then(()=>{if(input.isConnected&&passwordSuggestions.get(input)===values&&panel.firstChild===buttons[0]){lastWidth=-1;fit();}});
 return buttons.some(button=>!button.hidden);
}
// zxcvbn runs in a same-origin worker, loaded only on new-password input.
let strengthWorker=null,strengthBusy=null,strengthPending=null,strengthDebounce=0,strengthRequestId=0,strengthRetryAt=0,strengthTimeout=0;
const strengthRequests=new WeakMap();
function currentStrengthRequest(job){
 return job&&job.input.isConnected&&strengthRequests.get(job.input)===job.id;
}
function strengthUnavailable(job){
 if(!currentStrengthRequest(job))return;
 renderPasswordStrength(job.input,0);
}
function stopStrengthWorker(){
 clearTimeout(strengthTimeout);strengthTimeout=0;
 strengthWorker?.terminate();strengthWorker=null;
 const pending=strengthPending,active=strengthBusy;
 strengthPending=null;strengthBusy=null;strengthRetryAt=Date.now()+30000;
 strengthUnavailable(active);strengthUnavailable(pending);
}
function pumpStrengthWorker(){
 if(strengthBusy||!strengthPending)return;
 const job=strengthPending;strengthPending=null;
 if(!currentStrengthRequest(job))return;
 if(Date.now()<strengthRetryAt){strengthUnavailable(job);return;}
 try{
  if(!strengthWorker){
   strengthWorker=new Worker('/password-strength-worker.js');
   strengthWorker.onerror=()=>stopStrengthWorker();
   strengthWorker.onmessageerror=()=>stopStrengthWorker();
   strengthWorker.onmessage=event=>{
    const active=strengthBusy;
    if(!active||event.data?.id!==active.id)return;
    clearTimeout(strengthTimeout);strengthTimeout=0;
    strengthBusy=null;
    if(currentStrengthRequest(active)){
     const score=event.data.score;
     if(newPasswordIssue(active.input.value))
      renderPasswordStrength(active.input,0,'Не подходит');
     else if(Number.isInteger(score)&&score>=0&&score<=4){
      renderPasswordStrength(active.input,Math.max(1,score));
      const hint=active.input.closest('.password-field')?.querySelector('#password-hint');
      const advice=hint?.dataset.generated==='true'?'':passwordAdvice(active.input.value,score,event.data.reason);
      if(hint&&hint.dataset.generated!=='true')setPasswordHint(hint,advice);
      renderPasswordSuggestions(active.input,!!advice);
     }
     else strengthUnavailable(active);
    }
    pumpStrengthWorker();
   };
  }
  strengthBusy=job;
  // No password in a URL, fetch, log, storage or telemetry. Only worker IPC.
  const form=job.input.form;
  const context=[form?.elements.email?.value,form?.elements.name?.value].filter(Boolean);
  strengthWorker.postMessage({id:job.id,password:job.input.value,context});
  strengthTimeout=setTimeout(stopStrengthWorker,15000);
 }catch{stopStrengthWorker();strengthUnavailable(job);}
}
function updatePasswordStrength(input){
 renderPasswordSuggestions(input,false);
 const id=++strengthRequestId;
 strengthRequests.set(input,id);
 clearTimeout(strengthDebounce);
 strengthPending=null;
 // The server rejects passwords outside the bcrypt boundary. Do not score
 // an arbitrarily truncated prefix or retain long invalid input in the queue.
 if(!input.value){renderPasswordStrength(input,0);return;}
 const advice=passwordAdvice(input.value);
 if(newPasswordIssue(input.value)){
  renderPasswordStrength(input,0,'Не подходит');
  renderPasswordSuggestions(input,!!advice);return;
 }
 // Missing classes can be diagnosed immediately, even without the worker.
 if(advice)renderPasswordSuggestions(input,true);
 const indicator=input.closest('.password-field')?.querySelector('[data-password-strength]');
 if(indicator?.querySelector('[data-password-strength-label]')?.textContent==='Не подходит')
  renderPasswordStrength(input,0,'Оценка…');
 strengthDebounce=setTimeout(()=>{
  if(!input.isConnected||strengthRequests.get(input)!==id)return;
  strengthPending={id,input};pumpStrengthWorker();
 },60);
}
// One CSS progress value drives every segment. Retargeting starts from the
// current interpolated value; no per-segment timers or queued animations.
const passwordMeterMotion=new WeakMap();
function renderPasswordStrength(input,target,status=''){
 const indicator=input.closest('.password-field')?.querySelector('[data-password-strength]');
 if(!indicator)return;
 const node=indicator.querySelector('[data-password-strength-label]');
 const label=status||['','Слабый','Средний','Хороший','Надёжный'][target];
 if(node.textContent!==label)node.textContent=label;
 const pending=passwordMeterMotion.get(indicator);
 if(pending)clearTimeout(pending);
 passwordMeterMotion.delete(indicator);
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const show=target>0||!!status;
 if(show&&indicator.hidden){
  indicator.hidden=false;
  // Establish the empty state before assigning the next CSS target.
  void indicator.offsetWidth;
 }
 indicator.dataset.targetLevel=String(target);
 indicator.dataset.level=String(target);
 if(reduced){
  indicator.getAnimations().forEach(animation=>animation.cancel());
  indicator.style.setProperty('--shursh-strength-progress',String(target));
 }else indicator.style.removeProperty('--shursh-strength-progress');
 if(show)return;
 if(reduced||indicator.hidden||!(parseFloat(getComputedStyle(indicator).getPropertyValue('--shursh-strength-progress'))>0)){indicator.hidden=true;return;}
 const timer=setTimeout(()=>{
  passwordMeterMotion.delete(indicator);
  if(indicator.dataset.targetLevel==='0'&&!node.textContent)indicator.hidden=true;
 },460);
 passwordMeterMotion.set(indicator,timer);
}
function securePassword(length=20){
 if(!window.crypto || !crypto.getRandomValues)throw new Error('Для генерации пароля нужно защищённое HTTPS-соединение');
 const groups=['ABCDEFGHJKLMNPQRSTUVWXYZ','abcdefghijkmnopqrstuvwxyz','23456789','!@#$%&*'];
 const alphabet=groups.join(''),random=new Uint32Array(1);
 const pick=chars=>{const limit=Math.floor(4294967296/chars.length)*chars.length;let n;do{crypto.getRandomValues(random);n=random[0];}while(n>=limit);return chars[n%chars.length];};
 const chars=groups.map(pick);
 while(chars.length<length)chars.push(pick(alphabet));
 for(let i=chars.length-1;i>0;i--){const j=Math.floor(crypto.getRandomValues(new Uint32Array(1))[0]*(i+1)/4294967296);[chars[i],chars[j]]=[chars[j],chars[i]];}
 return chars.join('');
}
function authFormWarning(){
 return '<p class="auth-form-warning" role="alert" tabindex="-1" hidden></p>';
}
function clearAuthFormWarning(form){
 const warning=form.querySelector('.auth-form-warning');
 if(warning){warning.hidden=true;warning.textContent='';}
}
function showAuthFormWarning(error,form){
 const warning=form.querySelector('.auth-form-warning');
 if(!warning)return;
 const status=error?.status;
 let message;
 if(!status)message='Не удалось связаться с сервером. Попробуй ещё раз';
 else if(status===429)message='Слишком много попыток. Попробуй позже';
 else if(status>=500)message=error.message==='Сейчас не удалось проверить безопасность пароля. Попробуй ещё раз'?error.message:'Сервис входа временно недоступен. Попробуй позже';
 else message=error.message||'Проверь данные и попробуй ещё раз';
 warning.textContent=message.replace(/\.+$/,'');
 warning.hidden=false;
 warning.focus();
}
function confirmationModal(email){
 modal({title:'Проверь почту 💌',subtitle:'Ещё один маленький шаг - и все желания будут под рукой',
  content:'<div class="auth-confirm-card" role="status"><span class="auth-confirm-symbol" aria-hidden="true">'+ico('mail',28)+'</span><div class="auth-confirm-message"><strong>Запрос принят</strong><p>Если адрес <b>'+esc(email)+'</b> ожидает подтверждения, письмо должно прийти на эту почту</p></div></div>'+
   '<p class="auth-confirm-help">Если аккаунт уже есть, новое письмо может не прийти - войди с прежним паролем. Проверь адрес и «Спам», прежде чем запрашивать новое письмо</p>',
  footer:'<button type="button" data-open="resend" data-email="'+attr(email)+'">Отправить письмо ещё раз</button> · <button type="button" data-open="login" data-email="'+attr(email)+'">Войти</button>'});
}
function resendConfirmationModal(email=''){
 modal({title:'Повторить подтверждение',subtitle:'Если адрес ожидает подтверждения, отправим ещё одно письмо',
  content:field('Почта','email','you@example.com','text',email,true,'inputmode="email" autocomplete="email" autocapitalize="none" spellcheck="false" maxlength="200"')+
    '<p class="auth-confirm-help">Используй адрес, указанный при регистрации. Отправка нового письма может быть ограничена по частоте</p>'+authFormWarning(),
  onError:showAuthFormWarning,
  submitLabel:'Отправить письмо',
  onSubmit:async form=>{
   clearAuthFormWarning(form);
   const payload=readForm(form);
   await api('/api/auth/resend',{method:'POST',body:payload});
   if(!form.isConnected)return;
   modal({title:'Проверь почту 💌',content:'<p>Запрос принят. Если адрес ещё не подтверждён, проверь входящие и «Спам». Если аккаунт уже подтверждён, войди с паролем</p>',
     footer:'<button type="button" data-open="login" data-email="'+attr(payload.email)+'">Войти в аккаунт</button>'});
  },
  footer:'Уже подтвердил адрес? <button type="button" data-open="login" data-email="'+attr(email)+'">Войти</button>'});
 setupAuthFormValidation(modalRoot.querySelector('#modal-form'),false);
}
function authEmailIssue(value){
 const email=value.trim();
 if(!email)return 'Укажи почту';
 if(Array.from(email).length>200)return 'Адрес почты слишком длинный';
 if(/\s/.test(email))return 'Убери пробелы из адреса';
 if(/[\u0000-\u001f\u007f]/.test(email))return 'Убери управляющие символы из адреса';
 if(email.includes(','))return 'Убери запятую из адреса';
 if(email.includes('"'))return 'Убери двойные кавычки из адреса';
 if(/[()[\]<>]/.test(email))return 'Убери скобки из адреса';
 if(email.includes(':'))return 'Убери двоеточие из адреса';
 if(email.includes(';'))return 'Убери точку с запятой из адреса';
 if(email.includes('\\'))return 'Убери обратную косую черту из адреса';
 const parts=email.split('@');
 if(parts.length>2)return 'В адресе должен быть только один знак @';
 const [local,domain]=parts;
 if(!local)return 'Укажи имя почты перед @';
 if(/[^\x21-\x7e]/.test(local))return 'Перед @ используй латинские буквы, цифры и допустимые знаки';
 if(local.length>64)return 'Часть почты перед @ слишком длинная';
 if(local.startsWith('.')||local.includes('..')||(parts.length===2&&local.endsWith('.')))return 'Исправь точки в части почты перед @';
 if(!/^[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+$/.test(local))return 'Проверь символы в части почты перед @';
 if(parts.length===1)return 'Добавь знак @';
 if(!domain)return 'Укажи домен после @';
 if(/[^\x21-\x7e]/.test(domain))return 'Используй латинские буквы после @';
 // Reject invalid characters before diagnosing an unfinished domain.
 if(domain.includes('_'))return 'Убери нижнее подчёркивание из домена';
 const badDomain=domain.match(/[^a-z0-9.-]/i)?.[0];
 if(badDomain)return 'Убери символ '+badDomain+' из домена';
 if(domain.startsWith('.')||domain.includes('..'))return 'Убери лишние точки в домене';
 const labels=domain.split('.');
 if(labels.some(label=>label.startsWith('-')||label.endsWith('-')))return 'Домен не должен начинаться или заканчиваться дефисом';
 if(labels.some(label=>label.length>63))return 'Часть домена между точками слишком длинная';
 if(domain.endsWith('.'))return 'Допиши окончание домена, например ru или com';
 if(!domain.includes('.'))return 'Укажи домен с точкой, например example.com';
 if(!/^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$/i.test(labels.at(-1)))return 'Проверь окончание домена, например .ru или .com';
 if(/^(?:gmail|googlemail)\.com$/i.test(domain)){
  const base=local.split('+',1)[0],bad=base.match(/[^a-z0-9.]/i)?.[0];
  if(!base)return 'Укажи имя почты Gmail перед +';
  if(bad)return 'Убери символ '+bad+' из имени почты Gmail';
 }
 if(email.toLowerCase()==='demo@shursh.local')return 'Этот адрес недоступен для входа';
 return '';
}
function authFieldIssue(input, form, register){
 const value=input.value, kind=input.name;
 if(kind==='code'&&!/^[0-9]{6}$/.test(value.trim()))return 'Введи шесть цифр из письма';
 if(kind==='name' && register){
  const trimmed=value.trim();
  if(!trimmed)return 'Укажи имя';
  if(trimmed.length>40)return 'Имя должно быть не длиннее 40 символов';
  if(/[\u0000-\u001f\u007f]/.test(trimmed))return 'В имени есть недопустимые символы';
 }
 if(kind==='email')return authEmailIssue(value);
 if(kind==='password'||kind==='new_password'||kind==='current_password'){
  if(!value)return 'Введи пароль';
  const len=Array.from(value).length;
  if(register&&kind!=='current_password')return newPasswordIssue(value);
  if((len<8||len>200||value.includes('\u0000'))){
   return 'Пароль должен содержать от 8 до 200 символов';
  }
 }
 if(kind==='confirm_password' && register){
  if(!value)return 'Повтори пароль';
  if(value!==(form.elements.new_password||form.elements.password)?.value)return 'Пароли не совпадают';
 }
 return '';
}
// Paint only error ranges over the real input; never duplicate password text.
const authCharacterHighlights=new WeakMap();
function authInvalidCharRanges(input,register,message){
 if(!message)return [];
 const value=input.value,ranges=[];
 const add=(text,pattern,offset=0)=>{
  for(const match of text.matchAll(pattern))ranges.push([offset+match.index,offset+match.index+match[0].length]);
 };
 if(register&&['password','new_password'].includes(input.name)){
  if(input.type==='text')add(value,/[А-Яа-яЁё\u0000-\u001f\u007f]+/gu);
  return ranges;
 }
 if(input.name!=='email')return ranges;
 const email=value.trim(),offset=value.length-value.trimStart().length;
 add(email,/[\s\u0000-\u001f\u007f,"()[\]<>:;\\]+/gu,offset);
 const at=email.indexOf('@');
 if(at<0){
  add(email,/[^A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+/gu,offset);
  for(let i=0;i<email.length;i++)if(email[i]==='.'&&(i===0||email[i-1]==='.'))ranges.push([offset+i,offset+i+1]);
  return ranges;
 }
 const local=email.slice(0,at),domain=email.slice(at+1),domainOffset=offset+at+1;
 add(domain,/@/g,domainOffset);
 add(local,/[^A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+/gu,offset);
 add(domain,/[^A-Za-z0-9.@-]+/gu,domainOffset);
 const dots=(text,start,allowTrailing=false)=>{
  for(let i=0;i<text.length;i++)if(text[i]==='.'&&(i===0||(!allowTrailing&&i===text.length-1)||text[i-1]==='.'))ranges.push([start+i,start+i+1]);
 };
 dots(local,offset);dots(domain,domainOffset,true);
 if(/^(?:gmail|googlemail)\.com$/i.test(domain)){
  const base=local.split('+',1)[0];
  if(!base)ranges.push([offset,offset+1]);
  else add(base,/[^a-z0-9.]+/gi,offset);
 }
 let start=domainOffset;
 for(const label of domain.split('.')){
  if(label.startsWith('-'))ranges.push([start,start+1]);
  if(label.length>1&&label.endsWith('-'))ranges.push([start+label.length-1,start+label.length]);
  start+=label.length+1;
 }
 const lastDot=domain.lastIndexOf('.');
 if(lastDot>=0){
  const tld=domain.slice(lastDot+1);
  if(tld&&/^[a-z0-9-]+$/i.test(tld)&&!/^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$/i.test(tld))
   ranges.push([domainOffset+lastDot+1,domainOffset+domain.length]);
 }
 return ranges;
}
function installAuthCharacterHighlights(input,register){
 if(input.name!=='email'&&!(register&&['password','new_password'].includes(input.name)))return;
 let wrapper=input.parentElement;
 if(input.name==='email'){
  wrapper=document.createElement('div');wrapper.className='auth-character-input-row';
  input.before(wrapper);wrapper.append(input);
 }
 let canvas=null,message='',frame=0;
 const clear=()=>{if(canvas){canvas.hidden=true;canvas.width=0;canvas.height=0;}};
 const paint=()=>{
  if(!input.isConnected||input.type==='password'||!message){clear();return;}
  const ranges=authInvalidCharRanges(input,register,message);
  if(!ranges.length){clear();return;}
  // Mixed bidi text can reorder glyphs; retain the explicit error instead.
  if(/[\u0590-\u08ff\u202a-\u202e\u2066-\u2069]/u.test(input.value)){clear();return;}
  const rect=input.getBoundingClientRect();
  if(!rect.width||!rect.height){clear();return;}
  if(!canvas){
   canvas=document.createElement('canvas');canvas.className='auth-character-overlay';
   canvas.setAttribute('aria-hidden','true');wrapper.append(canvas);
  }
  const ratio=Math.min(window.devicePixelRatio||1,3),w=rect.width,h=rect.height;
  canvas.style.width=w+'px';canvas.style.height=h+'px';
  canvas.width=Math.ceil(w*ratio);canvas.height=Math.ceil(h*ratio);
  const ctx=canvas.getContext('2d');
  if(!ctx){clear();return;}
  ctx.scale(ratio,ratio);
  const style=getComputedStyle(input),px=name=>parseFloat(style[name])||0;
  ctx.font=style.fontStyle+' '+style.fontWeight+' '+style.fontSize+' '+style.fontFamily;
  if('letterSpacing' in ctx)ctx.letterSpacing=style.letterSpacing==='normal'?'0px':style.letterSpacing;
  if('fontKerning' in ctx)ctx.fontKerning=style.fontKerning;
  const left=px('borderLeftWidth')+px('paddingLeft');
  const right=w-px('borderRightWidth')-px('paddingRight');
  const size=px('fontSize'),top=(h-size)/2-2,bottom=top+size+4;
  const origin=left-input.scrollLeft;
  const width=text=>ctx.measureText(text).width+('letterSpacing' in ctx?0:Array.from(text).length*px('letterSpacing'));
  ctx.beginPath();ctx.rect(left,0,Math.max(0,right-left),h);ctx.clip();
  const merged=[];
  for(const range of ranges.sort((a,b)=>a[0]-b[0])){
   const last=merged.at(-1);
   if(last&&range[0]<=last[1])last[1]=Math.max(last[1],range[1]);
   else merged.push(range);
  }
  for(const [from,to] of merged){
   const x=origin+width(input.value.slice(0,from));
   const end=origin+width(input.value.slice(0,to));
   const span=Math.max(2,end-x);
   ctx.fillStyle='rgba(173,48,43,.15)';ctx.fillRect(x,top,span,bottom-top);
   ctx.fillStyle='#9f302b';ctx.fillRect(x,bottom-1,span,2);
  }
  canvas.hidden=false;
 };
 const schedule=()=>{
  if(!message||input.type==='password'||frame)return;
  frame=requestAnimationFrame(()=>{frame=0;paint();});
 };
 const update=next=>{
  if(typeof next==='string')message=next;
  if(!message||input.type==='password'){
   if(frame){cancelAnimationFrame(frame);frame=0;}
   clear();return;
  }
  paint();schedule();
 };
 authCharacterHighlights.set(input,update);
 // Insertion/paste and selection changes can move the native scroll offset
 // after the input handler. Coalesce a post-layout repaint into one frame.
 for(const event of ['input','scroll','focus','blur','keyup','click','select','compositionend'])
  input.addEventListener(event,schedule);
 document.fonts?.ready.then(()=>{if(message&&input.isConnected)paint();});
}
window.addEventListener('resize',()=>{
 for(const input of document.querySelectorAll('#modal-form input[aria-invalid="true"]'))authCharacterHighlights.get(input)?.();
});
const AUTH_EMAIL_IDLE_MS=2000;
function authEmailIncompleteIssue(value,message){
 const email=value.trim();
 if(message==='Добавь знак @')
  return /^[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+$/.test(email)&&!email.startsWith('.')&&!email.includes('..');
 if(message==='Укажи домен после @'||message==='Укажи домен с точкой, например example.com'||message==='Допиши окончание домена, например ru или com')return true;
 if(message==='Проверь окончание домена, например .ru или .com')
  return /\.[a-z]$/i.test(email);
 return false;
}
function setupAuthFormValidation(form,register){
 if(!form)return;
 // Inline errors, not native validation popups which differ across mobile browsers.
 form.noValidate=true;
 const names=register?['name','email','password','current_password','new_password','confirm_password']:['email','password','current_password','code'];
 const inputs=names.map(name=>form.elements.namedItem(name)).filter(Boolean);
 const touched=new Set();
 let emailIdleTimer=0;
 const cancelEmailIdle=()=>{if(emailIdleTimer)clearTimeout(emailIdleTimer);emailIdleTimer=0;};
 const validate=(input,override)=>{
  const message=override===undefined?authFieldIssue(input,form,register):override, field=input.closest('.field');
  const id='auth-error-'+input.name;
  let node=field?.querySelector('#'+id);
  if(!node&&field){
   node=document.createElement('p');
   node.id=id;node.className='auth-field-error';node.setAttribute('aria-live','polite');
   node.hidden=true;
   const passwordHint=field.querySelector('#password-hint');
   if(passwordHint)field.insertBefore(node,passwordHint);else field.append(node);
  }
  if(node){if(node.textContent!==message)node.textContent=message;node.hidden=!message;}
  if(message)input.setAttribute('aria-invalid','true');
  else input.removeAttribute('aria-invalid');
  authCharacterHighlights.get(input)?.(message);
  const hint=['password','new_password'].includes(input.name)&&register?'password-hint':'';
  const ids=[hint,message?id:''].filter(Boolean).join(' ');
  if(ids)input.setAttribute('aria-describedby',ids);
  else input.removeAttribute('aria-describedby');
  return message;
 };
 for(const input of inputs){
  installAuthCharacterHighlights(input,register);
  if(input.name==='email'&&input.value){touched.add(input.name);validate(input);}
  input.addEventListener('blur',event=>{
   // Modal footer controls are moved into a fixed rail. Creating an error while
   // pointer-down changes dialog height and can swallow a click on "Register".
   // Navigation does not require validating the old form; submit validates all.
   if(event.relatedTarget?.closest('[data-open],[data-close],[type="submit"]'))return;
   touched.add(input.name);
   // Preserve the typing deadline even when focus moves to another field.
   if(input.name==='email'&&emailIdleTimer)return;
   validate(input);
  });
  input.addEventListener('input',()=>{
   const newPassword=register&&['password','new_password'].includes(input.name);
   if(newPassword){
    const hint=form.querySelector('#password-hint');
    if(hint){
     delete hint.dataset.generated;
     setPasswordHint(hint,passwordAdvice(input.value));
    }
   }
   if(register&&input.name==='confirm_password'){
    const hint=form.querySelector('#password-hint');
    const primary=form.elements.new_password||form.elements.password;
    if(hint?.dataset.generated==='true'&&primary&&input.value!==primary.value){
     delete hint.dataset.generated;
     setPasswordHint(hint,passwordAdvice(primary.value));
    }
   }
   if(newPassword)updatePasswordStrength(input);
   // Illegal characters are immediate; unfinished structure waits until
   // the user has stopped editing for two seconds. No stale timer may paint
   // an error on a replaced modal or an updated value.
   if(input.name==='email'){
    cancelEmailIdle();
    if(input.value)touched.add(input.name);
    if(touched.has(input.name)){
     const message=authFieldIssue(input,form,register);
     if(authEmailIncompleteIssue(input.value,message)){
      validate(input,'');
      const snapshot=input.value;
      emailIdleTimer=setTimeout(()=>{
       emailIdleTimer=0;
       if(form.isConnected&&input.isConnected&&input.value===snapshot)validate(input);
      },AUTH_EMAIL_IDLE_MS);
     }else validate(input,message);
    }
   }else{
    if(newPassword&&input.value)touched.add(input.name);
    if(touched.has(input.name)||newPassword&&input.value)validate(input);
   }
   if(register&&['password','new_password'].includes(input.name)&&touched.has('confirm_password')){
    validate(form.elements.confirm_password);
   }
  });
 }
 form.addEventListener('submit',event=>{
  cancelEmailIdle();
  const invalid=inputs.filter(input=>{touched.add(input.name);return !!validate(input);});
  if(invalid.length){
   event.preventDefault();event.stopImmediatePropagation();
   invalid[0].focus({preventScroll:false});
   return;
  }
  if(form.elements.email)form.elements.email.value=form.elements.email.value.trim().toLowerCase();
  if(register&&form.elements.name)form.elements.name.value=form.elements.name.value.trim();
 },true);
}
// Let the browser's own password manager offer to save successful sign-ins.
 // Never persist credentials in app storage; unsupported or rejected requests
 // must not affect authentication or navigation.
function offerLoginCredential(email,password){
 if(isPreview||!window.isSecureContext||typeof window.PasswordCredential!=='function'||typeof navigator.credentials?.store!=='function')return;
 try{void navigator.credentials.store(new window.PasswordCredential({id:email,password})).catch(()=>{});}catch{}
}
async function authSuccess(result,register){
 clearOwnerDataCache();currentUser=result.user;broadcastSessionChange();
 if(pendingGameClaim){
  const claim=pendingGameClaim;
  try{await claimPersonalGame(claim);}
  catch(error){nav('/p/'+claim,{force:true});notice('Ты вошёл, но игру пока не удалось привязать: '+error.message,true);}
  return;
 }
 const landing=result.invite_path||currentPath();
 nav((/^\/join\/([A-Za-z0-9_-]+|p\/[A-Za-z0-9_-]{43})$/.test(landing)||/^\/w\/[A-Za-z0-9_-]+$/.test(landing)||/^\/i\/[A-Za-z0-9_-]{24}$/.test(landing))?landing:'/',{force:true});
 notice(register?'Аккаунт создан!':'С возвращением!');
}
function loginModal(mode='login',email=''){
 const register=mode==='register';
 // Real touch browsers use a native POST/redirect login. AJAX remains for
 // desktop and preview, where the Credential Management API is available.
 const loginCsrf=document.querySelector('meta[name="shursh-login-csrf"]')?.content||'';
 const nativeSubmit=!register&&!isPreview&&/^[A-Za-z0-9_-]{43}$/.test(loginCsrf)&&matchMedia('(pointer: coarse)').matches;
 // Registering or logging in directly from a private participant page
 // is an explicit membership recovery action, even via the header.
 const pageToken=!currentUser&&currentPath().match(/^\/p\/([A-Za-z0-9_-]{43})$/)?.[1];
 if(pageToken&&!pendingGameClaim)savePendingGameClaim(pageToken);
 modal({nativeSubmit,authScreen:register?'register':'login',title:register?'Давай знакомиться!':'С возвращением!',
  subtitle:pendingGameClaim?'После входа сохраним эту игру в твоём аккаунте':register?'Создай аккаунт, чтобы хранить свои списки и организовывать игры':'Твои желания уже соскучились',
  content:(register?field('Как тебя зовут?','name','Например, Саша','text','',true,'maxlength="40" autocomplete="name"'):'')+
   field('Почта','email','you@example.com','text',email,true,'inputmode="email" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="200"')+passwordField(register)+
   (register?confirmPasswordField():shurshCheckbox('remember','Оставаться в аккаунте 30 дней',true))+
   (nativeSubmit?'<input type="hidden" name="login_csrf" value="'+attr(loginCsrf)+'"><input type="hidden" name="return_path" value="'+attr(currentPath())+'">':'')+authFormWarning(),
  onError:showAuthFormWarning,
  submitLabel:register?'Создать аккаунт':'Войти',
  onSubmit:async form=>{
   clearAuthFormWarning(form);
   const payload=readForm(form);
   delete payload.confirm_password;
   if(!register)payload.remember=!!form.elements.remember?.checked;
   const invite=currentPath().match(/^\/i\/([A-Za-z0-9_-]{24})$/)?.[1];
   if(register&&invite)payload.invite_code=invite;
   const result=await api(register?'/api/register':'/api/login',{method:'POST',body:payload});
   if(result.pending_confirmation){if(register)persistSignupClaim();if(form.isConnected)confirmationModal(payload.email);return;}
   if(!register&&result.user)offerLoginCredential(payload.email,payload.password);
   await authSuccess(result,register);
  },
  footer:(register?'Уже есть аккаунт?':'Нет аккаунта?')+
   ' <button type="button" data-open="'+(register?'login':'register')+'">'+(register?'Войти':'Зарегистрироваться')+'</button>'+
   (!register?'<span> · </span><button type="button" data-open="resend">Не пришло подтверждение?</button>':'')+
   (!register&&isDemo?'<p style="margin-top:12px"><button type="button" data-action="demo-login">Войти в демонстрационный аккаунт →</button></p>':'')
 });
 const form=modalRoot.querySelector('#modal-form');
 if(form){
  form.setAttribute('method','post');
  form.setAttribute('action',register?'/api/register':'/api/login');
  form.setAttribute('autocomplete','on');
 }
 setupAuthFormValidation(form,register);
}
function listModal(edit=null){if(!currentUser){loginModal('register');return;}
 const selected=edit||{};modal({title:edit?'Настройки вишлиста':'Новый вишлист',subtitle:edit?'Меняй оформление и доступ, когда захочешь':'Как назовём твою маленькую коллекцию желаний?',content:`${field('Название','title','Например, День рождения, ура!','text',selected.title||'',true,'maxlength="90"')}${textArea('Пара слов о списке','description','Что важно знать дарителям?',selected.description||'')}<div class="form-grid">${selectField('Повод','occasion',['Просто так','День рождения','Годовщина','Новоселье','Свадьба','Новый год','Другое'].map(v=>[v,v]),selected.occasion||'День рождения')}${selectField('Оформление','theme',[['peach','🟠 Персиковое'],['lilac','🟣 Лавандовое'],['mint','🟢 Мятное'],['yellow','🟡 Солнечное']],selected.theme||'peach')}</div>${selectField('Доступ к списку','visibility',[['link','По ссылке'],['private','Только мне']],selected.visibility||'link')}${!isPreview?'<div class="field"><label for="wishlist-cover-file">Своя обложка (необязательно)</label><div class="file-picker"><input id="wishlist-cover-file" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"></div></div>'+(selected.cover_path?shurshCheckbox('remove_cover','Вернуть тематическую обложку',false):''):''}`,submitLabel:edit?'Сохранить':'Создать список',onSubmit:async form=>{const payload=readForm(form);delete payload.remove_cover;const file=form.querySelector('#wishlist-cover-file')?.files?.[0];if(file)payload.cover_data=await compressToWebp(file,{maxDimension:960,maxBytes:65000});else if(form.elements.remove_cover?.checked)payload.cover_data=null;if(edit){await api(`/api/lists/${edit.id}`,{method:'PATCH',body:payload});notice('Настройки сохранены');await render();}else{const r=await api('/api/lists',{method:'POST',body:payload});nav(`/list/${r.id}`);notice('Список создан!');}}});}
function fixWishModalLayout(){
 const dialog=modalRoot.querySelector('.modal');
 dialog?.classList.add('wish-edit-modal');
 // Keep heading and action buttons fixed while only the long form scrolls.
 const scrollArea=dialog?.querySelector('.modal-scroll-area');
 const heading=scrollArea?.querySelector(':scope > h2');
 const actions=scrollArea?.querySelector('#modal-form > .form-actions');
 if(scrollArea&&heading&&actions){
  const fixedHeader=document.createElement('div');
  fixedHeader.className='modal-fixed-header';
  fixedHeader.appendChild(heading);
  dialog.insertBefore(fixedHeader,scrollArea);
  const fixedFooter=document.createElement('div');
  fixedFooter.className='modal-fixed-footer';
  actions.querySelector('[type="submit"]')?.setAttribute('form','modal-form');
  fixedFooter.appendChild(actions);
  dialog.appendChild(fixedFooter);
 }
}
function wishModal(edit=null){
 if(!currentUser||!loadedList){notice('Сначала открой список',true);return;}
 const listId=loadedList.list.id,w=edit||{};
 modal({
  title:edit?'Редактировать желание':'Добавить желание',
  subtitle:'Можно добавить конкретную вещь или просто идею. Ссылка на магазин необязательна',
  content:
   field('Ссылка на товар (необязательно)','shop_url','https://...', 'url',w.shop_url||'')+
   '<p class="field-hint">Сохраним ссылку, а название, цену и фото ты добавишь самостоятельно</p>'+
   field('Что хочется?','title','Например, керамическая чашка','text',w.title||'',true,'maxlength="130"')+
   textArea('Комментарий','description','Цвет, размер, пожелания или настроение',w.description||'')+
   field('Ориентировочная цена','price','Например, 2500','number',w.price_cents!=null?w.price_cents/100:'',false,'min="0" step="0.01"')+
   '<div class="form-grid">'+
   selectField('Тип','kind',[['item','Конкретный подарок'],['experience','Идея / впечатление']],w.kind||'item')+
   selectField('Приоритет','priority',[['nice','Было бы здорово'],['love','Очень хочу!']],w.priority||'nice')+
   '</div>'+
   '<div class="field"><label for="wish-file">Фотография (необязательно)</label>'+
   '<div class="file-picker"><input id="wish-file" name="image" type="file" accept="image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif">'+
   '<div class="field-hint">JPG, PNG, WebP или HEIC до 12 МБ</div></div></div>',
  submitLabel:edit?'Сохранить':'Добавить в список',
  onSubmit:async form=>{
   const data=readForm(form);
   delete data.image;
   const file=form.elements.image.files[0];
   if(file)data.image_data=await compressToWebp(file,{maxDimension:1440,maxBytes:850000});
   if(edit){
    await api('/api/wishes/'+edit.id,{method:'PATCH',body:data});
    notice('Желание обновлено');
   }else{
    await api('/api/lists/'+listId+'/wishes',{method:'POST',body:data});
    notice('Желание добавлено!');
   }
   await refreshOwnerWishes(listId);
  }
 });
 fixWishModalLayout();

}
function fileToData(file){return compressToWebp(file,{maxDimension:1440,maxBytes:850000});}
function santaModal(){if(!currentUser){loginModal('register');return;}modal({title:'Создать Тайного Санту',subtitle:'Праздничный заговор начинается здесь. Ты автоматически станешь первым участником',content:`${field('Название игры','title','Например, Санта в нашем офисе','text','',true,'maxlength="100"')}${textArea('Описание','description','Кого зовём и что задумали?')}<div class="form-grid">${field('Дата обмена','exchange_date','','date')}${field('Бюджет','budget','Например, 2500','number','','','min="0" step="0.01"')}</div>${textArea('Дополнительные правила','rules','Что стоит учесть каждому?')}`,submitLabel:'Создать игру',onSubmit:async form=>{const r=await api('/api/santas',{method:'POST',body:readForm(form)});nav(`/santa/${r.id}`);notice('Игра создана! Зови участников');}});}

function showParticipantLink(token,name){
 const url=getLink('/p/'+token);
 modal({title:'Личная ссылка участника',subtitle:'Передай ссылку только участнику '+name+'. Он должен открыть её и выбрать «Сохранить игру в аккаунте». Одного совпадения имени недостаточно',
   content:'<div class="share-field"><input class="input" readonly aria-label="Личная ссылка участника" value="'+attr(url)+'">'+
     '<button type="button" class="btn btn-dark btn-small" data-action="copy" data-url="'+attr(url)+'">'+ico('copy')+' Копировать</button></div>'+
     '<p class="note">Ссылка показывается сейчас. Позже организатор может выпустить новую, но старая перестанет работать</p>'});
}
function showPersonalInviteLink(value){
 const link=getLink('/join/p/'+value);
 modal({title:'Личное приглашение',subtitle:'Ссылка действует 24 часа, рассчитана на одного человека. Получатель входит в аккаунт и сам указывает имя',
  content:'<div class="share-field"><input class="input" readonly aria-label="Личная ссылка для приглашения" value="'+attr(link)+'">'+
   '<button type="button" class="btn btn-dark btn-small" data-action="copy" data-url="'+attr(link)+'">'+ico('copy')+' Копировать</button></div>'+
   '<p class="note">До присоединения ссылка не создаёт участника игры. После первого успешного входа ею нельзя воспользоваться повторно</p>'});
}
function addPlayerModal(){
 const event=loadedSanta?.event;
 if(!event||event.status!=='open')return;
 modal({title:'Создать личное приглашение',subtitle:'Имя указывать не нужно: человек сам заполнит его после входа или регистрации',
  content:'<p class="note">Отправь полученную ссылку одному человеку. Общая ссылка находится в блоке участников игры</p>',
  submitLabel:'Создать ссылку',onSubmit:async()=>{
   const result=await api('/api/santas/'+event.id+'/personal-invites',{method:'POST',body:{}});
   showPersonalInviteLink(result.invite_token);
  }});
}
async function importOwnWishesModal(el){
 if(!currentUser){loginModal();return;}
 // One server call fetches only safe list/gift titles (no bulky image blobs).
 const collection=await api('/api/santa/library');
 const lists=collection.lists||[];
 if(!lists.length){notice('Сначала создай собственный вишлист',true);return;}
 const state=activeGameContext;
 if(!state||!el.isConnected)return;
 const endpoint=state.base+(state.base.startsWith('/api/santas/')?'/my-wishes/import':'/wishes/import');
 const options=lists.map(l=>'<option value="'+l.id+'">'+esc(l.title)+'</option>').join('');
 modal({title:'Добавить из вишлиста',subtitle:'Выбери список и подарки. Копируются название, описание, цена, ссылка и доступное фото',
   content:'<div class="field"><label for="import-list">Вишлист</label><select id="import-list" name="list_id">'+options+'</select></div>'+
     '<div id="import-wish-choices" class="import-wish-choices" role="group" aria-label="Выбрать подарки"></div>',
   submitLabel:'Добавить выбранное',onSubmit:async form=>{
     const list_id=Number(form.querySelector('#import-list').value);
     const wish_ids=[...form.querySelectorAll('[name="wish_ids"]:checked')].map(input=>Number(input.value));
     if(!wish_ids.length)throw new Error('Выбери хотя бы один подарок');
     const result=await api(endpoint,{method:'POST',body:{list_id,wish_ids}});
     notice(result.added?'Добавлено '+ruCount(result.added,'подарок','подарка','подарков'):'Эти подарки уже добавлены');
     if(result.added)await refreshGameOwnWishes(state);
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
function personalGameTokenFromLink(value){
 let url;
 try{url=new URL(String(value||'').trim());}
 catch{throw new Error('Вставь полную личную ссылку участника');}
 const match=url.pathname.match(/^\/p\/([A-Za-z0-9_-]{43})$/);
 if(url.origin!==location.origin||!match||url.search||url.hash)
  throw new Error('Нужна личная ссылка участника с этого сайта, а не общее приглашение');
 return match[1];
}
async function claimPersonalGame(token){
 const result=await api('/api/participant/'+encodeURIComponent(token)+'/claim',{method:'POST',body:{}});
 clearPendingGameClaim();
 nav('/santas',{force:true});
 notice('Игра привязана к аккаунту!');
 return result;
}
function connectGameModal(){
 modal({title:'Привязать игру',subtitle:'Если тебя добавили до регистрации, попроси организатора личную ссылку участника. Общая ссылка для приглашений не подойдёт',
  content:field('Личная ссылка','personal_link',getLink('/p/…'),'url','',true,'autocomplete="off" spellcheck="false"'),
  submitLabel:'Привязать',onSubmit:async form=>{
   const token=personalGameTokenFromLink(form.elements.personal_link.value);
   await claimPersonalGame(token);
  }});
}
async function reserveModal(id,key){await toggleGiftReservation(id,key);}
async function confirmAction(title,subtitle,handler,label='Удалить'){modal({title,subtitle,content:'<div class="alert alert-error">Это действие нельзя отменить</div>',submitLabel:label,onSubmit:handler});}
async function dispatch(action,el){const epoch=toastRouteEpoch;try{
 if(action==='retry-error'){location.reload();return;}
 if(action==='report-incident'){
  if(el.disabled)return;el.disabled=true;
  const result=el.closest('.error-page')?.querySelector('[data-incident-result]');
  try{await api('/api/incidents',{method:'POST',body:visibleIncident||{kind:'unknown',route:incidentRoute(),context:true}});el.textContent='Сообщение отправлено';if(result)result.textContent='Администрация получила сообщение';}
  catch(err){el.disabled=false;if(result)result.textContent='Не удалось отправить сообщение. Попробуй ещё раз';}
  return;
 }
 if(action==='accept-santa-invite'){
  if(!currentUser)return;
  await api('/api/invites/'+encodeURIComponent(el.dataset.key)+'/join',{method:'POST',body:{name:currentUser.name}});
  // Signed-in joins are already bound to the verified UID server-side.
  nav('/santas',{force:true});notice('Ты в игре!');return;
 }

 if(action==='delete-santa'){
  const game=loadedSanta?.event;if(!game)return;
  confirmAction('Удалить игру «'+game.title+'»?','Все участники, пожелания, чаты и фотографии будут удалены без возможности восстановления',async()=>{
   await api('/api/santas/'+game.id,{method:'DELETE'});loadedSanta=null;nav('/santas',{force:true});notice('Игра удалена');
  },'Удалить игру');return;
 }
 if(action==='finish-santa'){
  const event=loadedSanta?.event;
  if(!event||event.status==='finished')return;
  modal({title:'Завершить Тайного Санту?',subtitle:event.status==='open'?'Перенесём игру в завершённые без жеребьёвки и назначения получателей':'Сохраним жеребьёвку и историю, а игру перенесём в завершённые',
   content:'<div class="field"><label for="finish-santa-photo">Общее фото с участниками и подарками (необязательно)</label>'+
    '<div class="file-picker"><input id="finish-santa-photo" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif">'+
    '<p class="field-hint">Можно добавить сейчас или позже</p></div></div>',
   submitLabel:'Завершить игру',onSubmit:async form=>{
    const file=form.querySelector('#finish-santa-photo')?.files?.[0];
    const body=file?{image_data:await compressSantaMemory(file)}:{};
    await api('/api/santas/'+event.id+'/finish',{method:'POST',body});
    notice('Игра завершена');await render();
   }});
  return;
 }
 if(action==='edit-santa-preferences'){const f=document.getElementById('santa-preferences-form'),d=document.getElementById('santa-preferences-display');if(f&&d){f.hidden=false;d.hidden=true;f.querySelector(el.dataset.pref==='unwanted'?'[name="unwanted"]':'[name="wanted"]')?.focus();}return;}
 if(action==='cancel-santa-preferences'){const f=document.getElementById('santa-preferences-form'),d=document.getElementById('santa-preferences-display');if(f&&d){f.reset();f.hidden=true;d.hidden=false;}return;}
 if(action==='claim-game'){
  const token=el.dataset.token;
  if(!/^[A-Za-z0-9_-]{43}$/.test(token||''))return;
  if(!currentUser){savePendingGameClaim(token);loginModal('login');return;}
  await claimPersonalGame(token);
  return;
 }
 if(action==='connect-game'){connectGameModal();return;}
 if(action==='reset-preview'){window.SHURSH_PREVIEW_RESET?.();return;}
 if(action==='logout'){await api('/api/logout',{method:'POST',body:{}});clearPendingGameClaim();clearOwnerDataCache();currentUser=null;broadcastSessionChange();nav('/',{force:true});notice('Ты вышел из аккаунта');}
 if(action==='demo-login'){const r=await api('/api/demo-login',{method:'POST',body:{}});currentUser=r.user;closeModal();nav('/lists');notice('Демо-аккаунт открыт');}
 if(action==='sample-list'){if(!isDemo){listModal();return;}if(!currentUser){const r=await api('/api/demo-login',{method:'POST',body:{}});currentUser=r.user;}const {lists}=await api('/api/lists');if(lists.length)nav(`/w/${lists[lists.length-1].share_key}`);else nav('/lists');}
 if(action==='copy')await clipboard(el.dataset.url);
 if(action==='contact-developer')contactDeveloperModal();
  if(action==='admin-feedback-status'){
   await api('/api/admin/feedback/'+el.dataset.id,{method:'PATCH',body:{status:el.dataset.status}});
   await adminFeedbackPage();return;
  }
 if(action==='scroll-game-gifts'){const track=el.closest('.game-gifts-carousel')?.querySelector('.game-gifts-track');if(track){const dir=el.dataset.direction==='prev'?-1:1,first=track.firstElementChild,second=first?.nextElementSibling;const step=first&&second?second.offsetLeft-first.offsetLeft:first?.offsetWidth||track.clientWidth;track.scrollBy({left:dir*step,behavior:motionReduced()?'instant':'smooth'});}}
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
   const state=activeGameContext,base=state.base;
   await api(base+(base.startsWith('/api/santas/')?'/my-wishes':'/wishes')+'/'+gift.id,{method:'DELETE'});
   notice('Подарок удалён');await refreshGameOwnWishes(state);
  });
 }
 if(action==='show-wish')showWishDetails(el);
 if(action==='edit-santa')editSantaIdentity('exchange_date');
 if(action==='toggle-santa-rule-form'){const f=document.getElementById('rule-form');if(f){f.hidden=!f.hidden;document.querySelector('.santa-rule-toggle')?.toggleAttribute('hidden',!f.hidden);if(!f.hidden)f.querySelector('select')?.focus();}return;}
 if(action==='edit-santa-title'||action==='edit-santa-description'||action==='edit-santa-date'||action==='edit-santa-budget'){editSantaIdentity(({'edit-santa-title':'title','edit-santa-description':'description','edit-santa-date':'exchange_date','edit-santa-budget':'budget'})[action]);return;}
 if(action==='cookie-ack'){try{localStorage.setItem('shursh-cookie-notice-v1','yes')}catch{}document.querySelector('.cookie-notice')?.remove();return;}
 if(action==='add-player')addPlayerModal();
 if(action==='import-own-wishes')await importOwnWishesModal(el);
 if(action==='new-player-link')confirmAction('Выдать новую личную ссылку?','Старая ссылка перестанет работать. Участнику потребуется новая',async()=>{
   const player=loadedSanta.participants.find(p=>p.id===Number(el.dataset.id));
   const result=await api('/api/santas/'+loadedSanta.event.id+'/participants/'+el.dataset.id+'/new-link',{method:'POST',body:{}});
   showParticipantLink(result.participant_token,player?.name||'');
 },'Обновить ссылку');
 if(action==='edit-wish')wishModal(loadedList.wishes.find(w=>w.id===Number(el.dataset.id)));
 if(action==='delete-wish'){
  const listId=loadedList?.list.id,wishId=el.dataset.id;
  if(listId)confirmAction('Удалить это желание?','Подарок пропадёт из списка. Активная бронь тоже будет удалена',async()=>{await api(`/api/wishes/${wishId}`,{method:'DELETE'});notice('Желание удалено');await refreshOwnerWishes(listId);});
 }
 if(action==='delete-list')confirmAction('Удалить весь вишлист?','Все желания, ссылки и связанные брони будут удалены',async()=>{await api(`/api/lists/${loadedList.list.id}`,{method:'DELETE'});nav('/lists');notice('Список удалён');});
 if(action==='reserve'){await reserveModal(el.dataset.id,el.dataset.key);return;}
 if(action==='cancel-reservation')confirmAction('Отменить бронирование?','Подарок снова станет доступен другим дарителям',async()=>{await api(`/api/reservations/${el.dataset.token}`,{method:'DELETE'});notice('Бронь отменена');await render();},'Отменить бронь');
 if(action==='remove-player')confirmAction('Убрать участника?','Его приватная ссылка перестанет работать, и он не будет участвовать в жеребьёвке',async()=>{await api(`/api/santas/${loadedSanta.event.id}/participants/${el.dataset.id}`,{method:'DELETE'});notice('Участник удалён');await render();});
 if(action==='remove-rule'){await api(`/api/santas/${loadedSanta.event.id}/exclusions/${el.dataset.from}/${el.dataset.to}`,{method:'DELETE'});loadedSanta.exclusions=loadedSanta.exclusions.filter(r=>r.giver_id!==Number(el.dataset.from)||r.receiver_id!==Number(el.dataset.to));refreshSantaRules();notice('Ограничение снято');return;}
 if(action==='draw')modal({title:'Провести жеребьёвку?',subtitle:'После этого изменить участников и исключения уже нельзя. Имена распределятся случайно и останутся в секрете',content:`<div class="alert">Сейчас участвуют: ${loadedSanta.participants.map(p=>esc(p.name)).join(', ')}.</div>`,submitLabel:'Провести жеребьёвку',onSubmit:async()=>{await api(`/api/santas/${loadedSanta.event.id}/draw`,{method:'POST',body:{}});notice('Готово! Все подарки нашли своего дарителя');await render();}});
 if(action==='reveal'){
  const state=activeGameContext;
  if(!state?.base||el.disabled||!el.isConnected)return;
  el.disabled=true;
  try{
   const result=await api(state.base+'/reveal',{method:'POST',body:{}});
   if(activeGameContext!==state||!el.isConnected)return;
   const assignment=result.assignment;
   if(!assignment?.revealed)throw new Error('Не удалось раскрыть получателя. Попробуй ещё раз');
   const card=el.closest('.secret-card');
   if(!card)return;
   const template=document.createElement('template');
   template.innerHTML=secretCard(assignment);
   const revealed=template.content.firstElementChild;
   const scrollY=window.scrollY;
   state.recipient=assignment.wish_cards||[];
   if(!state.memberView&&loadedSanta?.event.id===state.event.id)loadedSanta.my_assignment=assignment;
   // Update only the secret card. Keep the game, chat, drafts and scroll intact.
   card.replaceWith(revealed);
   setupGameGiftOverflow(revealed);
   if(Math.abs(window.scrollY-scrollY)>1)window.scrollTo({top:scrollY,behavior:'instant'});
   notice('Секрет раскрыт!');
  }finally{if(el.isConnected)el.disabled=false;}
  return;
 }
 }catch(err){if(epoch===toastRouteEpoch)notice(err.message,true)}}
// Invalidate sensitive owner RAM cache across browser tabs after sign-in/out.
const sessionChannel=(!isPreview&&'BroadcastChannel' in window)?
 new BroadcastChannel('shursh-session-changed'):null;
function broadcastSessionChange(){sessionChannel?.postMessage('changed');}
sessionChannel?.addEventListener('message',event=>{
 if(event.data!=='changed')return;
 resetOwnerSession();
});
let renderStarted=false;
let pendingGameClaim=null;
const claimStorageKey='shursh-pending-game-claim';
const validPendingClaim=entry=>entry&&Number.isFinite(entry.created)
 &&Date.now()-entry.created>=0&&Date.now()-entry.created<86400000
 &&typeof entry.token==='string'&&/^[A-Za-z0-9_-]{43}$/.test(entry.token);
try{
 const session=JSON.parse(sessionStorage.getItem(claimStorageKey)||'null');
 const emailReturn=JSON.parse(localStorage.getItem(claimStorageKey)||'null');
 const entry=validPendingClaim(session)?session:validPendingClaim(emailReturn)?emailReturn:null;
 if(entry)pendingGameClaim=entry.token;
 else {sessionStorage.removeItem(claimStorageKey);localStorage.removeItem(claimStorageKey);}
}catch{}
function savePendingGameClaim(token){
 if(!/^[A-Za-z0-9_-]{43}$/.test(token))return;
 pendingGameClaim=token;
 try{sessionStorage.setItem(claimStorageKey,JSON.stringify({token,created:Date.now()}));}catch{}
}
function persistSignupClaim(){
 if(!pendingGameClaim)return;
 // Email confirmation often opens a NEW browser tab, without sessionStorage.
 // Keep the private claim for at most one day in this browser and clear on success.
 try{localStorage.setItem(claimStorageKey,JSON.stringify({token:pendingGameClaim,created:Date.now()}));}catch{}
}
function clearPendingGameClaim(){
 pendingGameClaim=null;
 try{sessionStorage.removeItem(claimStorageKey);localStorage.removeItem(claimStorageKey);}catch{}
}
let authReturnNotice = null;
let authReturnError = false;
let confirmationToken = null;
const authFragment=new URLSearchParams(location.hash.slice(1));
const nativeLoginQuery=new URLSearchParams(location.search);
const nativeLoginResult=!isPreview?nativeLoginQuery.get('shursh_login'):null;
if(nativeLoginResult){
 nativeLoginQuery.delete('shursh_login');
 history.replaceState(null,'',location.pathname+(nativeLoginQuery.size?'?'+nativeLoginQuery:'')+location.hash);
}
if(!isPreview && ['access_token','refresh_token','error','error_code','error_description']
    .some(key=>authFragment.has(key))){
 confirmationToken=authFragment.get('access_token');
 const callbackType=authFragment.get('type');
 authReturnError=authFragment.has('error')||authFragment.has('error_code')||authFragment.has('error_description')||!confirmationToken||
  (callbackType!==null&&callbackType!=='signup'&&callbackType!=='email'&&callbackType!=='email_change');
 if(authReturnError){
  confirmationToken=null;
  authReturnNotice='Ссылка подтверждения недействительна или истекла';
 }
 // Remove all provider credentials from URL before performing requests,
 // navigating or drawing any UI. Do not store tokens in localStorage.
 history.replaceState(null,'',location.pathname+location.search);
}
async function render(){beginToastRoute();closeCalendar();stopGameLifecycle();const marker=++lastRenderToken;try{
 const path=currentPath();
 syncNavigationSelection(path);
 if(!renderStarted&&path==='/'&&!isPreview){
  const data=await startupApi('/api/dashboard');
  if(marker!==lastRenderToken)return;
  currentUser=data.user;isDemo=data.demo;renderStarted=true;
  if(currentUser){seedOwnerCache('/api/dashboard',data);dashboardContent(data);}else home();
  return;
 }
 if(!renderStarted){
  const r=await startupApi('/api/me');
  if(marker!==lastRenderToken)return;
  currentUser=r.user;isDemo=r.demo;renderStarted=true;
 }
 if(path==='/'){
  if(currentUser){if(!cachedOwnerValue('/api/dashboard'))dashboardLoading();await dashboardPage(marker);}else home();
  return;
 }
 const routeApi=ownerApiForTab(path)||
  (/^\/santa\/\d+$/.test(path)?'/api/santas/'+path.split('/')[2]:
   /^\/list\/\d+$/.test(path)?'/api/lists/'+path.split('/')[2]:null);
 if(!routeApi||!cachedOwnerValue(routeApi))loading();
 if(/^\/i\/[A-Za-z0-9_-]{24}$/.test(path))await socialFriendInvitePage(path.split('/')[2],marker);else if(path==='/friends')await socialFriendsPage(marker);else if(path==='/profile')await socialOwnProfilePage(marker);else if(/^\/u\/[A-Za-z0-9_]{3,20}$/.test(path))await socialProfilePage(path.split('/')[2],marker,true);else if(/^\/users\/[0-9a-fA-F-]{36}$/.test(path))await socialProfilePage(path.split('/')[2],marker);else if(path==='/notifications')await socialNotificationsPage(marker);else if(path==='/admin')await socialAdminPage(marker);else if(path==='/admin/users')await socialAdminUsersPage(marker);else if(path==='/admin/audit')await socialAdminAuditPage(marker);else if(path==='/lists')await listsPage();else if(/^\/list\/\d+$/.test(path))await ownerListPage(path.split('/')[2]);else if(/^\/w\/[A-Za-z0-9_-]+$/.test(path))await publicListPage(path.split('/')[2]);else if(/^\/r\/[A-Za-z0-9_-]+$/.test(path))await reservationPage(path.split('/')[2]);else if(path==='/santas')await santasPage();else if(path==='/admin/feedback')await adminFeedbackPage();else if(/^\/santa\/\d+$/.test(path))await santaAdminPage(path.split('/')[2]);else if(/^\/join\/p\/[A-Za-z0-9_-]{43}$/.test(path))await invitePage(path.split('/')[3],marker,true);else if(/^\/join\/[A-Za-z0-9_-]+$/.test(path))await invitePage(path.split('/')[2]);else if(/^\/p\/[A-Za-z0-9_-]+$/.test(path))await participantPage(path.split('/')[2]);else errorView(new Error('Похоже, такой страницы ещё нет'),'Страница потерялась');
 }catch(err){if(marker===lastRenderToken){
  if(!renderStarted)errorView(err,'Не получилось загрузить Шурш');
  else errorView(err,err.status===404?'Страница не найдена':'Страница не загрузилась');
 }}}
document.addEventListener('click',async ev=>{
 const reveal=ev.target.closest('[data-password-visibility]');
 if(reveal){
  ev.preventDefault();
  const input=reveal.closest('.password-field')?.querySelector('.password-input-row input');
  if(!input)return;
  const visible=input.type==='password';input.type=visible?'text':'password';
  reveal.setAttribute('aria-pressed',String(visible));
  reveal.setAttribute('aria-label',(visible?'Скрыть':'Показать')+(input.name==='confirm_password'?' повтор пароля':' пароль'));
  reveal.innerHTML=ico(visible?'eye-off':'eye');
  authCharacterHighlights.get(input)?.();
  if(passwordSuggestions.has(input))renderPasswordSuggestions(input,true);
  input.focus({preventScroll:true});return;
 }
 const suggested=ev.target.closest('[data-password-suggestion]');
 const generator=ev.target.closest('[data-password-generate]')||suggested;
 if(generator){
  ev.preventDefault();
  try{
   const field=generator.closest('.password-field'),input=field?.querySelector('.password-input-row input');
   if(!input)return;
   const value=suggested?passwordSuggestions.get(input)?.[Number(suggested.dataset.passwordSuggestion)]:securePassword();
   if(!value)return;
   input.value=value;if(!suggested)input.type='text';
   const confirmation=field.closest('form')?.elements.namedItem('confirm_password');
   if(confirmation){confirmation.value=input.value;confirmation.type='password';
    const ct=confirmation.closest('.password-field')?.querySelector('[data-password-visibility]');
    if(ct){ct.setAttribute('aria-pressed','false');ct.setAttribute('aria-label','Показать повтор пароля');ct.innerHTML=ico('eye');}
   }
   input.dispatchEvent(new Event('input',{bubbles:true}));
   confirmation?.dispatchEvent(new Event('input',{bubbles:true}));
   const toggle=field.querySelector('[data-password-visibility]');
   const visible=input.type==='text';
   toggle.setAttribute('aria-pressed',String(visible));toggle.setAttribute('aria-label',visible?'Скрыть пароль':'Показать пароль');toggle.innerHTML=ico(visible?'eye-off':'eye');
   const hint=field.querySelector('#password-hint');
   if(hint){hint.dataset.generated='true';setPasswordHint(hint,'Пароль создан и повторён. Сохрани его в менеджере паролей');}
   input.focus({preventScroll:true});
  }catch(err){notice(err.message,true)}
  return;
 }
 const n=ev.target.closest('[data-nav]');if(n){if(n.tagName==='A'&&(ev.ctrlKey||ev.metaKey||ev.shiftKey||ev.altKey||ev.button!==0))return;ev.preventDefault();nav(n.dataset.nav);return;}const op=ev.target.closest('[data-open]');if(op){ev.preventDefault();const key=op.dataset.open;if(key==='login'||key==='register'||key==='resend'){const email=op.closest('.modal')?.querySelector('#fld-email')?.value||op.dataset.email||'';if(key==='resend')resendConfirmationModal(email);else loginModal(key,email);}if(key==='list')listModal();if(key==='wish')wishModal();if(key==='santa')santaModal();return;}const a=ev.target.closest('[data-action]');if(a){ev.preventDefault();await dispatch(a.dataset.action,a);}});
window.addEventListener('popstate',()=>{beginToastRoute();stopGameLifecycle();rememberOwnerTab();if(restoreOwnerTab(currentPath()))lastRenderToken++;else render();});window.addEventListener('hashchange',()=>{if(isPreview)render();});
async function startApplication(){
 if(confirmationToken&&!authReturnError){
  try{
   const token=confirmationToken;confirmationToken=null;
   const result=await api('/api/auth/complete',{method:'POST',body:{access_token:token}});
   clearOwnerDataCache();currentUser=result.user;broadcastSessionChange();
   authReturnNotice='Почта подтверждена! Ты вошёл в аккаунт';
   if(result.invite_path&&!pendingGameClaim)history.replaceState(null,'',result.invite_path);
   if(pendingGameClaim){
    const claim=pendingGameClaim;
    try{
     await api('/api/participant/'+encodeURIComponent(claim)+'/claim',{method:'POST',body:{}});
     clearPendingGameClaim();authReturnNotice='Почта подтверждена! Игра сохранена в аккаунте';
    }catch(_error){authReturnNotice='Почта подтверждена. Открой личную ссылку игры, чтобы сохранить её в аккаунте';}
   }
  }catch(_error){
   // Never include token, provider response or URL in UI or logs.
   authReturnError=true;
   authReturnNotice='Не получилось завершить вход после подтверждения';
  }finally{confirmationToken=null;}
 }
 await render();
 if(nativeLoginResult==='ok'&&currentUser){
  broadcastSessionChange();
  if(pendingGameClaim){
   const claim=pendingGameClaim;
   try{await claimPersonalGame(claim);}
   catch(err){nav('/p/'+claim,{force:true});notice('Ты вошёл, но игру пока не удалось привязать',true);}
   return;
  }
  notice('С возвращением!');
 }else if(['invalid','rate','unavailable'].includes(nativeLoginResult)){
  loginModal();
  const form=modalRoot.querySelector('#modal-form');
  const status=nativeLoginResult==='rate'?429:nativeLoginResult==='unavailable'?503:401;
  showAuthFormWarning({status,message:'Проверь почту, пароль и подтверждение адреса'},form);
 }
 if(authReturnError){
  modal({title:'Не получилось завершить подтверждение',
   subtitle:authReturnNotice||'Ссылка могла истечь или быть открыта повторно',
   content:'<p>Если почта уже подтверждена, попробуй войти с паролем. Если нет, запроси новое письмо</p>',
   footer:'<button type="button" data-open="login">Войти</button> · <button type="button" data-open="resend">Новое письмо</button>'});
 }else if(authReturnNotice)notice(authReturnNotice);
}
if(!isPreview){
 const boot=()=>void startApplication().catch(err=>errorView(err,'Не получилось загрузить Шурш'));
 // First route must wait for the deferred feature modules to execute.
 if(document.readyState==='complete')boot();else document.addEventListener('DOMContentLoaded',boot,{once:true});
}
