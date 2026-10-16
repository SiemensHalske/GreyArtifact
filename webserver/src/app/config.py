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
    LOGIN_THROTTLE_WINDOW_SECONDS = 15 * 60
    LOGIN_MAX_FAILURES_PER_USERNAME = 5
    LOGIN_MAX_FAILURES_PER_ADDRESS = 20
    TRUSTED_PROXY_COUNT = 0
    RUNNER_SUBFINDER_PATH = "/opt/greyartifact/bin/subfinder"
    RUNNER_DNSX_PATH = "/opt/greyartifact/bin/dnsx"
    RUNNER_HTTPX_PATH = "/opt/greyartifact/bin/httpx"
    STATUS_BACKUP_DIR = None
    STATUS_DDNS_LOG = None
    STATUS_TLS_HOSTNAME = None
    STATUS_TLS_ADDRESS = "127.0.0.1:443"
    STATUS_DISK_PATHS = "/"
    IMPRINT_FILE = None
    PRIVACY_FILE = None
