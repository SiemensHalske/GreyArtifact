# GreyArtifact web server and controlled runner

The Flask application manages identities, projects, immutable report artifacts,
normalized evidence, engagements, and recon jobs. It never starts tools in the
request process. The separate runner accepts only the fixed
`domain_basic_v1` profile (`subfinder → dnsx → ProjectDiscovery httpx`) and
never accepts free commands or caller-supplied CLI arguments.

Configuration is loaded from the repository-root `.env`, independent of the
current working directory. `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, and a private `JWT_SECRET_KEY` are required. Placeholder secrets
using `CHANGE_ME` are rejected.

Artifact storage additionally requires `S3_ENDPOINT_URL`, `S3_BUCKET`,
`S3_ACCESS_KEY`, and `S3_SECRET_KEY`. `MAX_ARTIFACT_BYTES` defaults to 100 MiB.
Copy `.env.example` to `.env` and fill the values locally; the example contains
key names only and `.env` is ignored.

## Local Compose environment

`compose.yaml` is GreyArtifact's own environment and is independent of the
existing Faraday file at `docker/docker-compose.yaml`. It starts PostgreSQL,
MinIO, the web application, and the separate runner:

```text
docker compose up --build
```

PostgreSQL applies migrations 001–012 only when its volume is created for the
first time. MinIO is built from the official, pinned
`RELEASE.2025-10-15T17-29-55Z` source because anonymous official community
images are no longer reliably distributed. Review the MinIO AGPLv3 obligations
before redistribution.

Apply migrations explicitly and in numeric order as the PostgreSQL
administrator, from the repository root. The file is passed on standard input
because the `postgres` account cannot read files inside a private home
directory (`psql -f` fails there with "permission denied"). For an existing
database that already has migrations 001-003, apply the composable-role
migration with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/004_composable_roles_audit.sql
```

Upgrade a database already at migration 004 to the private-demo schema with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/005_private_demo_slice.sql
```

Enable generic asset-list imports on an existing private-demo database with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/006_generic_asset_imports.sql
```

Enable normalized Nuclei findings on an existing database with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/007_findings.sql
```

Enable audited finding triage and the `sensitive.read` permission with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/008_finding_triage.sql
```

Enable append-only analyst notes on findings with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/009_finding_notes.sql
```

Revoke existing access tokens on password changes with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/010_credentials_version.sql
```

Access tokens carry the principal's `credentials_version`. Changing the
password increments it, so every earlier token is rejected; the response to
`PUT /api/v1/auth/password` contains a fresh token for the current session.
Deactivated principals are rejected regardless of their token.

Enable batched run imports with a mandatory recon_ml result and per-asset
predictions with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/011_fennec_import_batches.sql
```

The import package format is defined by
`docs/greyartifact-run-manifest-v1.schema.json`
(`greyartifact-run-manifest/v1`). A package always carries a completed
`recon_ml` result; the model status is kept per batch and per prediction, and a
prediction is only a triage ranking, never an automatic finding.

Enable the append-only analyst feedback on predictions with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/012_ml_prediction_reviews.sql
```

Principals with `data.import` record one of four Stage-7 decisions per
prediction through `POST …/ml-predictions/<prediction-id>/review`
(`expected`, `data_artifact`, `review_worthy`, `confirmed_finding`). Reviews are
append-only; the latest per prediction is shown with each prediction.
`GET …/import-batches/<batch-id>/review-feedback` exports the latest decision
per reviewed prediction as JSONL (entity, engagement_ref, inference_run_ref,
decision, note) for recon_ml's `submit_review`; Fennec applies it with
`python -m recon_ml.review import-feedback <file> --analyst <key>`.

