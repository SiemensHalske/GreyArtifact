import hashlib
import io
import json
import secrets
import unittest
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

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
    Finding,
    FindingNote,
    FindingStatusAudit,
    ImportBatch,
    MlClaim,
    MlPrediction,
    MlPredictionReview,
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
                    "source_value",
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

    def test_pasted_asset_list_normalizes_values_and_preserves_provenance(self):
        source = (
            "# manually collected\n"
            "Example.TEST.\n"
            "192.0.2.10\n"
            "2001:db8::1\n"
            "https://Example.TEST:443/login#fragment\n"
        )
        uploaded = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports",
            headers=self._headers(),
            data={"format": "simple_list", "text": source},
            content_type="multipart/form-data",
        )

        self.assertEqual(uploaded.status_code, 201)
        import_body = uploaded.get_json()["import"]
        self.assertEqual(import_body["parser_name"], "simple_list")
        self.assertEqual(import_body["original_filename"], "pasted-assets.txt")
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_body['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)
        self.assertEqual(
            processed.get_json()["import"]["parser_version"],
            "simple_asset_list_v1",
        )

        assets = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets",
            headers=self._headers(),
        ).get_json()["assets"]
        self.assertEqual(
            {(item["type"], item["canonical_value"]) for item in assets},
            {
                ("domain", "example.test"),
                ("ipv4", "192.0.2.10"),
                ("ipv6", "2001:db8::1"),
                ("url", "https://example.test/login"),
            },
        )
        domain = next(item for item in assets if item["type"] == "domain")
        detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets/{domain['asset_id']}",
            headers=self._headers(),
        ).get_json()
        observation = detail["observations"][0]
        self.assertEqual(observation["kind"], "property")
        self.assertEqual(observation["code"], "source_value")
        self.assertEqual(observation["value"], "Example.TEST.")
        self.assertEqual(observation["evidence_locator"], "line:2")
        self.assertEqual(observation["import_id"], import_body["import_id"])
        self.assertEqual(observation["parser_name"], "simple_list")
        with self.app.app_context():
            artifact = db.session.get(Artifact, UUID(import_body["artifact_id"]))
            self.assertEqual(self.storage.objects[artifact.storage_key], source.encode())

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

    def test_nuclei_import_creates_safe_findings_with_provenance(self):
        uploaded = self._upload("nuclei.jsonl", "nuclei")
        import_body = uploaded.get_json()["import"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_body['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)
        self.assertEqual(
            processed.get_json()["import"]["parser_version"],
            "projectdiscovery_nuclei_jsonl_v1",
        )

        response = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings?severity=high",
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        findings = response.get_json()["findings"]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["external_id"], "exposed-api-key")
        self.assertEqual(finding["matched_at"], "https://api.example.test/config")
        self.assertEqual(finding["asset"]["canonical_value"], "https://api.example.test/config")
        self.assertEqual(finding["evidence_locator"], "line:1")
        self.assertEqual(finding["import_id"], import_body["import_id"])
        self.assertEqual(finding["parser_name"], "nuclei")
        self.assertTrue(finding["is_sensitive"])
        self.assertNotIn("extracted-results", finding["metadata"])
        self.assertNotIn("FAKE_TEST_TOKEN_DO_NOT_USE", json.dumps(finding))
        self.assertNotIn("FAKE_URL_TOKEN_DO_NOT_USE", json.dumps(finding))

        detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings/{finding['finding_id']}",
            headers=self._headers(),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["finding"]["artifact_id"], import_body["artifact_id"])
        self.assertEqual(len(detail.get_json()["finding"]["artifact_sha256"]), 64)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(Finding.finding_id))), 2)
            artifact = db.session.get(Artifact, UUID(import_body["artifact_id"]))
            self.assertIn(
                b"FAKE_TEST_TOKEN_DO_NOT_USE",
                self.storage.objects[artifact.storage_key],
            )
            self.assertIn(
                b"FAKE_URL_TOKEN_DO_NOT_USE",
                self.storage.objects[artifact.storage_key],
            )

    def _member_headers(self, role_code, permission_codes):
        username = f"{role_code}-{secrets.token_hex(6)}"
        password = secrets.token_urlsafe(24)
        with self.app.app_context():
            member = Principal(
                principal_id=uuid4(),
                username=username,
                password_hash=generate_password_hash(password),
                is_active=True,
            )
            role = Role(role_id=10, code=role_code, label=role_code)
            db.session.add_all([member, role])
            db.session.flush()
            db.session.add(
                ScopeMembership(
                    scope_id=self.scope_id,
                    principal_id=member.principal_id,
                    role_id=role.role_id,
                )
            )
            permissions = db.session.execute(
                select(Permission).where(Permission.code.in_(permission_codes))
            ).scalars()
            db.session.add_all(
                [
                    RolePermission(role_id=role.role_id, permission_id=item.permission_id)
                    for item in permissions
                ]
            )
            db.session.commit()
        login = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        return {"Authorization": f"Bearer {login.get_json()['access_token']}"}

    def _grant_owner_permission(self, code):
        with self.app.app_context():
            permission = Permission(permission_id=100, code=code, label=code)
            db.session.add(permission)
            db.session.flush()
            db.session.add(RolePermission(role_id=1, permission_id=permission.permission_id))
            db.session.commit()

    def _processed_nuclei_import(self):
        body = self._upload("nuclei.jsonl", "nuclei").get_json()["import"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{body['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)
        return processed.get_json()["import"]

    def test_finding_status_change_is_audited_once(self):
        self._processed_nuclei_import()
        headers = self._headers()
        finding = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings?severity=high",
            headers=headers,
        ).get_json()["findings"][0]
        url = f"/api/v1/projects/{self.project_id}/findings/{finding['finding_id']}/status"

        invalid = self.client.put(url, headers=headers, json={"status": "fixed"})
        self.assertEqual(invalid.status_code, 400)
        changed = self.client.put(url, headers=headers, json={"status": "confirmed"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.get_json()["finding"]["status"], "confirmed")
        repeated = self.client.put(url, headers=headers, json={"status": "confirmed"})
        self.assertEqual(repeated.status_code, 200)

        with self.app.app_context():
            events = db.session.execute(select(FindingStatusAudit)).scalars().all()
            self.assertEqual(len(events), 1)
            self.assertEqual(str(events[0].finding_id), finding["finding_id"])
            self.assertEqual(events[0].changed_by, self.principal_id)
            self.assertEqual(
                (events[0].status_before, events[0].status_after),
                ("new", "confirmed"),
            )

    def test_finding_status_change_requires_data_import(self):
        self._processed_nuclei_import()
        finding = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings",
            headers=self._headers(),
        ).get_json()["findings"][0]
        viewer_headers = self._member_headers("viewer", ["scope.read", "data.read"])
        denied = self.client.put(
            f"/api/v1/projects/{self.project_id}/findings/{finding['finding_id']}/status",
            headers=viewer_headers,
            json={"status": "false_positive"},
        )
        self.assertEqual(denied.status_code, 404)
        with self.app.app_context():
            stored = db.session.get(Finding, UUID(finding["finding_id"]))
            self.assertEqual(stored.status, "new")
            self.assertEqual(
                db.session.scalar(select(func.count(FindingStatusAudit.audit_id))), 0
            )

    def test_finding_notes_and_status_history_are_chronological(self):
        self._processed_nuclei_import()
        headers = self._headers()
        finding = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings?severity=high",
            headers=headers,
        ).get_json()["findings"][0]
        base = f"/api/v1/projects/{self.project_id}/findings/{finding['finding_id']}"

        empty_history = self.client.get(f"{base}/history", headers=headers)
        self.assertEqual(empty_history.status_code, 200)
        self.assertEqual(empty_history.get_json()["events"], [])

        self.assertEqual(
            self.client.put(
                f"{base}/status", headers=headers, json={"status": "confirmed"}
            ).status_code,
            200,
        )
        created = self.client.post(
            f"{base}/notes", headers=headers, json={"body": "  Reproduziert im Staging.  "}
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["event"]["body"], "Reproduziert im Staging.")
        for invalid in ("   ", "x" * 4001):
            self.assertEqual(
                self.client.post(
                    f"{base}/notes", headers=headers, json={"body": invalid}
                ).status_code,
                400,
            )

        events = self.client.get(f"{base}/history", headers=headers).get_json()["events"]
        self.assertEqual([event["kind"] for event in events], ["status", "note"])
        self.assertEqual(
            (events[0]["status_before"], events[0]["status_after"]),
            ("new", "confirmed"),
        )
        self.assertEqual(events[1]["body"], "Reproduziert im Staging.")
        self.assertEqual(
            {event["actor"]["username"] for event in events}, {self.username}
        )

    def test_viewer_reads_history_but_cannot_add_notes(self):
        self._processed_nuclei_import()
        finding = self.client.get(
            f"/api/v1/projects/{self.project_id}/findings",
            headers=self._headers(),
        ).get_json()["findings"][0]
        base = f"/api/v1/projects/{self.project_id}/findings/{finding['finding_id']}"
        viewer_headers = self._member_headers("viewer", ["scope.read", "data.read"])

        denied = self.client.post(
            f"{base}/notes", headers=viewer_headers, json={"body": "Nicht erlaubt"}
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(
            self.client.get(f"{base}/history", headers=viewer_headers).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/projects/{self.project_id}/findings/{uuid4()}/history",
                headers=viewer_headers,
            ).status_code,
            404,
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count(FindingNote.note_id))), 0
            )

    def test_sensitive_raw_artifact_requires_sensitive_read(self):
        pending = self._upload("dnsx.jsonl", "dnsx").get_json()["import"]
        self.assertTrue(pending["requires_sensitive_access"])
        nuclei = self._processed_nuclei_import()
        self.assertTrue(nuclei["requires_sensitive_access"])
        listed = self.client.get(
            f"/api/v1/projects/{self.project_id}/imports", headers=self._headers()
        ).get_json()["imports"]
        self.assertEqual(
            {item["import_id"]: item["requires_sensitive_access"] for item in listed},
            {pending["import_id"]: True, nuclei["import_id"]: True},
        )

        nuclei_url = (
            f"/api/v1/projects/{self.project_id}/imports/{nuclei['import_id']}/artifact"
        )
        pending_url = (
            f"/api/v1/projects/{self.project_id}/imports/{pending['import_id']}/artifact"
        )
        denied = self.client.get(nuclei_url, headers=self._headers())
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["error"]["code"], "sensitive_artifact")
        self.assertNotIn(b"FAKE_TEST_TOKEN_DO_NOT_USE", denied.data)
        self.assertEqual(
            self.client.get(pending_url, headers=self._headers()).status_code, 403
        )

        self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{pending['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(
            self.client.get(pending_url, headers=self._headers()).status_code, 200
        )

        self._grant_owner_permission("sensitive.read")
        allowed = self.client.get(nuclei_url, headers=self._headers())
        self.assertEqual(allowed.status_code, 200)
        self.assertIn(b"FAKE_TEST_TOKEN_DO_NOT_USE", allowed.data)

    def _manifest_package(self, *, predictions, external_ref="run-1", drop_ml=False, break_hash=False):
        nuclei_bytes = (FIXTURES / "nuclei.jsonl").read_bytes()
        pred_bytes = ("\n".join(json.dumps(line) for line in predictions)).encode("utf-8")

        def digest(data):
            return hashlib.sha256(data).hexdigest()

        manifest = {
            "manifest_version": "greyartifact-run-manifest/v1",
            "source": "fennec",
            "run": {
                "external_ref": external_ref,
                "started_at": "2026-10-15T06:00:00Z",
                "engagement_reference": "https://example.test/auth",
            },
            "tools": [
                {
                    "name": "nuclei",
                    "version": "3.0.0",
                    "file": "nuclei.jsonl",
                    "parser": "nuclei",
                    "sha256": digest(nuclei_bytes),
                    "redaction": "raw",
                }
            ],
            "ml": {
                "model": "relational",
                "version": "2026.10",
                "status": "candidate",
                "pipeline_release": "pr-1",
                "inference_run_ref": "inf-9",
                "file": "predictions.jsonl",
                "parser": "recon_ml_predictions_v1",
                "sha256": digest(pred_bytes),
            },
        }
        if break_hash:
            manifest["ml"]["sha256"] = "0" * 64
        if drop_ml:
            del manifest["ml"]
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        return {
            "manifest": (io.BytesIO(manifest_bytes), "manifest.json"),
            "nuclei.jsonl": (io.BytesIO(nuclei_bytes), "nuclei.jsonl"),
            "predictions.jsonl": (io.BytesIO(pred_bytes), "predictions.jsonl"),
        }

    def _post_batch(self, data):
        return self.client.post(
            f"/api/v1/projects/{self.project_id}/import-batches",
            headers=self._headers(),
            data=data,
            content_type="multipart/form-data",
        )

    def test_import_batch_stores_package_and_ml_predictions(self):
        predictions = [
            {"entity_type": "domain", "entity_value": "api.example.test",
             "percentile": 98.0, "rank": 1, "explanation": {"top_feature": "tls_age"}},
            {"entity_type": "url", "entity_value": "https://api.example.test/config",
             "percentile": 80.5, "rank": 2, "explanation": {}},
        ]
        response = self._post_batch(self._manifest_package(predictions=predictions))
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["batch"]["ml_model_status"], "candidate")
        self.assertEqual(body["batch"]["external_run_ref"], "run-1")
        self.assertEqual(
            {item["original_filename"]: item["status"] for item in body["imports"]},
            {"nuclei.jsonl": "completed", "predictions.jsonl": "completed"},
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count(MlPrediction.prediction_id))), 2
            )
            top = db.session.execute(
                select(MlPrediction).where(MlPrediction.rank == 1)
            ).scalar_one()
            self.assertEqual(top.model_version, "2026.10")
            self.assertEqual(top.model_status, "candidate")
            self.assertAlmostEqual(top.percentile, 98.0)
            self.assertEqual(top.evidence_locator, "line:1")
            batch = db.session.execute(select(ImportBatch)).scalar_one()
            self.assertEqual(batch.ml_inference_run_ref, "inf-9")
            # Tool findings were also imported under the same batch.
            self.assertEqual(
                db.session.scalar(select(func.count(Finding.finding_id))), 2
            )

        batch_id = body["batch"]["batch_id"]
        batches = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches",
            headers=self._headers(),
        )
        self.assertEqual(batches.status_code, 200)
        self.assertEqual(
            [item["batch_id"] for item in batches.get_json()["batches"]], [batch_id]
        )

        predictions = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches/{batch_id}/predictions",
            headers=self._headers(),
        )
        self.assertEqual(predictions.status_code, 200)
        ranked = predictions.get_json()["predictions"]
        self.assertEqual([item["rank"] for item in ranked], [1, 2])
        self.assertEqual(ranked[0]["asset"]["canonical_value"], "api.example.test")
        self.assertEqual(ranked[0]["model_status"], "candidate")
        self.assertEqual(ranked[0]["explanation"], {"top_feature": "tls_age"})

        missing = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches/{uuid4()}/predictions",
            headers=self._headers(),
        )
        self.assertEqual(missing.status_code, 404)

    def test_import_batch_rejects_missing_ml_block(self):
        response = self._post_batch(
            self._manifest_package(predictions=[], drop_ml=True)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "invalid_manifest")
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(ImportBatch.batch_id))), 0)

    def test_import_batch_rejects_hash_mismatch(self):
        predictions = [
            {"entity_type": "domain", "entity_value": "api.example.test",
             "percentile": 50.0, "rank": 1, "explanation": {}},
        ]
        response = self._post_batch(
            self._manifest_package(predictions=predictions, break_hash=True)
        )
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(ImportBatch.batch_id))), 0)
            self.assertEqual(
                db.session.scalar(select(func.count(MlPrediction.prediction_id))), 0
            )

    def test_import_batch_rejects_duplicate_run(self):
        predictions = [
            {"entity_type": "domain", "entity_value": "api.example.test",
             "percentile": 50.0, "rank": 1, "explanation": {}},
        ]
        first = self._post_batch(
            self._manifest_package(predictions=predictions, external_ref="dup-run")
        )
        self.assertEqual(first.status_code, 201)
        second = self._post_batch(
            self._manifest_package(predictions=predictions, external_ref="dup-run")
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()["error"]["code"], "batch_conflict")

    def test_observations_import_creates_assets_properties_relationships(self):
        content = (FIXTURES / "observations.jsonl").read_bytes()
        uploaded = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports",
            headers=self._headers(),
            data={"format": "greyartifact_observations", "file": (io.BytesIO(content), "observations.jsonl")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201)
        import_body = uploaded.get_json()["import"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_body['import_id']}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 200)
        self.assertEqual(
            processed.get_json()["import"]["parser_version"],
            "greyartifact_observations_v1",
        )

        assets = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets", headers=self._headers()
        ).get_json()["assets"]
        by_type = {asset["type"]: asset for asset in assets}
        self.assertEqual(set(by_type), {"domain", "ipv4", "url"})

        url_detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets/{by_type['url']['asset_id']}",
            headers=self._headers(),
        ).get_json()
        props = {
            item["code"]: item["value"]
            for item in url_detail["observations"]
            if item["kind"] == "property"
        }
        self.assertEqual(props["http_status"], 200)
        self.assertIsInstance(props["http_status"], int)
        self.assertEqual(props["server"], "nginx")
        self.assertEqual(props["tls_subject_cn"], "api.example.test")

        domain_detail = self.client.get(
            f"/api/v1/projects/{self.project_id}/assets/{by_type['domain']['asset_id']}",
            headers=self._headers(),
        ).get_json()
        rel_codes = {
            item["code"]
            for item in domain_detail["observations"]
            if item["kind"] == "relationship"
        }
        self.assertEqual(rel_codes, {"resolves_to", "hosts"})

    def test_observations_import_rejects_unknown_property(self):
        bad = b'{"asset":{"type":"domain","value":"api.example.test"},"properties":{"made_up":1}}'
        uploaded = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports",
            headers=self._headers(),
            data={"format": "greyartifact_observations", "file": (io.BytesIO(bad), "bad.jsonl")},
            content_type="multipart/form-data",
        )
        import_id = uploaded.get_json()["import"]["import_id"]
        processed = self.client.post(
            f"/api/v1/projects/{self.project_id}/imports/{import_id}/process",
            headers=self._headers(),
        )
        self.assertEqual(processed.status_code, 409)
        self.assertIn("made_up", processed.get_json()["error"]["message"])

    def _batch_with_prediction(self):
        predictions = [
            {"entity_type": "domain", "entity_value": "api.example.test",
             "percentile": 98.0, "rank": 1, "explanation": {}},
        ]
        batch = self._post_batch(self._manifest_package(predictions=predictions)).get_json()["batch"]
        preds = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches/{batch['batch_id']}/predictions",
            headers=self._headers(),
        ).get_json()["predictions"]
        return batch, preds[0]

    def test_prediction_review_is_append_only_and_latest_wins(self):
        batch, prediction = self._batch_with_prediction()
        url = f"/api/v1/projects/{self.project_id}/ml-predictions/{prediction['prediction_id']}/review"

        bad = self.client.post(url, headers=self._headers(), json={"decision": "nonsense"})
        self.assertEqual(bad.status_code, 400)

        first = self.client.post(
            url, headers=self._headers(),
            json={"decision": "confirmed_finding", "note": "  Reproduziert  "},
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.get_json()["review"]["decision"], "confirmed_finding")
        self.assertEqual(first.get_json()["review"]["note"], "Reproduziert")

        second = self.client.post(url, headers=self._headers(), json={"decision": "review_worthy"})
        self.assertEqual(second.status_code, 201)

        preds = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches/{batch['batch_id']}/predictions",
            headers=self._headers(),
        ).get_json()["predictions"]
        review = preds[0]["review"]
        self.assertEqual(review["decision"], "review_worthy")
        self.assertEqual(review["reviewer"]["username"], self.username)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count(MlPredictionReview.review_id))), 2
            )

    def test_prediction_review_requires_data_import(self):
        _batch, prediction = self._batch_with_prediction()
        viewer = self._member_headers("viewer", ["scope.read", "data.read"])
        denied = self.client.post(
            f"/api/v1/projects/{self.project_id}/ml-predictions/{prediction['prediction_id']}/review",
            headers=viewer, json={"decision": "expected"},
        )
        self.assertEqual(denied.status_code, 404)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count(MlPredictionReview.review_id))), 0
            )

    def test_review_feedback_export_is_jsonl_with_latest_decision(self):
        batch, prediction = self._batch_with_prediction()
        url = f"/api/v1/projects/{self.project_id}/ml-predictions/{prediction['prediction_id']}/review"
        self.client.post(url, headers=self._headers(), json={"decision": "expected"})
        self.client.post(
            url, headers=self._headers(),
            json={"decision": "confirmed_finding", "note": "Reproduziert"},
        )

        export = self.client.get(
            f"/api/v1/projects/{self.project_id}/import-batches/{batch['batch_id']}/review-feedback",
            headers=self._headers(),
        )
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.mimetype, "application/x-ndjson")
        lines = [l for l in export.get_data(as_text=True).splitlines() if l]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["decision"], "confirmed_finding")
        self.assertEqual(entry["note"], "Reproduziert")
        self.assertEqual(entry["entity_type"], "domain")
        self.assertEqual(entry["entity_value"], "api.example.test")
        self.assertEqual(entry["engagement_ref"], batch["external_run_ref"])
        self.assertEqual(entry["inference_run_ref"], batch["ml_inference_run_ref"])

    def _claims_package(self, claim_lines, *, parser="recon_ml_claims_v1"):
        data = self._manifest_package(
            predictions=[
                {"entity_type": "domain", "entity_value": "api.example.test",
                 "percentile": 90.0, "rank": 1, "explanation": {}},
            ]
        )
        manifest = json.loads(data["manifest"][0].getvalue())
        claims_bytes = "\n".join(json.dumps(line) for line in claim_lines).encode("utf-8")
        manifest["claims"] = {
            "file": "claims.jsonl",
            "parser": parser,
            "sha256": hashlib.sha256(claims_bytes).hexdigest(),
        }
        data["manifest"] = (io.BytesIO(json.dumps(manifest).encode("utf-8")), "manifest.json")
        data["claims.jsonl"] = (io.BytesIO(claims_bytes), "claims.jsonl")
        return data

    @staticmethod
    def _claim(claim, state, **extra):
        return {
            "claim": claim,
            "version": "3.1",
            "state": state,
            "as_of": "2026-10-15T06:00:00+00:00",
            "engine_version": "claim-engine-3",
            **extra,
        }

    def test_import_batch_stores_claims_for_display(self):
        candidate = {
            "action_type": "http_probe",
            "policy_class": "active_http_recon",
            "recommendation": {
                "utility_score": -0.06,
                "expected_information_gain": 0.03,
                "created_at": "2026-09-10T10:00:00+00:00",
                "decision": None,
            },
        }
        lines = [
            {"entity_type": "domain", "entity_value": "api.example.test", "claims": [
                self._claim(
                    "asset.publicly_reachable", "insufficient_evidence",
                    evidence=[{"direction": "neutral", "reason": "missing_http_evidence", "count": 2}],
                    candidates=[candidate],
                ),
                self._claim("exposure.internal_system", "supported"),
            ]},
            {"entity_type": "domain", "entity_value": "www.example.test", "claims": [
                self._claim("exposure.internal_system", "supported"),
            ]},
        ]
        response = self._post_batch(self._claims_package(lines))
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(
            {item["original_filename"]: item["status"] for item in body["imports"]}["claims.jsonl"],
            "completed",
        )
        base = f"/api/v1/projects/{self.project_id}/import-batches/{body['batch']['batch_id']}"
        overview = self.client.get(f"{base}/claims", headers=self._headers()).get_json()
        self.assertEqual(overview["claims"], [])
        self.assertEqual(
            overview["summary"],
            [
                {"claim": "asset.publicly_reachable", "state": "insufficient_evidence", "count": 1},
                {"claim": "exposure.internal_system", "state": "supported", "count": 2},
            ],
        )
        prediction = self.client.get(
            f"{base}/predictions", headers=self._headers()
        ).get_json()["predictions"][0]
        detail = self.client.get(
            f"{base}/claims",
            headers=self._headers(),
            query_string={"asset_id": prediction["asset"]["asset_id"]},
        ).get_json()["claims"]
        self.assertEqual(
            [claim["claim"] for claim in detail],
            ["asset.publicly_reachable", "exposure.internal_system"],
        )
        self.assertEqual(detail[0]["state"], "insufficient_evidence")
        self.assertEqual(detail[0]["candidates"], [candidate])
        self.assertEqual(detail[0]["evidence"][0]["reason"], "missing_http_evidence")

    def test_invalid_claim_state_fails_only_the_claims_import(self):
        lines = [{"entity_type": "domain", "entity_value": "api.example.test",
                  "claims": [self._claim("asset.publicly_reachable", "maybe")]}]
        response = self._post_batch(self._claims_package(lines))
        self.assertEqual(response.status_code, 201)
        imports = {item["original_filename"]: item for item in response.get_json()["imports"]}
        self.assertEqual(imports["predictions.jsonl"]["status"], "completed")
        self.assertEqual(imports["claims.jsonl"]["status"], "failed")
        self.assertIn("state", imports["claims.jsonl"]["error_message"])
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(MlClaim.claim_id))), 0)

    def test_manifest_rejects_unknown_claims_parser(self):
        lines = [{"entity_type": "domain", "entity_value": "api.example.test",
                  "claims": [self._claim("asset.publicly_reachable", "supported")]}]
        response = self._post_batch(self._claims_package(lines, parser="claims_v0"))
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count(ImportBatch.batch_id))), 0)

    def test_claims_require_data_read(self):
        lines = [{"entity_type": "domain", "entity_value": "api.example.test",
                  "claims": [self._claim("asset.publicly_reachable", "supported")]}]
        batch_id = self._post_batch(self._claims_package(lines)).get_json()["batch"]["batch_id"]
        url = f"/api/v1/projects/{self.project_id}/import-batches/{batch_id}/claims"
        denied = self.client.get(url, headers=self._member_headers("viewer", ["scope.read"]))
        self.assertEqual(denied.status_code, 404)

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
