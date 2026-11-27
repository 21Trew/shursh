"""CI-only acceptance of the actual application batch path, not a copy."""
from contextlib import contextmanager
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import struct
import threading
from unittest.mock import patch

from flask import Flask, g
import psycopg
from cloud import db
from cloud.environment import STAGING_REF
from cloud.backend import RATE_LIMIT_SQL, consume_committed_rate_limit
from tools import rate_limit_experiment as exp
from tools import rate_limit_pooler_experiment as pooler

DSN = ('postgresql://bench_login.ratebench:ci-bench-only@127.0.0.1:6543/'
       'shursh_rate_bench?sslmode=disable&gssencmode=disable')


def candidate(c, key, bucket, limit):
    if limit < 1:
        raise ValueError('Rate limit must be positive')
    return db._rate_limit_batch(c, RATE_LIMIT_SQL, (key, bucket, limit))


def read_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise EOFError('PostgreSQL peer closed')
        data.extend(chunk)
    return bytes(data)


def lost_commit_ack(admin, profile='production'):
    # Transparent TCP proxy: only discard the COMMIT CommandComplete and
    # all subsequent bytes. PostgreSQL has already committed; verify from
    # an independent admin socket. No synthetic driver exception.
    key = exp.key_for('integrated-lost-commit', profile)
    seen = threading.Event()
    frontend = bytearray()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]

        def proxy():
            with listener.accept()[0] as client, socket.create_connection(('127.0.0.1', 6543), 5) as upstream:
                client.settimeout(15)
                upstream.settimeout(15)
                def forward():
                    try:
                        while True:
                            chunk = client.recv(65536)
                            if not chunk:
                                break
                            frontend.extend(chunk)
                            upstream.sendall(chunk)
                    except OSError:
                        pass
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as forwarding:
                    sender = forwarding.submit(forward)
                    try:
                        while True:
                            tag = read_exact(upstream, 1)
                            length = read_exact(upstream, 4)
                            payload = read_exact(upstream, struct.unpack('!I', length)[0] - 4)
                            if tag == b'C' and payload == b'COMMIT\x00':
                                seen.set()
                                break
                            client.sendall(tag + length + payload)
                    finally:
                        for sock in (client, upstream):
                            try:
                                sock.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                        sender.result(timeout=16)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            worker = executor.submit(proxy)
            with psycopg.connect(host='127.0.0.1', port=port,
                    dbname=exp.DB_NAME, user='bench_login.ratebench',
                    password='ci-bench-only', sslmode='disable', gssencmode='disable',
                    connect_timeout=5, autocommit=True, prepare_threshold=None) as conn:
                @contextmanager
                def one_lease():
                    yield conn
                with patch.object(db, '_lease_connection', one_lease):
                    exp.must_fail(lambda: consume_committed_rate_limit(key, 100, 10),
                                  (psycopg.Error, RuntimeError))
                assert conn.closed, 'Ambiguous connection must be discarded'
            worker.result(timeout=20)
    assert seen.is_set(), 'COMMIT response was not intercepted'
    assert frontend.count(b'INSERT INTO app_rate_limits') == 1, 'Quota was replayed'
    assert exp.state(admin, key)[:2] == (100, 1), 'Expected exactly one durable increment'
    assert consume_committed_rate_limit(key, 100, 10)
    assert exp.state(admin, key)[:2] == (100, 2)
    return {'commit_ack_dropped': True, 'attempts': 1, 'durable_hits': 1,
            'connection_discarded': True, 'next_request_succeeded': True}