Enable the optional Stage-8 claim states of a package with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  < database/migrations/013_ml_claims.sql
```

A package may carry `claims.jsonl` (`recon_ml_claims_v1`): per asset the current
claim states with evidence reasons, open acquisition candidates and any
recommendation with its Fennec decision. `GET …/import-batches/<batch-id>/claims`
returns counts per claim and state, and one asset's claims with `asset_id`.
They are display only: GreyArtifact never executes a candidate; execution stays
with an engagement and the controlled runner.

After applying the migrations, grant an existing application role the least
privileges required by identity management, imports, evidence, engagements,
and the runner without recreating or changing the owner account:

```text
set -o pipefail
PYTHONPATH=webserver/src .venv/bin/python \
  webserver/scripts/grant_app_privileges.py | \
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1
```

Start the development server from the repository root with:

```text
.venv/bin/python webserver/src/run.py
```

Keep `FLASK_RUN_HOST=127.0.0.1` and `FLASK_DEBUG=0` whenever the host is
reachable from a network: the Werkzeug debugger allows code execution.

On a host reachable from a network, run the app under gunicorn behind the
reverse proxy instead. `webserver/scripts/host_serve.sh` starts it on
`127.0.0.1:${FLASK_RUN_PORT:-5000}` with one worker and eight threads: the
login throttle counts failures in process memory, so several workers would each
keep their own count. It is meant for cron (`@reboot` plus an every-minute
guard) and appends to `app.log`.

### Artifact storage for the host development server

When the web process runs directly on the host, start only MinIO from the
Compose environment and publish its S3 API on loopback:

```text
docker compose -f compose.yaml -f compose.host.yaml up -d --build minio minio-init
```

Set `S3_ENDPOINT_URL=http://127.0.0.1:9000` and the remaining `S3_*` values in
the root `.env`; `S3_ACCESS_KEY` and `S3_SECRET_KEY` are also MinIO's root
credentials.

### HTTPS for LAN access

`docker/caddy/compose.yaml` runs Caddy with host networking in front of the
web process on `127.0.0.1:${FLASK_RUN_PORT}`. It serves the addresses in
`TLS_SITE_ADDRESSES` (for example `192.168.2.4, localhost`) on port 443 with
certificates from Caddy's local CA and redirects port 80 to HTTPS. The admin
API is disabled, so configuration changes require a container restart.

```text
docker compose -f docker/caddy/compose.yaml --env-file .env up -d
```

Import the local root certificate once into each client browser:

```text
docker exec greyartifact-proxy-caddy-1 \
  cat /data/caddy/pki/authorities/local/root.crt > greyartifact-root.crt
```

The CA private key lives in the `greyartifact-proxy_caddy-data` volume and must
be protected like any other secret.

Set `TRUSTED_PROXY_COUNT=1` while the web process is reachable only through this
proxy, so client addresses are taken from `X-Forwarded-For`. Keep it unset or
`0` without a proxy; otherwise clients could spoof their address.

Failed logins are throttled per process: after 5 failures for one username or
20 failures from one client address within 15 minutes, `POST
/api/v1/auth/login` answers `429` with `Retry-After` until the window passes.
A successful login clears the username counter. The counters are kept in
memory and reset on restart.

The initial migrations intentionally create no login. Before the login endpoint
can be used, an operator must perform a controlled bootstrap that creates a
password-hashed row in `recon.principals` and assigns that principal the
`owner` role in the intended scope. No default account or password is provided.

Generate the bootstrap SQL with the local helper and execute it explicitly as
the PostgreSQL administrator:

```text
set -o pipefail
PYTHONPATH=webserver/src .venv/bin/python webserver/scripts/bootstrap_user.py \
  --username <name> --display-name <display-name> | \
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1
```

The helper prompts for the password without echoing it. The first owner can
then create further local accounts from the dashboard. Account creation is
scope-bound, requires the live `membership.manage` permission, accepts one base
role, and requires an initial password of at least 12 characters.

The base roles and their permissions are:

