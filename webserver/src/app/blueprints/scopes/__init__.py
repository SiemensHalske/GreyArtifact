from flask_smorest import Blueprint


bp = Blueprint(
    "scopes",
    __name__,
    url_prefix="/api/v1/scopes",
    description="Scope-bound workspaces, projects, members, and approvals.",
)


from app.blueprints.scopes import routes  # noqa: E402, F401
