/* OFFLINE INTERACTIVE PREVIEW ONLY. LocalStorage is NOT secure or shared with other devices.
 * Open the Python server for server-validated permissions and atomic writes. */
(function(){
'use strict';
const KEY='shursh-preview-v3';
const fresh=()=>({seq:50,user:1,users:[{id:1,name:'Саша',email:'demo@shursh.local',password:'demo12345'}],
 lists:[{id:1,owner_id:1,title:'День рождения, ура!',description:'Собрала здесь то, чему буду очень рада. Но сюрпризы тоже люблю ♡',occasion:'День рождения',theme:'peach',visibility:'link',share_key:'preview-birthday'},
 {id:2,owner_id:1,title:'Маленькие радости',description:'На случай, если захочется сделать мой день чуть теплее.',occasion:'Просто так',theme:'lilac',visibility:'link',share_key:'preview-joy'}],
 wishes:[{id:1,list_id:1,title:'Плёночный фотоаппарат',description:'Хочется снимать неловкие, живые моменты.',price_cents:890000,currency:'RUB',priority:'love',kind:'item'},
 {id:2,list_id:1,title:'Керамическая чашка ручной работы',description:'Большая, с характером. Можно необычной формы.',price_cents:250000,currency:'RUB',priority:'nice',kind:'item'},
 {id:3,list_id:1,title:'Билеты на спектакль',description:'Буду рада любому необычному театру.',price_cents:500000,currency:'RUB',priority:'love',kind:'experience'},
 {id:4,list_id:1,title:'Красивое издание любимой книги',description:'С иллюстрациями и плотной бумагой.',price_cents:180000,currency:'RUB',priority:'nice',kind:'item'},
 {id:5,list_id:2,title:'Вечер настолок',description:'С печеньем и классной компанией.',price_cents:null,currency:'RUB',priority:'nice',kind:'experience'},
 {id:6,list_id:2,title:'Набор цветных карандашей',description:'Для спонтанных зарисовок.',price_cents:190000,currency:'RUB',priority:'nice',kind:'item'}],
 reservations:[],
 events:[{id:1,owner_id:1,title:'Санта на нашей кухне',description:'Чай, печенье и маленькие сюрпризы',exchange_date:'2026-12-25',budget_cents:250000,currency:'RUB',rules:'Главное — внимание, а не цена. Упаковываем подарки красиво!',invite_key:'preview-santa',status:'open'}],
 participants:[{id:1,event_id:1,user_id:1,name:'Саша',access_token:null},{id:2,event_id:1,user_id:null,name:'Маша',access_token:'sample-masha'},
 {id:3,event_id:1,user_id:null,name:'Дима',access_token:'sample-dima'},{id:4,event_id:1,user_id:null,name:'Настя',access_token:'sample-nastya'}],
 p_wishes:[{id:1,participant_id:1,title:'Виниловая пластинка'},{id:2,participant_id:2,title:'Кофе в зёрнах'},{id:3,participant_id:2,title:'Пазл на 500 деталей'},{id:4,participant_id:3,title:'Настольная игра'},{id:5,participant_id:4,title:'Набор для рисования'}],
 exclusions:[],assignments:[]});
let db;
try{db=JSON.parse(localStorage.getItem(KEY))||fresh()}catch{db=fresh()}
let storageWarningShown=false;
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(db))}catch(err){if(!storageWarningShown){storageWarningShown=true;setTimeout(()=>notice('Хранилище браузера недоступно. Изменения сохраняются только до закрытия страницы.',true),300)}}};
const fail=(msg)=>{throw new Error(msg)};
const ident=()=>++db.seq;
const newToken=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
const user=()=>db.users.find(u=>u.id===db.user)||null;
const needUser=()=>user()||fail('Сначала войди в аккаунт');
const list=id=>db.lists.find(x=>x.id===Number(id)&&x.owner_id===needUser().id)||fail('Вишлист не найден');
const event=id=>db.events.find(x=>x.id===Number(id)&&x.owner_id===needUser().id)||fail('Игра не найдена');
const part=token=>db.participants.find(x=>x.access_token===token)||fail('Личная ссылка недействительна');
const getBody=opt=>opt?.body||{};
const price=d=>(d===undefined||d===null||d==='')?null:Math.round(Number(d)*100);
const ownWish=(id)=>{const w=db.wishes.find(x=>x.id===Number(id));if(!w)fail('Желание не найдено');list(w.list_id);return w;};
const assignmentView=(e,pid)=>{const a=db.assignments.find(a=>a.event_id===e&&a.giver_id===pid);if(!a||!a.revealed)return{revealed:false};return{revealed:true,receiver_name:db.participants.find(p=>p.id===a.receiver_id).name,wishes:db.p_wishes.filter(w=>w.participant_id===a.receiver_id).map(w=>w.title)}};
const choosePairs=(ids,excluded)=>{
 const n=ids.length;if(n<3)fail('Для жеребьёвки нужно минимум 3 участника');if(n>12)fail('В MVP максимум 12 участников');
 const banned=new Set(excluded.map(x=>x.giver_id+'-'+x.receiver_id));const dp=new Map();
 const count=(mask)=>{if(mask===(1<<n)-1)return 1;if(dp.has(mask))return dp.get(mask);const i=mask.toString(2).replaceAll('0','').length;let total=0;for(let j=0;j<n;j++)if(!(mask&(1<<j))&&i!==j&&!banned.has(ids[i]+'-'+ids[j]))total+=count(mask|(1<<j));dp.set(mask,total);return total;};
 if(count(0)===0)fail('С такими исключениями жеребьёвка невозможна. Убери часть ограничений.');
 let mask=0;const out=[];for(let i=0;i<n;i++){const choices=[];let total=0;for(let j=0;j<n;j++)if(!(mask&(1<<j))&&i!==j&&!banned.has(ids[i]+'-'+ids[j])){let weight=count(mask|(1<<j));if(weight){total+=weight;choices.push({j,weight})}}const buf=new Uint32Array(1);crypto.getRandomValues(buf);let random=buf[0]/4294967296*total;for(const {j,weight} of choices){if(random<weight){out.push({giver_id:ids[i],receiver_id:ids[j]});mask|=1<<j;break}random-=weight;}}
 return out;
};
window.previewApi=async function(path,opt={}){
 const method=opt.method||'GET',data=getBody(opt);
 await new Promise(r=>setTimeout(r,30));
 if(path==='/api/me')return {user:user()&&{id:user().id,name:user().name,email:user().email},demo:true};
 if(path==='/api/demo-login'&&method==='POST'){db.user=1;save();return{user:{id:1,name:'Саша',email:'demo@shursh.local'}}}
 if(path==='/api/logout'&&method==='POST'){db.user=null;save();return{ok:true}}
 if((path==='/api/login'||path==='/api/register')&&method==='POST'){
 let u=db.users.find(u=>u.email===data.email);if(path.endsWith('register')){if(u)fail('Аккаунт уже есть');if(String(data.password||'').length<8)fail('Пароль слишком короткий');u={id:ident(),name:data.name,email:data.email,password:data.password};db.users.push(u)}else if(!u||u.password!==data.password)fail('Неверная почта или пароль');db.user=u.id;save();return{user:{id:u.id,name:u.name,email:u.email}};
 }
 if(path==='/api/lists'&&method==='GET'){const u=needUser();return {lists:db.lists.filter(l=>l.owner_id===u.id).map(l=>({...l,wish_count:db.wishes.filter(w=>w.list_id===l.id).length})).reverse()}}
 if(path==='/api/lists'&&method==='POST'){const u=needUser();const id=ident();db.lists.push({id,owner_id:u.id,share_key:newToken(),...data});save();return{id}}
 let m=path.match(/^\/api\/lists\/(\d+)$/);if(m){const l=list(m[1]);if(method==='GET')return{list:{...l},wishes:db.wishes.filter(w=>w.list_id===l.id).reverse().map(w=>({...w}))};if(method==='PATCH'){Object.assign(l,data);save();return{ok:true}}if(method==='DELETE'){db.lists=db.lists.filter(x=>x.id!==l.id);const ids=db.wishes.filter(w=>w.list_id===l.id).map(w=>w.id);db.wishes=db.wishes.filter(w=>w.list_id!==l.id);db.reservations=db.reservations.filter(r=>!ids.includes(r.wish_id));save();return{ok:true}}}
 m=path.match(/^\/api\/lists\/(\d+)\/wishes$/);if(m&&method==='POST'){const l=list(m[1]);const id=ident();db.wishes.push({id,list_id:l.id,title:data.title,description:data.description||'',price_cents:price(data.price),currency:data.currency||'RUB',kind:data.kind||'item',priority:data.priority||'nice',shop_url:data.shop_url||null,image_path:data.image_data||null});save();return{id}}
 m=path.match(/^\/api\/wishes\/(\d+)$/);if(m){const w=ownWish(m[1]);if(method==='DELETE'){db.wishes=db.wishes.filter(x=>x.id!==w.id);db.reservations=db.reservations.filter(r=>r.wish_id!==w.id);save();return{ok:true}}if(method==='PATCH'){Object.assign(w,data);if('price'in data)w.price_cents=price(data.price);if(data.image_data)w.image_path=data.image_data;save();return{ok:true}}}
 m=path.match(/^\/api\/public\/([^/]+)$/);if(m&&method==='GET'){const l=db.lists.find(x=>x.share_key===m[1]&&x.visibility==='link');if(!l)fail('Список по этой ссылке недоступен');const owner_view=user()?.id===l.owner_id;return{list:{...l,owner_name:db.users.find(u=>u.id===l.owner_id)?.name},owner_view,wishes:db.wishes.filter(w=>w.list_id===l.id).reverse().map(w=>({...w,...(owner_view?{}:{reserved:db.reservations.some(r=>r.wish_id===w.id&&!r.cancelled_at)})}))}}
 m=path.match(/^\/api\/public\/([^/]+)\/reserve\/(\d+)$/);if(m&&method==='POST'){const l=db.lists.find(x=>x.share_key===m[1]&&x.visibility==='link');const w=db.wishes.find(w=>w.id===Number(m[2])&&w.list_id===l?.id);if(!w)fail('Подарок не найден');if(l.owner_id===user()?.id)fail('Нельзя бронировать свои подарки');if(db.reservations.some(r=>r.wish_id===w.id&&!r.cancelled_at))fail('Подарок уже забронирован');const manage_token=newToken();db.reservations.push({id:ident(),wish_id:w.id,guest_name:data.guest_name,manage_token,cancelled_at:null});save();return{manage_token}}
 m=path.match(/^\/api\/reservations\/([^/]+)$/);if(m){const r=db.reservations.find(x=>x.manage_token===m[1]);if(!r)fail('Бронь не найдена');if(method==='DELETE'){if(r.cancelled_at)fail('Бронь уже отменена');r.cancelled_at=new Date().toISOString();save();return{ok:true}}const w=db.wishes.find(w=>w.id===r.wish_id),l=db.lists.find(l=>l.id===w.list_id);return{reservation:{...r,wish_title:w.title,list_title:l.title}}}
 if(path==='/api/santa/library'&&method==='GET'){const owner=needUser();return {lists:db.lists.filter(l=>l.owner_id===owner.id).slice().reverse().map(l=>({id:l.id,title:l.title,wishes:db.wishes.filter(w=>w.list_id===l.id).slice().reverse().map(w=>({id:w.id,title:w.title}))}))}}
 let roster=path.match(/^\/api\/santas\/(\d+)\/roster$/);if(roster&&method==='GET'){const e=event(roster[1]);return {status:e.status,participants:db.participants.filter(p=>p.event_id===e.id).map(p=>({id:p.id,name:p.name,wish_count:db.p_wishes.filter(w=>w.participant_id===p.id).length,is_organizer:p.user_id===e.owner_id?1:0}))}}
 roster=path.match(/^\/api\/participant\/([^/]+)\/roster$/);if(roster&&method==='GET'){const p=part(roster[1]),e=db.events.find(e=>e.id===p.event_id);return {status:e.status,participants:db.participants.filter(x=>x.event_id===e.id).map(x=>({id:x.id,name:x.name,wish_count:db.p_wishes.filter(w=>w.participant_id===x.id).length,is_organizer:x.user_id===e.owner_id?1:0}))}}
 if(path==='/api/santas'&&method==='GET'){const u=needUser();return{events:db.events.filter(e=>e.owner_id===u.id).map(e=>({...e,participant_count:db.participants.filter(p=>p.event_id===e.id).length})).reverse()}}
 if(path==='/api/santas'&&method==='POST'){const u=needUser();const id=ident();db.events.push({id,owner_id:u.id,title:data.title,description:data.description||'',exchange_date:data.exchange_date||'',budget_cents:price(data.budget),currency:data.currency||'RUB',rules:data.rules||'',invite_key:newToken(),status:'open'});db.participants.push({id:ident(),event_id:id,user_id:u.id,name:u.name,access_token:null});save();return{id}}
 m=path.match(/^\/api\/santas\/(\d+)$/);if(m&&method==='GET'){const e=event(m[1]),ps=db.participants.filter(p=>p.event_id===e.id);const me=ps.find(p=>p.user_id===user().id);return{event:{...e},participants:ps.map(p=>({id:p.id,name:p.name,user_id:p.user_id,wish_count:db.p_wishes.filter(w=>w.participant_id===p.id).length})),exclusions:db.exclusions.filter(x=>x.event_id===e.id),my_assignment:e.status==='drawn'?assignmentView(e.id,me.id):null}}
 m=path.match(/^\/api\/santas\/(\d+)\/my-wishes$/);if(m){const e=event(m[1]),p=db.participants.find(p=>p.event_id===e.id&&p.user_id===user().id);if(!p)fail('Не найден участник');if(method==='GET')return{wishes:db.p_wishes.filter(w=>w.participant_id===p.id)};if(method==='POST'){db.p_wishes.push({id:ident(),participant_id:p.id,title:data.title});save();return{ok:true}}}
 m=path.match(/^\/api\/santas\/(\d+)\/participants\/(\d+)$/);if(m&&method==='DELETE'){const e=event(m[1]);if(e.status!=='open')fail('Состав заморожен');const p=db.participants.find(x=>x.id===Number(m[2])&&x.event_id===e.id);if(!p||p.user_id===user().id)fail('Нельзя удалить участника');db.participants=db.participants.filter(x=>x.id!==p.id);db.exclusions=db.exclusions.filter(x=>x.giver_id!==p.id&&x.receiver_id!==p.id);db.p_wishes=db.p_wishes.filter(x=>x.participant_id!==p.id);save();return{ok:true}}
 m=path.match(/^\/api\/santas\/(\d+)\/exclusions$/);if(m&&method==='POST'){const e=event(m[1]);if(e.status!=='open')fail('Правила заморожены');const giver_id=Number(data.giver_id),receiver_id=Number(data.receiver_id);if(giver_id===receiver_id)fail('Самому себе и так нельзя дарить');if(!db.participants.some(p=>p.id===giver_id&&p.event_id===e.id)||!db.participants.some(p=>p.id===receiver_id&&p.event_id===e.id))fail('Участник не найден');if(!db.exclusions.some(x=>x.event_id===e.id&&x.giver_id===giver_id&&x.receiver_id===receiver_id))db.exclusions.push({event_id:e.id,giver_id,receiver_id});save();return{ok:true}}
 m=path.match(/^\/api\/santas\/(\d+)\/exclusions\/(\d+)\/(\d+)$/);if(m&&method==='DELETE'){const e=event(m[1]);if(e.status!=='open')fail('Правила заморожены');db.exclusions=db.exclusions.filter(x=>!(x.event_id===e.id&&x.giver_id===Number(m[2])&&x.receiver_id===Number(m[3])));save();return{ok:true}}
 m=path.match(/^\/api\/santas\/(\d+)\/draw$/);if(m&&method==='POST'){const e=event(m[1]);if(e.status==='drawn')return{ok:true,already_drawn:true};const ids=db.participants.filter(p=>p.event_id===e.id).map(p=>p.id);const pairs=choosePairs(ids,db.exclusions.filter(x=>x.event_id===e.id));db.assignments.push(...pairs.map(x=>({...x,event_id:e.id,revealed:false})));e.status='drawn';save();return{ok:true,already_drawn:false}}
 m=path.match(/^\/api\/santas\/(\d+)\/reveal$/);if(m&&method==='POST'){const e=event(m[1]),p=db.participants.find(p=>p.event_id===e.id&&p.user_id===user().id);const a=db.assignments.find(a=>a.event_id===e.id&&a.giver_id===p?.id);if(!a)fail('Жеребьёвка ещё не состоялась');a.revealed=true;save();return{assignment:assignmentView(e.id,p.id)}}
 m=path.match(/^\/api\/invites\/([^/]+)$/);if(m&&method==='GET'){const e=db.events.find(e=>e.invite_key===m[1]);if(!e)fail('Приглашение не найдено');return{event:{...e,participant_count:db.participants.filter(p=>p.event_id===e.id).length}}}
 m=path.match(/^\/api\/invites\/([^/]+)\/join$/);if(m&&method==='POST'){const e=db.events.find(e=>e.invite_key===m[1]);if(!e)fail('Приглашение не найдено');if(e.status!=='open')fail('Жеребьёвка уже прошла');if(db.participants.filter(p=>p.event_id===e.id).length>=12)fail('Максимум 12 участников');const participant_token=newToken();db.participants.push({id:ident(),event_id:e.id,user_id:null,name:data.name,access_token:participant_token});save();return{participant_token}}
 m=path.match(/^\/api\/participant\/([^/]+)$/);if(m&&method==='GET'){const p=part(m[1]),e=db.events.find(e=>e.id===p.event_id);return{participant:{...p,...e,name:p.name},wishes:db.p_wishes.filter(w=>w.participant_id===p.id),assignment:e.status==='drawn'?assignmentView(e.id,p.id):null}}
 m=path.match(/^\/api\/participant\/([^/]+)\/wishes$/);if(m&&method==='POST'){const p=part(m[1]);db.p_wishes.push({id:ident(),participant_id:p.id,title:data.title});save();return{ok:true}}
 m=path.match(/^\/api\/participant\/([^/]+)\/reveal$/);if(m&&method==='POST'){const p=part(m[1]);const a=db.assignments.find(a=>a.event_id===p.event_id&&a.giver_id===p.id);if(!a)fail('Жеребьёвка ещё не состоялась');a.revealed=true;save();return{assignment:assignmentView(p.event_id,p.id)}}
 fail('Действие не поддерживается в локальной демоверсии');
};
window.SHURSH_PREVIEW_RESET=function(){db=fresh();save();location.reload()};
save();
})();
render();
