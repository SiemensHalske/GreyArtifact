#!/usr/bin/env bash
# Restore a backup written by backup.sh into an empty database and a bucket.
#
# Usage: RESTORE_DB_NAME=<empty-database> webserver/scripts/restore.sh <backup-directory>
#
# The target database must already exist and be empty; the live DB_NAME is
# refused. Objects are imported into S3_BUCKET at S3_ENDPOINT_URL (environment
# first, then .env); existing objects are kept, every object is SHA-256 checked.
# Decryption uses the GnuPG keyring or BACKUP_PASSPHRASE_FILE.
# PG_RESTORE overrides the restore command (default: sudo -u postgres pg_restore).
# Ownership and grants are not restored; run grant_app_privileges.py afterwards.
set -euo pipefail
umask 077

root=$(cd "$(dirname "$0")/../.." && pwd)
backup=${1:?usage: restore.sh <backup-directory>}
target_db=${RESTORE_DB_NAME:?set RESTORE_DB_NAME to an existing, empty database}
live_db=$(sed -n 's/^DB_NAME=//p' "$root/.env" 2>/dev/null || true)
if [[ -n "$live_db" && "$target_db" == "$live_db" ]]; then
    echo "Refusing to restore over the live database $live_db." >&2
    exit 2
fi
read -r -a pg_restore <<< "${PG_RESTORE:-sudo -u postgres pg_restore}"

decrypt() {
    if [[ -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
        gpg --batch --quiet --decrypt --pinentry-mode loopback \
            --passphrase-file "$BACKUP_PASSPHRASE_FILE" "$1"
    else
        gpg --batch --quiet --decrypt "$1"
    fi
}

(cd "$backup" && sha256sum --check --quiet SHA256SUMS)
decrypt "$backup/postgres.dump.gpg" \
    | "${pg_restore[@]}" --no-owner --no-acl --exit-on-error --dbname "$target_db"
decrypt "$backup/artifacts.tar.gpg" \
    | "$root/.venv/bin/python" -I "$root/webserver/scripts/artifact_archive.py" import
echo "Restored $backup into database $target_db." >&2
