from datetime import timedelta


class Config:
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    API_TITLE = "GreyArtifact API"
    API_VERSION = "1.0.0"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api/v1"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = None
    MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
    RUNNER_SUBFINDER_PATH = "/opt/greyartifact/bin/subfinder"
    RUNNER_DNSX_PATH = "/opt/greyartifact/bin/dnsx"
    RUNNER_HTTPX_PATH = "/opt/greyartifact/bin/httpx"
