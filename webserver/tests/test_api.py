import secrets
import unittest
from uuid import UUID, uuid4

from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
    Permission,
    Principal,
    Project,
    RegistrationRequest,
    Role,
    RoleAssignmentAudit,
    RolePermission,
    Scope,
    ScopeMembership,
)
from app.services.authorization import principal_has_scope_permission


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.username = f"user-{secrets.token_hex(8)}"
        self.password = secrets.token_urlsafe(24)
        self.jwt_secret = secrets.token_urlsafe(48)
        self.app = create_app(
            {
                "TESTING": True,
                "JWT_SECRET_KEY": self.jwt_secret,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_ENGINE_OPTIONS": {
                    "execution_options": {
                        "schema_translate_map": {"recon": None},
                    },
                },
            }
        )
        self.client = self.app.test_client()

        with self.app.app_context():
            sqlite_connection = db.engine.raw_connection()
            sqlite_connection.create_function("btrim", 1, lambda value: value.strip())
            sqlite_connection.close()
            db.create_all()
            self.principal = Principal(
                principal_id=uuid4(),
                username=self.username,
                password_hash=generate_password_hash(self.password),
                display_name="Test principal",
                is_active=True,
            )
            db.session.add(self.principal)
            db.session.commit()
            self.principal_id = self.principal.principal_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["access_token"]

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def _add_readable_membership(self, scope):
        role = Role(role_id=1, code="viewer", label="Viewer")
        permission = Permission(
            permission_id=1,
            code="scope.read",
            label="Read scope content",
        )
        db.session.add_all(
            [
                role,
                permission,
                RolePermission(
                    role_id=role.role_id,
                    permission_id=permission.permission_id,
                ),
                ScopeMembership(
                    scope_id=scope.scope_id,
                    principal_id=self.principal_id,
                    role_id=role.role_id,
                ),
            ]
        )

    def _add_owner_membership(self, scope):
        owner = Role(role_id=1, code="owner", label="Scope owner")
        viewer = Role(role_id=2, code="viewer", label="Viewer")
        researcher = Role(role_id=3, code="researcher", label="Researcher")
        analyst = Role(role_id=4, code="analyst", label="Analyst")
        pipeline_operator = Role(
            role_id=5,
            code="pipeline_operator",
            label="Pipeline operator",
        )
        scope_read = Permission(
            permission_id=1,
            code="scope.read",
            label="Read scope content",
        )
        membership_manage = Permission(
            permission_id=2,
            code="membership.manage",
            label="Manage scope memberships",
        )
        db.session.add_all(
            [
                owner,
                viewer,
                researcher,
                analyst,
                pipeline_operator,
                scope_read,
                membership_manage,
                RolePermission(
                    role_id=owner.role_id,
                    permission_id=scope_read.permission_id,
                ),
                RolePermission(
                    role_id=owner.role_id,
                    permission_id=membership_manage.permission_id,
                ),
                RolePermission(
                    role_id=viewer.role_id,
                    permission_id=scope_read.permission_id,
                ),
                ScopeMembership(
                    scope_id=scope.scope_id,
                    principal_id=self.principal_id,
                    role_id=owner.role_id,
                ),
            ]
        )

    def test_app_factory_initializes_extensions_and_health(self):
        self.assertIs(db, self.app.extensions["sqlalchemy"])
        self.assertIn("flask-jwt-extended", self.app.extensions)

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_recon_execution_endpoints_require_authentication(self):
        project_id = uuid4()
        engagement_id = uuid4()
        run_id = uuid4()

        responses = (
            self.client.post(
                f"/api/v1/projects/{project_id}/engagements", json={}
            ),
            self.client.post(f"/api/v1/engagements/{engagement_id}/runs"),
            self.client.post(f"/api/v1/runs/{run_id}/cancel"),
        )

        for response in responses:
            self.assertEqual(response.status_code, 401)

    def test_index_renders_dashboard(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dein lokales Lagebild", response.data)
        self.assertIn(b'id="login-form"', response.data)
        self.assertIn(b'data-theme="dark"', response.data)
        self.assertIn(b'id="theme-toggle"', response.data)
        self.assertIn(b'id="registration-form"', response.data)
        self.assertIn(b'href="/admin"', response.data)
        self.assertIn(b'id="project-workspace"', response.data)
        self.assertIn(b'id="import-form"', response.data)
        self.assertIn(b'id="engagement-form"', response.data)
        self.assertIn(b'id="run-list"', response.data)

    def test_admin_page_renders_dedicated_management_workspace(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Administration.", response.data)
        self.assertIn(b'id="admin-login-form"', response.data)
        self.assertIn(b'id="registration-list"', response.data)
        self.assertIn(b'id="member-form"', response.data)
        self.assertIn(b'id="audit-list"', response.data)
        self.assertIn(b'value="researcher"', response.data)
        self.assertIn(b'name="pipeline_operator"', response.data)
        self.assertIn(b"js/admin.js", response.data)

    def test_login_succeeds_and_rejects_wrong_password(self):
        login_response = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access_token", login_response.get_json())

        wrong_password_response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": self.username,
                "password": secrets.token_urlsafe(24),
            },
        )
        self.assertEqual(wrong_password_response.status_code, 401)
        self.assertEqual(
            wrong_password_response.get_json()["error"]["code"],
            "invalid_credentials",
        )

    def test_protected_route_rejects_missing_and_invalid_jwt(self):
        missing_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(missing_response.status_code, 401)
        self.assertEqual(missing_response.get_json()["error"]["code"], "unauthorized")

        invalid_response = self.client.get(
            "/api/v1/auth/me",
            headers=self._headers(secrets.token_urlsafe(48)),
        )
        self.assertEqual(invalid_response.status_code, 401)
        self.assertEqual(invalid_response.get_json()["error"]["code"], "unauthorized")

    def test_me_returns_current_principal(self):
        response = self.client.get(
            "/api/v1/auth/me",
            headers=self._headers(self._login()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["principal"]["username"], self.username)
        self.assertEqual(
            response.get_json()["principal"]["principal_id"],
            str(self.principal_id),
        )

    def test_scope_list_only_contains_authorized_memberships(self):
        with self.app.app_context():
            readable_scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            hidden_scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add_all([readable_scope, hidden_scope])
            db.session.flush()
            self._add_readable_membership(readable_scope)
            db.session.commit()
            readable_scope_id = readable_scope.scope_id

        response = self.client.get(
            "/api/v1/scopes",
            headers=self._headers(self._login()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [scope["scope_id"] for scope in response.get_json()["scopes"]],
            [str(readable_scope_id)],
        )

    def test_manageable_scope_list_only_contains_admin_scopes(self):
        with self.app.app_context():
            owner_scope = Scope(scope_id=uuid4(), name=f"owner-{uuid4()}")
            viewer_scope = Scope(scope_id=uuid4(), name=f"viewer-{uuid4()}")
            db.session.add_all([owner_scope, viewer_scope])
            db.session.flush()
            self._add_owner_membership(owner_scope)
            db.session.add(
                ScopeMembership(
                    scope_id=viewer_scope.scope_id,
                    principal_id=self.principal_id,
                    role_id=2,
                )
            )
            db.session.commit()
            owner_scope_id = owner_scope.scope_id

        response = self.client.get(
            "/api/v1/scopes/manageable",
            headers=self._headers(self._login()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [scope["scope_id"] for scope in response.get_json()["scopes"]],
            [str(owner_scope_id)],
        )

    def test_project_list_hides_scope_without_membership_or_permission(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.commit()
            scope_id = scope.scope_id

        token = self._login()
        without_membership = self.client.get(
            f"/api/v1/scopes/{scope_id}/projects",
            headers=self._headers(token),
        )
        self.assertEqual(without_membership.status_code, 404)

        with self.app.app_context():
            role = Role(role_id=1, code="viewer", label="Viewer")
            db.session.add_all(
                [
                    role,
                    ScopeMembership(
                        scope_id=scope_id,
                        principal_id=self.principal_id,
                        role_id=role.role_id,
                    ),
                ]
            )
            db.session.commit()

        without_permission = self.client.get(
            f"/api/v1/scopes/{scope_id}/projects",
            headers=self._headers(token),
        )
        self.assertEqual(without_permission.status_code, 404)
        self.assertEqual(without_permission.get_json()["error"]["code"], "not_found")

    def test_project_list_does_not_cross_scope_boundary(self):
        with self.app.app_context():
            requested_scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            other_scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add_all([requested_scope, other_scope])
            db.session.flush()
            self._add_readable_membership(requested_scope)
            db.session.add(
                ScopeMembership(
                    scope_id=other_scope.scope_id,
                    principal_id=self.principal_id,
                    role_id=1,
                )
            )
            included_project = Project(
                project_id=uuid4(),
                scope_id=requested_scope.scope_id,
                slug=f"project-{uuid4()}",
                name="Included project",
            )
            excluded_project = Project(
                project_id=uuid4(),
                scope_id=other_scope.scope_id,
                slug=f"project-{uuid4()}",
                name="Excluded project",
            )
            db.session.add_all([included_project, excluded_project])
            db.session.commit()
            requested_scope_id = requested_scope.scope_id
            included_project_id = included_project.project_id

        response = self.client.get(
            f"/api/v1/scopes/{requested_scope_id}/projects",
            headers=self._headers(self._login()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [project["project_id"] for project in response.get_json()["projects"]],
            [str(included_project_id)],
        )

    def test_owner_can_create_and_list_scope_member(self):
        member_username = f"member-{secrets.token_hex(8)}"
        member_password = secrets.token_urlsafe(24)
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_owner_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        headers = self._headers(self._login())
        create_response = self.client.post(
            f"/api/v1/scopes/{scope_id}/members",
            headers=headers,
            json={
                "username": member_username,
                "password": member_password,
                "display_name": "New member",
                "role": "researcher",
                "additional_roles": ["pipeline_operator"],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.get_json()["member"]["role"], "researcher")
        self.assertEqual(
            create_response.get_json()["member"]["additional_roles"],
            ["pipeline_operator"],
        )
        with self.app.app_context():
            member = db.session.execute(
                select(Principal).where(Principal.username == member_username)
            ).scalar_one()
            self.assertNotEqual(member.password_hash, member_password)
            self.assertTrue(check_password_hash(member.password_hash, member_password))
            memberships = db.session.execute(
                select(ScopeMembership, Role.code)
                .join(Role, Role.role_id == ScopeMembership.role_id)
                .where(
                    ScopeMembership.scope_id == scope_id,
                    ScopeMembership.principal_id == member.principal_id,
                )
            ).all()
            self.assertEqual(
                {role_code for _membership, role_code in memberships},
                {"researcher", "pipeline_operator"},
            )
            self.assertTrue(
                all(
                    membership.granted_by == self.principal_id
                    for membership, _role_code in memberships
                )
            )
            audit = db.session.execute(
                select(RoleAssignmentAudit).where(
                    RoleAssignmentAudit.scope_id == scope_id,
                    RoleAssignmentAudit.principal_id == member.principal_id,
                )
            ).scalar_one()
            self.assertEqual(audit.event_type, "member_created")
            self.assertEqual(audit.roles_before, [])
            self.assertEqual(
                audit.roles_after,
                ["researcher", "pipeline_operator"],
            )

        list_response = self.client.get(
            f"/api/v1/scopes/{scope_id}/members",
            headers=headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            {member["username"] for member in list_response.get_json()["members"]},
            {self.username, member_username},
        )
        listed_member = next(
            member
            for member in list_response.get_json()["members"]
            if member["username"] == member_username
        )
        self.assertEqual(listed_member["role"], "researcher")
        self.assertEqual(
            listed_member["additional_roles"],
            ["pipeline_operator"],
        )

    def test_member_creation_requires_membership_manage_permission(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_readable_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        response = self.client.post(
            f"/api/v1/scopes/{scope_id}/members",
            headers=self._headers(self._login()),
            json={
                "username": f"member-{secrets.token_hex(8)}",
                "password": secrets.token_urlsafe(24),
                "display_name": None,
                "role": "viewer",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "not_found")

    def test_composable_role_permission_matrix(self):
        expected_permissions = {
            "viewer": {"scope.read", "data.read"},
            "researcher": {
                "scope.read",
                "data.read",
                "data.import",
                "data.delete",
            },
            "analyst": {
                "scope.read",
                "project.manage",
                "data.read",
                "data.import",
                "data.delete",
            },
            "owner": {
                "scope.read",
                "scope.manage",
                "membership.manage",
                "project.manage",
                "data.read",
                "data.import",
                "data.delete",
                "pipeline.manage",
                "recon.execute",
            },
            "pipeline_operator": {"pipeline.execute"},
        }
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            permissions = {
                code: Permission(permission_id=index, code=code, label=code)
                for index, code in enumerate(
                    sorted(set().union(*expected_permissions.values())),
                    start=1,
                )
            }
            roles = {
                code: Role(role_id=index, code=code, label=code)
                for index, code in enumerate(expected_permissions, start=1)
            }
            db.session.add_all([*permissions.values(), *roles.values()])
            db.session.flush()
            principals = {}
            for role_code, permission_codes in expected_permissions.items():
                principal = Principal(
                    principal_id=uuid4(),
                    username=f"{role_code}-{uuid4()}",
                    password_hash=generate_password_hash("not-a-login-password"),
                )
                principals[role_code] = principal
                db.session.add(principal)
                db.session.add(
                    ScopeMembership(
                        scope_id=scope.scope_id,
                        principal_id=principal.principal_id,
                        role_id=roles[role_code].role_id,
                    )
                )
                db.session.add_all(
                    [
                        RolePermission(
                            role_id=roles[role_code].role_id,
                            permission_id=permissions[permission_code].permission_id,
                        )
                        for permission_code in permission_codes
                    ]
                )
            db.session.commit()

            all_permission_codes = set(permissions)
            for role_code, principal in principals.items():
                for permission_code in all_permission_codes:
                    self.assertEqual(
                        principal_has_scope_permission(
                            principal.principal_id,
                            scope.scope_id,
                            permission_code,
                        ),
                        permission_code in expected_permissions[role_code],
                        f"unexpected {permission_code} result for {role_code}",
                    )

            researcher = principals["researcher"]
            db.session.add(
                ScopeMembership(
                    scope_id=scope.scope_id,
                    principal_id=researcher.principal_id,
                    role_id=roles["pipeline_operator"].role_id,
                )
            )
            db.session.commit()
            self.assertTrue(
                principal_has_scope_permission(
                    researcher.principal_id,
                    scope.scope_id,
                    "pipeline.execute",
                )
            )

    def test_owner_can_update_roles_and_read_paginated_audit(self):
        member_username = f"member-{secrets.token_hex(8)}"
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_owner_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        headers = self._headers(self._login())
        created = self.client.post(
            f"/api/v1/scopes/{scope_id}/members",
            headers=headers,
            json={
                "username": member_username,
                "password": secrets.token_urlsafe(24),
                "display_name": "Second owner",
                "role": "owner",
            },
        )
        self.assertEqual(created.status_code, 201)
        principal_id = created.get_json()["member"]["principal_id"]

        updated = self.client.put(
            f"/api/v1/scopes/{scope_id}/members/{principal_id}/roles",
            headers=headers,
            json={
                "role": "researcher",
                "additional_roles": ["pipeline_operator"],
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["member"]["role"], "researcher")
        self.assertEqual(
            updated.get_json()["member"]["additional_roles"],
            ["pipeline_operator"],
        )

        unchanged = self.client.put(
            f"/api/v1/scopes/{scope_id}/members/{principal_id}/roles",
            headers=headers,
            json={
                "role": "researcher",
                "additional_roles": ["pipeline_operator"],
            },
        )
        self.assertEqual(unchanged.status_code, 200)

        audit_page_one = self.client.get(
            f"/api/v1/scopes/{scope_id}/role-audit?page=1&per_page=1",
            headers=headers,
        )
        self.assertEqual(audit_page_one.status_code, 200)
        self.assertEqual(audit_page_one.get_json()["pagination"]["total"], 2)
        self.assertEqual(audit_page_one.get_json()["pagination"]["pages"], 2)
        self.assertEqual(
            audit_page_one.get_json()["events"][0]["event_type"],
            "roles_updated",
        )
        self.assertEqual(
            audit_page_one.get_json()["events"][0]["roles_before"],
            ["owner"],
        )
        self.assertEqual(
            audit_page_one.get_json()["events"][0]["roles_after"],
            ["researcher", "pipeline_operator"],
        )

        audit_page_two = self.client.get(
            f"/api/v1/scopes/{scope_id}/role-audit?page=2&per_page=1",
            headers=headers,
        )
        self.assertEqual(audit_page_two.status_code, 200)
        self.assertEqual(
            audit_page_two.get_json()["events"][0]["event_type"],
            "member_created",
        )

    def test_last_owner_cannot_be_demoted(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_owner_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        response = self.client.put(
            f"/api/v1/scopes/{scope_id}/members/{self.principal_id}/roles",
            headers=self._headers(self._login()),
            json={"role": "analyst", "additional_roles": []},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "last_owner_required",
        )
        with self.app.app_context():
            roles = db.session.execute(
                select(Role.code)
                .join(ScopeMembership, ScopeMembership.role_id == Role.role_id)
                .where(
                    ScopeMembership.scope_id == scope_id,
                    ScopeMembership.principal_id == self.principal_id,
                )
            ).scalars().all()
            self.assertEqual(roles, ["owner"])
            self.assertEqual(
                db.session.execute(
                    select(RoleAssignmentAudit).where(
                        RoleAssignmentAudit.scope_id == scope_id
                    )
                ).scalars().all(),
                [],
            )

    def test_role_payload_rejects_unknown_and_duplicate_roles(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_owner_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        headers = self._headers(self._login())
        invalid_selections = [
            {"role": "unknown", "additional_roles": []},
            {"role": "viewer", "additional_roles": ["unknown"]},
            {
                "role": "viewer",
                "additional_roles": ["pipeline_operator", "pipeline_operator"],
            },
            {"role": "viewer", "additional_roles": "pipeline_operator"},
        ]
        for index, selection in enumerate(invalid_selections):
            with self.subTest(selection=selection):
                response = self.client.post(
                    f"/api/v1/scopes/{scope_id}/members",
                    headers=headers,
                    json={
                        "username": f"invalid-{index}-{uuid4()}",
                        "password": secrets.token_urlsafe(24),
                        "display_name": None,
                        **selection,
                    },
                )
                self.assertEqual(response.status_code, 400)

    def test_role_management_and_audit_require_membership_manage(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            other_principal = Principal(
                principal_id=uuid4(),
                username=f"member-{uuid4()}",
                password_hash=generate_password_hash("not-a-login-password"),
            )
            db.session.add_all([scope, other_principal])
            db.session.flush()
            self._add_readable_membership(scope)
            db.session.add(
                ScopeMembership(
                    scope_id=scope.scope_id,
                    principal_id=other_principal.principal_id,
                    role_id=1,
                )
            )
            db.session.commit()
            scope_id = scope.scope_id
            other_principal_id = other_principal.principal_id

        headers = self._headers(self._login())
        update_response = self.client.put(
            f"/api/v1/scopes/{scope_id}/members/{other_principal_id}/roles",
            headers=headers,
            json={"role": "viewer", "additional_roles": []},
        )
        audit_response = self.client.get(
            f"/api/v1/scopes/{scope_id}/role-audit",
            headers=headers,
        )
        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(audit_response.status_code, 404)

    def test_registration_creates_inactive_principal_and_pending_request(self):
        registration_username = f"registration-{secrets.token_hex(8)}"
        registration_password = secrets.token_urlsafe(24)
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.commit()
            scope_name = scope.name
            scope_id = scope.scope_id

        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "username": registration_username,
                "password": registration_password,
                "display_name": "Waiting user",
                "scope_name": scope_name,
            },
        )

        self.assertEqual(response.status_code, 202)
        with self.app.app_context():
            principal = db.session.execute(
                select(Principal).where(Principal.username == registration_username)
            ).scalar_one()
            self.assertFalse(principal.is_active)
            self.assertTrue(
                check_password_hash(principal.password_hash, registration_password)
            )
            registration = db.session.get(
                RegistrationRequest,
                principal.principal_id,
            )
            self.assertEqual(registration.scope_id, scope_id)
            self.assertEqual(registration.status, "pending")

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": registration_username,
                "password": registration_password,
            },
        )
        self.assertEqual(login_response.status_code, 401)
        self.assertEqual(
            login_response.get_json()["error"]["code"],
            "invalid_credentials",
        )

    def test_registration_does_not_reveal_scope_or_username_existence(self):
        payload = {
            "username": self.username,
            "password": secrets.token_urlsafe(24),
            "display_name": None,
            "scope_name": f"missing-{uuid4()}",
        }
        missing_scope = self.client.post("/api/v1/auth/register", json=payload)

        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.commit()
            payload["scope_name"] = scope.name

        duplicate_username = self.client.post(
            "/api/v1/auth/register",
            json=payload,
        )

        self.assertEqual(missing_scope.status_code, 202)
        self.assertEqual(duplicate_username.status_code, 202)
        self.assertEqual(missing_scope.get_json(), duplicate_username.get_json())
        with self.app.app_context():
            principal_count = len(
                db.session.execute(
                    select(Principal).where(Principal.username == self.username)
                ).scalars().all()
            )
            self.assertEqual(principal_count, 1)

    def test_owner_can_approve_registration_and_enable_login(self):
        registration_username = f"registration-{secrets.token_hex(8)}"
        registration_password = secrets.token_urlsafe(24)
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_owner_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id
            scope_name = scope.name

        self.client.post(
            "/api/v1/auth/register",
            json={
                "username": registration_username,
                "password": registration_password,
                "display_name": None,
                "scope_name": scope_name,
            },
        )
        headers = self._headers(self._login())
        list_response = self.client.get(
            f"/api/v1/scopes/{scope_id}/registrations",
            headers=headers,
        )
        self.assertEqual(list_response.status_code, 200)
        registrations = list_response.get_json()["registrations"]
        self.assertEqual(len(registrations), 1)
        registration_principal_id = registrations[0]["principal_id"]

        approval_response = self.client.post(
            f"/api/v1/scopes/{scope_id}/registrations/"
            f"{registration_principal_id}/approve",
            headers=headers,
            json={
                "role": "researcher",
                "additional_roles": ["pipeline_operator"],
            },
        )

        self.assertEqual(approval_response.status_code, 200)
        self.assertEqual(
            approval_response.get_json()["member"]["role"],
            "researcher",
        )
        self.assertEqual(
            approval_response.get_json()["member"]["additional_roles"],
            ["pipeline_operator"],
        )
        with self.app.app_context():
            principal = db.session.get(
                Principal,
                UUID(registration_principal_id),
            )
            registration = db.session.get(
                RegistrationRequest,
                principal.principal_id,
            )
            self.assertTrue(principal.is_active)
            self.assertEqual(registration.status, "approved")
            self.assertEqual(registration.reviewed_by, self.principal_id)
            memberships = db.session.execute(
                select(ScopeMembership, Role.code)
                .join(Role, Role.role_id == ScopeMembership.role_id)
                .where(
                    ScopeMembership.scope_id == scope_id,
                    ScopeMembership.principal_id == principal.principal_id,
                )
            ).all()
            self.assertEqual(
                {role_code for _membership, role_code in memberships},
                {"researcher", "pipeline_operator"},
            )
            audit = db.session.execute(
                select(RoleAssignmentAudit).where(
                    RoleAssignmentAudit.scope_id == scope_id,
                    RoleAssignmentAudit.principal_id == principal.principal_id,
                )
            ).scalar_one()
            self.assertEqual(audit.event_type, "registration_approved")
            self.assertEqual(audit.roles_before, [])
            self.assertEqual(
                audit.roles_after,
                ["researcher", "pipeline_operator"],
            )

        login_response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": registration_username,
                "password": registration_password,
            },
        )
        self.assertEqual(login_response.status_code, 200)

    def test_registration_review_requires_membership_manage_permission(self):
        with self.app.app_context():
            scope = Scope(scope_id=uuid4(), name=f"scope-{uuid4()}")
            db.session.add(scope)
            db.session.flush()
            self._add_readable_membership(scope)
            db.session.commit()
            scope_id = scope.scope_id

        response = self.client.get(
            f"/api/v1/scopes/{scope_id}/registrations",
            headers=self._headers(self._login()),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
