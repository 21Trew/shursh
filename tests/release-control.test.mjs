import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateIntent,validateWorkflow,validateApproval,checkApproval,checkTrustedCI,openCentralJournal,assertJournalBaseline,RELEASE_REPO,RELEASE_ENV,JOURNAL_BRANCH,JOURNAL_PATH} from '../tools/release-control.mjs';
const sha='a'.repeat(40),prior='b'.repeat(40),previous='dpl_old',candidate='dpl_new';
const env={GITHUB_ACTIONS:'true',GITHUB_REPOSITORY:RELEASE_REPO,GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REF:'refs/heads/main',GITHUB_WORKFLOW_REF:RELEASE_REPO+'/.github/workflows/production-release.yml@refs/heads/main',GITHUB_REF_PROTECTED:'true',GITHUB_SHA:prior,GITHUB_RUN_ID:'42',GITHUB_RUN_ATTEMPT:'1',SHURSH_RELEASE_ENABLED:'true',DISPATCH_ACTION:'publish',DISPATCH_APPLY:'true',DISPATCH_SHA:sha,DISPATCH_PR:'19',DISPATCH_RUN:'480',DISPATCH_DEPLOYMENT:candidate,RELEASE_EXPECTED_LIVE:previous,RELEASE_CONFIRM:'PUBLISH '+sha};
const environment={id:123,name:RELEASE_ENV,protection_rules:[{type:'required_reviewers',prevent_self_review:true,reviewers:[{type:'User',reviewer:{id:2}}]}],deployment_branch_policy:{custom_branch_policies:true}};
const run={id:42,head_sha:prior,head_branch:'main',event:'workflow_dispatch',path:'.github/workflows/production-release.yml',repository:{full_name:RELEASE_REPO},run_attempt:1,actor:{id:1}};
const approval={state:'approved',environments:[{id:123,name:RELEASE_ENV}],user:{id:2}};
test('exact SHA, expected live and independent confirmation',()=>{
 assert.ok(validateIntent(env).includes('--apply'));
 assert.ok(!validateIntent({...env,DISPATCH_APPLY:'false'}).includes('--apply'));
 for(const patch of [{DISPATCH_SHA:'abc'},{RELEASE_EXPECTED_LIVE:candidate},{RELEASE_CONFIRM:'yes'},{DISPATCH_RUN:'1; echo x'},{DISPATCH_APPLY:'TRUE'}])assert.throws(()=>validateIntent({...env,...patch}));
});
test('audit cannot mutate and rollback cannot override deployment',()=>{
 assert.deepEqual(validateIntent({DISPATCH_ACTION:'audit',DISPATCH_APPLY:'false'}),['audit']);
 assert.throws(()=>validateIntent({DISPATCH_ACTION:'audit',DISPATCH_APPLY:'true'}));
 const e={DISPATCH_ACTION:'rollback',DISPATCH_APPLY:'true',DISPATCH_SHA:prior,DISPATCH_PR:'',DISPATCH_RUN:'',DISPATCH_DEPLOYMENT:'',RELEASE_EXPECTED_LIVE:candidate,RELEASE_CONFIRM:'ROLLBACK '+prior};
 assert.deepEqual(validateIntent(e),['rollback','--apply']);
 assert.throws(()=>validateIntent({...e,DISPATCH_DEPLOYMENT:previous}));
});
test('local, fork, unprotected branch, rerun and disabled gate cannot apply',()=>{
 validateWorkflow(env,{apply:true});
 for(const patch of [{GITHUB_ACTIONS:'false'},{GITHUB_REF:'refs/heads/feature'},{GITHUB_REF_PROTECTED:'false'},{GITHUB_EVENT_NAME:'pull_request'},{GITHUB_RUN_ATTEMPT:'2'},{GITHUB_REPOSITORY:'other/shursh'},{SHURSH_RELEASE_ENABLED:''}])assert.throws(()=>validateWorkflow({...env,...patch},{apply:true}));
});
test('approval must be independent, actual, current run and protected environment',()=>{
 validateApproval(environment,run,[approval],env);
 for(const reviews of [[],[{...approval,state:'rejected'}],[{...approval,user:{id:1}}],[{...approval,environments:[{id:999,name:RELEASE_ENV}]}],[approval,approval]])assert.throws(()=>validateApproval(environment,run,reviews,env));
 assert.throws(()=>validateApproval({...environment,protection_rules:[]},run,[approval],env));
 assert.throws(()=>validateApproval(environment,{...run,head_sha:sha},[approval],env));
});
test('environment branch policy must permit only main',async()=>{
 const api=async p=>p.includes('deployment-branch-policies')?{total_count:1,branch_policies:[{name:'main',type:'branch'}]}:p.endsWith('/approvals')?[approval]:p.includes('/environments/')?environment:run;
 await checkApproval(api,env);
 await assert.rejects(checkApproval(async p=>p.includes('deployment-branch-policies')?{total_count:1,branch_policies:[{name:'*',type:'branch'}]}:api(p),env),/only the trusted/);
});
const entry={schema:1,state:'prepared',previous,previousSHA:prior,candidate,sha,runId:'42',lastRunId:'42',startedAt:100,inventory:{direct:['shursh.fun']},baseline:{hashes:{}},expected:{hashes:{}}};
function journalMock({initial={schema:1,state:'idle'},fail=false,lost=false}={}){
 let data=initial,blob='c'.repeat(40),writes=0;
 const gh=async (path,method='GET',body)=>{
   if(method==='PUT'){
     assert.equal(path,'/contents/'+JOURNAL_PATH);assert.equal(body.branch,JOURNAL_BRANCH);assert.equal(body.sha,blob);writes++;
     if(fail)throw Error('409');
     data=JSON.parse(Buffer.from(body.content,'base64'));blob='d'.repeat(40);
     if(lost)throw Error('response lost');
     return {content:{sha:blob},commit:{sha:'e'.repeat(40)}};
   }
   assert.equal(path,'/contents/'+JOURNAL_PATH+'?ref='+JOURNAL_BRANCH);
   const content=Buffer.from(JSON.stringify(data));return {path:JOURNAL_PATH,type:'file',encoding:'base64',sha:blob,size:content.length,content:content.toString('base64')};
 };
 return {gh,change:()=>{blob='f'.repeat(40)},writes:()=>writes,data:()=>data};
}
test('dry-run is read-only and journal is mandatory',async()=>{
 const m=journalMock();const j=await openCentralJournal(m.gh,env);
 await assert.rejects(j.save(entry),/Dry-run/);assert.equal(m.writes(),0);
 await assert.rejects(openCentralJournal(async()=>{throw Error('404')},env),/404/);
});
test('prepared record is durable across runner crash and blocks new publish',async()=>{
 const m=journalMock();const j=await openCentralJournal(m.gh,env,{apply:true});await j.save(entry);
 const fresh=await openCentralJournal(m.gh,{...env,GITHUB_RUN_ID:'43'},{apply:true});
 assert.equal(fresh.read().state,'prepared');assert.throws(()=>assertJournalBaseline(fresh.read(),previous,prior),/Unresolved/);
});
test('journal concurrent change or CAS conflict fails closed',async()=>{
 const m=journalMock();const j=await openCentralJournal(m.gh,env,{apply:true});m.change();
 await assert.rejects(j.assertCurrent(),/concurrently/);
 const f=journalMock({fail:true});const k=await openCentralJournal(f.gh,env,{apply:true});await assert.rejects(k.save(entry),/409/);
});
test('lost journal write response blocks execution, prepared record survives',async()=>{
 const m=journalMock({lost:true});const j=await openCentralJournal(m.gh,env,{apply:true});await assert.rejects(j.save(entry),/response lost/);
 const next=await openCentralJournal(m.gh,env);assert.equal(next.read().state,'prepared');
});
test('published and rollback baselines reject external domain changes',()=>{
 assertJournalBaseline({...entry,state:'published'},candidate,sha);
 assertJournalBaseline({...entry,state:'rolled-back'},previous,prior);
 assert.throws(()=>assertJournalBaseline({...entry,state:'published'},previous,prior));
 assert.throws(()=>assertJournalBaseline({...entry,state:'rollback-required'},candidate,sha));
});
test('workflow only manual, shared concurrency, protected environments and pinned checkout',()=>{
 const w=readFileSync(new URL('../.github/workflows/production-release.yml',import.meta.url),'utf8');
 assert.match(w,/\non:\n  workflow_dispatch:/);
 assert.doesNotMatch(w,/^\s{2}(push|pull_request|schedule|workflow_run):/m);
 assert.match(w,/group: shursh-production-release\n  cancel-in-progress: false/);
 assert.match(w,/needs: plan/);
 assert.match(w,/environment: shursh-production/);
 assert.match(w,/environment: shursh-release-read/);
 assert.match(w,/contents: read/);assert.match(w,/contents: write/);
 assert.match(w,/DISPATCH_APPLY: 'false'/);assert.match(w,/DISPATCH_APPLY: 'true'/);
 assert.equal((w.match(/persist-credentials: false/g)||[]).length,2);
 for(const m of w.matchAll(/uses: [^@\n]+@([^\n]+)/g))assert.match(m[1],/^[a-f0-9]{40}$/);
 assert.doesNotMatch(w,/run:.*\$\{\{/);
});

test('candidate cannot substitute a green but different CI definition',async()=>{
 const file={path:'.github/workflows/ci.yml',type:'file',sha:'c'.repeat(40)};
 await checkTrustedCI(async()=>file,sha,prior);
 await assert.rejects(checkTrustedCI(async path=>path.endsWith(sha)?{...file,sha:'d'.repeat(40)}:file,sha,prior),/differs from trusted/);
});
