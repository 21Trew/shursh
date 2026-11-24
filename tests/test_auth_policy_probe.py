"""Synthetic password-history feasibility test, NOT an enforcement mechanism.

Only the disposable CI PostgreSQL instance may be used. No auth.users rows
are read or written; random candidates and hashes stay inside PostgreSQL.
"""
import os
from time import perf_counter

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


def test_password_history_requires_candidate_and_rejects_last_three():
    dsn = os.environ.get('SHURSH_DATABASE_URL', '')
    assert dsn, 'Disposable PostgreSQL database is required'
    cfg = conninfo_to_dict(dsn)
    assert cfg.get('host') in ('localhost', '127.0.0.1')
    assert cfg.get('dbname') == 'shursh_ci'
    assert not cfg.get('hostaddr') and not cfg.get('service') and not cfg.get('options')
    assert not os.environ.get('VERCEL') and not os.environ.get('VERCEL_ENV')
    with psycopg.connect(dsn) as con:
        try:
            con.execute('CREATE SCHEMA IF NOT EXISTS auth_probe_crypto')
            con.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA auth_probe_crypto')
            namespace = con.execute(
                "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n "
                "ON n.oid=e.extnamespace WHERE e.extname='pgcrypto'"
            ).fetchone()[0]
            start = perf_counter()
            result = con.execute(sql.SQL("""
                WITH sample AS MATERIALIZED (
                  SELECT encode({ext}.gen_random_bytes(24),'hex') AS p1,
                         encode({ext}.gen_random_bytes(24),'hex') AS p2,
                         encode({ext}.gen_random_bytes(24),'hex') AS p3,
                         encode({ext}.gen_random_bytes(24),'hex') AS p4
                ), hashes AS MATERIALIZED (
                  SELECT *, {ext}.crypt(p1,{ext}.gen_salt('bf',10)) AS h1,
                            {ext}.crypt(p1,{ext}.gen_salt('bf',10)) AS h1_again,
                            {ext}.crypt(p2,{ext}.gen_salt('bf',10)) AS h2,
                            {ext}.crypt(p3,{ext}.gen_salt('bf',10)) AS h3
                  FROM sample
                )
                SELECT h1<>h1_again,
                       {ext}.crypt(p1,h1)=h1 AND {ext}.crypt(p1,h1_again)=h1_again,
                       {ext}.crypt(p1,h1)=h1,
                       {ext}.crypt(p2,h2)=h2,
                       {ext}.crypt(p3,h3)=h3,
                       {ext}.crypt(p4,h1)<>h1 AND {ext}.crypt(p4,h2)<>h2
                         AND {ext}.crypt(p4,h3)<>h3
                FROM hashes
            """).format(ext=sql.Identifier(namespace))).fetchone()
            assert result == (True, True, True, True, True, True)
            print('SHURSH_AUTH_POLICY_PROBE synthetic-only: '
                  f'{(perf_counter()-start)*1000:.1f}ms')
        finally:
            con.rollback()