| Role | Permissions |
|---|---|
| `viewer` | `scope.read`, `data.read` |
| `researcher` | Viewer permissions plus `data.import`, `data.delete` |
| `analyst` | Researcher permissions plus `project.manage` |
| `owner` | Analyst permissions plus `scope.manage`, `membership.manage`, `pipeline.manage`, `recon.execute`, `sensitive.read` |

`pipeline_operator` is an optional additional role that grants only
`pipeline.execute`. It does not grant `recon.execute`; controlled recon is
owner-only. `data.delete` applies to imported data in the entire scope, not
only to a principal's own uploads.

Users can also submit a registration request for a named workspace. A request
creates an inactive principal and never grants a membership by itself. A scope
owner must approve it in the dashboard and choose a role before login is
possible. Unknown workspaces and duplicate usernames receive the same generic
response to avoid exposing account or workspace existence.

The standalone registration page is `/register`. The dashboard keeps the same
flow available next to login for compatibility.

The dedicated administration workspace is available at `/admin`. It only lists
scopes in which the signed-in principal currently has `membership.manage` and
provides the registration queue, member overview, role approval, rejection, and
direct account creation. Owners can change a member's base role and explicit
Pipeline Operator assignment after creation. The last owner of a scope cannot
be demoted. Every effective role change is recorded in an append-only audit and
is visible in the administration workspace. The short-lived access token is
shared between the dashboard, project workspace, and admin page through
tab-scoped session storage and is removed on logout. Selecting a project on the
dashboard opens its dedicated workspace at `/projects/<project-id>`; imports,
evidence, recon, and project settings remain outside the dashboard.

The account avatar in the shared top bar opens the account menu. Anonymous
users reach the standalone `/login` page; signed-in users get profile and
logout actions. `/profile` allows a user to update their display name and
change their password after confirming the current password. The Administration navigation
entry remains hidden until `/api/v1/scopes/manageable` confirms at least one
scope with `membership.manage`; direct access by another signed-in user shows a
denial instead of the management workspace.

### Security headers

Every response carries a strict `Content-Security-Policy` (`default-src 'self'`,
no inline scripts or styles, `frame-ancestors 'none'`), `X-Content-Type-Options:
nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`. Only
`/api/docs` additionally allows `https://cdn.jsdelivr.net` for Swagger UI.
Templates therefore must not contain inline `<script>` or `<style>` blocks or
`style` attributes; put them under `static/`.

### Backup and restore

`webserver/scripts/backup.sh <output-directory>` writes a timestamped directory
outside the repository with `postgres.dump.gpg` (`pg_dump --format=custom`),
`artifacts.tar.gpg` (every bucket object via `artifact_archive.py export`), and
`SHA256SUMS`. Both streams are encrypted before they reach the disk; set either
`BACKUP_GPG_RECIPIENT` (public-key encryption, preferred) or
`BACKUP_PASSPHRASE_FILE` (symmetric AES-256). The database dump runs as
`sudo -u postgres pg_dump` unless `PG_DUMP` overrides the command.

```text
BACKUP_GPG_RECIPIENT=<key-id> webserver/scripts/backup.sh /srv/data/greyartifact-backups
```

For an unattended cron job, allow exactly that dump command without a password
(`sudo visudo -f /etc/sudoers.d/greyartifact-backup`):

```text
<user> ALL=(postgres) NOPASSWD: /usr/bin/pg_dump --format=custom <db-name>
```

Do not widen the rule to arbitrary `pg_dump` arguments: `-f` would let the user
write files as `postgres`. `backup.sh` never deletes older backups.

`webserver/scripts/restore.sh <backup-directory>` verifies the checksums,
restores into the existing, empty database named by `RESTORE_DB_NAME` (the live
`DB_NAME` is refused) without owners or grants, and imports the objects into
`S3_BUCKET`. Every object is re-hashed and must match its SHA-256 key; objects
already present are kept. Apply `grant_app_privileges.py` to the restored
database before pointing the application at it.

```text
sudo -u postgres createdb recon_restore
RESTORE_DB_NAME=recon_restore webserver/scripts/restore.sh <backup-directory>
```

