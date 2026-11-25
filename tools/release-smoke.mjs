/**
 * Anonymous, read-only smoke check for an approved Shursh release
 * This does not sign up users, create data, or use authentication credentials
 * Never print response bodies, cookie values, request URLs, or provider tokens
 *
 * Run only AFTER an authorized deploy: node tools/release-smoke.mjs
 */
import { createHash } from 'node:crypto';
const ORIGINS = ['https://shursh.fun', 'https://shursh.vercel.app'];
const ASSETS = ['app.js','santa-ui.js','social-ui.js','styles.css','polish.css','fonts.css'];
let ORIGIN = ORIGINS[0];
const path = name => new URL(name, ORIGIN);

async function get(name) {
  const resource = path(name);
  if (resource.origin !== ORIGIN || resource.hash || (resource.search && !(ASSETS.includes(resource.pathname.slice(1)) && /^\?v=[a-f0-9]{20}$/.test(resource.search)))) {
    throw new Error('Unsafe smoke target');
  }
  const response = await fetch(resource, {
    method: 'GET',
    redirect: 'manual',
    cache: 'no-store',
    signal: AbortSignal.timeout(15000)
  });
  return {
    status: response.status,
    type: response.headers.get('content-type') || '',
    cache: response.headers.get('cache-control') || '',
    frame: response.headers.get('x-frame-options') || '',
    csp: response.headers.get('content-security-policy') || '',
    version: response.headers.get('x-shursh-ui-version') || '',
    body: await response.text()
  };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function run() {
  const home = await get('/');
  console.log('PUBLIC_SMOKE_META', JSON.stringify({ status: home.status, type: home.type.split(';')[0], xFrame: home.frame || '(absent)', cspPresent: Boolean(home.csp), cache: home.cache || '(absent)', htmlLength: home.body.length }));
  const anonymousMe = await get('/api/me');
  console.log('PUBLIC_SMOKE_API_META', JSON.stringify({status: anonymousMe.status, type: anonymousMe.type.split(';')[0], cache: anonymousMe.cache || '(absent)' }));
  assert(home.status === 200, 'Homepage must return 200');
  assert(home.type.includes('text/html'), 'Homepage must return HTML');
  assert(home.body.includes('Шурш!'), 'Homepage must contain product title');
  assert(home.frame.toUpperCase() === 'DENY', 'Homepage must block framing');
  assert(home.csp.includes("default-src 'self'"), 'Homepage needs a CSP');

  assert(/^[a-f0-9]{20}$/.test(home.version), 'Homepage must identify the UI version');
  const hashes = {};
  for (const asset of ASSETS) {
    const url = '/'+asset+'?v='+home.version;
    assert(home.body.includes('"'+url+'"'), 'HTML must reference versioned assets');
    const result = await get(url);
    assert(result.status === 200 && result.version === home.version, 'Versioned UI asset must match homepage');
    assert(result.type.includes(asset.endsWith('.js')?'javascript':'text/css'), 'Incorrect asset content type');
    hashes[asset] = createHash('sha256').update(result.body).digest('hex');
    if (asset === 'app.js') assert(result.body.includes("state.base+'/reveal'"), 'Santa reveal must use role-aware context');
  }

  const me = anonymousMe;
  assert(me.status === 200 && me.type.includes('application/json'),
    'Anonymous /api/me must return JSON 200');
  assert(me.cache.toLowerCase().includes('no-store'),
    'Session endpoint must not be cached');
  let user;
  try { user = JSON.parse(me.body); } catch { throw new Error('Invalid /api/me JSON'); }
  assert(user.user === null && user.demo === false,
    'Anonymous /api/me must not expose a user or demo mode');

  const dashboard = await get('/api/dashboard');
  assert(dashboard.status === 200 && dashboard.type.includes('application/json'),
    'Anonymous dashboard must return JSON 200');
  assert(dashboard.cache.toLowerCase().includes('no-store'),
    'Dashboard must not be cached');
  let state;
  try { state = JSON.parse(dashboard.body); }
  catch { throw new Error('Invalid dashboard JSON'); }
  assert(state.user === null && state.demo === false &&
    Array.isArray(state.lists) && state.lists.length === 0 &&
    Array.isArray(state.events) && state.events.length === 0,
    'Anonymous dashboard must contain no private user data');

  const missing = await get('/this-page-does-not-exist');
  assert(missing.status === 404, 'Unknown application path must return 404');

  console.log('SHURSH PUBLIC ANONYMOUS SMOKE: PASS');
  console.log('Checked homepage, assets, headers, no-session API and unknown route');
  console.log('Manual authenticated signup, email redirect and guest-flow checks are still required');
  return { version:home.version, hashes };
}

async function runAll() {
  let first;
  for (const origin of ORIGINS) {
    ORIGIN=origin;
    const result=await run();
    if (!first) first=result;
    else assert(JSON.stringify(first)===JSON.stringify(result), 'Production domains serve different UI builds');
  }
  console.log('SHURSH PRODUCTION DOMAIN PARITY: PASS');
}
runAll().catch(error => {
  // Error messages are authored strings only; never output request URLs or response bodies
  console.error('SHURSH PUBLIC ANONYMOUS SMOKE: FAIL');
  console.error(error instanceof Error ? error.message : 'Unexpected smoke failure');
  process.exitCode = 1;
});
