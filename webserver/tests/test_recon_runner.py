import secrets
import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
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
from app.services.recon_runner import ProcessResult, RunCancelled, execute_run
from support import InMemoryArtifactStorage


FIXTURES = Path(__file__).parent / "fixtures"


class FakeProcessRunner:
    def __init__(self):
        self.calls = []
        self.outputs = {
            "subfinder": (FIXTURES / "subfinder.jsonl").read_bytes(),
            "dnsx": (FIXTURES / "dnsx.jsonl").read_bytes(),
            "httpx": (FIXTURES / "httpx.jsonl").read_bytes(),
        }

    def execute(self, arguments, input_bytes, timeout_seconds, cancel_check):
        operation = Path(arguments[0]).name
        self.calls.append((arguments, input_bytes, timeout_seconds))
        return ProcessResult(self.outputs[operation], f"{operation} fixture-version")


class CancellingProcessRunner:
    def execute(self, arguments, input_bytes, timeout_seconds, cancel_check):
        raise RunCancelled("Cancellation requested.")


class ReconRunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "JWT_SECRET_KEY": secrets.token_urlsafe(48),
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "execution_options": {"schema_translate_map": {"recon": None}}
                },
                "RUNNER_SUBFINDER_PATH": "/opt/greyartifact/bin/subfinder",
                "RUNNER_DNSX_PATH": "/opt/greyartifact/bin/dnsx",
                "RUNNER_HTTPX_PATH": "/opt/greyartifact/bin/httpx",
            }
        )
        self.storage = InMemoryArtifactStorage()
        self.app.extensions["artifact_storage"] = self.storage
        with self.app.app_context():
            connection = db.engine.raw_connection()
            connection.create_function("btrim", 1, lambda value: value.strip())
            connection.close()
            db.create_all()
            principal = Principal(
                principal_id=uuid4(),
                username=f"runner-{uuid4()}",
                password_hash=generate_password_hash("not-used-password"),
            )
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            project = Project(
                project_id=uuid4(), scope_id=scope.scope_id, slug="runner", name="Runner"
            )
            engagement = Engagement(
                engagement_id=uuid4(),
                project_id=project.project_id,
                name="Fixture",
                authorization_reference="https://example.test/policy",
                valid_from=date(2026, 1, 1),
                valid_until=date(2027, 1, 1),
                created_by=principal.principal_id,
            )
            limits = {
                "max_hosts": 10_000,
                "total_timeout_seconds": 1_200,
                "subfinder_timeout_seconds": 300,
                "dnsx_timeout_seconds": 300,
                "httpx_timeout_seconds": 600,
                "dnsx_rate_limit": 100,
                "httpx_rate_limit": 50,
                "max_output_bytes": 100 * 1024 * 1024,
                "max_total_output_bytes": 100 * 1024 * 1024,
                "max_memory_bytes": 512 * 1024 * 1024,
                "max_parallelism": 20,
            }
            run = ReconRun(
                run_id=uuid4(),
                project_id=project.project_id,
                engagement_id=engagement.engagement_id,
                requested_by=principal.principal_id,
                profile_code="domain_basic_v1",
                status="running",
                cancel_requested=False,
                configuration_snapshot={
                    "profile_code": "domain_basic_v1",
                    "authorization_reference": engagement.authorization_reference,
                    "valid_from": "2026-01-01",
                    "valid_until": "2027-01-01",
                    "allowed_targets": [
                        {"domain": "example.test", "include_subdomains": True}
                    ],
                    "excluded_targets": [
                        {"domain": "blocked.example.test", "include_subdomains": True}
                    ],
                    "limits": limits,
                },
            )
            db.session.add_all([principal, scope, project, engagement, run])
            db.session.flush()
            db.session.add(
                EngagementTarget(
                    target_id=uuid4(),
                    engagement_id=engagement.engagement_id,
                    domain="example.test",
                    is_allowed=True,
                    include_subdomains=True,
                )
            )
            for number, operation in enumerate(("subfinder", "dnsx", "httpx"), start=1):
                db.session.add(
                    ReconRunStep(
                        step_id=uuid4(),
                        run_id=run.run_id,
                        step_number=number,
                        operation_code=operation,
                        status="pending",
                    )
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
                ["http_status", "title", "server", "content_type", "tls_subject_cn", "tls_issuer_cn", "tls_not_before", "tls_not_after"],
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
            self.run_id = run.run_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_fixed_runner_chain_stores_and_imports_each_step(self):
        fake = FakeProcessRunner()
        with self.app.app_context():
            execute_run(self.run_id, fake)
            run = db.session.get(ReconRun, self.run_id)
            self.assertEqual(run.status, "succeeded")
            steps = db.session.execute(
                select(ReconRunStep)
                .where(ReconRunStep.run_id == self.run_id)
                .order_by(ReconRunStep.step_number)
            ).scalars().all()
            self.assertEqual([step.status for step in steps], ["succeeded"] * 3)
            self.assertTrue(all(step.artifact_id for step in steps))
            imports = db.session.execute(
                select(ImportRecord).where(
                    ImportRecord.recon_run_step_id.is_not(None)
                )
            ).scalars().all()
            self.assertEqual(len(imports), 3)
            self.assertEqual(
                {record.recon_run_step_id for record in imports},
                {step.step_id for step in steps},
            )

        self.assertEqual(
            [Path(call[0][0]).name for call in fake.calls],
            ["subfinder", "dnsx", "httpx"],
        )
        self.assertIn(b"api.example.test", fake.calls[1][1])
        self.assertIn(b"api.example.test", fake.calls[2][1])
        self.assertTrue(
            all(call[0][0].startswith("/opt/greyartifact/bin/") for call in fake.calls)
        )

    def test_cancellation_marks_run_and_unfinished_steps_cancelled(self):
        with self.app.app_context():
            execute_run(self.run_id, CancellingProcessRunner())
            run = db.session.get(ReconRun, self.run_id)
            steps = db.session.execute(
                select(ReconRunStep)
                .where(ReconRunStep.run_id == self.run_id)
                .order_by(ReconRunStep.step_number)
            ).scalars().all()

            self.assertEqual(run.status, "cancelled")
            self.assertIsNotNone(run.finished_at)
            self.assertEqual([step.status for step in steps], ["cancelled"] * 3)


if __name__ == "__main__":
    unittest.main()
