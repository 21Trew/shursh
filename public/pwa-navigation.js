/* Mobile navigation: a device-local preference, not an account mutation. */
'use strict';
(()=>{
 const key='shursh-mobile-navigation-v1', html=document.documentElement;
 const defaults={mode:'panel',side:'right',ratio:.72};
 const modes=[['panel','Панель','Пять вкладок у нижнего края'],['island','Длинный островок','Плавающая капсула снизу'],['radial','Маленький островок','Вращающееся меню у стенки']];
 const routes=[['/','Главная','home'],['/lists','Вишлисты','gift'],['/santas','Санта','spark'],['/friends','Друзья','users'],['/profile','Профиль','person']];
 const mobile=matchMedia('(max-width:760px)'), reduced=matchMedia('(prefers-reduced-motion: reduce)');
 const clamp=(n,a,b)=>Math.max(a,Math.min(b,n)), mod=(n,m)=>((n%m)+m)%m;
 const symbol=n=>n==='person'?'<svg class="icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg>':ico(n,22);
 const label=r=>r[0]==='/santas'?'Тайный Санта':r[1];
 function read(){
  try{
   const p=JSON.parse(localStorage.getItem(key)||'null');
   if(p)return {mode:modes.some(m=>m[0]===p.mode)?p.mode:defaults.mode,side:p.side==='left'?'left':'right',ratio:typeof p.ratio==='number'&&Number.isFinite(p.ratio)?clamp(p.ratio,0,1):defaults.ratio};
  }catch{}
  return {...defaults};
 }
 let prefs=read(),open=false,offset=0,raf=0,animation=0,wheelTimer=0,drag=null,suppress=false,lastPath='',renderedMode='',observedCookie=null;
 function save(){try{localStorage.setItem(key,JSON.stringify(prefs));return true;}catch{return false;}}
 const root=document.createElement('div');root.id='mobile-nav';root.className='mobile-nav';root.hidden=true;document.body.append(root);
 const enabled=()=>!!currentUser&&!isPreview&&mobile.matches;
 const blocked=()=>!!modalRoot.firstElementChild||!!document.querySelector('#page-view :is(input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=file]):not([type=button]):not([type=submit]),textarea,[contenteditable="true"]):focus')||
  (window.visualViewport&&window.visualViewport.scale<1.05&&innerHeight-window.visualViewport.height-window.visualViewport.offsetTop>120);
 const link=r=>'<a href="'+r[0]+'" data-nav="'+r[0]+'" aria-label="'+label(r)+'">'+symbol(r[2])+'<span>'+r[1]+'</span></a>';
 function settingsMarkup(){
  return '<section class="panel mobile-navigation-settings"><h2>Навигация</h2><p class="note">Выбери удобный способ перемещения на этом устройстве</p><div class="mobile-nav-choices" role="group" aria-label="Модель навигации">'+
    modes.map(([id,name,desc])=>'<button type="button" class="mobile-nav-choice" data-nav-mode="'+id+'" aria-pressed="'+(prefs.mode===id)+'"><span class="mobile-nav-mini '+id+'" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span><span><strong>'+name+'</strong><small>'+desc+'</small></span><span class="mobile-nav-check" aria-hidden="true">'+ico('check',18)+'</span></button>').join('')+
    '</div><div class="mobile-nav-position" '+(prefs.mode==='radial'?'':'hidden')+'><p class="note">Перетащи закрытый островок вверх, вниз или к другой границе</p><div class="btn-row" role="group" aria-label="Расположение островка"><button type="button" class="btn btn-soft btn-small" data-nav-side="left" aria-pressed="'+(prefs.side==='left')+'">Слева</button><button type="button" class="btn btn-soft btn-small" data-nav-side="right" aria-pressed="'+(prefs.side==='right')+'">Справа</button><button type="button" class="btn btn-soft btn-small" data-nav-reset>Сброс места</button></div></div>'+
    (currentUser?.is_admin?'<a class="btn btn-soft btn-small mobile-nav-admin" href="/admin" data-nav="/admin">Админка</a>':'')+'<p class="note mobile-nav-storage" role="status"></p></section>';
 }
 function syncSettings(){
  const s=document.querySelector('.mobile-navigation-settings');if(!s)return;
  s.querySelectorAll('[data-nav-mode]').forEach(n=>setAttrIfChanged(n,'aria-pressed',String(n.dataset.navMode===prefs.mode)));
  s.querySelectorAll('[data-nav-side]').forEach(n=>setAttrIfChanged(n,'aria-pressed',String(n.dataset.navSide===prefs.side)));
  const p=s.querySelector('.mobile-nav-position');if(p&&p.hidden!==(prefs.mode!=='radial'))p.hidden=prefs.mode!=='radial';
 }
 function build(){
  renderedMode=prefs.mode;root.dataset.mode=prefs.mode;root.dataset.side=prefs.side;
  if(prefs.mode!=='radial')root.innerHTML='<nav class="mobile-nav-bar" aria-label="Мобильная навигация">'+routes.map(link).join('')+'</nav>';
  else root.innerHTML='<div id="mobile-nav-radial-menu" class="mobile-nav-radial" hidden><div class="mobile-nav-shade" data-mobile-dismiss></div><div class="mobile-nav-arc" role="group" aria-label="Вращающееся меню">'+routes.map(link).join('')+'</div><div class="mobile-nav-spin"><button type="button" data-mobile-spin="-1" aria-label="Предыдущий раздел">↑</button><span aria-live="polite"></span><button type="button" data-mobile-spin="1" aria-label="Следующий раздел">↓</button></div></div><button type="button" class="mobile-nav-handle" aria-label="Открыть навигацию" aria-expanded="false" aria-controls="mobile-nav-radial-menu"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h14"/></svg></button>';
 }
 function selected(){
  const section=navigationSection(currentPath());
  root.querySelectorAll('[data-nav]').forEach(a=>{
   const active=a.dataset.nav===section;
   a.classList.toggle('active',active);
   if(active)setAttrIfChanged(a,'aria-current',a.dataset.nav===currentPath()?'page':'location');
   else if(a.hasAttribute('aria-current'))a.removeAttribute('aria-current');
  });
 }
 function cancelMotion(){cancelAnimationFrame(animation);animation=0;clearTimeout(wheelTimer);wheelTimer=0;}
 function close(focus=false){
  if(!open)return;open=false;cancelMotion();drag=null;
  html.classList.remove('mobile-nav-open');root.classList.remove('is-open');
  const layer=root.querySelector('.mobile-nav-radial'),handle=root.querySelector('.mobile-nav-handle');
  if(layer)layer.hidden=true;
  if(handle){handle.setAttribute('aria-expanded','false');handle.setAttribute('aria-label','Открыть навигацию');if(focus&&!root.hidden)handle.focus({preventScroll:true});}
  schedule();
 }
 function bounds(){
  const viewport=window.visualViewport;const H=viewport?Math.min(innerHeight,viewport.height+viewport.offsetTop):innerHeight;
  const header=document.querySelector('.site-header')?.getBoundingClientRect();
  const top=Math.max(36,(header?.bottom||62)+31);
  const safeBottom=parseFloat(getComputedStyle(root).paddingBottom)||0;
  let bottom=H-35-safeBottom;
  for(const n of [document.querySelector('.cookie-notice'),document.querySelector('#toast-root:not(:empty)'),document.querySelector('.scroll-to-top.is-visible')]){
   if(n&&n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden')bottom=Math.min(bottom,n.getBoundingClientRect().top-32);
  }
  return {top:Math.min(top,H-35),bottom:Math.max(Math.min(top,H-35),bottom),H};
 }
 function edgeY(){const b=bounds();return b.top+prefs.ratio*(b.bottom-b.top);}
 function geom(){
  const b=bounds(),style=getComputedStyle(root),safeTop=parseFloat(style.paddingTop)||0,safeBottom=parseFloat(style.paddingBottom)||0;
  let lower=b.H-safeBottom-8;
  const toast=document.querySelector('#toast-root:not(:empty)');
  if(toast?.getClientRects().length)lower=Math.min(lower,toast.getBoundingClientRect().top-6);
  const short=lower-safeTop<435,span=short?1.5:2.5;
  const step=short?53:35,radius=short?88:Math.min(126,innerWidth*.39);
  const margin=short?94:radius+26;
  const low=safeTop+margin,high=Math.max(low,lower-margin);
  const y=clamp(edgeY(),low,high);
  return {y,step,radius,span,lower,safeTop};
 }
 function layout(){
  if(!enabled()||root.hidden||prefs.mode!=='radial')return;
  const handle=root.querySelector('.mobile-nav-handle');if(!handle)return;
  const g=open?geom():null;
  handle.style.top=(g?.y??edgeY())+'px';root.dataset.side=prefs.side;
  if(!open)return;
  const side=prefs.side==='left'?1:-1;
  for(const [i,a] of [...root.querySelectorAll('.mobile-nav-arc a')].entries()){
   const slot=mod(i-offset+routes.length/2,routes.length)-routes.length/2;
   const angle=slot*g.step*Math.PI/180;
   const opacity=clamp((g.span-Math.abs(slot))/.5,0,1);
   const x=side*g.radius*Math.cos(angle),y=g.y+g.radius*Math.sin(angle);
   a.style.top=y+'px';a.style.transform='translate('+x+'px,-50%)';a.style.opacity=String(opacity);a.style.visibility=opacity>.08?'visible':'hidden';
   a.style.pointerEvents=opacity>.7?'auto':'none';a.tabIndex=opacity>.7?0:-1;
  }
  const spin=root.querySelector('.mobile-nav-spin');
  spin.style.top=clamp(g.y<g.lower/2?g.lower-55:g.safeTop+8,g.safeTop+4,Math.max(g.safeTop+4,g.lower-52))+'px';
  const text=spin.querySelector('span'),name=label(routes[mod(Math.round(offset),routes.length)]);
  if(text.textContent!==name)text.textContent=name;
 }
 function schedule(){if(!raf)raf=requestAnimationFrame(()=>{raf=0;layout();});}
 function sync(){
  const active=enabled(),hidden=!active||blocked(),path=currentPath();
  if(lastPath!==path){close();lastPath=path;}
  if(hidden)close();
  html.classList.toggle('mobile-nav-active',active);
  html.classList.toggle('mobile-nav-blocked',active&&hidden);
  if(html.dataset.mobileNavMode!==(active?prefs.mode:''))html.dataset.mobileNavMode=active?prefs.mode:'';
  if(renderedMode!==prefs.mode){close();build();}
  if(root.hidden!==hidden)root.hidden=hidden;
  if(root.inert!==hidden)root.inert=hidden;
  selected();syncSettings();
  const cookie=document.querySelector('.cookie-notice');
  if(cookie!==observedCookie){if(observedCookie)resize?.unobserve(observedCookie);observedCookie=cookie;if(cookie)resize?.observe(cookie);}
  schedule();
 }
 function focusCenter(){root.querySelectorAll('.mobile-nav-arc a')[mod(Math.round(offset),routes.length)]?.focus({preventScroll:true});}
 function toggle(){
  if(root.hidden||prefs.mode!=='radial')return;
  if(open){close(true);return;}
  open=true;offset=Math.max(0,routes.findIndex(r=>r[0]===navigationSection(currentPath())));
  html.classList.add('mobile-nav-open');root.classList.add('is-open');
  root.querySelector('.mobile-nav-radial').hidden=false;
  const h=root.querySelector('.mobile-nav-handle');h.setAttribute('aria-expanded','true');h.setAttribute('aria-label','Закрыть навигацию');
  layout();focusCenter();
 }
 function snap(to=Math.round(offset),focus=false){
  cancelMotion();const start=offset;
  if(reduced.matches||Math.abs(start-to)<.01){offset=mod(to,routes.length);layout();if(focus)focusCenter();return;}
  const t0=performance.now();
  function frame(t){if(!open)return;const u=clamp((t-t0)/170,0,1);offset=start+(to-start)*(1-Math.pow(1-u,3));layout();if(u<1)animation=requestAnimationFrame(frame);else{animation=0;offset=mod(to,routes.length);layout();if(focus)focusCenter();}}
  animation=requestAnimationFrame(frame);
 }
 const angle=e=>{const g=geom(),style=getComputedStyle(root),inset=parseFloat(prefs.side==='left'?style.paddingLeft:style.paddingRight)||0,x=prefs.side==='left'?e.clientX:innerWidth-e.clientX;return Math.atan2(e.clientY-g.y,x-24-inset)*180/Math.PI;};
 root.addEventListener('pointerdown',e=>{
  if(!e.isPrimary||e.button!==0||root.hidden)return;
  suppress=false;const h=e.target.closest('.mobile-nav-handle');
  if(h){drag={kind:'edge',id:e.pointerId,x:e.clientX,y:e.clientY,side:prefs.side,ratio:prefs.ratio,moved:false,wasOpen:open,target:h};}
  else if(open&&e.target.closest('.mobile-nav-arc')){cancelMotion();drag={kind:'arc',id:e.pointerId,x:e.clientX,y:e.clientY,last:angle(e),moved:false,target:e.target.closest('a')||root.querySelector('.mobile-nav-arc')};}
  if(drag){try{drag.target.setPointerCapture(e.pointerId);}catch{}}
 });
 root.addEventListener('pointermove',e=>{
  const d=drag;if(!d||d.id!==e.pointerId)return;
  if(!d.moved&&Math.hypot(e.clientX-d.x,e.clientY-d.y)<8)return;
  if(!d.moved)d.moved=true;
  e.preventDefault();
  if(d.kind==='edge'){
   if(d.wasOpen)return;
   const b=bounds();prefs.side=e.clientX<innerWidth/2?'left':'right';prefs.ratio=clamp((e.clientY-b.top)/Math.max(1,b.bottom-b.top),0,1);
   root.classList.add('is-dragging');layout();
  }else if(open){
   const a=angle(e);let delta=a-d.last;if(delta>180)delta-=360;if(delta<-180)delta+=360;d.last=a;
   offset-=delta/geom().step;layout();
  }
 });
 function finish(e){
  const d=drag;if(!d||d.id!==e.pointerId)return;drag=null;
  if(d.target.hasPointerCapture?.(e.pointerId))d.target.releasePointerCapture(e.pointerId);
  root.classList.remove('is-dragging');
  if(d.moved){
   suppress=true;
   if(d.kind==='edge'&&!d.wasOpen){if(e.type!=='pointerup'){prefs.side=d.side;prefs.ratio=d.ratio;}else save();syncSettings();layout();}
   else if(d.kind==='arc'&&open)snap();
  }else if(d.kind==='edge'&&e.type==='pointerup'){
   suppress=true;toggle();
  }
 }
 root.addEventListener('pointerup',finish);root.addEventListener('pointercancel',finish);
 root.addEventListener('lostpointercapture',e=>{if(drag?.id===e.pointerId)finish(e);});
 root.addEventListener('click',e=>{
  if(suppress&&e.detail>0){suppress=false;e.preventDefault();e.stopImmediatePropagation();return;}
  if(e.target.closest('.mobile-nav-handle')){e.preventDefault();toggle();return;}
  if(e.target.closest('[data-mobile-dismiss]')){close(true);return;}
  const spin=e.target.closest('[data-mobile-spin]');
  if(spin&&open){snap(Math.round(offset)+Number(spin.dataset.mobileSpin),true);return;}
  if(e.target.closest('[data-nav]')&&open)close(true);
 },true);
 root.addEventListener('wheel',e=>{if(!open)return;e.preventDefault();cancelMotion();offset+=clamp((e.deltaY||e.deltaX)*(e.deltaMode===1?16:e.deltaMode===2?120:1)/85,-1.3,1.3);layout();wheelTimer=setTimeout(()=>snap(),110);},{passive:false});
 document.addEventListener('keydown',e=>{
  if(!open)return;
  if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close(true);return;}
  if(!root.contains(document.activeElement))return;
  if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();snap(Math.round(offset)+(['ArrowUp','ArrowLeft'].includes(e.key)?-1:1),true);}
  else if(e.key==='Tab'){
   const targets=[...root.querySelectorAll('button,a')].filter(n=>n.tabIndex>=0&&n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden');
   if(targets.length&&((e.shiftKey&&document.activeElement===targets[0])||(!e.shiftKey&&document.activeElement===targets.at(-1)))){e.preventDefault();(e.shiftKey?targets.at(-1):targets[0]).focus();}
  }
 },true);
 document.addEventListener('click',e=>{
  const b=e.target.closest('[data-nav-mode],[data-nav-side],[data-nav-reset]');if(!b||!b.closest('.mobile-navigation-settings'))return;
  if(b.hasAttribute('data-nav-mode')&&modes.some(m=>m[0]===b.dataset.navMode)){close();prefs.mode=b.dataset.navMode;}
  else if(b.hasAttribute('data-nav-side'))prefs.side=b.dataset.navSide==='left'?'left':'right';
  else if(b.hasAttribute('data-nav-reset')){prefs.side=defaults.side;prefs.ratio=defaults.ratio;}
  const ok=save();sync();const status=b.closest('section').querySelector('.mobile-nav-storage');if(status)status.textContent=ok?'Сохранено на этом устройстве':'Настройка действует до перезагрузки';
 });
 const resize=typeof ResizeObserver==='function'?new ResizeObserver(schedule):null;
 if(resize){resize.observe(document.getElementById('toast-root'));}
 new MutationObserver(sync).observe(modalRoot,{childList:true});
 document.addEventListener('focusin',sync);document.addEventListener('focusout',()=>requestAnimationFrame(sync));
 mobile.addEventListener?.('change',sync);window.addEventListener('resize',()=>{close();sync();},{passive:true});
 window.visualViewport?.addEventListener('resize',sync,{passive:true});window.visualViewport?.addEventListener('scroll',sync,{passive:true});
 window.addEventListener('scroll',schedule,{passive:true});
 window.addEventListener('storage',e=>{if(e.key===key||e.key===null){close();prefs=read();sync();}});
 window.shurshNavigation={sync,settingsMarkup};
 sync();
})();
