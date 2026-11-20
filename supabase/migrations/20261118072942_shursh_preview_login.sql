-- Deployment-only login. Password is provisioned out of band; never commit it.
CREATE ROLE shursh_preview_login LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL CONNECTION LIMIT 8;
GRANT shursh_backend TO shursh_preview_login WITH INHERIT FALSE, SET TRUE;
GRANT CONNECT ON DATABASE postgres TO shursh_preview_login;
