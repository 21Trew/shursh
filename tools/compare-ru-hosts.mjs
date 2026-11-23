/** Anonymous comparison of the Vercel and Russian pilot origins.
 * Usage (run from a Russian network WITHOUT VPN):
 *   node tools/compare-ru-hosts.mjs https://<timeweb-technical-host>
 * No auth, cookies, write requests, response bodies or access tokens.
 */
const input=process.argv[2];
if (!input) {
  console.error('Usage: node tools/compare-ru-hosts.mjs https://<pilot-host>');
  process.exit(2);
}
let pilot;
try { pilot=new URL(input); } catch { throw Error('Expected a valid HTTPS origin'); }
if (pilot.protocol!=='https:' || pilot.username || pilot.password ||
    pilot.pathname!=='/' || pilot.search || pilot.hash ||
    !pilot.hostname || pilot.hostname==='shursh.fun' ||
    pilot.hostname==='shursh.vercel.app') {
  throw Error('Pilot must be a different HTTPS origin, without path/query');
}
const hosts=[{name:'Vercel',origin:'https://shursh.fun'},
             {name:'RU pilot',origin:pilot.origin}];
const paths=['/','/app.js','/styles.css','/fonts.css','/api/me','/api/dashboard'];
const samples=3,timeoutMs=12000;
const records=[];
const median=values=>{
  const v=[...values].sort((a,b)=>a-b);
  if(!v.length) return null;
  const mid=Math.floor(v.length/2);
  return v.length%2?v[mid]:Math.round((v[mid-1]+v[mid])/2);
};
for (const path of paths){
  for(let n=0;n<samples;n++){
    // Alternate networks per attempt to reduce bias from changing RF routing.
    for(const host of (n%2===0?hosts:[...hosts].reverse())){
      const start=performance.now();
      let firstByte=null;
      let status=null;
      let error=null;
      try{
        const r=await fetch(host.origin+path,{
          method:'GET',redirect:'manual',cache:'no-store',
          credentials:'omit',signal:AbortSignal.timeout(timeoutMs)});
        firstByte=Math.round(performance.now()-start);
        status=r.status;
        await r.body?.cancel();
      }catch(e){ error=e?.cause?.code||e?.name||'network-error'; }
      records.push({host:host.name,path,attempt:n+1,status,
                    ttfbMs:firstByte,error,elapsedMs:Math.round(performance.now()-start)});
    }
  }
}
const summary=hosts.flatMap(h=>paths.map(p=>{
  const rows=records.filter(r=>r.host===h.name&&r.path===p);
  const ok=rows.filter(r=>r.status===200);
  const errors=rows.filter(r=>r.status!==200).map(r=>r.error||'HTTP_'+r.status);
  return {host:h.name,path:p,ok:ok.length+'/'+rows.length,
          medianTtfbMs:median(ok.map(r=>r.ttfbMs)),
          failures:errors.join(',')||'-'};
}));
console.table(summary);
console.log('Measurements are anonymous and limited to 3 requests per route/origin.');
console.log('These are spot checks, not an uptime guarantee.');
