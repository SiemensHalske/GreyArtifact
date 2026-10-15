from flask import jsonify, make_response, render_template

from app.blueprints.main import bp


@bp.get("/")
def index():
    return render_template("index.html")


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
