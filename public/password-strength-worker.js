/* Local-only password estimate. No network requests with credentials. */
'use strict';
importScripts('/zxcvbn-4.4.2.js');
self.onmessage=({data})=>{
 const id=data?.id;
 try{
  if(typeof data.password!=='string'||new TextEncoder().encode(data.password).length>72)
   throw new Error('Invalid input');
  const context=Array.isArray(data.context)?data.context.filter(v=>typeof v==='string').map(v=>v.slice(0,200)).slice(0,2):[];
  const result=self.zxcvbn(data.password,context);
  // Only coarse reason codes leave the worker, never matched password substrings.
  const matches=result.sequence||[];
  let reason='';
  if(result.score<=1){
   if(matches.some(m=>m.pattern==='sequence'||(/^[0-9]{4,}$/.test(m.token||'')&&[...m.token].slice(1).every((c,i)=>Number(c)-Number(m.token[i])===1||Number(c)-Number(m.token[i])===-1))))reason='sequence';
   else if(matches.some(m=>m.pattern==='repeat'))reason='repeat';
   else if(matches.some(m=>m.pattern==='spatial'))reason='spatial';
   else if(matches.some(m=>m.pattern==='date'||m.pattern==='regex'))reason='date';
   else if(matches.some(m=>m.pattern==='dictionary'))reason='dictionary';
   else reason='short';
  }
  self.postMessage({id,score:result.score,reason});
 }catch{self.postMessage({id,score:null});}
};
