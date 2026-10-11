import io
import json
import secrets
import unittest
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
    Artifact,
    Asset,
    AssetType,
    Engagement,
    EngagementTarget,
    ImportRecord,
    Permission,
    Principal,
    Project,
    PropertyType,
    ReconRun,
    ReconRunStep,
    RelationshipType,
    Role,
    RolePermission,
    Scope,
    ScopeMembership,
)
from support import InMemoryArtifactStorage


FIXTURES = Path(__file__).parent / "fixtures"


class ImportApiTestCase(unittest.TestCase):
    def setUp(self):
        self.username = f"owner-{secrets.token_hex(6)}"
        self.password = secrets.token_urlsafe(24)
        self.app = create_app(
            {
                "TESTING": True,
                "JWT_SECRET_KEY": secrets.token_urlsafe(48),
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "execution_options": {"schema_translate_map": {"recon": None}}
                },
            }
        )
        self.client = self.app.test_client()
        self.storage = InMemoryArtifactStorage()
        self.app.extensions["artifact_storage"] = self.storage
        with self.app.app_context():
            connection = db.engine.raw_connection()
            connection.create_function("btrim", 1, lambda value: value.strip())
            connection.close()
            db.create_all()
            self.principal = Principal(
                principal_id=uuid4(),
                username=self.username,
                password_hash=generate_password_hash(self.password),
                is_active=True,
            )
            self.scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            self.project = Project(
                project_id=uuid4(),
                scope_id=self.scope.scope_id,
                slug="fixture-project",
                name="Fixture project",
            )
            owner = Role(role_id=1, code="owner", label="Owner")
            permission_codes = [
                "scope.read",
                "scope.manage",
                "project.manage",
                "data.read",
                "data.import",
                "recon.execute",
            ]
            permissions = [
                Permission(permission_id=index, code=code, label=code)
                for index, code in enumerate(permission_codes, start=1)
            ]
            db.session.add_all(
                [self.principal, self.scope, self.project, owner, *permissions]
            )
            db.session.flush()
            db.session.add(
                ScopeMembership(
                    scope_id=self.scope.scope_id,
                    principal_id=self.principal.principal_id,
                    role_id=owner.role_id,
                )
            )
            db.session.add_all(
                [
                    RolePermission(
                        role_id=owner.role_id,
                        permission_id=permission.permission_id,
                    )
                    for permission in permissions
                ]
            )
            for index, code in enumerate(
                ["domain", "ipv4", "ipv6", "url", "service_endpoint"], start=1
            ):
                db.session.add(AssetType(asset_type_id=index, code=code, label=code))
            db.session.add_all(
                [
                    RelationshipType(relationship_type_id=1, code="resolves_to", label="Resolves to"),
                    RelationshipType(relationship_type_id=2, code="hosts", label="Hosts"),
                ]
            )
            for index, code in enumerate(
                [
                    "http_status",
                    "title",
                    "server",
                    "content_type",
                    "tls_subject_cn",
                    "tls_issuer_cn",
                    "tls_not_before",
                    "tls_not_after",
                ],
                start=1,
            ):
                db.session.add(
                    PropertyType(
                        property_type_id=index,
                        code=code,
                        label=code,
                        value_kind="number" if code == "http_status" else "text",
                    )
                )
            db.session.commit()
            self.project_id = self.project.project_id
            self.scope_id = self.scope.scope_id
            self.principal_id = self.principal.principal_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def _headers(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def _upload(self, fixture, tool):
        content = (FIXTURES / fixture).read_bytes()
        return self.client.post(
            f"/api/v1/projects/{self.project_id}/imports",
            headers=self._headers(),
            data={"tool": tool, "file": (io.BytesIO(content), fixture)},
            content_type="multipart/form-data",
        )

    def test_upload_is_pending_and_sha256_deduplicated(self):
        first = self._upload("dnsx.jsonl", "dnsx")
        second = self._upload("dnsx.jsonl", "dnsx")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.get_json()["import"]["status"], "pending")
        self.assertEqual(second.status_code, 201)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(Artifact.artifact_id))), 1)
            self.assertEqual(db.session.scalar(select(func.count(ImportRecord.import_id))), 2)
            self.assertEqual(db.session.scalar(select(func.count(Asset.asset_id))), 0)

    def test_dnsx_import_normalizes_assets_and_preserves_provenance(self):
        uploaded = self._upload("dnsx.jsonl", "dnsx")
        import_id = uploaded.get_json()["import"]["import_id"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_id}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)
        self.assertEqual(processed.get_json()["import"]["status"], "completed")

        assets = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets?type=domain",
            headers=self._headers(),
        ).get_json()["assets"]
        self.assertEqual(
            {item["canonical_value"] for item in assets},
            {"api.example.test", "www.example.test"},
        )
        api_asset = next(
            item for item in assets if item["canonical_value"] == "api.example.test"
        )
        detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets/{api_asset['asset_id']}",
            headers=self._headers(),
        )
        self.assertEqual(detail.status_code, 200)
        observation = detail.get_json()["observations"][0]
        self.assertEqual(observation["import_id"], import_id)
        self.assertEqual(observation["parser_name"], "dnsx")
        self.assertEqual(observation["parser_version"], "dnsx_jsonl_v1")
        self.assertEqual(observation["evidence_locator"], "line:1")
        self.assertEqual(len(observation["artifact_sha256"]), 64)
        self.assertIsNone(observation["recon_run_id"])
        self.assertIsNone(observation["recon_run_step_id"])

    def test_httpx_numeric_property_is_returned_as_number(self):
        uploaded = self._upload("httpx.jsonl", "httpx")
        import_id = uploaded.get_json()["import"]["import_id"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_id}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)

        assets = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets?type=url",
            headers=self._headers(),
        ).get_json()["assets"]
        detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets/{assets[0]['asset_id']}",
            headers=self._headers(),
        )
        observations = {
            item["code"]: item["value"]
            for item in detail.get_json()["observations"]
            if item["kind"] == "property"
        }
        self.assertEqual(observations["http_status"], 200)
        self.assertIsInstance(observations["http_status"], int)

    def test_invalid_jsonl_fails_but_keeps_raw_artifact(self):
        uploaded = self._upload("invalid.jsonl", "subfinder")
        body = uploaded.get_json()["import"]
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{body['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("line 2", response.get_json()["error"]["message"])
        with self.app.app_context():
            record = db.session.get(ImportRecord, uuid4())
            self.assertIsNone(record)
            failed = db.session.execute(select(ImportRecord)).scalar_one()
            artifact = db.session.get(Artifact, failed.artifact_id)
            self.assertEqual(failed.status, "failed")
            self.assertIn(artifact.storage_key, self.storage.objects)

    def test_upload_limit_returns_413(self):
        self.storage.max_bytes = 4
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports",
            headers=self._headers(),
            data={"tool": "dnsx", "file": (io.BytesIO(b"12345"), "large.jsonl")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)

    def test_openapi_and_ui_paths_are_available(self):
        spec = self.client.get("/api/v1/openapi.json")
        self.assertEqual(spec.status_code, 200)
        self.assertEqual(spec.get_json()["openapi"], "3.0.3")
        self.assertIn("bearerAuth", spec.get_json()["components"]["securitySchemes"])
        self.assertEqual(self.client.get("/api/docs").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_owner_can_start_and_cancel_fixed_profile_run(self):
        today = date.today()
        engagement = self.client.post(
            f"/api/v1/projects/{self.project_id}/engagements",
            headers=self._headers(),
            json={
                "name": "Authorized fixture",
                "authorization_reference": "https://example.test/policy",
                "valid_from": (today - timedelta(days=1)).isoformat(),
                "valid_until": (today + timedelta(days=1)).isoformat(),
                "allowed_targets": [
                    {"domain": "Example.TEST.", "include_subdomains": True}
                ],
                "excluded_targets": [
                    {
                        "domain": "blocked.example.test",
                        "include_subdomains": True,
                    }
                ],
            },
        )
        self.assertEqual(engagement.status_code, 201)
        engagement_body = engagement.get_json()["engagement"]
        self.assertEqual(
            engagement_body["allowed_targets"][0]["domain"], "example.test"
        )

        started = self.client.post(
            f"/api/v1/engagements/{engagement_body['engagement_id']}/runs",
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 201)
        run = started.get_json()["run"]
        self.assertEqual(run["profile_code"], "domain_basic_v1")
        self.assertEqual(run["status"], "pending")
        self.assertEqual(len(run["steps"]), 3)
        self.assertEqual(
            run["configuration_snapshot"]["authorization_reference"],
            "https://example.test/policy",
        )

        cancelled = self.client.post(
            f"/api/v1/runs/{run['run_id']}/cancel", headers=self._headers()
        )
        self.assertEqual(cancelled.status_code, 200)
        cancelled_run = cancelled.get_json()["run"]
        self.assertEqual(cancelled_run["status"], "cancelled")
        self.assertTrue(cancelled_run["cancel_requested"])
        self.assertEqual(
            [step["status"] for step in cancelled_run["steps"]],
            ["cancelled"] * 3,
        )

    def test_non_owner_cannot_start_recon(self):
        today = date.today()
        created = self.client.post(
            f"/api/v1/projects/{self.project_id}/engagements",
            headers=self._headers(),
            json={
                "name": "Owner only",
                "authorization_reference": "https://example.test/policy",
                "valid_from": today.isoformat(),
                "valid_until": today.isoformat(),
                "allowed_targets": [{"domain": "example.test"}],
                "excluded_targets": [],
            },
        )
        self.assertEqual(created.status_code, 201)

        analyst_username = f"analyst-{secrets.token_hex(6)}"
        analyst_password = secrets.token_urlsafe(24)
        with self.app.app_context():
            analyst = Principal(
                principal_id=uuid4(),
                username=analyst_username,
                password_hash=generate_password_hash(analyst_password),
                is_active=True,
            )
            analyst_role = Role(role_id=2, code="analyst", label="Analyst")
            db.session.add_all([analyst, analyst_role])
            db.session.flush()
            db.session.add(
                ScopeMembership(
                    scope_id=self.scope_id,
                    principal_id=analyst.principal_id,
                    role_id=analyst_role.role_id,
                )
            )
            readable_permissions = db.session.execute(
                select(Permission).where(
                    Permission.code.in_(["scope.read", "project.manage", "data.read", "data.import"])
                )
            ).scalars()
            db.session.add_all(
                [
                    RolePermission(
                        role_id=analyst_role.role_id,
                        permission_id=permission.permission_id,
                    )
                    for permission in readable_permissions
                ]
            )
            db.session.commit()

        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": analyst_username, "password": analyst_password},
        )
        analyst_headers = {
            "Authorization": f"Bearer {login.get_json()['access_token']}"
        }
        denied = self.client.post(
            f"/api/v1/engagements/{created.get_json()['engagement']['engagement_id']}/runs",
            headers=analyst_headers,
        )
        self.assertEqual(denied.status_code, 404)

    def test_run_read_and_cancel_do_not_cross_scope_boundaries(self):
        today = date.today()
        with self.app.app_context():
            other_scope = Scope(scope_id=uuid4(), name=f"other-{uuid4()}")
            other_project = Project(
                project_id=uuid4(),
                scope_id=other_scope.scope_id,
                slug="other-project",
                name="Other project",
            )
            engagement = Engagement(
                engagement_id=uuid4(),
                project_id=other_project.project_id,
                name="Other engagement",
                authorization_reference="https://other.example.test/policy",
                valid_from=today,
                valid_until=today,
                created_by=self.principal_id,
            )
            run = ReconRun(
                run_id=uuid4(),
                project_id=other_project.project_id,
                engagement_id=engagement.engagement_id,
                requested_by=self.principal_id,
                profile_code="domain_basic_v1",
                status="pending",
                cancel_requested=False,
                configuration_snapshot={"profile_code": "domain_basic_v1"},
            )
            db.session.add_all([other_scope, other_project, engagement, run])
            db.session.flush()
            db.session.add(
                EngagementTarget(
                    target_id=uuid4(),
                    engagement_id=engagement.engagement_id,
                    domain="other.example.test",
                    is_allowed=True,
                    include_subdomains=True,
                )
            )
            for number, operation in enumerate(
                ("subfinder", "dnsx", "httpx"), start=1
            ):
                db.session.add(
                    ReconRunStep(
                        step_id=uuid4(),
                        run_id=run.run_id,
                        step_number=number,
                        operation_code=operation,
                        status="pending",
                    )
                )
            db.session.commit()
            run_id = run.run_id

        headers = self._headers()
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{run_id}", headers=headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/runs/{run_id}/cancel", headers=headers
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
