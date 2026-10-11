from flask import jsonify, render_template

from app.blueprints.main import bp


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/admin")
def admin():
    return render_template("admin.html")


@bp.get("/register")
def register():
    return render_template("register.html")


@bp.get("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})
