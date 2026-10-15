#!/usr/bin/env bash
# Keep the GreyArtifact web app running under gunicorn on 127.0.0.1:<port>,
# behind the reverse proxy. Intended for cron: one @reboot entry and one
# every-minute guard entry. It starts the app only when nothing is listening
# on the configured port.
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

root=$(cd "$(dirname "$0")/../.." && pwd)
port=$(sed -n 's/^FLASK_RUN_PORT=//p' "$root/.env" 2>/dev/null || true)
port=${port:-5000}

if ss -tln 2>/dev/null | grep -q "127.0.0.1:${port} "; then
    exit 0
fi

cd "$root"
# One worker keeps the in-process login throttle exact (several workers would
# each count failures separately); threads serve concurrent requests. The
# timeout matches the proxy's read timeout for large imports. The access log
# records the client address the proxy put into X-Real-IP.
setsid nohup "$root/.venv/bin/gunicorn" \
    --chdir webserver/src \
    --bind "127.0.0.1:${port}" \
    --workers 1 --worker-class gthread --threads 8 \
    --timeout 300 \
    --no-control-socket \
    --access-logfile - \
    --access-logformat '%({x-real-ip}i)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms' \
    'app:create_app()' \
    >> "$root/app.log" 2>&1 < /dev/null &
