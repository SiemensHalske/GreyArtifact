from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.extensions import db
from app.models import Principal, Role, RoleAssignmentAudit, Scope, ScopeMembership


BASE_ROLE_CODES = ("viewer", "researcher", "analyst", "owner")
ADDITIONAL_ROLE_CODES = ("pipeline_operator",)
AUDIT_EVENT_TYPES = (
    "bootstrap",
    "member_created",
    "registration_approved",
    "roles_updated",
)
# Account-level events keep the member's roles unchanged (before == after),
# except member_removed, which records the roles that were taken away.
ACCOUNT_EVENT_TYPES = (
    "member_removed",
    "account_deactivated",
    "account_reactivated",
    "password_reset",
    "display_name_updated",
)


class InvalidRoleSelection(ValueError):
    pass


class MembershipNotFoundError(LookupError):
    pass


class LastOwnerError(RuntimeError):
    pass


def validate_role_selection(
    base_role: object,
    additional_roles: object,
) -> tuple[str, tuple[str, ...]]:
    if base_role not in BASE_ROLE_CODES:
        raise InvalidRoleSelection
    if not isinstance(additional_roles, list):
        raise InvalidRoleSelection
    if (
        any(not isinstance(code, str) for code in additional_roles)
        or len(additional_roles) != len(set(additional_roles))
        or any(code not in ADDITIONAL_ROLE_CODES for code in additional_roles)
    ):
        raise InvalidRoleSelection
    return base_role, tuple(additional_roles)


def split_role_codes(role_codes: list[str] | tuple[str, ...]) -> tuple[str, list[str]]:
    base_roles = [code for code in role_codes if code in BASE_ROLE_CODES]
    additional_roles = [code for code in role_codes if code in ADDITIONAL_ROLE_CODES]
    if len(base_roles) != 1 or len(base_roles) + len(additional_roles) != len(role_codes):
        raise InvalidRoleSelection
    return base_roles[0], additional_roles


def ordered_role_codes(base_role: str, additional_roles: tuple[str, ...]) -> list[str]:
    return [base_role, *additional_roles]


