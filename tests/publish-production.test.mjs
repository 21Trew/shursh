import test from 'node:test';
import assert from 'node:assert/strict';
import {REPO,PROJECT,REQUIRED,validateCI,validateDeployment,inventory,assertAliasSnapshot,transact} from '../tools/publish-production.mjs';
const sha='a'.repeat(40),prev='dpl_old',next='dpl_new',names=['shursh.fun','shursh.vercel.app'];
const pr={number:18,head:{sha,repo:{full_name:REPO}},base:{repo:{full_name:REPO}},state:'open'};
const run={head_sha:sha,repository:{full_name:REPO},head_repository:{full_name:REPO},path:'.github/workflows/ci.yml',event:'pull_request',status:'completed',conclusion:'success',pull_requests:[{number:18,head:{sha}}]};
const jobs=REQUIRED.map(name=>({name,status:'completed',conclusion:'success',head_sha:sha}));
test('CI gate exact SHA and all six checks',()=>{
 validateCI(pr,run,jobs,sha);
 for(const change of [{...run,head_sha:'b'.repeat(40)},{...run,conclusion:'failure'},{...run,path:'other.yml'},{...run,pull_requests:[]}])assert.throws(()=>validateCI(pr,change,jobs,sha));
 assert.throws(()=>validateCI(pr,run,jobs.slice(1),sha));
 assert.throws(()=>validateCI(pr,run,[...jobs,jobs[0]],sha));
 assert.throws(()=>validateCI(pr,run,jobs.map(j=>({...j,conclusion:'skipped'})),sha));
});
test('only exact production build in the project',()=>{
 const d={id:next,target:'production',readyState:'READY',project:{id:PROJECT},meta:{githubCommitSha:sha},url:'shursh-candidate.vercel.app'};
 validateDeployment(d,sha);
 for(const patch of [{target:'preview'},{readyState:'BUILDING'},{project:{id:'wrong'}},{meta:{githubCommitSha:'b'.repeat(40)}},{url:'evil.com'}])assert.throws(()=>validateDeployment({...d,...patch},sha));
});
test('domain inventory includes redirects and new production hosts; rejects unsafe redirects',()=>{
 const rows=[...names.map(name=>({name,verified:true,projectId:PROJECT})),{name:'www.shursh.fun',verified:true,projectId:PROJECT,redirect:'shursh.fun',redirectStatusCode:308}];
 assert.deepEqual(inventory(rows).direct,names);
 assert.equal(inventory([...rows,{name:'extra.shursh.fun',verified:true,projectId:PROJECT}]).direct.length,3);
 assert.throws(()=>inventory(rows.slice(1)));
 assert.throws(()=>inventory(rows.map(d=>d.redirect?{...d,redirect:'evil.com'}:d)));
 assert.throws(()=>assertAliasSnapshot({'shursh.fun':prev,'shursh.vercel.app':next},prev,names));
});
function harness({fail=false,external=false,rollbackFail=false}={}){
 let current=prev;const events=[];
 const snapshot=async()=>Object.fromEntries(names.map(d=>[d,current]));
 return {events,options:{previous:prev,candidate:next,domains:names,snapshot,inspect:async()=>events.push('inspect'),activate:async id=>{current=id;events.push('activate')},rollback:async id=>{events.push('rollback');if(rollbackFail)throw Error('rollback failed');current=id},verify:async id=>{events.push('verify:'+id);if(fail&&id===next){if(external)current='dpl_external';throw Error('smoke failed')}assert.equal(current,id)},save:async s=>events.push(s)}};
}
test('successful promotion uses one deployment and verifies before success',async()=>{const h=harness();await transact(h.options);assert.deepEqual(h.events,['inspect','prepared','activate','verify:'+next,'published'])});
test('failed smoke rolls back and verifies previous deployment',async()=>{const h=harness({fail:true});await assert.rejects(transact(h.options),/restored and verified/);assert.deepEqual(h.events,['inspect','prepared','activate','verify:'+next,'rollback','verify:'+prev,'rolled-back'])});
test('external concurrent release is never overwritten',async()=>{const h=harness({fail:true,external:true});await assert.rejects(transact(h.options),/rollback not verified/);assert.equal(h.events.at(-1),'rollback-required');assert.ok(!h.events.includes('rollback'))});
test('rollback failure is not reported as success',async()=>{const h=harness({fail:true,rollbackFail:true});await assert.rejects(transact(h.options),/rollback not verified/);assert.equal(h.events.at(-1),'rollback-required')});
test('divergent starting aliases fail before any mutation',async()=>{const h=harness();h.options.snapshot=async()=>({'shursh.fun':prev,'shursh.vercel.app':next});await assert.rejects(transact(h.options),/diverge/);assert.deepEqual(h.events,['inspect'])});
