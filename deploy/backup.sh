#!/usr/bin/env bash
# Nightly backup of CodeAssure: the database and the stored files (review workbooks, sample templates).
# Quarterly source zips are not included: they're temporary and deleted once a review is approved.
#
# Run from cron (see docs/deployment.md). Settings, all optional:
#   BACKUP_DIR        where backups go           (default /var/backups/codeassure)
#   BACKUP_KEEP_DAYS  how many days to keep      (default 14)
#
# Restore (stop the backend first: docker compose stop backend):
#   docker compose exec -T postgres pg_restore -U postgres -d codereviews --clean --if-exists < db_<stamp>.dump
#   docker compose exec -T backend tar -xzf - -C /data < files_<stamp>.tgz
#   docker compose start backend
set -euo pipefail
cd "$(dirname "$0")/.."

dest="${BACKUP_DIR:-/var/backups/codeassure}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$dest"

# Write to .partial first, so a failed run never leaves a file that looks like a good backup.
docker compose exec -T postgres pg_dump -U postgres -d codereviews --format=custom > "$dest/db_$stamp.dump.partial"
docker compose exec -T backend tar -czf - -C /data reviews sample-templates > "$dest/files_$stamp.tgz.partial"
for f in "$dest/db_$stamp.dump" "$dest/files_$stamp.tgz"; do
    [ -s "$f.partial" ] || { echo "backup failed: $f is empty" >&2; exit 1; }
    mv "$f.partial" "$f"
done

find "$dest" -type f \( -name 'db_*.dump' -o -name 'files_*.tgz' \) -mtime +"$keep_days" -delete
find "$dest" -type f -name '*.partial' -mtime +1 -delete
echo "$(date '+%F %T') backup ok: db_$stamp.dump ($(du -h "$dest/db_$stamp.dump" | cut -f1)), files_$stamp.tgz ($(du -h "$dest/files_$stamp.tgz" | cut -f1))"
