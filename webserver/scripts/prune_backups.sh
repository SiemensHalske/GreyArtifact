#!/usr/bin/env bash
# Delete backups in <output-directory> that are older than <keep-days>.
# Only completed backups (with SHA256SUMS, which backup.sh writes last) are
# aged out, and the newest completed backup is always kept, however old it is.
# Leftovers of interrupted runs (no SHA256SUMS) are removed after one day.
#
# Usage: webserver/scripts/prune_backups.sh <output-directory> <keep-days>
# Run it after backup_if_due.sh in the same cron entry, joined with &&, so
# nothing is deleted while backups are failing.
set -euo pipefail

usage="usage: prune_backups.sh <output-directory> <keep-days>"
output_root=${1:?$usage}
keep_days=${2:?$usage}
# Capped at five digits so keep_days * 86400 cannot overflow below.
if [[ ! "$keep_days" =~ ^[1-9][0-9]{0,4}$ ]]; then
    echo "keep-days must be a whole number from 1 to 99999" >&2
    exit 2
fi
if [[ ! -d "$output_root" ]]; then
    echo "Backup directory not found: $output_root" >&2
    exit 2
fi

# Only directories named like backup.sh's targets; find does not follow symlinks.
mapfile -t backups < <(find "$output_root" -mindepth 1 -maxdepth 1 -type d \
    -regextype posix-extended -regex '.*/greyartifact-[0-9]{8}T[0-9]{6}Z' | LC_ALL=C sort)

newest=
newest_mtime=-1
for dir in "${backups[@]}"; do
    [[ -f "$dir/SHA256SUMS" ]] || continue
    mtime=$(stat -c %Y "$dir/SHA256SUMS")
    if (( mtime > newest_mtime )); then
        newest=$dir
        newest_mtime=$mtime
    fi
done

now=$(date +%s)
for dir in "${backups[@]}"; do
    if [[ -f "$dir/SHA256SUMS" ]]; then
        [[ "$dir" != "$newest" ]] || continue
        (( $(stat -c %Y "$dir/SHA256SUMS") < now - keep_days * 86400 )) || continue
        reason="older than $keep_days days"
    else
        (( $(stat -c %Y "$dir") < now - 86400 )) || continue
        reason="incomplete, older than 1 day"
    fi
    rm -r --one-file-system -- "$dir"
    echo "Removed backup $dir ($reason)" >&2
done
