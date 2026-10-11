#!/usr/bin/env python3
"""Create the first local principal through the PostgreSQL administrator."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from dotenv import dotenv_values
from psycopg import sql
from werkzeug.security import generate_password_hash


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a local GreyArtifact principal and grant an owner membership."
        )
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--scope", default="default")
    parser.add_argument("--display-name")
    return parser.parse_args()


def require_text(value: str, label: str) -> str:
    value = value.strip()
    if not value or len(value) > 255 or "\x00" in value:
        raise ValueError(f"{label} must contain between 1 and 255 characters.")
    return value


def read_application_role() -> str:
    config = dotenv_values(PROJECT_ROOT / ".env")
    database_user = config.get("DB_USER")
    if not database_user:
        raise RuntimeError("DB_USER must be set in the root .env file.")
    return database_user


def read_password(username: str) -> str:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Repeat password: ")
    if not password:
        raise ValueError("Password must not be empty.")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    if password == username:
        print(
            "Warning: using the username as password is unsafe and suitable only "
            "for isolated local testing.",
            file=sys.stderr,
        )
    return password


def build_bootstrap_sql(
    *,
    username: str,
    password_hash: str,
    display_name: str | None,
    scope_name: str,
    application_role: str,
) -> str:
    return sql.SQL(
        """
BEGIN;

DO $bootstrap$
BEGIN
    IF EXISTS (
        SELECT 1 FROM recon.principals WHERE username = {username}
    ) THEN
        RAISE EXCEPTION 'Principal already exists';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM recon.scopes WHERE name = {scope_name}
    ) THEN
        RAISE EXCEPTION 'Scope does not exist';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM recon.roles WHERE code = 'owner'
    ) THEN
        RAISE EXCEPTION 'Owner role does not exist';
    END IF;
END
$bootstrap$;

INSERT INTO recon.principals
    (username, password_hash, display_name, is_active)
VALUES
    ({username}, {password_hash}, {display_name}, TRUE);

INSERT INTO recon.scope_memberships (scope_id, principal_id, role_id)
SELECT s.scope_id, p.principal_id, r.role_id
FROM recon.scopes AS s
CROSS JOIN recon.principals AS p
CROSS JOIN recon.roles AS r
WHERE s.name = {scope_name}
  AND p.username = {username}
  AND r.code = 'owner';

INSERT INTO recon.role_assignment_audit
    (scope_id, principal_id, changed_by, event_type, roles_before, roles_after)
SELECT s.scope_id,
       p.principal_id,
       NULL,
       'bootstrap',
       '[]'::jsonb,
       '["owner"]'::jsonb
FROM recon.scopes AS s
CROSS JOIN recon.principals AS p
WHERE s.name = {scope_name}
  AND p.username = {username};

GRANT SELECT ON
    recon.principals,
    recon.scopes,
    recon.projects,
    recon.roles,
    recon.permissions,
    recon.role_permissions,
    recon.scope_memberships,
    recon.registration_requests,
    recon.role_assignment_audit
TO {application_role};

GRANT INSERT ON
    recon.principals,
    recon.scope_memberships,
    recon.registration_requests,
    recon.role_assignment_audit
TO {application_role};

GRANT UPDATE ON
    recon.principals,
    recon.registration_requests
TO {application_role};

GRANT DELETE ON recon.scope_memberships TO {application_role};

COMMIT;
"""
    ).format(
        username=sql.Literal(username),
        password_hash=sql.Literal(password_hash),
        display_name=sql.Literal(display_name),
        scope_name=sql.Literal(scope_name),
        application_role=sql.Identifier(application_role),
    ).as_string()


def main() -> int:
    try:
        args = parse_args()
        username = require_text(args.username, "Username")
        scope_name = require_text(args.scope, "Scope")
        display_name = (
            require_text(args.display_name, "Display name")
            if args.display_name
            else None
        )
        application_role = read_application_role()
        password = read_password(username)
        statement = build_bootstrap_sql(
            username=username,
            password_hash=generate_password_hash(password),
            display_name=display_name,
            scope_name=scope_name,
            application_role=application_role,
        )
    except (RuntimeError, ValueError) as error:
        print(f"Bootstrap aborted: {error}", file=sys.stderr)
        return 2

    print(statement)
    print(
        f"Bootstrap SQL generated for principal {username!r} and scope "
        f"{scope_name!r}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
