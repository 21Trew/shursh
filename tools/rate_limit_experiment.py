"""Disposable CI-only rate limiter transport experiment; not application code."""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import tempfile
import threading
import time

import psycopg
from psycopg import ClientCursor
from psycopg.pq import TransactionStatus
from cloud import db
from cloud.backend import RATE_LIMIT_SQL, consume_rate_limit

BASE = 'febf3a436d9694cf65fec5730bd5bb2bfe5f7b33'
SQL = RATE_LIMIT_SQL.replace('?', '%s')
SETTINGS = tuple(s.strip() for s in db._TX_SETTINGS.split(';') if s.strip())
IDLE = TransactionStatus.IDLE
DB_NAME = 'shursh_rate_bench'
WORKLOADS = ('allowed_hot', 'allowed_distinct', 'mixed_hot', 'rejected_hot')

def connect(admin=False):
    # No DSN, service file, application credentials or remote host allowed.
    if os.environ.get('CI') != 'true' or os.environ.get('SHURSH_BENCH_DISPOSABLE') != 'yes':
        raise RuntimeError('Only the disposable CI database is supported')
    c = psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
                        dbname=DB_NAME, user='postgres' if admin else 'bench_login',
                        password='ci-bench-only', sslmode='disable', gssencmode='disable',
                        connect_timeout=5, autocommit=True, prepare_threshold=None,
                        options='-c search_path=public', application_name='shursh-rate-bench')
    try:
        name, version = c.execute("SELECT current_database(), current_setting('server_version_num')").fetchone()
        assert name == DB_NAME and 170000 <= int(version) < 180000
        return c
    except BaseException:
        c.close()
        raise

def init(c):
    # Deliberately fail on an existing fixture. No destructive reset or migrations.
    c.execute("""
        CREATE ROLE shursh_backend NOLOGIN NOINHERIT;
        CREATE ROLE bench_login LOGIN NOINHERIT PASSWORD 'ci-bench-only';
        CREATE ROLE anon NOLOGIN;
        CREATE ROLE authenticated NOLOGIN;
        GRANT shursh_backend TO bench_login;
        GRANT USAGE ON SCHEMA public TO shursh_backend;
        CREATE TABLE public.app_rate_limits (
          key_hash text PRIMARY KEY CHECK (key_hash ~ '^[0-9a-f]{64}$'),
          bucket bigint NOT NULL, hits integer NOT NULL CHECK(hits > 0)
        );
        CREATE INDEX app_rate_limits_bucket_idx ON public.app_rate_limits(bucket);
        ALTER TABLE public.app_rate_limits ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.app_rate_limits FROM PUBLIC, anon, authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.app_rate_limits TO shursh_backend;
        CREATE POLICY shursh_backend_only ON public.app_rate_limits
          FOR ALL TO shursh_backend USING (true) WITH CHECK (true);
        CREATE TABLE public.bench_business(id integer PRIMARY KEY);
        GRANT SELECT, INSERT ON public.bench_business TO shursh_backend;
    """)
    # Only for a deterministic COMMIT failure gate, removed before timing.
    c.execute("""
        CREATE FUNCTION public.bench_commit_failure() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'intentional deferred commit failure' USING ERRCODE='23514';
          END $$;
        CREATE CONSTRAINT TRIGGER bench_commit_failure
          AFTER INSERT OR UPDATE ON public.app_rate_limits
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
          WHEN (NEW.key_hash = repeat('f',64))
          EXECUTE FUNCTION public.bench_commit_failure();
    """)

def check_input(limit):
    if limit < 1:
        raise ValueError('Rate limit must be positive')

def baseline(c, key, bucket, limit):
    # Exact current transaction body, excluding pool checkout and Staging marker.
    with c.transaction():
        db._timed_execute(c, db._TX_SETTINGS, statement_count=3)
        allowed = consume_rate_limit(db.DB(c), key, bucket, limit)
    return allowed

