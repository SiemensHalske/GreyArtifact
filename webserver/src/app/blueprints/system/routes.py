from flask import jsonify
from flask_jwt_extended import current_user, jwt_required

from app.api import error_response
from app.blueprints.system import bp
from app.schemas import SystemStatusEnvelopeSchema
from app.services.scope_access import list_scopes_with_permission
from app.services.system_status import collect_status


@bp.get("/status")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.response(200, SystemStatusEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Not an owner or admin")
def system_status():
    """Live health checks: app, database, object storage, backup, TLS
    certificate, dynamic DNS and disk usage.

    Restricted to principals with membership.manage in any scope; everyone
    else gets 404 so the endpoint does not reveal host details.
    """
    if not list_scopes_with_permission(current_user.principal_id, "membership.manage"):
        return error_response("not_found", "Not found.", 404)
    return jsonify(collect_status())
