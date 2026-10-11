from uuid import uuid4

from flask import jsonify
from flask_jwt_extended import create_access_token, current_user, jwt_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from app.api import error_response
from app.blueprints.auth import bp
from app.extensions import db
from app.models import Principal, RegistrationRequest, Scope
from app.schemas import (
    LoginInputSchema,
    PrincipalEnvelopeSchema,
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
def login(payload: dict):
    username = payload["username"]
    password = payload["password"]

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
        return error_response("invalid_credentials", "Invalid credentials.", 401)

    access_token = create_access_token(identity=str(principal.principal_id))
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
