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

PostgreSQL applies migrations 001–005 only when its volume is created for the
first time. MinIO is built from the official, pinned
`RELEASE.2025-10-15T17-29-55Z` source because anonymous official community
images are no longer reliably distributed. Review the MinIO AGPLv3 obligations
before redistribution.

Apply migrations explicitly and in numeric order as the PostgreSQL
administrator. For an existing database that already has migrations 001-003,
apply the composable-role migration with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  -f database/migrations/004_composable_roles_audit.sql
```

Upgrade a database already at migration 004 to the private-demo schema with:

```text
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 \
  -f database/migrations/005_private_demo_slice.sql
```

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
| `owner` | Analyst permissions plus `scope.manage`, `membership.manage`, `pipeline.manage`, `recon.execute` |

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
shared between the dashboard and admin page through tab-scoped session storage
and is removed on logout.

## Imports, evidence, and recon

Multipart uploads are stored under content-addressed
`sha256/<prefix>/<digest>` keys. The application calculates SHA-256 while
copying the bounded stream, uses conditional S3 creation, and records separate
imports for deduplicated artifacts. Uploading never starts parsing or recon;
the user explicitly triggers report processing.

Versioned JSONL parsers support Subfinder, DNSx, and ProjectDiscovery HTTPx.
One invalid non-empty line fails the import while preserving its raw artifact.
Asset evidence links back through parser version, import, artifact hash, and an
optional recon step.

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

The integration suite checks a fresh five-migration install, upgrade from 004
to 005, the owner-only recon permission, and real MinIO object deduplication.
