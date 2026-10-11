from flask_smorest import Blueprint


bp = Blueprint(
    "recon",
    __name__,
    url_prefix="/api/v1",
    description="Authorized engagements and controlled domain_basic_v1 runs.",
)


from app.blueprints.recon import routes  # noqa: E402, F401
