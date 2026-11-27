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


def lost_commit_ack(admin):
    # Transparent TCP proxy: only discard the COMMIT CommandComplete and
    # all subsequent bytes. PostgreSQL has already committed; verify from
    # an independent admin socket. No synthetic driver exception.
    key = exp.key_for('integrated-lost-commit')
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


def application_path(admin):
    app = Flask(__name__)
    app.teardown_request(lambda error: db.close_request_connection())
    key = exp.key_for('integrated-nested')
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
        key = exp.key_for('integrated-metrics')
        assert consume_committed_rate_limit(key, 100, 1)
        conn = g.shursh_db_connection
        assert not consume_committed_rate_limit(key, 100, 1)
        assert g.sql_exec_count == 8 and g.sql_exec_calls == 2
        assert g.db_connect_count == 1 and g.shursh_db_connection is conn
    key = exp.key_for('integrated-concurrent')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        allowed = sum(executor.map(lambda _: consume_committed_rate_limit(key, 100, 17), range(96)))
    assert allowed == 17 and exp.state(admin, key)[:2] == (100, 17)
    return {'independent_commit': True, 'metric_counts': True, 'connection_reused': True,
            'concurrent_attempts': 96, 'concurrent_allowed': allowed}


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
        report['status'] = 'passed'
    finally:
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
        db._close_pool_at_exit()
    print('INTEGRATED_RATE_BATCH=' + json.dumps(report, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
