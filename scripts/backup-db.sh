#!/usr/bin/env sh
set -eu

repository_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
environment_file=${1:-"$repository_dir/.env.production"}
backup_dir=${BACKUP_DIR:-"$repository_dir/backups"}

if [ ! -f "$environment_file" ]; then
  echo "environment file not found: $environment_file" >&2
  exit 1
fi

mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_file="$backup_dir/trend-radar-$timestamp.sql"

docker compose \
  --env-file "$environment_file" \
  -f "$repository_dir/compose.prod.yaml" \
  exec -T db sh -c 'pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$backup_file"

chmod 600 "$backup_file"
echo "$backup_file"
