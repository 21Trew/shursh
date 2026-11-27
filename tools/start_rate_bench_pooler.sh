#!/usr/bin/env bash
set -euo pipefail
test "${CI:-}" = true
test "${SHURSH_BENCH_DISPOSABLE:-}" = yes
# All credentials and metadata are disposable CI-only values.
docker run -d --name shursh-bench-pooler --network host --ulimit nofile=100000:100000 \
  -e DATABASE_URL=ecto://postgres:ci-bench-only@127.0.0.1:5432/supavisor_metadata \
  -e SECRET_KEY_BASE=ci-only-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \
  -e VAULT_ENC_KEY=0123456789abcdef0123456789abcdef \
  -e API_JWT_SECRET=ci-only-api-jwt-secret-not-for-production \
  -e METRICS_JWT_SECRET=ci-only-metrics-secret-not-for-production \
  -e REGION=local -e DB_POOL_SIZE=3 -e PORT=14000 \
  -e PROXY_PORT_SESSION=55432 -e PROXY_PORT_TRANSACTION=6543 \
  -e ERL_AFLAGS="-proto_dist inet_tcp" \
  supabase/supavisor:2.9.5 /bin/sh -ec '
    /app/bin/migrate
    /app/bin/supavisor eval '\''{:ok, _} = Application.ensure_all_started(:supavisor)
      {:ok, _} = Supavisor.Tenants.create_tenant(%{
        "external_id" => "ratebench", "db_host" => "127.0.0.1",
        "db_port" => 5432, "db_database" => "shursh_rate_bench",
        "require_user" => true, "ip_version" => "v4",
        "enforce_ssl" => false, "upstream_ssl" => false,
        "allow_list" => ["127.0.0.1/32"],
        "default_pool_size" => 4, "default_max_clients" => 32,
        "default_parameter_status" => %{"server_version" => "17.12"},
        "users" => [%{"db_user" => "bench_login", "db_password" => "ci-bench-only",
          "mode_type" => "transaction", "pool_size" => 4, "is_manager" => true,
          "pool_checkout_timeout" => 15000, "max_clients" => 32}]
      })'\''
    exec /app/bin/server
  '
docker image inspect supabase/supavisor:2.9.5 --format '{{json .RepoDigests}}'
