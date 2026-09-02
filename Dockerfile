# BharatNXT Wave - container image for managed platforms (Render).
#
# A container is used rather than Render's native Python runtime because the
# app shells out to `pg_dump` for the mandatory pre-import database snapshot
# (toolkit/intelligence/final_import.backup_database). The native runtime has
# no PostgreSQL client, so every import would be refused.

FROM python:3.13-slim

# pg_dump refuses to dump a server newer than itself, and Debian bookworm
# ships client 15 while Render's PostgreSQL is 16/17. Install the client from
# PGDG instead - a newer client reads older servers, so 17 covers both.
ARG PG_MAJOR=17

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
        gosu; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "postgresql-client-${PG_MAJOR}"; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/*; \
    pg_dump --version; \
    gosu --version

WORKDIR /app

COPY deployment/requirements-production.txt ./requirements-production.txt
RUN pip install --no-cache-dir -r requirements-production.txt

COPY . .

# Bake the hashed static manifest into the image. This runs with development
# defaults (BHARATNXT_ENVIRONMENT is not set at build time), which is fine -
# collectstatic touches no secrets and no database.
RUN python manage.py collectstatic --noinput

RUN useradd --system --create-home --uid 10001 bharatnxt \
    && chown -R bharatnxt:bharatnxt /app

COPY deployment/render-entrypoint.sh /usr/local/bin/render-entrypoint.sh
RUN chmod +x /usr/local/bin/render-entrypoint.sh

# The entrypoint deliberately starts as root: the platform mounts the
# persistent disk owned by root, so the mount has to be chowned before the
# app can write scheme flyers to it. The entrypoint drops to the unprivileged
# `bharatnxt` user with gosu before exec'ing gunicorn, so nothing that serves
# a request ever runs as root.

# Render injects PORT and expects the process to bind it on 0.0.0.0.
ENV PORT=10000
EXPOSE 10000

ENTRYPOINT ["/usr/local/bin/render-entrypoint.sh"]
