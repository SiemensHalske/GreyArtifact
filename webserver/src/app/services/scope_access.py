from uuid import UUID

from sqlalchemy import select

from app.extensions import db
from app.models import Permission, RolePermission, Scope, ScopeMembership


def list_scopes_with_permission(
    principal_id: UUID,
    permission_code: str,
) -> list[Scope]:
    statement = (
        select(Scope)
        .join(ScopeMembership, ScopeMembership.scope_id == Scope.scope_id)
        .join(RolePermission, RolePermission.role_id == ScopeMembership.role_id)
        .join(Permission, Permission.permission_id == RolePermission.permission_id)
        .where(
            ScopeMembership.principal_id == principal_id,
            Permission.code == permission_code,
        )
        .distinct()
        .order_by(Scope.name, Scope.scope_id)
    )
    return list(db.session.execute(statement).scalars().all())
