from uuid import UUID

from flask_jwt_extended import create_access_token

from app.api import error_response
from app.extensions import db, jwt
from app.models import Principal


CREDENTIALS_VERSION_CLAIM = "cver"


def issue_access_token(principal: Principal) -> str:
    return create_access_token(
        identity=str(principal.principal_id),
        additional_claims={CREDENTIALS_VERSION_CLAIM: principal.credentials_version},
    )


def configure_jwt() -> None:
    @jwt.user_lookup_loader
    def load_principal(_jwt_header, jwt_data):
        try:
            principal_id = UUID(jwt_data["sub"])
        except (KeyError, TypeError, ValueError):
            return None

        principal = db.session.get(Principal, principal_id)
        if principal is None or not principal.is_active:
            return None
        # A password change invalidates every token issued before it.
        if jwt_data.get(CREDENTIALS_VERSION_CLAIM) != principal.credentials_version:
            return None
        return principal

    @jwt.user_lookup_error_loader
    def principal_not_found(_jwt_header, _jwt_data):
        return error_response("unauthorized", "Authentication required.", 401)

    @jwt.unauthorized_loader
    def missing_token(_reason):
        return error_response("unauthorized", "Authentication required.", 401)

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return error_response("unauthorized", "Invalid access token.", 401)

    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_data):
        return error_response("unauthorized", "Access token has expired.", 401)

    @jwt.revoked_token_loader
    def revoked_token(_jwt_header, _jwt_data):
        return error_response("unauthorized", "Invalid access token.", 401)

    @jwt.needs_fresh_token_loader
    def non_fresh_token(_jwt_header, _jwt_data):
        return error_response("unauthorized", "Invalid access token.", 401)
