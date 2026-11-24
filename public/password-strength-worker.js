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
  self.postMessage({id,score:result.score});
 }catch{self.postMessage({id,score:null});}
};
