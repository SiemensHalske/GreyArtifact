from uuid import UUID

from sqlalchemy import select

from app.extensions import db
from app.models import Permission, RolePermission, ScopeMembership


def principal_has_scope_permission(
    principal_id: UUID,
    scope_id: UUID,
    permission_code: str,
) -> bool:
    statement = (
        select(ScopeMembership.scope_id)
        .join(
            RolePermission,
            RolePermission.role_id == ScopeMembership.role_id,
        )
        .join(
            Permission,
            Permission.permission_id == RolePermission.permission_id,
        )
        .where(
            ScopeMembership.principal_id == principal_id,
            ScopeMembership.scope_id == scope_id,
            Permission.code == permission_code,
        )
        .limit(1)
    )
    return db.session.execute(statement).scalar_one_or_none() is not None
