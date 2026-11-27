'use strict';
(()=>{
 if(!window.isSecureContext||location.pathname.endsWith('/shursh-preview.html'))return;
 const standalone=()=>matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
 let pending=null;
 const sync=()=>document.documentElement.classList.toggle('pwa-install-available',!standalone());
 sync();
 window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();pending=event;sync();});
 window.addEventListener('appinstalled',()=>{pending=null;document.documentElement.classList.remove('pwa-install-available');});
 const mode=matchMedia('(display-mode: standalone)');
 mode.addEventListener?.('change',sync);
 if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js',{scope:'/',updateViaCache:'none'}).catch(()=>{});
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-pwa-install]');
  if(!button||standalone())return;
  if(pending){
   const prompt=pending;pending=null;
   try{await prompt.prompt();await prompt.userChoice;return;}catch{}
  }
  modal({title:'Установить Шурш!',content:'<div class="pwa-help"><p><strong>iPhone и iPad</strong><br>В Safari открой «Поделиться», затем «На экран Домой» и подтверди добавление</p><p><strong>Android</strong><br>В меню браузера выбери «Установить приложение» или «Добавить на главный экран»</p><p><strong>Компьютер</strong><br>Используй кнопку установки в адресной строке или меню браузера, если она доступна</p></div>'});
 });
})();
