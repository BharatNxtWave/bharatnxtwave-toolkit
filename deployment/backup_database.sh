#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKUP_DIR="${BHARATNXT_BACKUP_DIR:-$PROJECT_DIR/backups}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"

DB_ENGINE="${BHARATNXT_DB_ENGINE:-sqlite}"


if [ "$DB_ENGINE" = "postgresql" ]; then

    : "${BHARATNXT_DB_NAME:?BHARATNXT_DB_NAME is required}"
    : "${BHARATNXT_DB_USER:?BHARATNXT_DB_USER is required}"
    : "${BHARATNXT_DB_PASSWORD:?BHARATNXT_DB_PASSWORD is required}"

    export PGPASSWORD="$BHARATNXT_DB_PASSWORD"

    BACKUP_FILE="$BACKUP_DIR/bharatnxt_${TIMESTAMP}.dump"

    pg_dump \
        --format=custom \
        --no-owner \
        --no-privileges \
        --host="${BHARATNXT_DB_HOST:-127.0.0.1}" \
        --port="${BHARATNXT_DB_PORT:-5432}" \
        --username="$BHARATNXT_DB_USER" \
        --file="$BACKUP_FILE" \
        "$BHARATNXT_DB_NAME"

    unset PGPASSWORD

else

    DATABASE_FILE="$PROJECT_DIR/db.sqlite3"

    if [ ! -f "$DATABASE_FILE" ]; then
        echo "SQLite database not found: $DATABASE_FILE"
        exit 1
    fi

    BACKUP_FILE="$BACKUP_DIR/bharatnxt_${TIMESTAMP}.sqlite3"

    cp "$DATABASE_FILE" "$BACKUP_FILE"

fi


# Keep only the latest 14 backup files.
find "$BACKUP_DIR" \
    -maxdepth 1 \
    -type f \
    -name "bharatnxt_*" \
    -printf '%T@ %p\n' \
    | sort -nr \
    | tail -n +15 \
    | cut -d' ' -f2- \
    | xargs -r rm -f


echo "Backup created:"
echo "$BACKUP_FILE"
