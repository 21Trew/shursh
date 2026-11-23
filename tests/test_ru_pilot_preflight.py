"""No-network safety checks for the Timeweb/Staging-only pilot image."""
import pytest

from tools.ru_pilot_preflight import validate

REF = "vwhzhbsaspbelkvnjjho"
PROD = "rqnbhjhwmubsjwzontnu"


@pytest.fixture
def environment(monkeypatch):
    for name in ("VERCEL", "VERCEL_ENV", "SHURSH_AUTH_REDIRECT_URL"):
        monkeypatch.delenv(name, raising=False)
    variables = {
        "SHURSH_PILOT": "1",
        "SHURSH_ENV": "staging",
        "SHURSH_EXPECTED_SUPABASE_REF": REF,
        "SHURSH_HTTPS": "1",
        "SHURSH_RATE_SECRET": "not-a-real-secret-only-for-CI-000000",
        "SUPABASE_URL": f"https://{REF}.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fake_for_ci",
        "SHURSH_DATABASE_URL": (
            f"postgresql://shursh_preview_login.{REF}:fake-ci-password@"
            "aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"
        ),
        "PORT": "8080",
    }
    for name, value in variables.items():
        monkeypatch.setenv(name, value)


def test_pilot_accepts_exact_staging_configuration_without_network(environment):
    validate()


@pytest.mark.parametrize("name,value", [
    ("SHURSH_PILOT", "0"),
    ("SHURSH_ENV", "production"),
    ("SHURSH_EXPECTED_SUPABASE_REF", PROD),
    ("SHURSH_HTTPS", "0"),
    ("SHURSH_RATE_SECRET", "short"),
    ("PORT", "80"),
])
def test_pilot_fails_closed_on_wrong_environment(environment, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        validate()


@pytest.mark.parametrize("database_url", [
    "postgresql://postgres:pass@db.vwhzhbsaspbelkvnjjho.supabase.co:5432/postgres?sslmode=require",
    f"postgresql://shursh_preview_login.{PROD}:pass@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require",
    f"postgresql://shursh_preview_login.{REF}:pass@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=disable",
])
def test_pilot_rejects_unapproved_database_without_connection(
    environment, monkeypatch, database_url
):
    monkeypatch.setenv("SHURSH_DATABASE_URL", database_url)
    with pytest.raises(RuntimeError):
        validate()


def test_pilot_rejects_production_auth(environment, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", f"https://{PROD}.supabase.co")
    with pytest.raises(RuntimeError):
        validate()


@pytest.mark.parametrize("redirect", [
    "https://shursh.fun/",
    "https://shursh.vercel.app/",
    "http://pilot.example.org/",
    "https://pilot.example.org/?token=secret",
    "https://example.vercel.app/",
])
def test_pilot_rejects_wrong_redirect(environment, monkeypatch, redirect):
    monkeypatch.setenv("SHURSH_AUTH_REDIRECT_URL", redirect)
    with pytest.raises(RuntimeError):
        validate()


def test_pilot_accepts_separate_https_technical_origin(environment, monkeypatch):
    monkeypatch.setenv("SHURSH_AUTH_REDIRECT_URL", "https://pilot.webtm.ru/")
    validate()


def test_pilot_rejects_inherited_vercel_environment(environment, monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    with pytest.raises(RuntimeError):
        validate()
