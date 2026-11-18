/* Шурш! — manual, same-origin diagnostic for an authenticated HTTPS Preview.
 * No payloads, cookies, credentials, resource names, hosts, or dynamic URLs are logged.
 * Browser Resource Timing is not a pure network RTT or Vercel-edge measurement.
 */
(async () => {
  'use strict';
  if (location.protocol !== 'https:') {
    console.error('Run only on an HTTPS Preview.');
    return;
  }
  const paths = ['/api/me', '/api/dashboard'];
  const samplesPerEndpoint = 21; // 1 initial + 20 warm; read-only, below API rate limits
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const round = n => Math.round(n * 10) / 10;
  const percentile = (xs, p) => {
    if (!xs.length) return null;
    const sorted = [...xs].sort((a, b) => a - b);
    return round(sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)]);
  };
  const metric = (header, key) => {
    const item = header.split(',').map(x => x.trim()).find(x => x.startsWith(key + ';'));
    const match = item?.match(/(?:^|;)dur=([0-9.]+)/);
    return match ? Number(match[1]) : null;
  };
  const elapsed = (end, begin) =>
    Number.isFinite(end) && Number.isFinite(begin) && end >= begin
      ? round(end - begin) : null;

  // Resource Timing entries contain the full URL. Use names ONLY internally to
  // match our fixed endpoints; never print entries or their name/redirect fields.
  const resourcePhases = (path, start, finish, app) => {
    const target = new URL(path, location.origin).href;
    const entries = performance.getEntriesByName(target, 'resource')
      .filter(e => e.initiatorType === 'fetch' &&
        e.startTime >= start - 2 && e.startTime <= finish + 2 && e.responseEnd > 0)
      .sort((a, b) => Math.abs(a.startTime - start) - Math.abs(b.startTime - start));
    const e = entries[0];
    if (!e || !(e.requestStart > 0 && e.responseStart > 0)) {
      return { resource_timing: false };
    }
    const wait = elapsed(e.responseStart, e.requestStart);
    const tlsStart = e.secureConnectionStart > 0 ? e.secureConnectionStart : null;
    const tcpEnd = tlsStart !== null && tlsStart >= e.connectStart
      ? tlsStart : e.connectEnd;
    return {
      resource_timing: true,
      // Offsets relative to this resource's start, NOT absolute timestamps.
      request_start_offset_ms: elapsed(e.requestStart, e.startTime),
      response_start_offset_ms: elapsed(e.responseStart, e.startTime),
      resource_ttfb_ms: elapsed(e.responseStart, e.startTime),
      pre_request_ms: elapsed(e.requestStart, e.startTime),
      dns_ms: elapsed(e.domainLookupEnd, e.domainLookupStart),
      tcp_ms: elapsed(tcpEnd, e.connectStart),
      tls_ms: tlsStart !== null ? elapsed(e.connectEnd, tlsStart) : null,
      response_wait_ms: wait,
      response_wait_minus_app_ms: wait !== null && app !== null
        ? round(wait - app) : null,
      download_ms: elapsed(e.responseEnd, e.responseStart)
    };
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
        // Read, but never parse, print, persist, or copy private response data.
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
          browser_ttfb_ms: ttfb,
          full_ms: round(finish - start),
          app_ms: app,
          sql_exec_ms: sql,
          db_connect_ms: db,
          client_minus_app_ms: app === null ? null : round(ttfb - app),
          ...resourcePhases(path, start, finish, app)
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
    const stat = (key, p = 0.5) => {
      const xs = warm.map(row => row[key]).filter(Number.isFinite);
      return percentile(xs, p);
    };
    return {
      endpoint,
      successful: ok.length,
      warm_samples: warm.length,
      resource_samples: warm.filter(row => row.resource_timing).length,
      first_full_ms: ok[0]?.full_ms ?? null,
      ttfb_p50_ms: stat('browser_ttfb_ms'),
      ttfb_p95_ms: stat('browser_ttfb_ms', 0.95),
      full_p50_ms: stat('full_ms'),
      full_p95_ms: stat('full_ms', 0.95),
      app_p50_ms: stat('app_ms'),
      app_p95_ms: stat('app_ms', 0.95),
      sql_p50_ms: stat('sql_exec_ms'),
      sql_p95_ms: stat('sql_exec_ms', 0.95),
      db_checkout_p50_ms: stat('db_connect_ms'),
      db_checkout_p95_ms: stat('db_connect_ms', 0.95),
      overhead_p50_ms: stat('client_minus_app_ms'),
      overhead_p95_ms: stat('client_minus_app_ms', 0.95),
      resource_ttfb_p50_ms: stat('resource_ttfb_ms'),
      resource_ttfb_p95_ms: stat('resource_ttfb_ms', 0.95),
      pre_request_p50_ms: stat('pre_request_ms'),
      pre_request_p95_ms: stat('pre_request_ms', 0.95),
      dns_p95_ms: stat('dns_ms', 0.95),
      tcp_p95_ms: stat('tcp_ms', 0.95),
      tls_p95_ms: stat('tls_ms', 0.95),
      response_wait_p50_ms: stat('response_wait_ms'),
      response_wait_p95_ms: stat('response_wait_ms', 0.95),
      wait_minus_app_p50_ms: stat('response_wait_minus_app_ms'),
      wait_minus_app_p95_ms: stat('response_wait_minus_app_ms', 0.95)
    };
  });
  console.log('SHURSH — anonymized HTTPS Preview timings (ms); first is not proven cold start');
  console.table(summary);
  console.table(rows);
  console.info('pre_request includes connection setup and browser scheduling; response_wait includes network + Vercel + Flask; wait_minus_app is NOT pure RTT. DNS/TCP=0 may mean reuse/cache; TLS=null means not separately observed. Resource metrics exclude unmatched entries.');
})();
