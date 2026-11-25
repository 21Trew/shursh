import {validateIntent,validateWorkflow} from './release-control.mjs';
import {main} from './publish-production.mjs';
try {
 const args=validateIntent(process.env);
 validateWorkflow(process.env,{apply:args.includes('--apply')});
 await main(args);
}catch(error){
 console.error(error instanceof Error?error.message:'Release failed');
 process.exitCode=1;
}
