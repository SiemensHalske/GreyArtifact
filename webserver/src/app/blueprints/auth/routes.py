from uuid import uuid4

from flask import current_app, jsonify, request
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from app.api import error_response
from app.auth import issue_access_token
from app.blueprints.auth import bp
from app.extensions import db
from app.models import Principal, RegistrationRequest, Scope
from app.schemas import (
    LoginInputSchema,
    PasswordChangeSchema,
    PasswordChangedSchema,
    PrincipalEnvelopeSchema,
    ProfileUpdateSchema,
    RegistrationAcceptedSchema,
    RegistrationInputSchema,
    TokenSchema,
)


REGISTRATION_ACCEPTED = {
    "message": (
        "If the registration data is eligible, the request will be reviewed "
        "by a workspace owner."
    )
}


@bp.post("/register")
@bp.arguments(RegistrationInputSchema, error_status_code=400)
@bp.response(202, RegistrationAcceptedSchema)
@bp.alt_response(400, schema="Error", description="Invalid registration data")
def register(payload: dict):
    username = payload["username"]
    password = payload["password"]
    display_name = payload.get("display_name")
    scope_name = payload["scope_name"]

    # Hash every syntactically valid request before checking the workspace so
    # response timing does not trivially reveal whether that workspace exists.
    password_hash = generate_password_hash(password)
    scope = db.session.execute(
        select(Scope).where(Scope.name == scope_name.strip())
    ).scalar_one_or_none()
    if scope is None:
        return jsonify(REGISTRATION_ACCEPTED), 202

    principal = Principal(
        principal_id=uuid4(),
        username=username.strip(),
        password_hash=password_hash,
        display_name=display_name.strip() if display_name is not None else None,
        is_active=False,
    )
    registration_request = RegistrationRequest(
        principal_id=principal.principal_id,
        scope_id=scope.scope_id,
        status="pending",
    )
    try:
        db.session.add_all([principal, registration_request])
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    return jsonify(REGISTRATION_ACCEPTED), 202


@bp.post("/login")
@bp.arguments(LoginInputSchema, error_status_code=400)
@bp.response(200, TokenSchema)
@bp.alt_response(401, schema="Error", description="Invalid credentials")
@bp.alt_response(429, schema="Error", description="Too many failed login attempts")
def login(payload: dict):
    username = payload["username"]
    password = payload["password"]
    throttle = current_app.extensions["login_throttle"]
    retry_after = throttle.retry_after(username, request.remote_addr)
    if retry_after is not None:
        response, status = error_response(
            "too_many_attempts",
            "Too many failed login attempts. Try again later.",
            429,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response, status

    principal = db.session.execute(
        select(Principal).where(Principal.username == username)
    ).scalar_one_or_none()
    password_is_valid = False
    if principal is not None and principal.is_active:
        try:
            password_is_valid = check_password_hash(principal.password_hash, password)
        except ValueError:
            password_is_valid = False

    if not password_is_valid:
        throttle.record_failure(username, request.remote_addr)
        return error_response("invalid_credentials", "Invalid credentials.", 401)

    throttle.record_success(username)
    access_token = issue_access_token(principal)
    return jsonify({"access_token": access_token, "token_type": "Bearer"})


@bp.get("/me")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, PrincipalEnvelopeSchema)
@bp.alt_response(401, schema="Error", description="Authentication required")
@jwt_required()
def me():
    return jsonify(
        {
            "principal": {
                "principal_id": str(current_user.principal_id),
                "username": current_user.username,
                "display_name": current_user.display_name,
            }
        }
    )


@bp.patch("/me")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(ProfileUpdateSchema, error_status_code=400)
@bp.response(200, PrincipalEnvelopeSchema)
@bp.alt_response(401, schema="Error", description="Authentication required")
def update_profile(payload: dict):
    display_name = payload["display_name"]
    current_user.display_name = display_name.strip() if display_name else None
    db.session.commit()
    return jsonify(
        {
            "principal": {
                "principal_id": str(current_user.principal_id),
                "username": current_user.username,
                "display_name": current_user.display_name,
            }
        }
    )


@bp.put("/password")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(PasswordChangeSchema, error_status_code=400)
@bp.response(200, PasswordChangedSchema)
@bp.alt_response(400, schema="Error", description="Current password is invalid")
@bp.alt_response(409, schema="Error", description="New password matches current password")
def change_password(payload: dict):
    try:
        current_is_valid = check_password_hash(
            current_user.password_hash,
            payload["current_password"],
        )
    except ValueError:
        current_is_valid = False
    if not current_is_valid:
        return error_response(
            "invalid_current_password",
            "Current password is invalid.",
            400,
        )
    if check_password_hash(current_user.password_hash, payload["new_password"]):
        return error_response(
            "password_unchanged",
            "New password must differ from current password.",
            409,
        )
    current_user.password_hash = generate_password_hash(payload["new_password"])
    current_user.credentials_version += 1
    db.session.commit()
    return jsonify(
        {
            "status": "password_changed",
            "access_token": issue_access_token(current_user),
            "token_type": "Bearer",
        }
    )