def pipeline(c, key, bucket, limit):
    check_input(limit)
    # Conservative candidate: retain psycopg's BEGIN/COMMIT and rollback
    # context; pipeline only settings + parameterized UPSERT.
    with c.transaction():
        with c.pipeline():
            for statement in SETTINGS:
                c.execute(statement)
            cur = c.execute(SQL, (key, bucket, limit))
        allowed = cur.fetchone() is not None
    return allowed

def batch(c, key, bucket, limit):
    check_input(limit)
    # ClientCursor performs safe adaptation/quoting. Never interpolate keys.
    # COMMIT result must be received successfully before returning a verdict.
    try:
        with ClientCursor(c) as cur:
            cur.execute('; '.join(('BEGIN', *SETTINGS, SQL, 'COMMIT')),
                        (key, bucket, limit), prepare=False)
            for _ in range(1 + len(SETTINGS)):
                if not cur.nextset():
                    raise RuntimeError('Missing UPSERT result')
            allowed = cur.fetchone() is not None
            if not cur.nextset() or cur.statusmessage != 'COMMIT' or cur.nextset():
                raise RuntimeError('Missing successful COMMIT')
            if c.info.transaction_status != IDLE:
                raise RuntimeError('Transaction not idle after COMMIT')
            return allowed
    except BaseException:
        if c.info.transaction_status != IDLE:
            try:
                c.execute('ROLLBACK')
            except Exception:
                c.close()
        raise

VARIANTS = {'production': baseline, 'pipeline': pipeline, 'sql_batch': batch}

def key_for(*parts):
    return hashlib.sha256(':'.join(map(str, parts)).encode()).hexdigest()

def state(c, key):
    return c.execute('SELECT bucket,hits,ctid::text FROM public.app_rate_limits WHERE key_hash=%s',
                     (key,)).fetchone()

def session(c):
    assert c.info.transaction_status == IDLE
    return c.execute("SELECT current_user, current_setting('statement_timeout'), current_setting('lock_timeout')").fetchone()

def must_fail(fn, errors):
    try:
        fn()
    except errors:
        return
    raise AssertionError('Expected operation to fail closed')

def semantic_gates(admin, profile):
    results = {}
    for name, fn in VARIANTS.items():
        key = key_for(profile, name, 'security')
        with connect() as c:
            initial = session(c)
            assert initial[0] == 'bench_login'
            must_fail(lambda: c.execute(SQL, (key, 100, 2)), psycopg.errors.InsufficientPrivilege)
            assert fn(c, key, 100, 2) and fn(c, key, 100, 2)
            before = state(admin, key)
            assert not fn(c, key, 100, 2) and state(admin, key) == before
            assert fn(c, key, 101, 2) and state(admin, key)[:2] == (101, 1)
            assert not fn(c, key, 100, 2) and state(admin, key)[:2] == (101, 1)
            assert session(c) == initial
            must_fail(lambda: fn(c, key, 101, 0), ValueError)
            # Hostile-shaped input must be bound, not executed.
            must_fail(lambda: fn(c, "x'); SELECT 1; --", 101, 2), psycopg.Error)
            assert session(c) == initial and state(admin, key)[:2] == (101, 1)
            must_fail(lambda: fn(c, 'f'*64, 101, 2), psycopg.Error)
            assert state(admin, 'f'*64) is None and session(c) == initial
            assert fn(c, key, 101, 2) and state(admin, key)[:2] == (101, 2)
            # Revoke the scoped role's insert privilege: no superuser fallback.
            denied_key = key_for(profile, name, 'denied')
            admin.execute('REVOKE INSERT ON public.app_rate_limits FROM shursh_backend')
            try:
                must_fail(lambda: fn(c, denied_key, 100, 2), psycopg.errors.InsufficientPrivilege)
                assert state(admin, denied_key) is None and session(c) == initial
            finally:
                admin.execute('GRANT INSERT ON public.app_rate_limits TO shursh_backend')
            assert fn(c, denied_key, 100, 2)
            # The independent committed quota must survive business rollback.
            independent = key_for(profile, name, 'rollback')
            with connect() as business:
                business.execute('BEGIN')
                business.execute(db._TX_SETTINGS)
                business.execute('INSERT INTO bench_business VALUES(1)')
                assert fn(c, independent, 100, 1)
                business.execute('ROLLBACK')
            assert admin.execute('SELECT count(*) FROM bench_business').fetchone()[0] == 0
            assert not fn(c, independent, 100, 1)
        # Separate sockets contend for the same key; no local quota cache.
        contested = key_for(profile, name, 'contended')
        barrier = threading.Barrier(8, timeout=30)
        def contender(i):
            with connect() as c:
                barrier.wait()
                return sum(fn(c, contested, 100, 17) for _ in range(12))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            total = sum(pool.map(contender, range(8)))
        assert total == 17 and state(admin, contested)[:2] == (100, 17)
        results[name] = {'saturation': True, 'rollover': True, 'older_bucket_denied': True,
                         'role_timeout_restored': True, 'invalid_input_bound': True,
                         'commit_failure_closed': True, 'role_denied_closed': True,
                         'independent_commit': True, 'concurrent_attempts': 96,
                         'concurrent_allowed': total}
    for role in ('anon', 'authenticated'):
        def forbidden():
            with admin.transaction():
                admin.execute('SET LOCAL ROLE ' + role)
                admin.execute('SELECT * FROM app_rate_limits LIMIT 1')
        must_fail(forbidden, psycopg.errors.InsufficientPrivilege)
    for result in results.values():
        result['anon_authenticated_denied'] = True
    return results

