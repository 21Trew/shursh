"""Fail-closed startup gate for the Russian Staging-only Docker image.

No network calls, SQL, secrets or connection strings are logged. The same
existing Supabase project/role/TLS guard is reused before Gunicorn starts.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from cloud.environment import STAGING_REF, assert_staging_target


def validate() -> None:
    if os.environ.get("SHURSH_PILOT") != "1":
        raise RuntimeError("Russian pilot marker is missing")
    if os.environ.get("SHURSH_ENV") != "staging":
        raise RuntimeError("Russian pilot cannot start outside Staging")
    if os.environ.get("SHURSH_EXPECTED_SUPABASE_REF") != STAGING_REF:
        raise RuntimeError("Russian pilot requires the approved Staging project")
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        raise RuntimeError("Russian pilot must not inherit Vercel environment markers")
    if os.environ.get("SHURSH_HTTPS") != "1":
        raise RuntimeError("Russian pilot requires secure HTTPS cookies")
    if len(os.environ.get("SHURSH_RATE_SECRET", "")) < 24:
        raise RuntimeError("Russian pilot requires a separate strong rate-limit secret")
    if not os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip():
        raise RuntimeError("Russian pilot requires the Staging publishable key")
    # This verifies the exact Staging Auth URL and least-privilege PostgreSQL
    # Supavisor username, project, region, port, SSL and connection options.
    assert_staging_target()

    # The technical HTTPS hostname is issued only AFTER app creation. Allow
    # booting without the redirect; registration remains fail-closed until
    # SHURSH_AUTH_REDIRECT_URL and the Staging Auth allowlist are configured.
    redirect = os.environ.get("SHURSH_AUTH_REDIRECT_URL", "").strip()
    if redirect:
        parsed = urlsplit(redirect)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or not host or parsed.username or
                parsed.password or parsed.port not in (None, 443) or
                parsed.path not in ("", "/") or parsed.query or parsed.fragment or
                host in ("shursh.fun", "www.shursh.fun", "shursh.vercel.app") or
                host.endswith(".vercel.app") or host.endswith(".supabase.co")):
            raise RuntimeError("Russian pilot redirect must be its separate HTTPS origin")

    port = os.environ.get("PORT", "8080")
    if not port.isdecimal() or not 1024 <= int(port) <= 65535:
        raise RuntimeError("Russian pilot requires an unprivileged HTTP port")


if __name__ == "__main__":
    validate()
    print("RU pilot preflight OK: Staging isolation, HTTPS and least privilege", flush=True)
