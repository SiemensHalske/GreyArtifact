#!/usr/bin/env bash
# Run backup.sh only when the newest *completed* backup in <output-directory>
# is older than <max-age-hours> (default 24). Meant for an hourly cron entry on
# a host that is not always on: the backup runs in the first hour the host is
# up after it became due, instead of being skipped at a fixed time of night.
#
# Usage: webserver/scripts/backup_if_due.sh <output-directory> [max-age-hours]
# Encryption settings are passed through to backup.sh.
set -euo pipefail

output_root=${1:?usage: backup_if_due.sh <output-directory> [max-age-hours]}
max_age_hours=${2:-24}
if [[ ! "$max_age_hours" =~ ^[1-9][0-9]*$ ]]; then
    echo "max-age-hours must be a positive whole number" >&2
    exit 2
fi

# backup.sh writes SHA256SUMS last, so an interrupted run never counts as done.
if [[ -d "$output_root" ]] && [[ -n "$(find "$output_root" -maxdepth 2 \
        -path "$output_root/greyartifact-*/SHA256SUMS" \
        -mmin "-$((max_age_hours * 60))" -print -quit)" ]]; then
    exit 0
fi
exec "$(dirname "$0")/backup.sh" "$output_root"
