"""Offline fail-closed tests. These never connect to any hosted Supabase DB."""
import pytest

from cloud import auth, db
from cloud.environment import assert_staging_target, STAGING_REF, PRODUCTION_REF


@pytest.fixture
def staging_config(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    monkeypatch.setenv('SHURSH_ENV', 'staging')
    monkeypatch.setenv('SHURSH_EXPECTED_SUPABASE_REF', STAGING_REF)
    monkeypatch.setenv('SUPABASE_URL', f'https://{STAGING_REF}.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_test_only')
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://shursh_preview_login.{STAGING_REF}:test-password@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require')


def test_valid_staging_endpoints_pass_without_network(staging_config):
    assert_staging_target()
    assert_staging_target(require_database=False)


def test_production_database_cannot_be_staging(staging_config, monkeypatch):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://shursh_preview_login.{PRODUCTION_REF}:nope@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require')
    with pytest.raises(RuntimeError,match='not Staging'):
        assert_staging_target()


def test_production_auth_cannot_be_staging(staging_config, monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', f'https://{PRODUCTION_REF}.supabase.co')
    with pytest.raises(RuntimeError,match='Auth URL'):
        assert_staging_target()


def test_production_ref_cannot_be_expected(staging_config, monkeypatch):
    monkeypatch.setenv('SHURSH_EXPECTED_SUPABASE_REF', PRODUCTION_REF)
    with pytest.raises(RuntimeError,match='Unapproved'):
        assert_staging_target()


def test_missing_preview_marker_fails_closed(staging_config, monkeypatch):
    monkeypatch.delenv('SHURSH_ENV')
    with pytest.raises(RuntimeError,match='identity'):
        assert_staging_target()


def test_preview_tls_is_mandatory(staging_config, monkeypatch):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://shursh_preview_login.{STAGING_REF}:pass@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=disable')
    with pytest.raises(RuntimeError,match='TLS'):
        assert_staging_target()


def test_preview_api_auth_guard_runs_before_network(staging_config,monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', f'https://{PRODUCTION_REF}.supabase.co')
    monkeypatch.setattr(auth,'urlopen',lambda *args,**kwargs: pytest.fail('Unexpected network call'))
    with pytest.raises(RuntimeError,match='Auth URL'):
        auth.auth_request('login',email='x@example.com',password='ignored')


def test_preview_database_guard_runs_before_pool_checkout(staging_config,monkeypatch):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://postgres.{PRODUCTION_REF}:p@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require')
    monkeypatch.setattr(db,'_pool_for',lambda *args,**kwargs: pytest.fail('Unexpected DB connection'))
    with pytest.raises(RuntimeError,match='not Staging'):
        with db.transaction(): pass


def test_hosted_unknown_environment_is_rejected(staging_config,monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','custom')
    monkeypatch.delenv('SHURSH_ENV')
    with pytest.raises(RuntimeError,match='Unrecognized'):
        assert_staging_target()


def test_production_cannot_receive_staging_identity(staging_config,monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','production')
    with pytest.raises(RuntimeError,match='forbidden in Production'):
        assert_staging_target()


def test_local_ci_remains_unaffected(staging_config,monkeypatch):
    monkeypatch.delenv('VERCEL')
    monkeypatch.delenv('VERCEL_ENV')
    monkeypatch.delenv('SHURSH_ENV')
    monkeypatch.delenv('SHURSH_EXPECTED_SUPABASE_REF')
    monkeypatch.delenv('SUPABASE_URL')
    monkeypatch.delenv('SHURSH_DATABASE_URL')
    assert_staging_target()


@pytest.mark.parametrize('username',[
    'postgres.vwhzhbsaspbelkvnjjho',
    'shursh_preview_login.rqnbhjhwmubsjwzontnu',
    'shursh_backend.vwhzhbsaspbelkvnjjho',
])
def test_only_least_privilege_staging_login(staging_config, monkeypatch, username):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://{username}:password@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require')
    with pytest.raises(RuntimeError, match='not Staging'):
        assert_staging_target()


@pytest.mark.parametrize('host,port',[
    ('db.vwhzhbsaspbelkvnjjho.supabase.co', '5432'),
    ('aws-0-eu-west-1.pooler.supabase.com', '6543'),
    ('evil.pooler.supabase.com', '6543'),
    ('aws-0-eu-central-1.pooler.supabase.com', '5432'),
])
def test_pooler_host_and_port_must_match(staging_config, monkeypatch, host, port):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://shursh_preview_login.{STAGING_REF}:password@'
        f'{host}:{port}/postgres?sslmode=require')
    with pytest.raises(RuntimeError, match='not Staging'):
        assert_staging_target()


def test_unknown_postgres_options_are_rejected(staging_config, monkeypatch):
    monkeypatch.setenv('SHURSH_DATABASE_URL',
        f'postgresql://shursh_preview_login.{STAGING_REF}:password@'
        'aws-0-eu-central-1.pooler.supabase.com:6543/postgres'
        '?sslmode=require&options=-c%20search_path%3Dpublic')
    with pytest.raises(RuntimeError, match='not Staging'):
        assert_staging_target()
