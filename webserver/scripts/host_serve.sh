#!/usr/bin/env bash
# Keep the GreyArtifact host development server running on 127.0.0.1:<port>.
# Intended for cron: one @reboot entry and one every-minute guard entry.
# It starts the server only when nothing is listening on the configured port.
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

root=$(cd "$(dirname "$0")/../.." && pwd)
port=$(sed -n 's/^FLASK_RUN_PORT=//p' "$root/.env" 2>/dev/null || true)
port=${port:-5000}

if ss -tln 2>/dev/null | grep -q "127.0.0.1:${port} "; then
    exit 0
fi

cd "$root"
setsid nohup "$root/.venv/bin/python" webserver/src/run.py \
    >> "$root/app.log" 2>&1 < /dev/null &
