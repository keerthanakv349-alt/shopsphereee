#!/usr/bin/env bash
# Database backup: dumps the Postgres database to a timestamped,
# compressed file.
#
# WHY --format=custom (pg_dump's -Fc), NOT A PLAIN .sql FILE:
# Custom format is compressed automatically, restores faster, and —
# critically — supports SELECTIVE restore (pg_restore can pull back a
# single table without touching the rest) and PARALLEL restore for large
# databases. A plain SQL dump can only be restored top-to-bottom, all or
# nothing, via `psql`. For anything beyond a toy database, custom format
# is what you actually want.
#
# USAGE:
#   ./scripts/backup_db.sh
#   (reads DATABASE_URL from the environment, or backend/.env if present)
#
# In production this script is what a cron job / scheduled task calls
# nightly, with the output directory pointed at durable storage (an S3
# bucket mount, a managed backup service) — not left on the same disk as
# the database it's backing up, which wouldn't survive that disk failing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/../backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

if [ -z "${DATABASE_URL:-}" ] && [ -f "$SCRIPT_DIR/../backend/.env" ]; then
    # shellcheck disable=SC1091
    export "$(grep -E '^DATABASE_URL=' "$SCRIPT_DIR/../backend/.env" | xargs)"
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is not set (checked env and backend/.env). Aborting." >&2
    exit 1
fi

# pg_dump doesn't understand SQLAlchemy's "postgresql+psycopg2://" scheme
# prefix — strip the driver suffix down to the plain "postgresql://" libpq expects.
PG_URL="${DATABASE_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

mkdir -p "$BACKUP_DIR"
OUTPUT_FILE="$BACKUP_DIR/shopsphere_${TIMESTAMP}.dump"

echo "Backing up database to $OUTPUT_FILE ..."
pg_dump --format=custom --file="$OUTPUT_FILE" "$PG_URL"
echo "Done: $(du -h "$OUTPUT_FILE" | cut -f1) written."

# Retention: keep the last 14 backups, delete older ones. Adjust to your
# actual compliance/recovery requirements — this is a sane default, not
# a policy decision this script should be making silently forever.
ls -1t "$BACKUP_DIR"/shopsphere_*.dump | tail -n +15 | xargs -r rm --