def application_path(admin, profile='production'):
    app = Flask(__name__)
    app.teardown_request(lambda error: db.close_request_connection())
    key = exp.key_for('integrated-nested', profile)
    with app.test_request_context('/api/test'):
        try:
            with db.transaction(write=True) as business:
                business.execute('INSERT INTO bench_business VALUES(999)')
                assert consume_committed_rate_limit(key, 100, 1)
                raise ValueError('rollback business')
        except ValueError as exc:
            assert str(exc) == 'rollback business'
        assert admin.execute('SELECT count(*) FROM bench_business').fetchone()[0] == 0
        assert not consume_committed_rate_limit(key, 100, 1)
        assert exp.state(admin, key)[:2] == (100, 1)
        assert g.shursh_db_connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    with app.test_request_context('/api/test'):
        key = exp.key_for('integrated-metrics', profile)
        assert consume_committed_rate_limit(key, 100, 1)
        conn = g.shursh_db_connection
        assert not consume_committed_rate_limit(key, 100, 1)
        assert g.sql_exec_count == (10 if profile == 'staging' else 8) and g.sql_exec_calls == 2
        assert g.db_connect_count == 1 and g.shursh_db_connection is conn
    key = exp.key_for('integrated-concurrent', profile)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        allowed = sum(executor.map(lambda _: consume_committed_rate_limit(key, 100, 17), range(96)))
    assert allowed == 17 and exp.state(admin, key)[:2] == (100, 17)
    return {'independent_commit': True, 'metric_counts': True, 'connection_reused': True,
            'concurrent_attempts': 96, 'concurrent_allowed': allowed}



