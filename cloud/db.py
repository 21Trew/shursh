"""PostgreSQL adapter for the shared parameterized API queries."""
from contextlib import contextmanager
import atexit
import os
import sqlite3
import threading
import time
from flask import g, has_request_context

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from cloud.environment import assert_staging_target

# Project-wide write lock for the small MVP. It serializes conflicting state
# changes across multiple serverless instances, not merely one Python process.
WRITE_LOCK = 58310974031082412

# A *small* lazy pool for each Vercel Python worker. Supavisor is still the
# authoritative transaction pooler. No connections are created on module
# import; idle connections are released after 45 s. This never spans workers.
_POOL = None
_POOL_DSN = None
_POOL_LOCK = threading.Lock()


def _close_pool_at_exit():
    # Serverless workers can finish with idle pool maintenance threads.
    # Close explicitly before Python interpreter teardown, otherwise the
    # default daemon cleanup can block the CI job for 20+ seconds.
    pool = _POOL
    if pool is not None:
        pool.close(timeout=2)


atexit.register(_close_pool_at_exit)


def _pool_for(dsn):
    global _POOL, _POOL_DSN
    if _POOL is not None:
        if _POOL_DSN != dsn:
            raise RuntimeError('Database configuration changed in a live process')
        return _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ConnectionPool(
                conninfo=dsn, min_size=0, max_size=4, max_idle=45,
                max_lifetime=600, timeout=8, open=True,
                kwargs={'row_factory': dict_row, 'prepare_threshold': None,
                        'connect_timeout': 8, 'autocommit': True},
                check=ConnectionPool.check_connection)
            _POOL_DSN = dsn
    return _POOL


# These static, ordered statements share one PostgreSQL protocol call.
# Keep SET TRANSACTION first: it must precede data access in read transactions.
# No user-provided SQL or parameters are ever part of these batches.
_TX_SETTINGS = (
    "SET LOCAL ROLE shursh_backend; "
    "SET LOCAL statement_timeout = '10s'; "
    "SET LOCAL lock_timeout = '8s'"
)
_TX_SETTINGS_READ = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; " + _TX_SETTINGS


def _timed_execute(connection, statement, params=None, *, statement_count=1):
    """Aggregate timings/counts only: never retain SQL text or parameters."""
    started = time.perf_counter()
    try:
        if params is None:
            return connection.execute(statement)
        return connection.execute(statement, params)
    finally:
        if has_request_context():
            g.sql_exec_ms = getattr(g, 'sql_exec_ms', 0.0) + (time.perf_counter() - started) * 1000
            g.sql_exec_count = getattr(g, 'sql_exec_count', 0) + statement_count
            g.sql_exec_calls = getattr(g, 'sql_exec_calls', 0) + 1


class DB:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, params=()):
        # These markers came from the SQLite API. Cloud transactions are owned
        # by transaction() and MUST commit only once, before returning a result.
        if statement.strip().upper() in ('BEGIN IMMEDIATE', 'COMMIT'):
            return None
        try:
            return _timed_execute(self.connection, statement.replace('?', '%s'), params)
        except psycopg.IntegrityError as exc:
            # Preserve the shared API's existing conflict handling.
            raise sqlite3.IntegrityError('database constraint') from exc



def close_request_connection():
    """Release a connection retained only for the lifetime of one HTTP request."""
    if not has_request_context():
        return
    connection=getattr(g,'shursh_db_connection',None)
    if connection is not None:
        pool=getattr(g,'shursh_db_pool',None)
        g.shursh_db_connection=None
        g.shursh_db_pool=None
        if pool is not None:
            pool.putconn(connection)


@contextmanager
def _lease_connection():
    assert_staging_target()
    dsn=os.environ.get('SHURSH_DATABASE_URL')
    if not dsn:
        raise RuntimeError('SHURSH_DATABASE_URL is not configured')
    in_request=has_request_context()
    stored=getattr(g,'shursh_db_connection',None) if in_request else None
    pool = _pool_for(dsn)
    if stored is not None and stored.closed:
        # A broken socket must never be shared or retained in the request.
        pool.putconn(stored)
        stored=None
        g.shursh_db_connection=None
        g.shursh_db_pool=None
    # Reuse an idle connection within the request without another checkout.
    # Inner rate limit checks use their own connection and commit independently,
    # including when the enclosing business transaction later rolls back.
    reusable=(stored is not None and
              stored.info.transaction_status==psycopg.pq.TransactionStatus.IDLE)
    ephemeral=False
    if reusable:
        connection=stored
        retained=True
    else:
        started=time.perf_counter()
        if stored is not None:
            # An inner independent rate limit transaction must not wait for
            # another pool checkout while its outer transaction still holds
            # PostgreSQL locks: under concurrency that can deadlock the pool.
            # This uncommon path gets its own short-lived socket.
            connection=psycopg.connect(dsn,row_factory=dict_row,
                prepare_threshold=None,connect_timeout=8,autocommit=True)
            ephemeral=True
        else:
            # Pooled connections are checked for liveness on every lease.
            connection=pool.getconn(timeout=8)
        if in_request:
            g.db_connect_ms=getattr(g,'db_connect_ms',0.0)+(time.perf_counter()-started)*1000
            g.db_connect_count=getattr(g,'db_connect_count',0)+1
        retained=in_request and stored is None
        if retained:
            g.shursh_db_connection=connection
            g.shursh_db_pool=pool
    try:
        yield connection
    finally:
        # Primary checkout is returned by Flask teardown; nested leases are
        # returned immediately after their independent transaction finishes.
        if not retained:
            if ephemeral:
                connection.close()
            else:
                pool.putconn(connection)


