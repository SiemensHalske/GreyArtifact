#!/usr/bin/env python3
"""Generate the PostgreSQL grants required by the GreyArtifact web app."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import dotenv_values
from psycopg import sql


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_application_role() -> str:
    database_user = dotenv_values(PROJECT_ROOT / ".env").get("DB_USER")
    if not database_user:
        raise RuntimeError("DB_USER must be set in the root .env file.")
    return database_user


def build_grant_sql(application_role: str) -> str:
    return sql.SQL(
        """
BEGIN;

GRANT SELECT ON
    recon.principals,
    recon.scopes,
    recon.projects,
    recon.roles,
    recon.permissions,
    recon.role_permissions,
    recon.scope_memberships,
    recon.registration_requests,
    recon.role_assignment_audit,
    recon.tools,
    recon.artifacts,
    recon.imports,
    recon.asset_types,
    recon.assets,
    recon.project_assets,
    recon.property_types,
    recon.asset_property_observations,
    recon.relationship_types,
    recon.asset_relationship_observations,
    recon.findings,
    recon.finding_status_audit,
    recon.finding_notes,
    recon.import_batches,
    recon.ml_predictions,
    recon.ml_prediction_reviews,
    recon.ml_claims,
    recon.engagements,
    recon.engagement_targets,
    recon.recon_runs,
    recon.recon_run_steps
TO {application_role};

GRANT INSERT ON
    recon.principals,
    recon.projects,
    recon.scope_memberships,
    recon.registration_requests,
    recon.role_assignment_audit,
    recon.tools,
    recon.artifacts,
    recon.imports,
    recon.assets,
    recon.project_assets,
    recon.asset_property_observations,
    recon.asset_relationship_observations,
    recon.findings,
    recon.finding_status_audit,
    recon.finding_notes,
    recon.import_batches,
    recon.ml_predictions,
    recon.ml_prediction_reviews,
    recon.ml_claims,
    recon.engagements,
    recon.engagement_targets,
    recon.recon_runs,
    recon.recon_run_steps
TO {application_role};

GRANT UPDATE ON
    recon.principals,
    recon.projects,
    recon.registration_requests,
    recon.imports,
    recon.engagements,
    recon.recon_runs,
    recon.recon_run_steps
TO {application_role};

GRANT UPDATE (status, updated_at) ON recon.findings TO {application_role};

GRANT DELETE ON
    recon.scope_memberships,
    recon.asset_property_observations,
    recon.asset_relationship_observations,
    recon.findings,
    recon.engagement_targets
TO {application_role};

COMMIT;
"""
    ).format(application_role=sql.Identifier(application_role)).as_string()


def main() -> int:
    try:
        application_role = read_application_role()
    except RuntimeError as error:
        print(f"Grant generation aborted: {error}", file=sys.stderr)
        return 2

    print(build_grant_sql(application_role))
    print(
        f"Grant SQL generated for application role {application_role!r}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
