"""Fail-closed isolation of Supabase Staging from Production.

This check runs before opening any PostgreSQL connection or Auth HTTP request.
The two project references are public identifiers, not credentials.
"""
import os
import re
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict, make_conninfo

STAGING_REF = 'vwhzhbsaspbelkvnjjho'
PRODUCTION_REF = 'rqnbhjhwmubsjwzontnu'


class EnvironmentError(RuntimeError):
    """Only static, non-secret diagnostic codes; never include configuration."""
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)


def _needs_staging_guard():
    vercel_env = os.environ.get('VERCEL_ENV', '')
    app_env = os.environ.get('SHURSH_ENV', '')
    if vercel_env == 'production':
        if app_env == 'staging':
            raise EnvironmentError('staging_in_production', 'Staging configuration is forbidden in Production')
        return False
    if vercel_env == 'preview' or app_env == 'staging':
        return True
    # Hosted functions with a missing/unknown VERCEL_ENV must not silently
    # fall back to local mode and connect to any configured database.
    if os.environ.get('VERCEL') == '1':
        raise EnvironmentError('unknown_hosted_environment', 'Unrecognized hosted environment')
    return False


def assert_staging_target(*, require_database=True):
    """Validate Preview configuration without contacting Production.

    Local CI/SQLite and normal Production are unchanged. Preview requires
    both endpoints to identify the same, hard-coded Staging project.
    """
    if not _needs_staging_guard():
        return
    if os.environ.get('SHURSH_ENV') != 'staging':
        raise EnvironmentError('missing_staging_identity', 'Preview environment identity is missing')
    expected = os.environ.get('SHURSH_EXPECTED_SUPABASE_REF', '')
    if expected != STAGING_REF or expected == PRODUCTION_REF:
        raise EnvironmentError('unapproved_project', 'Unapproved Preview Supabase project')
    auth = urlsplit(os.environ.get('SUPABASE_URL', ''))
    if (auth.scheme != 'https' or auth.hostname != f'{expected}.supabase.co'
            or auth.username or auth.password or auth.port not in (None, 443)
            or auth.path not in ('', '/') or auth.query or auth.fragment):
        raise EnvironmentError('auth_url_mismatch', 'Preview Auth URL does not match Staging')
    if not require_database:
        return
    dsn = os.environ.get('SHURSH_DATABASE_URL', '')
    if not dsn:
        raise EnvironmentError('missing_database_config', 'Preview PostgreSQL connection is not configured')
    try:
        config = conninfo_to_dict(dsn)
    except (ValueError, TypeError) as exc:
        raise EnvironmentError('invalid_database_config', 'Invalid Preview PostgreSQL configuration') from exc
    host = config.get('host', '')
    username = config.get('user', '')
    # Only the dedicated, non-superuser login is accepted for serverless
    # Preview traffic, never postgres.<ref> or a direct admin connection.
    if (username != f'shursh_preview_login.{expected}' or
            not re.fullmatch(r'aws-[0-9]+-eu-central-1\.pooler\.supabase\.com', host) or
            str(config.get('port')) != '6543' or
            config.get('dbname') != 'postgres' or
            not config.get('password') or
            config.get('hostaddr') or config.get('service') or config.get('options')):
        raise EnvironmentError('database_identity_mismatch', 'Preview PostgreSQL project is not Staging')
    # Supabase's copied transaction-pooler URI may omit sslmode. Supply a
    # mandatory TLS default ourselves, never libpq's opportunistic default.
    # An explicitly insecure mode is still a configuration error.
    mode=config.get('sslmode','require')
    if mode not in ('require', 'verify-ca', 'verify-full'):
        raise EnvironmentError('database_tls_required', 'Preview PostgreSQL TLS is mandatory')
    return make_conninfo(dsn,sslmode=mode,gssencmode='disable')
