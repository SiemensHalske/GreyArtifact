from datetime import datetime, timezone
from uuid import UUID, uuid4

from flask import jsonify
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from werkzeug.security import generate_password_hash

from app.api import error_response
from app.blueprints.scopes import bp
from app.extensions import db
from app.models import (
    Principal,
    Project,
    RegistrationRequest,
    Role,
    RoleAssignmentAudit,
    Scope,
    ScopeMembership,
)
from app.schemas import (
    MemberActiveUpdateSchema,
    MemberCreateSchema,
    MemberEnvelopeSchema,
    MemberPasswordResetSchema,
    MembersEnvelopeSchema,
    PagePaginationQuerySchema,
    ProfileUpdateSchema,
    ProjectCreateSchema,
    ProjectEnvelopeSchema,
    ProjectsEnvelopeSchema,
    RegistrationsEnvelopeSchema,
    RoleAuditEnvelopeSchema,
    RoleSelectionSchema,
    RoleUpdateSchema,
    ScopesEnvelopeSchema,
    StatusSchema,
)
from app.services.authorization import principal_has_scope_permission
from app.services.role_management import (
    InvalidRoleSelection,
    LastOwnerError,
    MembershipNotFoundError,
    member_role_codes,
    member_scope_ids,
    record_account_event,
    remove_member,
    replace_member_roles,
    split_role_codes,
    validate_role_selection,
)
from app.services.scope_access import list_scopes_with_permission


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _scope_id_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _serialize_scope(scope: Scope) -> dict:
    return {
        "scope_id": str(scope.scope_id),
        "name": scope.name,
        "description": scope.description,
        "created_at": _timestamp(scope.created_at),
    }


def _serialize_project(project: Project) -> dict:
    return {
        "project_id": str(project.project_id),
        "scope_id": str(project.scope_id),
        "slug": project.slug,
        "name": project.name,
        "description": project.description,
        "created_at": _timestamp(project.created_at),
    }


def _serialize_member(principal: Principal, role_codes: list[str]) -> dict:
    base_role, additional_roles = split_role_codes(role_codes)
    return {
        "principal_id": str(principal.principal_id),
        "username": principal.username,
        "display_name": principal.display_name,
        "is_active": principal.is_active,
        "role": base_role,
        "additional_roles": additional_roles,
    }


@bp.get("")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ScopesEnvelopeSchema)
@jwt_required()
def list_scopes():
    scopes = list_scopes_with_permission(current_user.principal_id, "scope.read")
    return jsonify({"scopes": [_serialize_scope(scope) for scope in scopes]})


@bp.get("/manageable")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ScopesEnvelopeSchema)
@jwt_required()
def list_manageable_scopes():
    scopes = list_scopes_with_permission(
        current_user.principal_id,
        "membership.manage",
    )
    return jsonify({"scopes": [_serialize_scope(scope) for scope in scopes]})


@bp.get("/<scope_id>/projects")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ProjectsEnvelopeSchema)
@jwt_required()
def list_projects(scope_id: str):
    parsed_scope_id = _scope_id_or_none(scope_id)
    if parsed_scope_id is None:
        return error_response("not_found", "Scope not found.", 404)

    if not principal_has_scope_permission(
        current_user.principal_id,
        parsed_scope_id,
        "scope.read",
    ):
        return error_response("not_found", "Scope not found.", 404)

    projects = db.session.execute(
        select(Project)
        .where(Project.scope_id == parsed_scope_id)
        .order_by(Project.name, Project.project_id)
    ).scalars().all()
    return jsonify(
        {
            "projects": [
                _serialize_project(project)
                for project in projects
            ]
        }
    )


