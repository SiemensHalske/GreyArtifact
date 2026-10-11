import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.engine import URL

from app.extensions import api as smorest_api, db, jwt


def _database_url_from_environment() -> URL:
    required_settings = (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    )
    missing_settings = [
        setting
        for setting in required_settings
        if not os.environ.get(setting)
    ]
    if missing_settings:
        raise RuntimeError(
            "Missing required database settings: " +
            ", ".join(missing_settings)
        )

    if os.environ["DB_PASSWORD"] == "CHANGE_ME":
        raise RuntimeError("Set a private DB_PASSWORD in the root .env file.")

    try:
        port = int(os.environ["DB_PORT"])
    except ValueError as exc:
        raise RuntimeError("DB_PORT must be a valid integer.") from exc

    if not 1 <= port <= 65535:
        raise RuntimeError("DB_PORT must be between 1 and 65535.")

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=port,
        database=os.environ["DB_NAME"],
    )


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env")

    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY"),
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY"),
        S3_ENDPOINT_URL=os.environ.get("S3_ENDPOINT_URL"),
        S3_BUCKET=os.environ.get("S3_BUCKET"),
        S3_ACCESS_KEY=os.environ.get("S3_ACCESS_KEY"),
        S3_SECRET_KEY=os.environ.get("S3_SECRET_KEY"),
        S3_REGION=os.environ.get("S3_REGION", "us-east-1"),
        S3_USE_SSL=os.environ.get("S3_USE_SSL", "0").lower()
        in {"1", "true", "yes"},
        RUNNER_SUBFINDER_PATH=os.environ.get(
            "RUNNER_SUBFINDER_PATH", "/opt/greyartifact/bin/subfinder"
        ),
        RUNNER_DNSX_PATH=os.environ.get(
            "RUNNER_DNSX_PATH", "/opt/greyartifact/bin/dnsx"
        ),
        RUNNER_HTTPX_PATH=os.environ.get(
            "RUNNER_HTTPX_PATH", "/opt/greyartifact/bin/httpx"
        ),
    )
    if os.environ.get("MAX_ARTIFACT_BYTES"):
        try:
            app.config["MAX_ARTIFACT_BYTES"] = int(
                os.environ["MAX_ARTIFACT_BYTES"]
            )
        except ValueError as exc:
            raise RuntimeError("MAX_ARTIFACT_BYTES must be a valid integer.") from exc
    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = _database_url_from_environment()

    if (
        not app.config.get("JWT_SECRET_KEY")
        or app.config["JWT_SECRET_KEY"] == "CHANGE_ME"
    ):
        raise RuntimeError(
            "Set a private JWT_SECRET_KEY in the root .env file.")

    db.init_app(app)
    jwt.init_app(app)
    smorest_api.init_app(app)

    smorest_api.spec.components.security_scheme(
        "bearerAuth",
        {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        },
    )
    smorest_api.spec.options["security"] = []
    smorest_api.spec.options["servers"] = [{"url": "/"}]
    from app.schemas import ErrorSchema

    if "Error" not in smorest_api.spec.components.schemas:
        smorest_api.spec.components.schema("Error", schema=ErrorSchema)

    from app.api import register_error_handlers
    from app.auth import configure_jwt
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.projects import bp as projects_bp
    from app.blueprints.recon import bp as recon_bp
    from app.blueprints.scopes import bp as scopes_bp

    configure_jwt()
    register_error_handlers(app)
    app.register_blueprint(main_bp)
    smorest_api.register_blueprint(auth_bp)
    smorest_api.register_blueprint(scopes_bp)
    smorest_api.register_blueprint(projects_bp)
    smorest_api.register_blueprint(recon_bp)
    return app