def staging_marker_gates(admin):
    """Only on the disposable local DB; never contact hosted Staging."""
    pooler.guard()
    # The production marker is intentionally absent. We simulate Staging's
    # endpoint validation only, not the database guard or the application SQL.
    # Every quota operation still uses the real local connection lease.
    key_new = exp.key_for('staging-guard-new')
    key_old = exp.key_for('staging-guard-existing')
    admin.execute('INSERT INTO app_rate_limits VALUES(%s,100,1)', (key_old,))
    initial = exp.state(admin, key_old)
    # A sequence is non-transactional: an INSERT trigger that executes even
    # inside a rolled-back transaction would leave is_called=true.
    admin.execute("""
        CREATE SEQUENCE public.bench_guard_attempt;
        GRANT USAGE ON SEQUENCE public.bench_guard_attempt TO shursh_backend;
        CREATE FUNCTION public.bench_guard_probe() RETURNS trigger
        LANGUAGE plpgsql AS $bench_guard_probe$ BEGIN
          PERFORM nextval('public.bench_guard_attempt');
          RETURN NEW;
        END; $bench_guard_probe$;
        CREATE TRIGGER bench_guard_probe BEFORE INSERT ON app_rate_limits
        FOR EACH ROW EXECUTE FUNCTION public.bench_guard_probe();
    """)
    results = {}
    app = Flask(__name__)
    app.teardown_request(lambda error: db.close_request_connection())

    def denied(name, sqlstate):
        for key in (key_new, key_old):
            with app.test_request_context('/api/test'):
                try:
                    consume_committed_rate_limit(key, 100, 10)
                except psycopg.Error as exc:
                    assert exc.sqlstate == sqlstate, (name, exc.sqlstate)
                else:
                    raise AssertionError(('Marker failure returned a quota verdict', name))
                assert g.sql_exec_calls == 1 and g.sql_exec_count == 5
            assert exp.state(admin, key_new) is None
            assert exp.state(admin, key_old) == initial
            assert admin.execute('SELECT is_called FROM public.bench_guard_attempt').fetchone() == (False,)
        results[name] = {'sqlstate': sqlstate, 'new_row_absent': True,
                         'existing_row_unchanged': True, 'upsert_not_reached': True}

    # Patch ONLY the hosted endpoint check because the fixture is localhost.
    # The original production/preview configuration guard remains covered by
    # test_preview_isolation and the pre-checkout integration regression test.
    with patch.dict(os.environ, {'SHURSH_ENV': 'staging'}), patch.object(db, 'assert_staging_target'):
        try:
            denied('missing_schema', '42P01')
            admin.execute('CREATE SCHEMA shursh_env; REVOKE ALL ON SCHEMA shursh_env FROM PUBLIC; GRANT USAGE ON SCHEMA shursh_env TO shursh_backend')
            denied('missing_table', '42P01')
            # Same column types as Staging. Deliberately allow corrupt rows
            # here to test fail-closed even if an administrator misprovisions it.
            admin.execute("""
                CREATE TABLE shursh_env.environment_identity(
                    singleton boolean PRIMARY KEY, environment text NOT NULL,
                    project_ref text NOT NULL);
                REVOKE ALL ON shursh_env.environment_identity FROM PUBLIC, anon, authenticated;
                GRANT SELECT ON shursh_env.environment_identity TO shursh_backend;
            """)
            denied('missing_row', 'P0001')
            admin.execute("INSERT INTO shursh_env.environment_identity VALUES(true,'staging','wrong-ref')")
            denied('wrong_ref', 'P0001')
            admin.execute("UPDATE shursh_env.environment_identity SET environment='production', project_ref=%s", (STAGING_REF,))
            denied('wrong_environment', 'P0001')
            admin.execute("UPDATE shursh_env.environment_identity SET environment='staging', singleton=false")
            denied('wrong_singleton', 'P0001')
            admin.execute("UPDATE shursh_env.environment_identity SET singleton=true")
            admin.execute('REVOKE SELECT ON shursh_env.environment_identity FROM shursh_backend')
            denied('no_select_privilege', '42501')
            admin.execute('GRANT SELECT ON shursh_env.environment_identity TO shursh_backend')
            with pooler.pooled() as c:
                with c.transaction():
                    c.execute('SET LOCAL ROLE shursh_backend')
                    assert c.execute("SELECT has_language_privilege(current_user, 'plpgsql', 'USAGE')").fetchone()[0]
                    assert not c.execute("SELECT has_table_privilege(current_user, 'shursh_env.environment_identity', 'UPDATE')").fetchone()[0]
            assert consume_committed_rate_limit(key_new, 100, 1)
            assert not consume_committed_rate_limit(key_new, 100, 1)
            assert exp.state(admin, key_new)[:2] == (100, 1)
            assert admin.execute('SELECT is_called FROM public.bench_guard_attempt').fetchone() == (True,)
            results['valid_marker'] = {'allowed': True, 'saturated_denied': True,
                                       'durable_hits': 1, 'marker_read_only': True}
        finally:
            admin.execute('DROP TRIGGER bench_guard_probe ON app_rate_limits; DROP FUNCTION public.bench_guard_probe(); DROP SEQUENCE public.bench_guard_attempt')
        # Run the existing full SQL Batch gate set again with the real marker.
        results['security'] = exp.semantic_gates(admin, 'integrated-staging')
        results['protocol'] = exp.protocol_counts('sql_batch', candidate, 'integrated-staging')
        assert results['protocol'] == {'Query': 1, 'Sync': 0, 'Flush': 0, 'ReadyForQuery': 1}
        results['reuse'] = pooler.reuse(admin, 'integrated-staging', candidate)
        results['faults'] = pooler.faults(admin, 'integrated-staging', candidate)
        results['application'] = application_path(admin, 'staging')
        results['lost_commit_ack'] = lost_commit_ack(admin, 'staging')
    # Production never relies on the marker: remove it in this fixture and
    # prove a fresh production request still succeeds through the same executor.
    admin.execute('DROP SCHEMA shursh_env CASCADE')
    key = exp.key_for('production-without-marker-after-staging')
    assert consume_committed_rate_limit(key, 100, 1)
    results['production_without_marker'] = True
    return results


def main():
    pooler.guard()
    os.environ['SHURSH_DATABASE_URL'] = DSN
    exp.connect = pooler.pooled
    exp.VARIANTS = {'sql_batch': candidate}
    report = {}
    out = Path('artifacts/rate-batch/acceptance.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pooler.DIRECT(admin=True) as admin:
            report['security'] = exp.semantic_gates(admin, 'integrated')
            report['protocol'] = exp.protocol_counts('sql_batch', candidate, 'integrated')
            assert report['protocol'] == {'Query': 1, 'Sync': 0, 'Flush': 0, 'ReadyForQuery': 1}
            report['reuse'] = pooler.reuse(admin, 'integrated', candidate)
            report['faults'] = pooler.faults(admin, 'integrated', candidate)
            report['application'] = application_path(admin)
            report['lost_commit_ack'] = lost_commit_ack(admin)
            report['staging'] = staging_marker_gates(admin)
        report['status'] = 'passed'
    finally:
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
        db._close_pool_at_exit()
    print('INTEGRATED_RATE_BATCH=' + json.dumps(report, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
