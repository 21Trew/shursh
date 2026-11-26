// No SPA or session bootstrap needed to render a 404.
(() => {
 const main=document.querySelector('[data-incident-route]');
 const button=main?.querySelector('[data-report-404]');
 const status=main?.querySelector('[data-report-status]');
 if(!button||!status)return;
 button.classList.remove('hide');
 button.addEventListener('click',async()=>{
  if(button.disabled)return;
  button.disabled=true;
  try{
   const response=await fetch('/api/incidents',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'not_found',route:main.dataset.incidentRoute,context:true,status:404,ui_version:main.dataset.uiVersion})});
   if(!response.ok)throw new Error('report failed');
   button.textContent='Сообщение отправлено';
   status.textContent='Администрация получила сообщение';
  }catch{
   status.textContent='Не удалось отправить сообщение. Попробуй ещё раз';
   button.disabled=false;
  }
 });
})();
