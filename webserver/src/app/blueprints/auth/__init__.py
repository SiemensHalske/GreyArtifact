from flask_smorest import Blueprint


bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/v1/auth",
    description="Registration and short-lived bearer authentication.",
)


from app.blueprints.auth import routes  # noqa: E402, F401
