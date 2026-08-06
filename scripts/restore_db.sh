#!/usr/bin/env bash
# Database restore: restores a .dump file created by backup_db.sh.
#
# USAGE:
#   ./scripts/restore_db.sh backups/shopsphere_20260801_120000.dump
#
# WARNING: --clean drops existing objects before recreating them — this
# OVERWRITES the target database. Always double check DATABASE_URL points
# at the database you actually intend to restore INTO (a staging/recovery
# database, not accidentally production) before running this.

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path-to-backup.dump>" >&2
    exit 1
fi

DUMP_FILE="$1"
if [ ! -f "$DUMP_FILE" ]; then
    echo "Backup file not found: $DUMP_FILE" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${DATABASE_URL:-}" ] && [ -f "$SCRIPT_DIR/../backend/.env" ]; then
    # shellcheck disable=SC1091
    export "$(grep -E '^DATABASE_URL=' "$SCRIPT_DIR/../backend/.env" | xargs)"
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is not set (checked env and backend/.env). Aborting." >&2
    exit 1
fi

PG_URL="${DATABASE_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

echo "About to restore $DUMP_FILE into: $PG_URL"
read -r -p "This will DROP and recreate existing objects. Continue? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

pg_restore --clean --if-exists --no-owner --dbname="$PG_URL" "$DUMP_FILE"
echo "Restore complete."
