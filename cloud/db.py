"""PostgreSQL adapter for the shared parameterized API queries."""
from contextlib import contextmanager
import os
import sqlite3

import psycopg
from psycopg.rows import dict_row

# Project-wide write lock for the small MVP. It serializes conflicting state
# changes across multiple serverless instances, not merely one Python process.
WRITE_LOCK = 58310974031082412


class DB:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, params=()):
        # These markers came from the SQLite API. Cloud transactions are owned
        # by transaction() and MUST commit only once, before returning a result.
        if statement.strip().upper() in ('BEGIN IMMEDIATE', 'COMMIT'):
            return None
        try:
            return self.connection.execute(statement.replace('?', '%s'), params)
        except psycopg.IntegrityError as exc:
            # Preserve the shared API's existing conflict handling.
            raise sqlite3.IntegrityError('database constraint') from exc


@contextmanager
def transaction(write=False, *, rate_limit=False):
    dsn = os.environ.get('SHURSH_DATABASE_URL')
    if not dsn:
        raise RuntimeError('SHURSH_DATABASE_URL is not configured')
    # Transaction-mode Supavisor does not support named prepared statements.
    with psycopg.connect(dsn, row_factory=dict_row, prepare_threshold=None,
                         connect_timeout=8) as connection:
        # For a standalone Postgres CI fixture and the Supabase pooler alike.
        if not write and not rate_limit:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        connection.execute('SET LOCAL ROLE shursh_backend')
        connection.execute("SET LOCAL statement_timeout = '10s'")
        connection.execute("SET LOCAL lock_timeout = '8s'")
        if write and not rate_limit:
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (WRITE_LOCK,))
        yield DB(connection)
        # psycopg commits on successful context exit and rolls back on any error.
