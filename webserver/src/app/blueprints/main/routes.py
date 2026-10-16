import re
from pathlib import Path

from flask import abort, current_app, jsonify, make_response, render_template
from markupsafe import Markup, escape

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


_INLINE = (
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
)


_SHORT_LINE = 50


def _inline(line: str) -> str:
    html = str(escape(line))
    for pattern, replacement in _INLINE:
        html = pattern.sub(replacement, html)
    return html


def render_legal_text(text: str) -> Markup:
    """Render the Markdown subset used by the legal texts.

    Supports headings (## and ###), paragraphs, "- " lists with indented
    continuation lines, **bold** and `code`. A paragraph of short lines (an
    address or contact block) keeps its line breaks; longer lines are prose
    wrapped in the file and are joined like ordinary Markdown. Every line is
    escaped before any markup is added, so the file cannot inject HTML. A
    leading "# Title" is skipped because the page renders its own heading.
    """
    blocks: list[str] = []
    paragraph: list[str] = []
    paragraph_widths: list[int] = []
    items: list[str] = []

    def flush() -> None:
        if paragraph:
            short = all(width <= _SHORT_LINE for width in paragraph_widths)
            blocks.append("<p>" + ("<br>" if short else " ").join(paragraph) + "</p>")
            paragraph.clear()
            paragraph_widths.clear()
        if items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            items.clear()

    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("### "):
            flush()
            blocks.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            flush()
            blocks.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("- "):
            if paragraph:
                flush()
            items.append(_inline(stripped[2:]))
        elif items and line.startswith((" ", "\t")):
            items[-1] += " " + _inline(stripped)
        else:
            if items:
                flush()
            paragraph.append(_inline(stripped))
            paragraph_widths.append(len(stripped))
    flush()
    return Markup("".join(blocks))


def _legal_page(setting: str, heading: str):
    # The text lives outside the public repository (it contains the operator's
    # address) and may use a small Markdown subset, see render_legal_text.
    path = current_app.config.get(setting)
    if not path:
        abort(404)
    try:
        body = Path(path).read_text(encoding="utf-8")
    except OSError:
        current_app.logger.warning("%s is set but the file cannot be read.", setting)
        abort(404)
    return render_template("legal.html", heading=heading, body=render_legal_text(body))


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
