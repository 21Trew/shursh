/**
 * Anonymous connectivity probe for Russian ISP / mobile-network diagnostics.
 * Run from a Russian network WITHOUT VPN: node tools/ru-network-probe.mjs
 * Emits only status/timing/errors, never cookies, secrets or response bodies.
 */
import { lookup } from 'node:dns/promises';
import { performance } from 'node:perf_hooks';

const targets = [
  ['site', 'https://shursh.fun/'],
  ['script', 'https://shursh.fun/app.js'],
  ['style', 'https://shursh.fun/polish.css'],
  ['anonymous-api', 'https://shursh.fun/api/me'],
  ['vercel-fallback', 'https://shursh.vercel.app/'],
  ['google-fonts-css', 'https://fonts.googleapis.com/css2?family=Onest:wght@400;700&display=swap'],
];
const samples = 3;
const timeoutMs = 12000;
const maxBodyBytes = 1024 * 1024;
const result = [];

for (const [name, url] of targets) {
  const host = new URL(url).hostname;
  let dns;
  try {
    const start = performance.now();
    const addresses = await lookup(host, { all: true });
    dns = { ms: Math.round(performance.now() - start),
      addresses: addresses.map(a => a.address) };
  } catch (error) {
    dns = { error: error.code || error.name };
  }
  for (let attempt = 1; attempt <= samples; attempt++) {
    const start = performance.now();
    let firstByteMs = null;
    let bytes = 0;
    const row = { name, attempt, host, dns };
    try {
      const response = await fetch(url, {
        method: 'GET',
        redirect: 'manual',
        cache: 'no-store',
        credentials: 'omit',
        signal: AbortSignal.timeout(timeoutMs),
      });
      firstByteMs = Math.round(performance.now() - start);
      const reader = response.body?.getReader();
      if (reader) {
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            bytes += value?.byteLength || 0;
            if (bytes >= maxBodyBytes) break;
          }
        } finally {
          await reader.cancel().catch(() => {});
        }
      }
      row.status = response.status;
      row.ttfbMs = firstByteMs;
      row.totalMs = Math.round(performance.now() - start);
      row.bytes = bytes;
    } catch (error) {
      row.error = error?.cause?.code || error?.code || error?.name || 'network-error';
      row.elapsedMs = Math.round(performance.now() - start);
      if (firstByteMs !== null) row.ttfbMs = firstByteMs;
    }
    result.push(row);
  }
}
console.log(JSON.stringify({ timestamp: new Date().toISOString(),
  node: process.version, samples, timeoutMs, results: result }, null, 2));
