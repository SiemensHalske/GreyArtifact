from flask import Flask, jsonify


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(_error):
        return error_response("invalid_request", "Invalid request.", 400)

    @app.errorhandler(404)
    def not_found(_error):
        return error_response("not_found", "Resource not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return error_response("method_not_allowed", "Method not allowed.", 405)