@bp.post("/<scope_id>/projects")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(ProjectCreateSchema, error_status_code=400)
@bp.response(201, ProjectEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Scope not found")
@bp.alt_response(409, schema="Error", description="Slug already exists")
def create_project(payload: dict, scope_id: str):
    parsed_scope_id = _scope_id_or_none(scope_id)
    if parsed_scope_id is None or not principal_has_scope_permission(
        current_user.principal_id,
        parsed_scope_id,
        "project.manage",
    ):
        return error_response("not_found", "Scope not found.", 404)

    project = Project(
        project_id=uuid4(),
        scope_id=parsed_scope_id,
        slug=payload["slug"].strip(),
        name=payload["name"].strip(),
        description=(
            payload["description"].strip()
            if payload.get("description") is not None
            else None
        ),
    )
    try:
        db.session.add(project)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("project_conflict", "Project slug already exists.", 409)
    return jsonify({"project": _serialize_project(project)}), 201


@bp.get("/<scope_id>/members")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, MembersEnvelopeSchema)
@jwt_required()
def list_members(scope_id: str):
    parsed_scope_id = _scope_id_or_none(scope_id)
    if parsed_scope_id is None or not principal_has_scope_permission(
        current_user.principal_id,
        parsed_scope_id,
        "membership.manage",
    ):
        return error_response("not_found", "Scope not found.", 404)

    rows = db.session.execute(
        select(Principal, Role.code)
        .join(
            ScopeMembership,
            ScopeMembership.principal_id == Principal.principal_id,
        )
        .join(Role, Role.role_id == ScopeMembership.role_id)
        .where(ScopeMembership.scope_id == parsed_scope_id)
        .order_by(Principal.username, Principal.principal_id, Role.code)
    ).all()
    members: dict[UUID, tuple[Principal, list[str]]] = {}
    for principal, role_code in rows:
        if principal.principal_id not in members:
            members[principal.principal_id] = (principal, [])
        members[principal.principal_id][1].append(role_code)
    return jsonify(
        {
            "members": [
                _serialize_member(principal, role_codes)
                for principal, role_codes in members.values()
            ]
        }
    )


@bp.post("/<scope_id>/members")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(MemberCreateSchema, error_status_code=400)
@bp.response(201, MemberEnvelopeSchema)
def create_member(payload: dict, scope_id: str):
    parsed_scope_id = _scope_id_or_none(scope_id)
    if parsed_scope_id is None or not principal_has_scope_permission(
        current_user.principal_id,
        parsed_scope_id,
        "membership.manage",
    ):
        return error_response("not_found", "Scope not found.", 404)

    username = payload["username"]
    password = payload["password"]
    display_name = payload.get("display_name")
    try:
        role_code, additional_roles = validate_role_selection(
            payload.get("role"),
            payload.get("additional_roles", []),
        )
    except InvalidRoleSelection:
        return error_response("invalid_request", "Invalid member data.", 400)
    principal = Principal(
        principal_id=uuid4(),
        username=username.strip(),
        password_hash=generate_password_hash(password),
        display_name=display_name.strip() if display_name is not None else None,
        is_active=True,
    )
    try:
        db.session.add(principal)
        db.session.flush()
        _role_codes, _changed = replace_member_roles(
            scope_id=parsed_scope_id,
            principal_id=principal.principal_id,
            base_role=role_code,
            additional_roles=additional_roles,
            changed_by=current_user.principal_id,
            event_type="member_created",
            require_existing=False,
        )
        db.session.commit()
    except (IntegrityError, InvalidRoleSelection):
        db.session.rollback()
        return error_response(
            "member_not_created",
            "Member could not be created.",
            409,
        )

    return (
        jsonify(
            {
                "member": {
                    "principal_id": str(principal.principal_id),
                    "username": principal.username,
                    "display_name": principal.display_name,
                    "is_active": principal.is_active,
                    "role": role_code,
                    "additional_roles": list(additional_roles),
                }
            }
        ),
        201,
    )


def _manageable_scope_id(scope_id: str) -> UUID | None:
    parsed_scope_id = _scope_id_or_none(scope_id)
    if parsed_scope_id is None or not principal_has_scope_permission(
        current_user.principal_id,
        parsed_scope_id,
        "membership.manage",
    ):
        return None
    return parsed_scope_id


def _pending_registration(scope_id: UUID, principal_id: UUID):
    return db.session.execute(
        select(RegistrationRequest)
        .where(
            RegistrationRequest.scope_id == scope_id,
            RegistrationRequest.principal_id == principal_id,
            RegistrationRequest.status == "pending",
        )
        .with_for_update()
    ).scalar_one_or_none()


