from flask_smorest import Blueprint


bp = Blueprint(
    "projects",
    __name__,
    url_prefix="/api/v1/projects",
    description="Project imports, immutable artifacts, normalized assets, and evidence.",
)


from app.blueprints.projects import routes  # noqa: E402, F401
