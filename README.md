# GreyArtifact

GreyArtifact is an early private-demo platform for turning security-recon
reports into normalized, traceable evidence. The current workflow covers
registration with owner approval, scoped projects, immutable report artifacts,
Subfinder/DNSx/ProjectDiscovery HTTPx imports, evidence provenance, and a
separate controlled recon runner.

This repository is an in-development architecture proof, not a public or
production-ready multi-tenant service. Never run recon against a target unless
its current authorization explicitly permits the intended automated activity.

## Repository layout

- `webserver/` contains the Flask application, runner, tests, and operational
  documentation.
- `database/migrations/` contains the PostgreSQL schema migrations.
- `docs/` contains the business plan, API contract, validation material, and
  the current private-demo acceptance audit.
- `compose.yaml` defines the isolated GreyArtifact development environment.
- `docker/docker-compose.yaml` is the deliberately separate legacy Faraday
  environment.
- `docker/caddy/compose.yaml` is the optional HTTPS reverse proxy for LAN
  access.

## Local setup

Copy `.env.example` to `.env`, fill the values locally, and keep the resulting
file private. Full setup, migrations, account bootstrap, and runner safety notes
are documented in [webserver/README.md](webserver/README.md).

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

## Current status

The evidence workflow has automated unit/API coverage and disposable
PostgreSQL/MinIO integration coverage. Browser acceptance, an explicitly
authorized real-runner smoke test, and market validation remain open. See the
[acceptance audit](docs/validation/acceptance-audit-2026-10-11.md) for the
verified status and next gates.

## License

GreyArtifact is source-visible proprietary software, not open-source software.
Source review and narrowly limited non-production evaluation are permitted;
production use, redistribution, and integration require a separate written
license. See the [GreyArtifact Source-Visible License 1.0](LICENSE.md).
