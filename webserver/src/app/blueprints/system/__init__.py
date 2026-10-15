from flask_smorest import Blueprint


bp = Blueprint(
    "system",
    __name__,
    url_prefix="/api/v1/system",
    description="Operational health of the host, for owners and admins.",
)


from app.blueprints.system import routes  # noqa: E402, F401
