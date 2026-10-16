#!/usr/bin/env bash
# Daily disk check: emails every active admin when the disk holding Docker's data passes the threshold.
# Run from cron (see docs/deployment.md). Settings, optional:
#   DISK_ALERT_PERCENT  alert at or above this use   (default 80)
set -euo pipefail
cd "$(dirname "$0")/.."

threshold="${DISK_ALERT_PERCENT:-80}"
mount="$(df --output=target /var/lib/docker | tail -1 | tr -d ' ')"
used="$(df --output=pcent "$mount" | tail -1 | tr -dc '0-9')"
free="$(df -h --output=avail "$mount" | tail -1 | tr -d ' ')"

if [ "$used" -ge "$threshold" ]; then
    docker compose exec -T backend python -m app.ops.disk_alert "$used" "$free" "$mount"
    echo "$(date '+%F %T') disk $mount at ${used}% (${free} free): admins alerted"
else
    echo "$(date '+%F %T') disk $mount at ${used}% (${free} free): ok"
fi