@bp.get("/<scope_id>/registrations")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, RegistrationsEnvelopeSchema)
@jwt_required()
def list_registrations(scope_id: str):
    parsed_scope_id = _manageable_scope_id(scope_id)
    if parsed_scope_id is None:
        return error_response("not_found", "Scope not found.", 404)

    rows = db.session.execute(
        select(RegistrationRequest, Principal)
        .join(Principal, Principal.principal_id == RegistrationRequest.principal_id)
        .where(
            RegistrationRequest.scope_id == parsed_scope_id,
            RegistrationRequest.status == "pending",
        )
        .order_by(
            RegistrationRequest.requested_at,
            RegistrationRequest.principal_id,
        )
    ).all()
    return jsonify(
        {
            "registrations": [
                {
                    "principal_id": str(principal.principal_id),
                    "username": principal.username,
                    "display_name": principal.display_name,
                    "requested_at": _timestamp(registration.requested_at),
                }
                for registration, principal in rows
            ]
        }
    )


@bp.post("/<scope_id>/registrations/<principal_id>/approve")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(RoleSelectionSchema, error_status_code=400)
@bp.response(200, MemberEnvelopeSchema)
def approve_registration(payload: dict, scope_id: str, principal_id: str):
    parsed_scope_id = _manageable_scope_id(scope_id)
    parsed_principal_id = _scope_id_or_none(principal_id)
    if parsed_scope_id is None or parsed_principal_id is None:
        return error_response("not_found", "Registration not found.", 404)

    try:
        role_code, additional_roles = validate_role_selection(
            payload.get("role"),
            payload.get("additional_roles", []),
        )
    except InvalidRoleSelection:
        return error_response("invalid_request", "Invalid approval data.", 400)

    registration = _pending_registration(parsed_scope_id, parsed_principal_id)
    principal = db.session.get(Principal, parsed_principal_id)
    if registration is None or principal is None:
        return error_response("not_found", "Registration not found.", 404)

    principal.is_active = True
    registration.status = "approved"
    registration.reviewed_at = datetime.now(timezone.utc)
    registration.reviewed_by = current_user.principal_id
    try:
        replace_member_roles(
            scope_id=parsed_scope_id,
            principal_id=parsed_principal_id,
            base_role=role_code,
            additional_roles=additional_roles,
            changed_by=current_user.principal_id,
            event_type="registration_approved",
            require_existing=False,
        )
        db.session.commit()
    except (IntegrityError, InvalidRoleSelection):
        db.session.rollback()
        return error_response(
            "registration_not_approved",
            "Registration could not be approved.",
            409,
        )

    return jsonify(
        {
            "member": {
                "principal_id": str(principal.principal_id),
                "username": principal.username,
                "display_name": principal.display_name,
                "is_active": principal.is_active,
                "role": role_code,
                "additional_roles": list(additional_roles),
            }
        }
    )


@bp.put("/<scope_id>/members/<principal_id>/roles")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(RoleUpdateSchema, error_status_code=400)
@bp.response(200, MemberEnvelopeSchema)
def update_member_roles(payload: dict, scope_id: str, principal_id: str):
    parsed_scope_id = _manageable_scope_id(scope_id)
    parsed_principal_id = _scope_id_or_none(principal_id)
    if parsed_scope_id is None or parsed_principal_id is None:
        return error_response("not_found", "Member not found.", 404)

    try:
        role_code, additional_roles = validate_role_selection(
            payload.get("role"),
            payload.get("additional_roles"),
        )
    except InvalidRoleSelection:
        return error_response("invalid_request", "Invalid role data.", 400)

    principal = db.session.get(Principal, parsed_principal_id)
    if principal is None:
        return error_response("not_found", "Member not found.", 404)

    try:
        role_codes, _changed = replace_member_roles(
            scope_id=parsed_scope_id,
            principal_id=parsed_principal_id,
            base_role=role_code,
            additional_roles=additional_roles,
            changed_by=current_user.principal_id,
            event_type="roles_updated",
            require_existing=True,
        )
        db.session.commit()
    except MembershipNotFoundError:
        db.session.rollback()
        return error_response("not_found", "Member not found.", 404)
    except LastOwnerError:
        db.session.rollback()
        return error_response(
            "last_owner_required",
            "The scope must retain at least one owner.",
            409,
        )
    except (IntegrityError, InvalidRoleSelection):
        db.session.rollback()
        return error_response(
            "roles_not_updated",
            "Roles could not be updated.",
            409,
        )

    return jsonify({"member": _serialize_member(principal, role_codes)})


