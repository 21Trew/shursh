"""CI-only Supavisor transaction-mode verification, no remote connections."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import time
import traceback
from types import SimpleNamespace

import psycopg
from tools import rate_limit_experiment as exp

DIRECT = exp.connect
VARIANTS = {'production': exp.baseline, 'sql_batch': exp.batch}
POOL_PORT = 6543
POOL_SIZE = 4
# Supavisor v2.9.5 TenantSupervisor.pool_spec uses size=1 (warm worker)
# and max_overflow=pool_size for normal users, i.e. 1 + 4 workers.
# https://github.com/supabase/supavisor/blob/v2.9.5/lib/supavisor/tenant_supervisor.ex
POOL_WARM_SIZE = 1
POOL_MAX_WORKERS = POOL_SIZE + POOL_WARM_SIZE

def guard():
    if os.environ.get('CI') != 'true' or os.environ.get('SHURSH_BENCH_DISPOSABLE') != 'yes':
        raise RuntimeError('Disposable local CI only')

def pooled(admin=False):
    if admin:
        return DIRECT(admin=True)
    guard()
    c = psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=POOL_PORT,
                        dbname=exp.DB_NAME, user='bench_login.ratebench',
                        password='ci-bench-only', sslmode='disable', gssencmode='disable',
                        connect_timeout=5, autocommit=True, prepare_threshold=None,
                        application_name='shursh-rate-bench')
    try:
        name, version = c.execute("SELECT current_database(), current_setting('server_version_num')").fetchone()
        assert name == exp.DB_NAME and 170000 <= int(version) < 180000
        return c
    except BaseException:
        c.close()
        raise

def setup():
    guard()
    with DIRECT(admin=True) as c:
        exp.init(c)
        c.execute('CREATE DATABASE supavisor_metadata')
        # Local test fixture only, for the actual 10s production statement timeout.
        c.execute("""
            CREATE FUNCTION public.bench_slow_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              PERFORM pg_sleep(12);
              RETURN NEW;
            END $$;
            CREATE TRIGGER bench_slow_insert BEFORE INSERT ON app_rate_limits
            FOR EACH ROW WHEN (NEW.key_hash = repeat('e',64))
            EXECUTE FUNCTION public.bench_slow_insert();
        """)

def ready():
    deadline = time.monotonic() + 90
    while True:
        try:
            with pooled() as c:
                assert exp.session(c)[0] == 'bench_login'
                print('POOL_READY', flush=True)
                return
        except (psycopg.Error, AssertionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

def wait_locked(admin, deadline=5):
    until = time.monotonic()+deadline
    while time.monotonic()<until:
        rows = admin.execute("""
            SELECT pid FROM pg_stat_activity
            WHERE datname=current_database() AND usename='bench_login'
              AND wait_event_type='Lock' AND query LIKE '%INSERT INTO app_rate_limits%'
        """).fetchall()
        if len(rows)==1:
            return rows[0][0]
        time.sleep(.025)
    raise AssertionError('Expected rate limiter to be blocked on a row lock')

def idle_and_safe(c, initial, fn, prefix):
    if c.closed:
        with pooled() as fresh:
            assert exp.session(fresh)==initial
            assert fn(fresh, exp.key_for(prefix,'reconnect'), 100, 1)
        return 'reconnected'
    assert exp.session(c)==initial
    assert fn(c, exp.key_for(prefix,'reused'),100,1)
    return 'same_client'

def faults(admin, name, fn):
    results={}
    # Real statement_timeout: the test trigger sleeps longer than the 10s limit.
    with pooled() as c:
        initial=exp.session(c)
        start=time.monotonic()
        exp.must_fail(lambda: fn(c,'e'*64,100,2), psycopg.errors.QueryCanceled)
        elapsed=time.monotonic()-start
        assert 9 <= elapsed <= 15, elapsed
        assert exp.state(admin,'e'*64) is None
        results['statement_timeout']={'seconds':elapsed,'recovery':idle_and_safe(c,initial,fn,name+'-statement')}
    # Real lock_timeout, frontend cancellation, upstream loss, client TCP loss.
    for scenario in ('lock_timeout','cancel','upstream_disconnect','client_disconnect'):
        key=exp.key_for(name,scenario)
        admin.execute('INSERT INTO app_rate_limits VALUES(%s,100,1)',(key,))
        with DIRECT(admin=True) as blocker, pooled() as c:
            initial=exp.session(c)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                with blocker.transaction():
                    blocker.execute('SELECT hits FROM app_rate_limits WHERE key_hash=%s FOR UPDATE',(key,)).fetchone()
                    def run():
                        start=time.monotonic()
                        try:
                            result=fn(c,key,100,2)
                        except (psycopg.Error, RuntimeError) as exc:
                            return {'error':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None),
                                    'seconds':time.monotonic()-start}
                        raise AssertionError(('Fault returned quota verdict',scenario,result))
                    future=pool.submit(run)
                    pid=wait_locked(admin)
                    if scenario=='cancel':
                        c.cancel_safe(timeout=3)
                    elif scenario=='upstream_disconnect':
                        assert admin.execute('SELECT pg_terminate_backend(%s)',(pid,)).fetchone()[0]
                    elif scenario=='client_disconnect':
                        # Shutdown the real client TCP stream while UPSERT is blocked.
                        # Duplicate the descriptor: libpq retains ownership of its fd.
                        with socket.socket(fileno=os.dup(c.pgconn.socket)) as sock:
                            sock.shutdown(socket.SHUT_RDWR)
                    result=future.result(timeout=18)
                    assert exp.state(admin,key)[:2]==(100,1)
                    if scenario=='lock_timeout':
                        assert result['sqlstate']=='55P03' and 7<=result['seconds']<=13,result
                    elif scenario=='cancel':
                        assert result['sqlstate']=='57014' and result['seconds']<7,result
                    elif scenario=='client_disconnect':
                        assert result['seconds']<7,result
                    # A dropped client might have an ambiguous outcome. Wait for
                    # the original backend to stop executing before unlocking.
                    if scenario=='client_disconnect':
                        deadline=time.monotonic()+12
                        while admin.execute("""
                            SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                              WHERE pid=%s AND state='active'
                                AND query LIKE '%%INSERT INTO app_rate_limits%%')
                        """,(pid,)).fetchone()[0]:
                            assert time.monotonic()<deadline,'Orphaned query still running'
                            time.sleep(.05)
                    assert exp.state(admin,key)[:2]==(100,1)
                assert exp.state(admin,key)[:2]==(100,1)
                if scenario in ('upstream_disconnect','client_disconnect'):
                    c.close()
                result['recovery']=idle_and_safe(c,initial,fn,name+'-'+scenario)
                results[scenario]=result
    return results

def reuse(admin, name, fn):
    clients=[pooled() for _ in range(8)]
    try:
        expected=exp.session(clients[0])
        def worker(i):
            c=clients[i]
            pids=[]
            for j in range(12):
                assert fn(c,exp.key_for(name,'reuse',i,j),100,1)
                assert exp.session(c)==expected
                pids.append(c.execute('SELECT pg_backend_pid()').fetchone()[0])
            return pids
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pids=[p for row in pool.map(worker,range(8)) for p in row]
        distinct=len(set(pids))
        assert 1<=distinct<=POOL_MAX_WORKERS,(distinct,pids)
        assert distinct<len(clients), (distinct, len(clients))
        assert all(exp.session(c)==expected for c in clients)
        return {'client_connections':8,'backend_pids_observed':distinct,
                'successful_transactions':96,'role_timeout_restored':True,
                'configured_overflow_workers':POOL_SIZE,'warm_workers':POOL_WARM_SIZE,
                'max_pool_workers':POOL_MAX_WORKERS}
    finally:
        for c in clients: c.close()

def save(path, report):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--setup',action='store_true')
    parser.add_argument('--ready',action='store_true')
    parser.add_argument('--profile',choices=('local','netem'),default='local')
    parser.add_argument('--output',type=Path,default=Path('artifacts/rate-pooler/local.json'))
    args=parser.parse_args()
    guard()
    if args.setup:
        setup()
        return
    if args.ready:
        ready()
        return
    # Reuse the exact direct experiment workload and quota assertions, only
    # replace its local client transport and candidate selection in this process.
    exp.connect=pooled
    report={'base':exp.BASE,'supavisor_image':'supabase/supavisor:2.9.5',
            'pool_mode':'transaction','configured_pool_size':POOL_SIZE,
            'warm_pool_workers':POOL_WARM_SIZE,'max_pool_workers':POOL_MAX_WORKERS,
            'profile':args.profile,'security':{},'faults':{},'reuse':{},
            'protocol':{},'failures':{},'scope':'warm local TCP through Supavisor; not hosted pooler or HTTP'}
    with DIRECT(admin=True) as admin:
        report['server_version']=admin.execute('SHOW server_version').fetchone()[0]
        report['psycopg']=psycopg.__version__
        admin.execute('ALTER TABLE app_rate_limits ENABLE TRIGGER bench_commit_failure')
        for name,fn in VARIANTS.items():
            try:
                exp.VARIANTS={name:fn}
                report['security'].update(exp.semantic_gates(admin,'pooler-'+args.profile))
                report['protocol'][name]=exp.protocol_counts(name,fn,'pooler-'+args.profile)
                report['reuse'][name]=reuse(admin,'pooler-'+args.profile+'-'+name,fn)
                if args.profile=='local':
                    report['faults'][name]=faults(admin,name,fn)
                print('PASS',name,args.profile,flush=True)
            except Exception as exc:
                report['failures'][name]={'type':type(exc).__name__,'message':str(exc)}
                traceback.print_exc()
            finally:
                save(args.output,report)
        admin.execute('ALTER TABLE app_rate_limits DISABLE TRIGGER bench_commit_failure')
        # Never benchmark a candidate that failed a mandatory correctness gate.
        valid={name:fn for name,fn in VARIANTS.items() if name not in report['failures']}
        if valid:
            exp.VARIANTS=valid
            with pooled() as c:
                rtt=[]
                for _ in range(30):
                    start=time.perf_counter_ns()
                    c.execute('SELECT 1').fetchone()
                    rtt.append((time.perf_counter_ns()-start)/1e6)
            report['select1_rtt_ms']=exp.quantiles(rtt)
            raw,summary=exp.measure(admin,SimpleNamespace(profile=args.profile,requests=120,
                                                          repeats=5 if args.profile=='local' else 3))
            report.update({'runs':raw,'summary':summary,'requests':sum(r['requests'] for r in raw)})
        save(args.output,report)
    print('POOL_BENCH='+json.dumps({k:v for k,v in report.items() if k!='runs'},separators=(',',':')),flush=True)
    if report['failures']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