Backups contain unredacted raw artifacts. Store them and the decryption key
separately from the server.

### Public pages

`/` is a public landing page; the dashboard lives at `/dashboard`. `/impressum`
and `/datenschutz` render the plain-text files named by `IMPRINT_FILE` and
`PRIVACY_FILE`. Keep those files outside the repository, since an imprint
contains the operator's postal address. Without a file the routes answer 404
and the footer and sidebar links are hidden; the text is escaped and line
breaks are kept.

### System status

`/status` shows live checks from `GET /api/v1/system/status` to principals with
`membership.manage` in any scope; everyone else gets 404. It reports app uptime,
database and object-storage latency, the newest backup in `STATUS_BACKUP_DIR`
(warning after 26 h; error after 50 h or without `SHA256SUMS`), the TLS
certificate of `STATUS_TLS_HOSTNAME` fetched from `STATUS_TLS_ADDRESS` (default
`127.0.0.1:443`; warning below 14 days, error below 3), the latest result per
address family in the dynv6 log `STATUS_DDNS_LOG` (warning after 7 h or on a
failed update), and disk usage of the comma-separated `STATUS_DISK_PATHS`
(default `/`; warning at 85 %, error at 95 %). Unset settings are shown as not
configured.

## Imports, evidence, and recon

Multipart uploads are stored under content-addressed
`sha256/<prefix>/<digest>` keys. The application calculates SHA-256 while
copying the bounded stream, uses conditional S3 creation, and records separate
imports for deduplicated artifacts. Uploading never starts parsing or recon;
the user explicitly triggers report processing.

Imports are not limited to tool output. The project workspace accepts UTF-8
lists containing one domain, IPv4/IPv6 address, or HTTP(S) URL per line, either
as a text file or pasted directly. Blank lines and `#` comments are ignored.
The exact submitted text remains the immutable artifact, while each normalized
asset records its original line and value as provenance.

Versioned JSONL parsers support Subfinder, DNSx, and ProjectDiscovery HTTPx.
One invalid non-empty line fails the import while preserving its raw artifact.
Asset evidence links back through parser version, import, artifact hash, and an
optional recon step.

The ProjectDiscovery Nuclei JSONL parser creates findings. Extracted results
and URL query strings are never copied into findings; they remain only in the
raw artifact. Principals with `data.import` change a finding's status through
`PUT /api/v1/projects/<project-id>/findings/<finding-id>/status`; every effective
change is recorded in the append-only `finding_status_audit` table. The same
principals add analyst notes (1–4000 characters) through
`POST …/findings/<finding-id>/notes`; notes cannot be edited or deleted.
`GET …/findings/<finding-id>/history` returns status changes and notes in
chronological order to anyone with `data.read`. Notes are stored unencrypted
and must not contain secrets.

Downloading a raw artifact requires `sensitive.read` in addition to `data.read`
while its import is not yet completed, because unprocessed content is
unclassified, or when any import of the same deduplicated artifact produced a
sensitive finding. Imports expose this as `requires_sensitive_access`.

A whole reconnaissance run is imported as one package through `POST /api/v1/projects/<project-id>/import-batches` (`data.import`). The multipart request carries a `greyartifact-run-manifest/v1` manifest (field `manifest`) and every referenced file under its manifest path. The manifest requires a completed `recon_ml` block, and each file's SHA-256 must match before anything is stored. Tool files are parsed by their usual parsers; the predictions file uses `recon_ml_predictions_v1` and fills `ml_predictions` (one triage ranking per asset, never an automatic finding). A run is unique per `(project, source, external_ref)`; re-importing it returns `409`.

Runs and their rankings are read through `GET /api/v1/projects/<project-id>/import-batches` and `GET /api/v1/projects/<project-id>/import-batches/<batch-id>/predictions` (ordered by rank, cursor-paginated). The project workspace shows them under the “ML-Priorisierung” tab, with the model status always visible and candidate models marked as not validated.