def _managed_member(scope_id: str, principal_id: str):
    """The principal and its roles, if it is a member of a scope the caller manages."""
    parsed_scope_id = _manageable_scope_id(scope_id)
    parsed_principal_id = _scope_id_or_none(principal_id)
    if parsed_scope_id is None or parsed_principal_id is None:
        return None, None, []
    principal = db.session.get(Principal, parsed_principal_id)
    roles = member_role_codes(parsed_scope_id, parsed_principal_id) if principal else []
    if principal is None or not roles:
        return None, None, []
    return parsed_scope_id, principal, roles


def _account_change_refusal(principal: Principal):
    """Account-wide changes need management rights in every scope of the member."""
    if principal.principal_id == current_user.principal_id:
        return error_response(
            "cannot_modify_self",
            "Use the profile page to change your own account.",
            409,
        )
    for member_scope_id in member_scope_ids(principal.principal_id):
        if not principal_has_scope_permission(
            current_user.principal_id,
            member_scope_id,
            "membership.manage",
        ):
            return error_response(
                "member_managed_elsewhere",
                "The member also belongs to a scope you do not manage.",
                403,
            )
    return None


@bp.patch("/<scope_id>/members/<principal_id>")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(ProfileUpdateSchema, error_status_code=400)
@bp.response(200, MemberEnvelopeSchema)
@bp.alt_response(403, schema="Error", description="Member belongs to an unmanaged scope")
@bp.alt_response(404, schema="Error", description="Member not found")
def update_member_profile(payload: dict, scope_id: str, principal_id: str):
    _scope_id, principal, roles = _managed_member(scope_id, principal_id)
    if principal is None:
        return error_response("not_found", "Member not found.", 404)
    # Changing one's own display name is harmless; only foreign accounts need
    # rights in all of their scopes.
    if principal.principal_id != current_user.principal_id:
        refusal = _account_change_refusal(principal)
        if refusal is not None:
            return refusal

    display_name = payload["display_name"]
    display_name = display_name.strip() if display_name else None
    if display_name != principal.display_name:
        principal.display_name = display_name
        record_account_event(
            principal=principal,
            changed_by=current_user.principal_id,
            event_type="display_name_updated",
        )
        db.session.commit()
    return jsonify({"member": _serialize_member(principal, roles)})


@bp.put("/<scope_id>/members/<principal_id>/active")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(MemberActiveUpdateSchema, error_status_code=400)
@bp.response(200, MemberEnvelopeSchema)
@bp.alt_response(403, schema="Error", description="Member belongs to an unmanaged scope")
@bp.alt_response(404, schema="Error", description="Member not found")
@bp.alt_response(409, schema="Error", description="Own account or last active owner")
def update_member_active(payload: dict, scope_id: str, principal_id: str):
    """Deactivate or reactivate an account.

    A deactivated account cannot sign in, and its tokens stop working at once.
    """
    _scope_id, principal, roles = _managed_member(scope_id, principal_id)
    if principal is None:
        return error_response("not_found", "Member not found.", 404)
    refusal = _account_change_refusal(principal)
    if refusal is not None:
        return refusal

    is_active = payload["is_active"]
    if is_active != principal.is_active:
        try:
            record_account_event(
                principal=principal,
                changed_by=current_user.principal_id,
                event_type="account_reactivated" if is_active else "account_deactivated",
            )
        except LastOwnerError:
            db.session.rollback()
            return error_response(
                "last_owner_required",
                "The scope must retain at least one active owner.",
                409,
            )
        principal.is_active = is_active
        if not is_active:
            principal.credentials_version += 1
        db.session.commit()
    return jsonify({"member": _serialize_member(principal, roles)})


@bp.put("/<scope_id>/members/<principal_id>/password")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.arguments(MemberPasswordResetSchema, error_status_code=400)
@bp.response(200, StatusSchema)
@bp.alt_response(403, schema="Error", description="Member belongs to an unmanaged scope")
@bp.alt_response(404, schema="Error", description="Member not found")
@bp.alt_response(409, schema="Error", description="Own account")
def reset_member_password(payload: dict, scope_id: str, principal_id: str):
    """Set a new password for a member; all of the member's tokens are revoked."""
    _scope_id, principal, _roles = _managed_member(scope_id, principal_id)
    if principal is None:
        return error_response("not_found", "Member not found.", 404)
    refusal = _account_change_refusal(principal)
    if refusal is not None:
        return refusal

    principal.password_hash = generate_password_hash(payload["new_password"])
    principal.credentials_version += 1
    record_account_event(
        principal=principal,
        changed_by=current_user.principal_id,
        event_type="password_reset",
    )
    db.session.commit()
    return jsonify({"status": "password_reset"})


