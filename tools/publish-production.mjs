import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,renameSync,openSync,closeSync,unlinkSync,mkdirSync} from 'node:fs';
import {homedir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {setTimeout as sleep} from 'node:timers/promises';

export const REPO='21Trew/shursh', TEAM='team_JwJahAWZHQGMIoWnWAS0YWw3', PROJECT='prj_IRKWRDtNSrL0VXF0rPGmM358whHs';
export const ASSETS=['app.js','santa-ui.js','social-ui.js','styles.css','polish.css','fonts.css'];
export const REQUIRED=['frontend-syntax','python-tests (3.11)','python-tests (3.13)','postgres-integration','browser-e2e','pr4-ui-acceptance'];
const shaOK=s=>/^[a-f0-9]{40}$/.test(s||'');
const depOK=s=>/^dpl_[A-Za-z0-9]+$/.test(s||'');
const assert=(v,m)=>{if(!v)throw new Error(m)};
const hash=s=>createHash('sha256').update(s).digest('hex');
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function validateCI(pr,run,jobs,sha){
 assert(shaOK(sha)&&pr.head?.sha===sha&&pr.state==='open'&&pr.head?.repo?.full_name===REPO&&pr.base?.repo?.full_name===REPO,'PR HEAD/repository mismatch');
 assert(run.head_sha===sha&&run.repository?.full_name===REPO&&run.head_repository?.full_name===REPO&&run.path?.split('@')[0]==='.github/workflows/ci.yml'&&run.event==='pull_request'&&run.status==='completed'&&run.conclusion==='success','CI run is not successful for exact SHA');
 assert(run.pull_requests?.some(p=>p.number===pr.number&&p.head?.sha===sha),'CI run is not linked to this PR');
 for(const name of REQUIRED){
   const matches=jobs.filter(j=>j.name===name);
   assert(matches.length===1&&matches[0].status==='completed'&&matches[0].conclusion==='success'&&matches[0].head_sha===sha,'Required check failed or missing: '+name);
 }
}
export function validateDeployment(d,sha){
 assert(depOK(d.id)&&d.target==='production'&&d.readyState==='READY'&&(d.projectId??d.project?.id)===PROJECT,'Deployment is not READY Production in the expected project');
 assert(d.meta?.githubCommitSha===sha&&(!d.gitSource?.sha||d.gitSource.sha===sha)&&shaOK(sha),'Deployment SHA mismatch');
 assert(typeof d.url==='string'&&/^[a-z0-9-]+\.vercel\.app$/.test(d.url),'Unexpected deployment hostname');
}
export function inventory(rows){
 assert(Array.isArray(rows),'Missing domain inventory');
 const domains=rows.filter(d=>!d.gitBranch&&!d.customEnvironmentId);
 for(const d of domains){
   assert(d.projectId===PROJECT&&d.verified===true&&/^[a-z0-9.-]+$/.test(d.name),'Unverified or foreign Production domain');
   if(d.redirect)assert(domains.some(x=>x.name===d.redirect&&!x.redirect)&&[301,302,307,308].includes(d.redirectStatusCode),'Unsupported Production redirect');
 }
 const direct=domains.filter(d=>!d.redirect).map(d=>d.name).sort();
 const redirects=domains.filter(d=>d.redirect).map(d=>({name:d.name,to:d.redirect,status:d.redirectStatusCode})).sort((a,b)=>a.name.localeCompare(b.name));
 assert(direct.includes('shursh.fun')&&direct.includes('shursh.vercel.app')&&redirects.some(d=>d.name==='www.shursh.fun'&&d.to==='shursh.fun'),'Known Production domain missing or changed');
 assert(new Set(domains.map(d=>d.name)).size===domains.length,'Duplicate domain');
 return {direct,redirects};
}
export function assertAliasSnapshot(snapshot,id,domains){
 assert(depOK(id)&&Object.keys(snapshot).length===domains.length&&domains.every(d=>snapshot[d]===id),'Production aliases diverge or changed concurrently');
}
export async function transact({previous,candidate,domains,snapshot,inspect,verify,activate,rollback,save}){
 await inspect();
 assertAliasSnapshot(await snapshot(),previous,domains);
 await save('prepared');
 try{
   await activate(candidate);
   await verify(candidate);
   await save('published');
 }catch(error){
   try{
     const state=await snapshot();
     assert(domains.every(d=>[previous,candidate].includes(state[d])),'Concurrent external release; refusing to overwrite');
     await rollback(previous);
     await verify(previous);
     await save('rolled-back');
   }catch{
     await save('rollback-required');
     throw new Error('Release failed; rollback not verified. Use saved journal and inspect Production immediately.');
   }
   throw new Error('Release failed; previous Production restored and verified.');
 }
}
async function api(origin,path,token,method='GET',body){
 assert(token,'Missing API token');
 const url=new URL(path,origin);assert(url.origin===origin,'Invalid API host');
 const res=await fetch(url,{method,headers:{Authorization:'Bearer '+token,Accept:'application/json','Content-Type':'application/json',...(origin==='https://api.github.com'?{'X-GitHub-Api-Version':'2022-11-28'}:{})},body:body===undefined?undefined:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(30000)});
 assert(res.ok,'API request failed: '+method+' '+url.pathname+' HTTP '+res.status);
 return res.status===204?{}:await res.json();
}
const gh=(p)=>api('https://api.github.com','/repos/'+REPO+p,process.env.GH_TOKEN);
const vercel=(p,method='GET',body)=>api('https://api.vercel.com',p+(p.includes('?')?'&':'?')+'teamId='+TEAM,process.env.VERCEL_TOKEN,method,body);
async function getCI(prNumber,runId,sha){
 const [pr,run,jobs]=await Promise.all([gh('/pulls/'+prNumber),gh('/actions/runs/'+runId),gh('/actions/runs/'+runId+'/jobs?filter=latest&per_page=100')]);
 assert(jobs.total_count===jobs.jobs.length,'Incomplete CI job listing');
 validateCI(pr,run,jobs.jobs,sha);
}
async function getDeployment(id){return vercel('/v13/deployments/'+id+'?withGitRepoInfo=true')}
async function domains(){
 const data=await vercel('/v9/projects/'+PROJECT+'/domains?limit=100');
 assert(!data.pagination?.next,'Domain inventory exceeds supported page; stop');
 return inventory(data.domains);
}
async function aliases(list){
 return Object.fromEntries(await Promise.all(list.map(async name=>{
   const a=await vercel('/v4/aliases/'+encodeURIComponent(name));
   assert(a.projectId===PROJECT&&depOK(a.deploymentId),'Alias is not in expected project');
   return [name,a.deploymentId];
 })));
}
async function publicGet(origin,path,{bypass,method='GET'}={}){
 const url=new URL(path,origin);assert(url.origin===origin,'Invalid smoke origin');
 const headers={'Cache-Control':'no-cache',...(bypass?{'x-vercel-protection-bypass':bypass}:{})};
 const r=await fetch(url,{method,headers,redirect:'manual',cache:'no-store',signal:AbortSignal.timeout(15000)});
 return {status:r.status,headers:r.headers,bytes:Buffer.from(await r.arrayBuffer())};
}
async function smoke(origin,{versioned=true,bypass}={}){
 const get=(path,method)=>publicGet(origin,path,{bypass,method});
 const home=await get('/'), html=home.bytes.toString('utf8'), version=home.headers.get('x-shursh-ui-version')||'';
 assert(home.status===200&&home.headers.get('content-type')?.includes('text/html')&&html.includes('Шурш!')&&home.headers.get('cache-control')?.includes('no-store')&&home.headers.get('x-frame-options')==='DENY'&&home.headers.get('content-security-policy')?.includes("default-src 'self'"),'Homepage smoke failed');
 if(versioned)assert(/^[a-f0-9]{20}$/.test(version),'Missing UI fingerprint');
 const hashes={};
 for(const file of ASSETS){
   // The Flask /ui/<version>/ route bypasses Vercel's public-file
   // shadowing; older rollback baselines can still use unversioned assets.
   const path=version?'/ui/'+version+'/'+file:'/'+file;
   const result=await get(path);
   assert(result.status===200&&result.headers.get('content-type')?.includes(file.endsWith('.js')?'javascript':'text/css'),'Asset smoke failed: '+file);
   if(version)assert(html.includes('"'+path+'"')&&result.headers.get('x-shursh-ui-version')===version,'Mixed UI version: '+file);
   hashes[file]=hash(result.bytes);
 }
 for(const path of ['/api/me','/api/dashboard']){
   const r=await get(path),data=JSON.parse(r.bytes.toString('utf8'));
   assert(r.status===200&&r.headers.get('cache-control')?.includes('no-store')&&data.user===null&&data.demo===false,'Anonymous API smoke failed');
   if(path.endsWith('dashboard'))assert(Array.isArray(data.lists)&&!data.lists.length&&Array.isArray(data.events)&&!data.events.length,'Anonymous dashboard leaked state');
 }
 assert((await get('/this-page-does-not-exist')).status===404,'404 smoke failed');
 if(versioned){
   for(const path of ['/api/participant/reveal','/api/participant/null/reveal','/api/participant/undefined/reveal']){
     const r=await get(path,'POST');
     assert(r.status===409&&!Object.hasOwn(JSON.parse(r.bytes.toString('utf8')),'assignment'),'Unsafe stale route');
   }
 }
 return {version,hashes};
}
async function sourceHashes(sha){
 const hashes={};
 for(const file of ASSETS){
   const data=await gh('/contents/public/'+file+'?ref='+sha);
   assert(data.type==='file'&&data.encoding==='base64'&&typeof data.content==='string','Source asset unavailable');
   hashes[file]=hash(Buffer.from(data.content,'base64'));
 }
 return hashes;
}
async function liveSmoke(inv,expected){
 for(const d of inv.direct){
   const actual=await smoke('https://'+d,{versioned:!!expected.version});
   assert(equal(actual,expected),'Production bytes/version mismatch: '+d);
 }
 for(const d of inv.redirects){
   const probe='/santas';
   const r=await publicGet('https://'+d.name,probe);
   const location=r.headers.get('location');
   assert(r.status===d.status&&location&&new URL(location,'https://'+d.name).href==='https://'+d.to+probe,'Production redirect mismatch: '+d.name);
 }
}
async function settle(check){
 let error;
 for(let i=0;i<12;i++){try{return await check()}catch(e){error=e;if(i!==11)await sleep(5000)}}
 throw error;
}
function parse(argv){
 const [action,...rest]=argv;
 assert(['publish','rollback'].includes(action),'Use publish or rollback; dry-run unless --apply');
 const options={action,apply:false};
 for(let i=0;i<rest.length;i++){
   const key=rest[i];
   if(key==='--apply'){assert(!options.apply,'Duplicate option');options.apply=true;continue}
   assert(['--sha','--pr','--run','--deployment'].includes(key)&&!Object.hasOwn(options,key),'Invalid/duplicate option');
   options[key]=rest[++i];
 }
 if(action==='publish')assert(shaOK(options['--sha'])&&/^[1-9]\d*$/.test(options['--pr'])&&/^[1-9]\d*$/.test(options['--run'])&&depOK(options['--deployment']),'Exact full SHA, PR number, CI run ID and staged deployment ID required');
 else assert(Object.keys(options).length===2,'Rollback uses last journal; no overrides');
 return options;
}
async function main(){
 const opts=parse(process.argv.slice(2));
 const dir=join(homedir(),'.shursh-release');mkdirSync(dir,{recursive:true,mode:0o700});
 const journal=join(dir,'journal.json'),lock=join(dir,'lock');
 const fd=openSync(lock,'wx',0o600);
 const read=()=>JSON.parse(readFileSync(journal,'utf8'));
 const save=(data)=>{const temp=journal+'.tmp';writeFileSync(temp,JSON.stringify(data,null,2)+'\n',{mode:0o600});renameSync(temp,journal)};
 const activate=id=>vercel('/v10/projects/'+PROJECT+'/promote/'+id,'POST',{});
 const rollback=id=>vercel('/v1/projects/'+PROJECT+'/rollback/'+id,'POST',{});
 try{
   const inv=await domains(),snapshot=()=>aliases(inv.direct);
   if(opts.action==='rollback'){
     const j=read();
     assert(['published','prepared','rollback-required'].includes(j.state)&&equal(j.inventory,inv),'No valid rollback journal or changed domain inventory');
     const previous=await getDeployment(j.previous);validateDeployment(previous,j.previousSHA);
     const state=await snapshot();
     assert(inv.direct.every(d=>[j.previous,j.candidate].includes(state[d])),'Unexpected concurrent release');
     console.log('Rollback plan:',j.previous,j.previousSHA);
     if(!opts.apply)return;
     await rollback(j.previous);
     await settle(async()=>{assertAliasSnapshot(await snapshot(),j.previous,inv.direct);await liveSmoke(inv,j.baseline)});
     save({...j,state:'rolled-back'});console.log('Rollback verified');return;
   }
   const sha=opts['--sha'],pr=opts['--pr'],run=opts['--run'],candidate=opts['--deployment'];
   const ci=()=>getCI(pr,run,sha);
   await ci();
   const next=await getDeployment(candidate);validateDeployment(next,sha);
   const state=await snapshot(),previous=state['shursh.fun'];
   assertAliasSnapshot(state,previous,inv.direct);assert(candidate!==previous,'Candidate already live');
   const prior=await getDeployment(previous),previousSHA=prior.meta?.githubCommitSha;validateDeployment(prior,previousSHA);
   const delta=await gh('/compare/'+previousSHA+'...'+sha+'?per_page=100');
   assert(['ahead','identical'].includes(delta.status)&&Array.isArray(delta.files)&&delta.files.length<300,'Cannot establish forward-only release diff');
   assert(!delta.files.some(f=>[f.filename,f.previous_filename].some(n=>n?.startsWith('supabase/migrations/'))),'Release requires separate migration approval');
   const baseline=await smoke('https://shursh.fun',{versioned:false});
   await liveSmoke(inv,baseline);
   const expected=await smoke('https://'+next.url,{bypass:process.env.VERCEL_AUTOMATION_BYPASS_SECRET});
   assert(equal(expected.hashes,await sourceHashes(sha)),'Staged asset bytes differ from exact Git SHA');
   console.log('Release plan:',JSON.stringify({sha,pr,run,candidate,previous,previousSHA,inventory:inv,version:expected.version}));
   if(!opts.apply)return;
   let old;try{old=read()}catch(e){if(e.code!=='ENOENT')throw e}
   assert(!old||!['prepared','rollback-required'].includes(old.state),'Unresolved earlier transaction; recover first');
   const j={previous,previousSHA,candidate,sha,inventory:inv,baseline,expected};
   await transact({previous,candidate,domains:inv.direct,snapshot,
     inspect:async()=>{await ci();assert(equal(await domains(),inv),'Domain inventory changed');validateDeployment(await getDeployment(candidate),sha)},
     activate,rollback,save:state=>save({...j,state}),
     verify:id=>settle(async()=>{assert(equal(await domains(),inv),'Domain inventory changed');assertAliasSnapshot(await snapshot(),id,inv.direct);await liveSmoke(inv,id===candidate?expected:baseline)})});
   console.log('Production release verified');
 }finally{closeSync(fd);unlinkSync(lock)}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 main().catch(error=>{console.error(error instanceof Error?error.message:'Release failed');process.exitCode=1});
}
