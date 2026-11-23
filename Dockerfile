# Staging-only Russian hosting pilot. Production still runs on Vercel.
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    SHURSH_PILOT=1 \
    SHURSH_ENV=staging \
    SHURSH_EXPECTED_SUPABASE_REF=vwhzhbsaspbelkvnjjho \
    SHURSH_HTTPS=1

WORKDIR /srv/shursh
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    -r requirements.txt "gunicorn==23.0.0"

# Explicit copy list: never ship .env, Git history, tests or Production data.
COPY app.py server.py ./
COPY cloud/ ./cloud/
COPY public/ ./public/
COPY tools/ru_pilot_preflight.py ./tools/ru_pilot_preflight.py

USER 10001:10001
EXPOSE 8080
CMD ["/bin/sh", "-ec", "python tools/ru_pilot_preflight.py && exec gunicorn --workers 1 --worker-class gthread --threads 4 --bind 0.0.0.0:${PORT:-8080} --timeout 35 --access-logfile /dev/null --error-logfile - app:app"]
