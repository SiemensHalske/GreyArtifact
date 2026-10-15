# GreyArtifact

GreyArtifact is a self-hosted recon vault. It turns security-recon output into
normalized, traceable evidence and keeps findings, ML prioritization and their
provenance in one place. It runs on a single host with PostgreSQL and MinIO
behind a Caddy HTTPS reverse proxy.

The current workflow covers:

- registration with owner approval, scoped projects, and composable roles and
  permissions;
- immutable, content-addressed raw artifacts with provenance for every derived
  asset, property and relationship;
- Subfinder, DNSx, ProjectDiscovery HTTPx and Nuclei imports, and findings with
  audited status changes and append-only analyst notes;
- run packages from Fennec (`recon_pipeline` with `recon_ml`): a mandatory ML
  result, an ML prioritization view, analyst reviews exported back to
  `recon_ml`, and Stage-8 claim states, acquisition candidates and
  recommendations shown read-only;
- a separate controlled recon runner that starts only from an authorized
  engagement.

This repository is an in-development architecture proof, not a production-ready
multi-tenant service. Never run recon against a target unless its current
authorization explicitly permits the intended automated activity. GreyArtifact
never executes an ML recommendation; execution stays with an engagement and the
controlled runner.

## Repository layout

- `webserver/` contains the Flask application, runner, tests, operational
  scripts (backup, restore, host supervision) and the operational
  documentation.
- `database/migrations/` contains the PostgreSQL schema migrations, applied in
  numeric order.
- `docs/` contains the API contract, the Fennec run-manifest schema
  (`greyartifact-run-manifest-v1.schema.json`), the business plan and
  validation material.
- `plans/` contains the roadmap and the Fennec integration plan.
- `compose.yaml` defines the isolated GreyArtifact development environment;
  `compose.host.yaml` runs only MinIO, bound to loopback, for the host
  development server.
- `docker/caddy/compose.yaml` is the HTTPS reverse proxy for LAN access.
- `docker/docker-compose.yaml` is the deliberately separate legacy Faraday
  environment.

## Local setup

Copy `.env.example` to `.env`, fill the values locally, and keep the resulting
file private. Full setup, migrations, account bootstrap, HTTPS, backups and
runner safety notes are documented in [webserver/README.md](webserver/README.md).

Start the GreyArtifact Compose environment with:

```text
docker compose up --build
```

Run the default test suite without real network recon:

```text
PYTHONPATH=webserver/src .venv/bin/python -m unittest discover -s webserver/tests
```

Export and lint the OpenAPI contract with:

```text
npm ci
npm run api:export
npm run api:lint
```

Swagger UI is served at `/api/docs`; the generated OpenAPI 3.0.3 document is
served at `/api/v1/openapi.json`.

## Fennec integration

Fennec exports one engagement as a run package (manifest, predictions,
observations and, where available, Stage-8 claims):

```text
python -m recon_pipeline --database "$FENNEC_DATABASE_URL" export <engagement-key> --output <dir>
```

The package is imported with `POST /api/v1/projects/<project-id>/import-batches`.
Analyst reviews are exported with
`GET …/import-batches/<batch-id>/review-feedback` and applied in Fennec with:

```text
python -m recon_ml.review --database "$FENNEC_DATABASE_URL" import-feedback <file> --analyst <key>
```

A prediction is a triage ranking, never an automatic finding, and a package
without a completed `recon_ml` result is rejected.

## Current status

Unit/API tests, disposable PostgreSQL/MinIO integration tests and the Fennec
path with real data are verified; the server runs behind HTTPS with encrypted
nightly backups. Browser acceptance with login, an explicitly authorized
real-runner smoke test and market validation remain open. See the
[roadmap](plans/roadmap.md) and the
[acceptance audit](docs/validation/acceptance-audit-2026-10-14.md).

## License

GreyArtifact is source-visible proprietary software, not open-source software.
Source review and narrowly limited non-production evaluation are permitted;
production use, redistribution, and integration require a separate written
license. See the [GreyArtifact Source-Visible License 1.0](LICENSE.md).