The `greyartifact_observations` parser (`greyartifact_observations_v1`) ingests normalized recon data: each JSONL line is one asset with optional `properties` (http_status, title, server, content_type, tls_subject_cn, tls_issuer_cn, tls_not_before, tls_not_after, source_value) and `relationships` (resolves_to, hosts) to other assets. It maps onto the same asset/property/relationship model the tool parsers use, so a producer can carry its full normalized inventory without a tool-specific format.

The Fennec exporter lives in the separate recon pipeline (`recon_pipeline/.../recon_pipeline/export_greyartifact.py`, CLI `recon_pipeline export <engagement> --output <dir>`). It builds one package per engagement: the mandatory predictions file plus an observations file derived from Fennec's normalized tables, excluding proxy/Tor/secret data and loopback addresses.

An owner can start a run only for a currently valid engagement with at least
one allowed domain. The immutable run snapshot contains the authorization URL,
validity, allow/exclude targets, and fixed limits. Exclusions win over allows,
and every Subfinder result is checked again before DNSx and HTTPx. The runner:

- claims PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`;
- invokes absolute, pinned ProjectDiscovery binaries with argument arrays and
  `shell=False`;
- limits time, memory, file descriptors, concurrency, rates, output size, and
  hosts;
- terminates the process group on cancellation; and
- commits each raw step artifact before normalization, preserving partial
  evidence after failure or cancellation.

The runner image contains Subfinder v2.16.0, DNSx v1.3.1, and ProjectDiscovery
HTTPx v1.12.0. `/usr/bin/httpx` on the host is never consulted.

Never use the runner against a target unless its current program rules clearly
permit automated subdomain enumeration, DNS resolution, and HTTP probing. If
the permission is ambiguous, use only the fixtures in `webserver/tests/fixtures`
or an owned test lab.

## API contract

The generated OpenAPI 3.0.3 document is served at
`/api/v1/openapi.json`; Swagger UI is at `/api/docs`. Flask-Smorest and
Marshmallow schemas drive runtime request validation and the contract.

Export and lint the contract using commands that can later run unchanged in CI:

```text
npm ci
npm run api:export
npm run api:lint
```

Redocly CLI is pinned in `package-lock.json`. The repository intentionally does
not yet contain a platform-specific CI workflow.

## Verification

Run the default unit/API/fake-runner suite without network recon:

```text
PYTHONPATH=webserver/src .venv/bin/python -m unittest discover -s webserver/tests
```

GitHub Actions (`.github/workflows/test.yml`) runs this suite, checks the
shell scripts' syntax, and fails when `docs/openapi.json` differs from a fresh
export or does not pass `npm run api:lint`.

The PostgreSQL/MinIO tests are opt-in and require disposable services. The
tested Compose overlay exposes them on loopback only:

```text
docker compose -p greyartifact-integration \
  -f compose.yaml -f compose.integration.yaml up -d --build \
  postgres minio-permissions minio minio-init

GREYARTIFACT_INTEGRATION=1 \
INTEGRATION_DB_HOST=127.0.0.1 INTEGRATION_DB_PORT=55432 \
INTEGRATION_DB_NAME=<db> INTEGRATION_DB_USER=<user> \
INTEGRATION_DB_PASSWORD=<password> \
INTEGRATION_S3_ENDPOINT=http://127.0.0.1:59000 \
INTEGRATION_S3_ACCESS_KEY=<access-key> \
INTEGRATION_S3_SECRET_KEY=<secret-key> \
INTEGRATION_S3_BUCKET=<bucket> \
PYTHONPATH=webserver/src .venv/bin/python -m unittest \
  discover -s webserver/tests -p 'test_postgres_minio.py' -v
```

The integration suite checks a fresh install of all migrations, upgrade from
004 through 012, the owner-only `recon.execute` and `sensitive.read`
permissions, and real MinIO object deduplication.