@bp.delete("/<scope_id>/members/<principal_id>")
@jwt_required()
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, StatusSchema)
@bp.alt_response(404, schema="Error", description="Member not found")
@bp.alt_response(409, schema="Error", description="Own account or last active owner")
def delete_member(scope_id: str, principal_id: str):
    """Remove a member from this scope; the account itself is kept."""
    parsed_scope_id, principal, _roles = _managed_member(scope_id, principal_id)
    if principal is None:
        return error_response("not_found", "Member not found.", 404)
    if principal.principal_id == current_user.principal_id:
        return error_response(
            "cannot_modify_self",
            "You cannot remove yourself from a scope.",
            409,
        )
    try:
        remove_member(
            scope_id=parsed_scope_id,
            principal_id=principal.principal_id,
            changed_by=current_user.principal_id,
        )
        db.session.commit()
    except MembershipNotFoundError:
        db.session.rollback()
        return error_response("not_found", "Member not found.", 404)
    except LastOwnerError:
        db.session.rollback()
        return error_response(
            "last_owner_required",
            "The scope must retain at least one active owner.",
            409,
        )
    return jsonify({"status": "removed"})


@bp.get("/<scope_id>/role-audit")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(PagePaginationQuerySchema, location="query", error_status_code=400)
@bp.response(200, RoleAuditEnvelopeSchema)
def list_role_audit(pagination: dict, scope_id: str):
    parsed_scope_id = _manageable_scope_id(scope_id)
    if parsed_scope_id is None:
        return error_response("not_found", "Scope not found.", 404)

    page = pagination["page"]
    per_page = pagination["per_page"]

    target = aliased(Principal)
    actor = aliased(Principal)
    total = db.session.execute(
        select(func.count(RoleAssignmentAudit.audit_id)).where(
            RoleAssignmentAudit.scope_id == parsed_scope_id
        )
    ).scalar_one()
    rows = db.session.execute(
        select(RoleAssignmentAudit, target, actor)
        .join(target, target.principal_id == RoleAssignmentAudit.principal_id)
        .outerjoin(actor, actor.principal_id == RoleAssignmentAudit.changed_by)
        .where(RoleAssignmentAudit.scope_id == parsed_scope_id)
        .order_by(
            RoleAssignmentAudit.changed_at.desc(),
            RoleAssignmentAudit.audit_id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return jsonify(
        {
            "events": [
                {
                    "audit_id": str(event.audit_id),
                    "event_type": event.event_type,
                    "principal": {
                        "principal_id": str(target_principal.principal_id),
                        "username": target_principal.username,
                        "display_name": target_principal.display_name,
                    },
                    "changed_by": (
                        {
                            "principal_id": str(actor_principal.principal_id),
                            "username": actor_principal.username,
                            "display_name": actor_principal.display_name,
                        }
                        if actor_principal is not None
                        else None
                    ),
                    "roles_before": event.roles_before,
                    "roles_after": event.roles_after,
                    "changed_at": _timestamp(event.changed_at),
                }
                for event, target_principal, actor_principal in rows
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }
    )


@bp.post("/<scope_id>/registrations/<principal_id>/reject")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, StatusSchema)
@jwt_required()
def reject_registration(scope_id: str, principal_id: str):
    parsed_scope_id = _manageable_scope_id(scope_id)
    parsed_principal_id = _scope_id_or_none(principal_id)
    if parsed_scope_id is None or parsed_principal_id is None:
        return error_response("not_found", "Registration not found.", 404)

    registration = _pending_registration(parsed_scope_id, parsed_principal_id)
    if registration is None:
        return error_response("not_found", "Registration not found.", 404)

    registration.status = "rejected"
    registration.reviewed_at = datetime.now(timezone.utc)
    registration.reviewed_by = current_user.principal_id
    db.session.commit()
    return jsonify({"status": "rejected"})