@contextmanager
def transaction(write=False, *, rate_limit=False):
    with _lease_connection() as connection:
        with connection.transaction():
            if not write and not rate_limit:
                _timed_execute(connection, _TX_SETTINGS_READ, statement_count=4)
            else:
                _timed_execute(connection, _TX_SETTINGS, statement_count=3)
            # Verify a marker held only by the Staging database BEFORE
            # running the rate limiter, business writes or any other query.
            # The backend role has SELECT on this single marker table.
            if os.environ.get('SHURSH_ENV') == 'staging':
                marker=_timed_execute(connection,
                    "SELECT project_ref FROM shursh_env.environment_identity "
                    "WHERE singleton=true AND environment='staging'").fetchone()
                if not marker or marker['project_ref'] != 'vwhzhbsaspbelkvnjjho':
                    raise RuntimeError('Staging database identity mismatch')
            if write and not rate_limit:
                _timed_execute(connection, 'SELECT pg_advisory_xact_lock(%s)',(WRITE_LOCK,))
            yield DB(connection)


def _rate_limit_batch(connection, statement, params):
    """One simple-query exchange; never retry a possibly committed quota."""
    idle = psycopg.pq.TransactionStatus.IDLE
    if not connection.autocommit or connection.info.transaction_status != idle:
        raise RuntimeError('Rate limiter requires an idle autocommit connection')
    started = time.perf_counter()
    try:
        # The statement and settings are static application SQL. ClientCursor
        # adapts values safely before sending a single simple-query message.
        with psycopg.ClientCursor(connection) as cur:
            cur.execute('BEGIN; ' + _TX_SETTINGS + '; ' +
                        statement.replace('?', '%s') + '; COMMIT',
                        params, prepare=False)
            for expected in ('BEGIN', 'SET', 'SET', 'SET'):
                if cur.statusmessage != expected or not cur.nextset():
                    raise RuntimeError('Missing rate limiter transaction result')
            if cur.statusmessage not in ('INSERT 0 0', 'INSERT 0 1'):
                raise RuntimeError('Missing rate limiter UPSERT result')
            allowed = cur.fetchone() is not None
            if not cur.nextset() or cur.statusmessage != 'COMMIT' or cur.nextset():
                raise RuntimeError('Missing successful rate limiter COMMIT')
            if connection.info.transaction_status != idle:
                raise RuntimeError('Rate limiter transaction is not idle')
            return allowed
    except BaseException as exc:
        # Only a server-confirmed SQL error permits reuse after rollback.
        # Missing COMMIT acknowledgement or transport/protocol errors have an
        # ambiguous outcome: discard the socket, propagate, NEVER replay.
        try:
            if not connection.closed:
                status = connection.info.transaction_status
                if (isinstance(exc, psycopg.Error) and exc.sqlstate
                        and status in (idle, psycopg.pq.TransactionStatus.INERROR,
                                       psycopg.pq.TransactionStatus.INTRANS)):
                    if status != idle:
                        connection.execute('ROLLBACK')
                    if connection.info.transaction_status != idle:
                        connection.close()
                else:
                    connection.close()
        except BaseException:
            connection.close()
        raise
    finally:
        if has_request_context():
            # Preserve the existing logical statement count (3 settings +
            # UPSERT), while recording the actual single execute call.
            g.sql_exec_ms = getattr(g, 'sql_exec_ms', 0.0) + (time.perf_counter() - started) * 1000
            g.sql_exec_count = getattr(g, 'sql_exec_count', 0) + 4
            g.sql_exec_calls = getattr(g, 'sql_exec_calls', 0) + 1


def committed_rate_limit_batch(statement, params):
    """Lease independently of business transactions, and return after COMMIT."""
    # Do not let a caller accidentally bypass the Staging database marker.
    if os.environ.get('SHURSH_ENV') == 'staging':
        raise RuntimeError('Staging rate limiter requires database identity check')
    with _lease_connection() as connection:
        return _rate_limit_batch(connection, statement, params)
