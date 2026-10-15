#!/usr/bin/env bash
# Write an encrypted backup of the PostgreSQL database and the artifact bucket.
#
# Usage: webserver/scripts/backup.sh <output-directory>
#
# Encryption (required, plaintext never touches the disk):
#   BACKUP_GPG_RECIPIENT    public-key encryption for this key ID (preferred)
#   BACKUP_PASSPHRASE_FILE  symmetric AES-256 with the passphrase in this file
# PG_DUMP overrides the dump command (default: sudo -u postgres pg_dump).
set -euo pipefail
umask 077

root=$(cd "$(dirname "$0")/../.." && pwd)
output_root=$(realpath -m "${1:?usage: backup.sh <output-directory>}")
if [[ "$output_root/" == "$root/"* ]]; then
    echo "Refusing to write backups inside the repository: $output_root" >&2
    exit 2
fi
mkdir -p "$output_root"

db_name=${DB_NAME:-$(sed -n 's/^DB_NAME=//p' "$root/.env")}
: "${db_name:?DB_NAME is not set}"
read -r -a pg_dump <<< "${PG_DUMP:-sudo -u postgres pg_dump}"

encrypt() {
    if [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
        gpg --batch --yes --encrypt --recipient "$BACKUP_GPG_RECIPIENT" --output "$1"
    elif [[ -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
        gpg --batch --yes --symmetric --cipher-algo AES256 --pinentry-mode loopback \
            --passphrase-file "$BACKUP_PASSPHRASE_FILE" --output "$1"
    else
        echo "Set BACKUP_GPG_RECIPIENT or BACKUP_PASSPHRASE_FILE." >&2
        return 2
    fi
}

target="$output_root/greyartifact-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$target"
"${pg_dump[@]}" --format=custom "$db_name" | encrypt "$target/postgres.dump.gpg"
"$root/.venv/bin/python" -I "$root/webserver/scripts/artifact_archive.py" export \
    | encrypt "$target/artifacts.tar.gpg"
(cd "$target" && sha256sum postgres.dump.gpg artifacts.tar.gpg > SHA256SUMS)
echo "Backup written to $target" >&2
