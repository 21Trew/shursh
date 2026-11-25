// No deployment credentials or untrusted candidate code are used here.
export const RELEASE_REPO='21Trew/shursh';
export const RELEASE_BRANCH='main';
export const RELEASE_ENV='shursh-production';
export const JOURNAL_BRANCH='release-journal';
export const JOURNAL_PATH='release-journal.json';
const location='/contents/'+JOURNAL_PATH;
const shaOK=s=>/^[a-f0-9]{40}$/.test(s||'');
const depOK=s=>/^dpl_[A-Za-z0-9]+$/.test(s||'');
const numberOK=s=>/^[1-9]\d*$/.test(s||'');
const assert=(v,m)=>{if(!v)throw Error(m)};
const states=['idle','prepared','published','rolled-back','rollback-required'];
export function validateIntent(env){
 const action=env.DISPATCH_ACTION,apply=env.DISPATCH_APPLY==='true',sha=env.DISPATCH_SHA||'',live=env.RELEASE_EXPECTED_LIVE||'';
 assert(['true','false'].includes(env.DISPATCH_APPLY),'Explicit execution mode required');
 assert(['audit','publish','rollback'].includes(action),'Unknown release operation');
 if(action==='audit'){
   assert(!apply&&!sha&&!live&&!env.DISPATCH_PR&&!env.DISPATCH_RUN&&!env.DISPATCH_DEPLOYMENT&&!env.RELEASE_CONFIRM,'Audit takes no release parameters');
   return ['audit'];
 }
 assert(shaOK(sha)&&depOK(live),'Exact target SHA and expected live deployment required');
 assert(!apply||env.RELEASE_CONFIRM===action.toUpperCase()+' '+sha,'Exact confirmation required');
 if(action==='publish'){
   assert(numberOK(env.DISPATCH_PR)&&numberOK(env.DISPATCH_RUN)&&depOK(env.DISPATCH_DEPLOYMENT)&&env.DISPATCH_DEPLOYMENT!==live,'Invalid PR, CI run or staged deployment');
   return ['publish','--sha',sha,'--pr',env.DISPATCH_PR,'--run',env.DISPATCH_RUN,'--deployment',env.DISPATCH_DEPLOYMENT,...(apply?['--apply']:[])];
 }
 assert(!env.DISPATCH_PR&&!env.DISPATCH_RUN&&!env.DISPATCH_DEPLOYMENT,'Rollback target must come from central journal');
 return ['rollback',...(apply?['--apply']:[])];
}
export function validateWorkflow(env,{apply=false}={}){
 assert(env.GITHUB_ACTIONS==='true'&&env.GITHUB_REPOSITORY===RELEASE_REPO&&env.GITHUB_EVENT_NAME==='workflow_dispatch'&&env.GITHUB_REF==='refs/heads/'+RELEASE_BRANCH&&env.GITHUB_WORKFLOW_REF===RELEASE_REPO+'/.github/workflows/production-release.yml@refs/heads/'+RELEASE_BRANCH&&env.GITHUB_REF_PROTECTED==='true'&&shaOK(env.GITHUB_SHA)&&numberOK(env.GITHUB_RUN_ID)&&env.GITHUB_RUN_ATTEMPT==='1','Use a fresh dispatch from the protected controller branch');
 if(apply)assert(env.SHURSH_RELEASE_ENABLED==='true','Production release is disabled');
}
export function validateApproval(environment,run,reviews,env){
 validateWorkflow(env,{apply:true});
 assert(run.id===Number(env.GITHUB_RUN_ID)&&run.head_sha===env.GITHUB_SHA&&run.head_branch===RELEASE_BRANCH&&run.event==='workflow_dispatch'&&run.path?.split('@')[0]==='.github/workflows/production-release.yml'&&run.repository?.full_name===RELEASE_REPO&&run.run_attempt===1&&run.actor?.id,'Unexpected workflow run');
 const rule=environment.protection_rules?.find(r=>r.type==='required_reviewers');
 assert(environment.name===RELEASE_ENV&&environment.id&&rule?.prevent_self_review===true&&rule.reviewers?.length&&environment.deployment_branch_policy?.custom_branch_policies===true,'Protected environment with independent reviewer and branch policy required');
 const relevant=Array.isArray(reviews)?reviews.filter(r=>r.environments?.some(e=>e.id===environment.id&&e.name===RELEASE_ENV)):[];
 assert(relevant.length===1&&relevant[0].state==='approved'&&relevant[0].user?.id&&relevant[0].user.id!==run.actor.id,'Independent environment approval not verified');
}
export async function checkTrustedCI(gh,sha,controllerSHA){
 assert(shaOK(sha)&&shaOK(controllerSHA),'Invalid candidate or controller SHA');
 const path='/contents/.github/workflows/ci.yml?ref=';
 const [candidate,controller]=await Promise.all([gh(path+sha),gh(path+controllerSHA)]);
 assert(candidate.path==='.github/workflows/ci.yml'&&controller.path===candidate.path&&candidate.type==='file'&&controller.type==='file'&&shaOK(candidate.sha)&&candidate.sha===controller.sha,'Candidate CI definition differs from trusted controller; review it separately before release');
}
export async function checkApproval(gh,env){
 validateWorkflow(env,{apply:true});
 const id=env.GITHUB_RUN_ID;
 const [environment,run,reviews,policies]=await Promise.all([gh('/environments/'+RELEASE_ENV),gh('/actions/runs/'+id),gh('/actions/runs/'+id+'/approvals'),gh('/environments/'+RELEASE_ENV+'/deployment-branch-policies?per_page=100')]);
 validateApproval(environment,run,reviews,env);
 assert(policies.total_count===1&&policies.branch_policies?.length===1&&policies.branch_policies[0].name===RELEASE_BRANCH&&policies.branch_policies[0].type==='branch','Environment must allow only the trusted controller branch');
}
export function validateJournal(j){
 assert(j&&j.schema===1&&states.includes(j.state),'Missing or invalid central journal');
 if(j.state==='idle'){assert(Object.keys(j).length===2,'Invalid journal bootstrap');return j}
 assert(depOK(j.previous)&&depOK(j.candidate)&&j.previous!==j.candidate&&shaOK(j.previousSHA)&&shaOK(j.sha)&&numberOK(j.runId)&&numberOK(j.lastRunId)&&Number.isFinite(j.startedAt)&&j.inventory&&j.baseline?.hashes&&j.expected?.hashes,'Incomplete release journal');
 return j;
}
export function assertJournalBaseline(j,id,sha){
 validateJournal(j);
 assert(!['prepared','rollback-required'].includes(j.state),'Unresolved earlier transaction; run recovery before publishing');
 if(j.state==='published')assert(j.candidate===id&&j.sha===sha,'Live deployment differs from central journal');
 if(j.state==='rolled-back')assert(j.previous===id&&j.previousSHA===sha,'Live deployment differs from central journal');
}
export async function openCentralJournal(gh,env,{apply=false}={}){
 validateWorkflow(env,{apply});
 async function get(){
   const file=await gh(location+'?ref='+JOURNAL_BRANCH);
   assert(file.path===JOURNAL_PATH&&file.type==='file'&&file.encoding==='base64'&&shaOK(file.sha)&&typeof file.content==='string'&&file.size<=65536,'Invalid journal file');
   return {blob:file.sha,data:validateJournal(JSON.parse(Buffer.from(file.content,'base64').toString('utf8')))};
 }
 let current=await get();
 return {
   read:()=>current.data,
   assertCurrent:async()=>{const now=await get();assert(now.blob===current.blob,'Central journal changed concurrently')},
   save:async data=>{
     assert(apply,'Dry-run cannot write central journal');
     const entry=validateJournal({...data,schema:1,lastRunId:env.GITHUB_RUN_ID,updatedAt:new Date().toISOString()});
     const body=JSON.stringify(entry,null,2)+'\n';
     assert(Buffer.byteLength(body)<=65536,'Journal exceeds limit');
     const res=await gh(location,'PUT',{message:'Release journal '+entry.state+' (run '+env.GITHUB_RUN_ID+')',branch:JOURNAL_BRANCH,sha:current.blob,content:Buffer.from(body).toString('base64')});
     assert(shaOK(res.content?.sha)&&shaOK(res.commit?.sha),'Journal write unconfirmed');
     const now=await get();
     assert(now.blob===res.content.sha&&JSON.stringify(now.data)===JSON.stringify(entry),'Journal write not verified');
     current=now;
     console.log('Central journal:',entry.state,'commit',res.commit.sha);
   }
 };
}
