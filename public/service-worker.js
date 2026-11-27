'use strict';
// Network-only navigation; authenticated HTML, API data and mutations are never cached.
const OFFLINE_HTML='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#f9f7ef"><title>Шурш! — нет подключения</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:24px;background:#f9f7ef;color:#27272b;font:16px system-ui,sans-serif}main{max-width:360px;text-align:center}strong{font-size:36px}h1{font-size:23px;margin:22px 0 12px}p{line-height:1.55;color:#625b57}a{display:inline-flex;align-items:center;min-height:44px;margin-top:12px;padding:10px 20px;border-radius:14px;color:#27272b;background:#f9e7a3;text-decoration:none;font-weight:700}</style></head><body><main><strong>шурш<span style="color:#e58b67">!</span></strong><h1>Похоже, нет подключения</h1><p>Проверь интернет и попробуй снова. Чтобы открыть вишлисты и игры, нужно подключение</p><a href="">Повторить</a></main></body></html>';
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
 const request=event.request;
 if(request.method!=='GET'||request.mode!=='navigate')return;
 const url=new URL(request.url);
 if(url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname.startsWith('/uploads/'))return;
 event.respondWith(fetch(request).catch(()=>new Response(OFFLINE_HTML,{status:503,headers:{
  'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer',
  'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
 }})));
});