def quantiles(samples):
    s = sorted(samples)
    return {'p50_ms': statistics.median(s),
            'p95_ms': s[math.ceil(.95*len(s))-1],
            'p99_ms': s[math.ceil(.99*len(s))-1]}

def protocol_counts(name, fn, profile):
    # Trace only synthetic SQL on an established connection. No raw trace saved.
    with connect() as c, tempfile.TemporaryFile() as f:
        c.pgconn.trace(f.fileno())
        try:
            assert fn(c, key_for(profile, name, 'trace'), 100, 10)
        finally:
            c.pgconn.untrace()
        f.seek(0)
        trace = f.read().decode('utf-8', errors='replace')
    counts = {tag: len(re.findall(r'\b' + direction + r'\s+\d+\s+' + tag + r'\b', trace))
              for direction, tag in [('F','Query'),('F','Sync'),('F','Flush'),('B','ReadyForQuery')]}
    assert counts['ReadyForQuery'] >= 1, ('Unexpected libpq trace format', name, counts)
    return counts

def measure(admin, args):
    rng = random.Random(574)
    raw = []
    n = args.requests
    limit = n + 1
    bucket = 1000
    workloads = WORKLOADS if args.profile == 'local' else WORKLOADS[:2]
    for workers in (1, 4, 8):
        connections = [connect() for _ in range(workers)]
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                for rep in range(args.repeats):
                    order = list(workloads)
                    rng.shuffle(order)
                    for workload in order:
                        names = list(VARIANTS)
                        rng.shuffle(names)
                        for name in names:
                            fn = VARIANTS[name]
                            prefix = (args.profile, workers, rep, workload, name)
                            # Warm same connections before each timed run, outside wall clock.
                            for i,c in enumerate(connections):
                                assert fn(c,key_for(*prefix,'warm',i),bucket,limit)
                            keys = ([key_for(*prefix,i) for i in range(n)] if workload=='allowed_distinct'
                                    else [key_for(*prefix,'hot')]*n)
                            initial = (limit-n//2 if workload=='mixed_hot' else
                                       limit if workload=='rejected_hot' else 0)
                            if initial:
                                admin.execute('INSERT INTO app_rate_limits VALUES(%s,%s,%s)',
                                              (keys[0],bucket,initial))
                            barrier = threading.Barrier(workers, timeout=30)
                            def worker(i):
                                c = connections[i]
                                barrier.wait()
                                result = []
                                for key in keys[i::workers]:
                                    start = time.perf_counter_ns()
                                    allowed = fn(c,key,bucket,limit)
                                    result.append((allowed,(time.perf_counter_ns()-start)/1e6))
                                assert c.info.transaction_status == IDLE
                                return result
                            start = time.perf_counter_ns()
                            results = [v for chunk in pool.map(worker,range(workers)) for v in chunk]
                            wall = (time.perf_counter_ns()-start)/1e9
                            expected = n//2 if workload=='mixed_hot' else 0 if workload=='rejected_hot' else n
                            assert len(results)==n and sum(v[0] for v in results)==expected
                            if workload=='allowed_distinct':
                                rows=admin.execute('SELECT bucket,hits FROM app_rate_limits WHERE key_hash=ANY(%s)',(keys,)).fetchall()
                                assert len(rows)==n and all(row==(bucket,1) for row in rows)
                            else:
                                assert state(admin,keys[0])[:2]==(bucket,initial+expected)
                            samples=[v[1] for v in results]
                            raw.append({'variant':name,'workload':workload,'workers':workers,
                                        'repeat':rep+1,'requests':n,'allowed':expected,
                                        'wall_s':wall,'throughput_rps':n/wall,
                                        **quantiles(samples),'samples_ms':samples})
        finally:
            for c in connections: c.close()
    summary=[]
    for workers in (1,4,8):
        for workload in workloads:
            for name in VARIANTS:
                rows=[r for r in raw if (r['workers'],r['workload'],r['variant'])==(workers,workload,name)]
                fields=('p50_ms','p95_ms','p99_ms','throughput_rps')
                summary.append({'workers':workers,'workload':workload,'variant':name,
                                'repeats':len(rows),'requests':sum(r['requests'] for r in rows),
                                **{k:round(statistics.median(r[k] for r in rows),4) for k in fields},
                                'p95_min_ms':round(min(r['p95_ms'] for r in rows),4),
                                'p95_max_ms':round(max(r['p95_ms'] for r in rows),4)})
    return raw,summary

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',choices=('local','netem'),required=True)
    parser.add_argument('--requests',type=int,default=120)
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert 100<=args.requests<=1000 and 3<=args.repeats<=10 and args.requests%8==0
    with connect(admin=True) as admin:
        if args.profile=='local':
            init(admin)
        else:
            # Local profile created the disposable fixture, no schema reset.
            assert admin.execute("SELECT to_regclass('public.app_rate_limits') IS NOT NULL").fetchone()[0]
            admin.execute("ALTER TABLE app_rate_limits ENABLE TRIGGER bench_commit_failure")
        gates=semantic_gates(admin,args.profile)
        admin.execute("ALTER TABLE app_rate_limits DISABLE TRIGGER bench_commit_failure")
        protocol={name:protocol_counts(name,fn,args.profile) for name,fn in VARIANTS.items()}
        with connect() as c:
            rtt=[]
            for _ in range(30):
                start=time.perf_counter_ns()
                c.execute('SELECT 1').fetchone()
                rtt.append((time.perf_counter_ns()-start)/1e6)
        raw,summary=measure(admin,args)
        report={'base':BASE,'profile':args.profile,'server_version':admin.execute('SHOW server_version').fetchone()[0],
                'psycopg':psycopg.__version__,'python':__import__('sys').version.split()[0],
                'libpq':psycopg.pq.version(),'requests':sum(r['requests'] for r in raw),
                'select1_rtt_ms':quantiles(rtt),'protocol':protocol,'security':gates,
                'summary':summary,'runs':raw,
                'scope':'warm direct TCP connections, no pool checkout or HTTP, no Supavisor or Staging marker; median per-repeat statistics'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('RATE_BENCH='+json.dumps({k:v for k,v in report.items() if k!='runs'},separators=(',',':')),flush=True)

if __name__=='__main__':
    main()