def _lock_scope_role_assignments(scope_id: UUID) -> None:
    if db.session.get_bind().dialect.name != "postgresql":
        return

    # Serialize all role changes for a scope without requiring UPDATE access to
    # the otherwise read-only scopes table. The lock is released at transaction
    # end, including rollback.
    lock_key = int.from_bytes(scope_id.bytes[:8], byteorder="big", signed=True)
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _other_active_owner_exists(scope_id: UUID, principal_id: UUID) -> bool:
    # A deactivated owner cannot sign in, so only active owners keep a scope
    # manageable.
    other_owner = db.session.execute(
        select(ScopeMembership.principal_id)
        .join(Role, Role.role_id == ScopeMembership.role_id)
        .join(Principal, Principal.principal_id == ScopeMembership.principal_id)
        .where(
            ScopeMembership.scope_id == scope_id,
            ScopeMembership.principal_id != principal_id,
            Role.code == "owner",
            Principal.is_active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    return other_owner is not None


def member_role_codes(scope_id: UUID, principal_id: UUID) -> list[str]:
    """The member's roles in the scope, base role first; empty if none."""
    codes = db.session.execute(
        select(Role.code)
        .join(ScopeMembership, ScopeMembership.role_id == Role.role_id)
        .where(
            ScopeMembership.scope_id == scope_id,
            ScopeMembership.principal_id == principal_id,
        )
    ).scalars().all()
    if not codes:
        return []
    base_role, additional_roles = split_role_codes(list(codes))
    return ordered_role_codes(base_role, tuple(additional_roles))


def member_scope_ids(principal_id: UUID) -> list[UUID]:
    return sorted(
        set(
            db.session.execute(
                select(ScopeMembership.scope_id).where(
                    ScopeMembership.principal_id == principal_id
                )
            ).scalars().all()
        )
    )


def _add_account_audit(
    *,
    scope_id: UUID,
    principal_id: UUID,
    changed_by: UUID | None,
    event_type: str,
    roles_before: list[str],
    roles_after: list[str],
) -> None:
    if event_type not in ACCOUNT_EVENT_TYPES:
        raise ValueError("Unsupported account audit event type.")
    db.session.add(
        RoleAssignmentAudit(
            audit_id=uuid4(),
            scope_id=scope_id,
            principal_id=principal_id,
            changed_by=changed_by,
            event_type=event_type,
            roles_before=roles_before,
            roles_after=roles_after,
            changed_at=datetime.now(timezone.utc),
        )
    )


def remove_member(*, scope_id: UUID, principal_id: UUID, changed_by: UUID) -> list[str]:
    """Delete all of the member's roles in the scope; returns the removed roles."""
    _lock_scope_role_assignments(scope_id)
    memberships = db.session.execute(
        select(ScopeMembership).where(
            ScopeMembership.scope_id == scope_id,
            ScopeMembership.principal_id == principal_id,
        )
    ).scalars().all()
    if not memberships:
        raise MembershipNotFoundError
    removed = member_role_codes(scope_id, principal_id)
    if "owner" in removed and not _other_active_owner_exists(scope_id, principal_id):
        raise LastOwnerError
    for membership in memberships:
        db.session.delete(membership)
    _add_account_audit(
        scope_id=scope_id,
        principal_id=principal_id,
        changed_by=changed_by,
        event_type="member_removed",
        roles_before=removed,
        roles_after=[],
    )
    return removed


def record_account_event(
    *, principal: Principal, changed_by: UUID, event_type: str
) -> None:
    """Audit an account-wide change in every scope the principal belongs to.

    Deactivation is refused while the principal is the last active owner of
    any of those scopes.
    """
    scope_ids = member_scope_ids(principal.principal_id)
    # Sorted lock order keeps concurrent multi-scope changes deadlock free.
    for scope_id in scope_ids:
        _lock_scope_role_assignments(scope_id)
    roles_by_scope = {
        scope_id: member_role_codes(scope_id, principal.principal_id)
        for scope_id in scope_ids
    }
    if event_type == "account_deactivated":
        for scope_id, roles in roles_by_scope.items():
            if "owner" in roles and not _other_active_owner_exists(
                scope_id, principal.principal_id
            ):
                raise LastOwnerError
    for scope_id, roles in roles_by_scope.items():
        _add_account_audit(
            scope_id=scope_id,
            principal_id=principal.principal_id,
            changed_by=changed_by,
            event_type=event_type,
            roles_before=roles,
            roles_after=roles,
        )


def replace_member_roles(
    *,
    scope_id: UUID,
    principal_id: UUID,
    base_role: str,
    additional_roles: tuple[str, ...],
    changed_by: UUID | None,
    event_type: str,
    require_existing: bool,
) -> tuple[list[str], bool]:
    if event_type not in AUDIT_EVENT_TYPES:
        raise ValueError("Unsupported role audit event type.")

    _lock_scope_role_assignments(scope_id)
    scope = db.session.execute(
        select(Scope).where(Scope.scope_id == scope_id)
    ).scalar_one_or_none()
    if scope is None:
        raise MembershipNotFoundError

    memberships = db.session.execute(
        select(ScopeMembership, Role)
        .join(Role, Role.role_id == ScopeMembership.role_id)
        .where(
            ScopeMembership.scope_id == scope_id,
            ScopeMembership.principal_id == principal_id,
        )
    ).all()
    current_codes = [role.code for _membership, role in memberships]
    if require_existing and not current_codes:
        raise MembershipNotFoundError
    if current_codes:
        split_role_codes(current_codes)

    desired_codes = ordered_role_codes(base_role, additional_roles)
    current_set = set(current_codes)
    desired_set = set(desired_codes)
    if current_set == desired_set:
        return desired_codes, False

    if (
        "owner" in current_set
        and "owner" not in desired_set
        and not _other_active_owner_exists(scope_id, principal_id)
    ):
        raise LastOwnerError

    roles = db.session.execute(
        select(Role).where(Role.code.in_(desired_codes))
    ).scalars().all()
    roles_by_code = {role.code: role for role in roles}
    if set(roles_by_code) != desired_set:
        raise InvalidRoleSelection

    for membership, role in memberships:
        if role.code not in desired_set:
            db.session.delete(membership)
    for role_code in desired_codes:
        if role_code not in current_set:
            db.session.add(
                ScopeMembership(
                    scope_id=scope_id,
                    principal_id=principal_id,
                    role_id=roles_by_code[role_code].role_id,
                    granted_by=changed_by,
                )
            )

    before = []
    if current_codes:
        current_base, current_additional = split_role_codes(current_codes)
        before = ordered_role_codes(current_base, tuple(current_additional))
    db.session.add(
        RoleAssignmentAudit(
            audit_id=uuid4(),
            scope_id=scope_id,
            principal_id=principal_id,
            changed_by=changed_by,
            event_type=event_type,
            roles_before=before,
            roles_after=desired_codes,
            changed_at=datetime.now(timezone.utc),
        )
    )
    return desired_codes, True
