#!/bin/bash
set -e

LOCK_FILE="/tmp/migrations.lock"

echo "Waiting for migration lock..."

# Running alembic upgrade head.
# || true at the end is a trick. It means: "If the command on the left (alembic)
# fails, treat the whole line as successful (true)".
# This prevents the script from crashing if alembic complains about already existing tables.
flock -x "$LOCK_FILE" -c "alembic upgrade head || true"
echo "Migrations check completed."

echo "Starting application..."
exec "$@"
