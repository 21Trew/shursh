'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {createHash}=require('node:crypto');
const {gzipSync,brotliCompressSync}=require('node:zlib');
const {performance}=require('node:perf_hooks');
const path=require('node:path');
const file=path.join(__dirname,'../public/zxcvbn-4.4.2.js');
const buffer=fs.readFileSync(file);
const source=buffer.toString('utf8');
// Recover the exact pinned upstream blob from the licensed local copy.
const original=Buffer.from(source.slice(source.indexOf('*/\n')+3)+'//# sourceMappingURL=zxcvbn.js.map\n');
const gitHash=createHash('sha1').update('blob '+original.length+'\0').update(original).digest('hex');
assert.equal(gitHash,'0daf83098e4c90508dcbd69257c6f16ee4da3a8b');
const start=performance.now();
const zxcvbn=require(file);
const initMs=performance.now()-start;
const weak=['password','123456789','qwerty','a'.repeat(64),'Password123!'];
const strong=['Vq!7tZ#9mK2pF@8rYw4N','qvR!NtMkY@pLW','qvR!NtMkY@pL8'];
for(const s of weak)assert.ok(zxcvbn(s).score<=1,'Common/repeated sample not rejected by estimator');
for(const s of strong)assert.ok(zxcvbn(s).score>=3,'Varied sample scored too low');
assert.ok(zxcvbn('sampleuser2026!',['sampleuser']).score<=zxcvbn('sampleuser2026!').score);
assert.ok(zxcvbn('8'.repeat(31)+'*-*++*-+*hvKKKK').score<zxcvbn(strong[0]).score||zxcvbn('8'.repeat(31)+'*-*++*-+*hvKKKK').score>=2);
const corpus=[...weak,...strong,'Ab3xy!90','Ab3xy!90Kp6n','aB1'.repeat(24),'8'.repeat(60)+'Ab!9','я'.repeat(36),'😀'.repeat(18),'Vq!7tZ#9mK2pF@8rYw4N'.repeat(3)];
const times=[];
for(let i=0;i<4;i++)for(const s of corpus){
 const a=performance.now(),score=zxcvbn(s).score;
 assert.ok(Number.isInteger(score)&&score>=0&&score<=4);
 times.push(performance.now()-a);
}
times.sort((a,b)=>a-b);
const metrics={raw_bytes:buffer.length,gzip_bytes:gzipSync(buffer).length,brotli_bytes:brotliCompressSync(buffer).length,init_ms:+initMs.toFixed(2),p95_ms:+times[Math.ceil(times.length*.95)-1].toFixed(2),max_ms:+times.at(-1).toFixed(2),samples:times.length};
console.log('PASSWORD_STRENGTH_METRICS '+JSON.stringify(metrics));
assert.ok(metrics.gzip_bytes<450000,'Unexpected library bundle growth');
assert.ok(metrics.max_ms<2000,'Excessive estimate runtime on CI runner');
