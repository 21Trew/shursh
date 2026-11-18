/* Шурш! — browser-side diagnostic. Paste in DevTools on authenticated HTTPS Preview.
 * Only fixed same-origin GETs. Never logs URLs, bodies, cookies, tokens or identities.
 * Client-minus-app is an overhead estimate, NOT a measured network RTT.
 */
(async () => {
  'use strict';
  if (location.protocol !== 'https:') {
    console.error('Run only on an HTTPS Preview.');
    return;
  }
  const paths = ['/api/me', '/api/dashboard'];
  const samplesPerEndpoint = 21; // 1 initial + 20 warm; below API rate limits
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const round = n => Math.round(n * 10) / 10;
  const percentile = (xs, p) => {
    if (!xs.length) return null;
    const sorted = [...xs].sort((a, b) => a - b);
    // Nearest-rank: stable, explicitly documented for small samples.
    return round(sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)]);
  };
  const metric = (header, key) => {
    const item = header.split(',').map(x => x.trim()).find(x => x.startsWith(key + ';'));
    const match = item?.match(/(?:^|;)dur=([0-9.]+)/);
    return match ? Number(match[1]) : null;
  };
  const rows = [];
  for (const path of paths) {
    for (let i = 0; i < samplesPerEndpoint; i++) {
      const start = performance.now();
      try {
        const response = await fetch(path, {
          method: 'GET', credentials: 'same-origin',
          cache: 'no-store', redirect: 'error'
        });
        const headers = performance.now();
        // Read but never parse, print, persist or copy response data.
        await response.arrayBuffer();
        const finish = performance.now();
        const timing = response.headers.get('Server-Timing') || '';
        const app = metric(timing, 'app');
        const sql = metric(timing, 'sql-exec');
        const db = metric(timing, 'db-connect');
        const ttfb = round(headers - start);
        rows.push({
          endpoint: path,
          sample: i + 1,
          status: response.status,
          ttfb_ms: ttfb,
          total_ms: round(finish - start),
          app_ms: app,
          sql_exec_ms: sql,
          db_connect_ms: db,
          client_minus_app_ms: app === null ? null : round(Math.max(0, ttfb - app))
        });
      } catch (error) {
        rows.push({ endpoint: path, sample: i + 1, error: error.name });
      }
      await delay(400);
    }
  }
  const summary = paths.map(endpoint => {
    const ok = rows.filter(row => row.endpoint === endpoint && row.status === 200);
    const warm = ok.filter(row => row.sample > 1);
    const stat = (key, p = 0.5) => warm.length && warm.every(row => typeof row[key] === 'number')
      ? percentile(warm.map(row => row[key]), p) : null;
    return {
      endpoint,
      success: ok.length,
      warm_samples: warm.length,
      first_total_ms: ok[0]?.total_ms ?? null,
      warm_ttfb_p50_ms: stat('ttfb_ms'),
      warm_total_p50_ms: stat('total_ms'),
      warm_total_p95_ms: stat('total_ms', 0.95),
      warm_ttfb_p95_ms: stat('ttfb_ms', 0.95),
      warm_app_p50_ms: stat('app_ms'),
      warm_sql_p50_ms: stat('sql_exec_ms'),
      warm_sql_p95_ms: stat('sql_exec_ms', 0.95),
      warm_db_checkout_p50_ms: stat('db_connect_ms'),
      warm_overhead_p50_ms: stat('client_minus_app_ms'),
      warm_overhead_p95_ms: stat('client_minus_app_ms', 0.95)
    };
  });
  console.log('SHURSH — anonymized timing (ms); first is not proven cold start');
  console.table(summary);
  console.table(rows);
  console.info('client_minus_app includes network + Vercel edge, queue and routing; it is NOT network RTT.');
})();
