#!/usr/bin/env bash
#
# Container startup for BharatNXT Wave on Render.
#
# Starts as root so it can take ownership of the mounted persistent disk,
# then drops to the unprivileged `bharatnxt` user before running anything
# that touches a request. `exec` matters: gunicorn must become PID 1 so
# Render's shutdown signals reach it rather than this script.

set -euo pipefail

APP_USER=bharatnxt

echo "==> BharatNXT Wave starting"

# --------------------------------------------------------------------------
# Fail fast on the mistakes that are silent and expensive later
# --------------------------------------------------------------------------

if [ "${BHARATNXT_ENVIRONMENT:-}" != "production" ]; then
    echo "FATAL: BHARATNXT_ENVIRONMENT must be 'production' on Render." >&2
    echo "       Without it DEBUG stays on and the IP allow-list is off." >&2
    exit 1
fi

if [ -z "${BHARATNXT_DATA_ROOT:-}" ]; then
    echo "FATAL: BHARATNXT_DATA_ROOT is not set." >&2
    echo "       Render's container filesystem is wiped on every deploy," >&2
    echo "       so scheme flyers would be lost. Mount a persistent disk" >&2
    echo "       and point BHARATNXT_DATA_ROOT at it." >&2
    exit 1
fi

if [ ! -d "${BHARATNXT_DATA_ROOT}" ]; then
    echo "FATAL: BHARATNXT_DATA_ROOT=${BHARATNXT_DATA_ROOT} does not exist." >&2
    echo "       Check the disk mount path in render.yaml." >&2
    exit 1
fi

if ! command -v pg_dump > /dev/null 2>&1; then
    echo "FATAL: pg_dump is missing from the image." >&2
    echo "       Every workbook import would be refused." >&2
    exit 1
fi

# --------------------------------------------------------------------------
# Persistent storage
#
# The platform mounts the disk owned by root. Without this the app could not
# write flyers to it, and the failure would only show up when someone tried
# to upload one.
# --------------------------------------------------------------------------

mkdir -p \
    "${BHARATNXT_DATA_ROOT}/private_uploads" \
    "${BHARATNXT_DATA_ROOT}/audit" \
    "${BHARATNXT_DATA_ROOT}/logs"

if [ "$(id -u)" = "0" ]; then
    chown -R "${APP_USER}:${APP_USER}" "${BHARATNXT_DATA_ROOT}"
    RUN_AS="gosu ${APP_USER}"
else
    # Already unprivileged (some platforms force a UID). Nothing to drop.
    RUN_AS=""
fi

chmod 750 "${BHARATNXT_DATA_ROOT}/private_uploads"

echo "==> Data root ready: ${BHARATNXT_DATA_ROOT}"

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

echo "==> Applying migrations"
${RUN_AS} python manage.py migrate --noinput

# Backs the login lockout counters. Without a shared cache each gunicorn
# worker would count failures separately. Safe to re-run.
echo "==> Ensuring cache table"
${RUN_AS} python manage.py createcachetable

# --------------------------------------------------------------------------
# Hand over to gunicorn
# --------------------------------------------------------------------------

echo "==> Starting gunicorn on 0.0.0.0:${PORT:-10000} as ${APP_USER}"

exec ${RUN_AS} gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-10000}" \
    --workers "${WEB_CONCURRENCY:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
