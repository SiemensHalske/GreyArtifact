from pathlib import Path

from flask import abort, current_app, jsonify, make_response, render_template

from app.blueprints.main import bp


GITHUB_URL = "https://github.com/SiemensHalske/GreyArtifact"


@bp.app_context_processor
def inject_public_links():
    return {"github_url": GITHUB_URL}


# A template global, unlike a context processor, is also visible inside the
# imported shell macros.
@bp.app_template_global()
def legal_pages() -> dict:
    return {
        "imprint": bool(current_app.config.get("IMPRINT_FILE")),
        "privacy": bool(current_app.config.get("PRIVACY_FILE")),
    }


@bp.get("/")
def landing():
    return render_template("landing.html")


@bp.get("/dashboard")
def index():
    return render_template("index.html")


def _legal_page(setting: str, heading: str):
    # The text lives outside the public repository (it contains the operator's
    # address); it is rendered escaped, with line breaks kept by CSS.
    path = current_app.config.get(setting)
    if not path:
        abort(404)
    try:
        body = Path(path).read_text(encoding="utf-8")
    except OSError:
        current_app.logger.warning("%s is set but the file cannot be read.", setting)
        abort(404)
    return render_template("legal.html", heading=heading, body=body)


@bp.get("/impressum")
def imprint():
    return _legal_page("IMPRINT_FILE", "Impressum")


@bp.get("/datenschutz")
def privacy():
    return _legal_page("PRIVACY_FILE", "Datenschutzerklärung")


@bp.get("/admin")
def admin():
    return render_template("admin.html")


@bp.get("/projects/<project_id>")
def project(project_id: str):
    return render_template("project.html", project_id=project_id)


@bp.get("/profile")
def profile():
    return render_template("profile.html")


@bp.get("/status")
def status():
    return render_template("status.html")


@bp.get("/login")
def login():
    return render_template("login.html")


@bp.get("/register")
def register():
    return render_template("register.html")


# Swagger UI is loaded from jsDelivr, so this page alone may use that origin.
API_DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


@bp.get("/api/docs")
def api_docs():
    response = make_response(render_template("api_docs.html"))
    response.headers["Content-Security-Policy"] = API_DOCS_CONTENT_SECURITY_POLICY
    return response


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})
