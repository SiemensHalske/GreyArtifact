"""Read-only live health checks for the system status page (owners and admins).

Every check returns a state (ok, warning, error, unconfigured) plus structured
details; the page renders the text. Paths and the TLS hostname come from the
optional STATUS_* settings, so nothing host-specific lives in the code.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.services.artifact_storage import get_artifact_storage

STARTED_AT = datetime.now(timezone.utc)
BACKUP_NAME = re.compile(r"^greyartifact-(\d{8}T\d{6}Z)$")
DDNS_LINE = re.compile(r"^(\S+) (ipv[46]): (.*)$")
BACKUP_WARNING_HOURS = 26
BACKUP_ERROR_HOURS = 50
DDNS_WARNING_HOURS = 7
CERT_WARNING_DAYS = 14
CERT_ERROR_DAYS = 3
DISK_WARNING_RATIO = 0.85
DISK_ERROR_RATIO = 0.95
_SEVERITY = {"ok": 0, "unconfigured": 0, "warning": 1, "error": 2}


def _check(key: str, state: str, **details) -> dict:
    return {"key": key, "state": state, "details": details}


def _message(exc: BaseException) -> str:
    lines = str(exc).strip().splitlines()
    return f"{type(exc).__name__}: {lines[0]}"[:200] if lines else type(exc).__name__


def _hours_since(moment: datetime, now: datetime) -> float:
    return round((now - moment).total_seconds() / 3600, 1)


def check_app(now: datetime) -> dict:
    return _check(
        "app",
        "ok",
        started_at=STARTED_AT.isoformat(),
        uptime_seconds=int((now - STARTED_AT).total_seconds()),
        python=sys.version.split()[0],
    )


def check_database() -> dict:
    started = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception as exc:  # noqa: BLE001 - reported on the page, not raised
        db.session.rollback()
        return _check("database", "error", message=_message(exc))
    return _check("database", "ok", latency_ms=round((time.perf_counter() - started) * 1000, 1))


def check_object_storage() -> dict:
    started = time.perf_counter()
    try:
        storage = get_artifact_storage()
        storage.check()
    except Exception as exc:  # noqa: BLE001 - reported on the page, not raised
        return _check("object_storage", "error", message=_message(exc))
    return _check(
        "object_storage",
        "ok",
        bucket=getattr(storage, "bucket", None),
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )


def check_backup(directory: str | None, now: datetime) -> dict:
    if not directory:
        return _check("backup", "unconfigured", setting="STATUS_BACKUP_DIR")
    try:
        stamps = sorted(
            match.group(1)
            for entry in os.scandir(directory)
            if entry.is_dir() and (match := BACKUP_NAME.match(entry.name))
        )
    except OSError as exc:
        return _check("backup", "error", directory=directory, message=_message(exc))
    if not stamps:
        return _check("backup", "error", directory=directory, message="No backup found.")
    latest = datetime.strptime(stamps[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    age_hours = _hours_since(latest, now)
    checksums = (Path(directory) / f"greyartifact-{stamps[-1]}" / "SHA256SUMS").is_file()
    if age_hours > BACKUP_ERROR_HOURS or not checksums:
        state = "error"
    elif age_hours > BACKUP_WARNING_HOURS:
        state = "warning"
    else:
        state = "ok"
    return _check(
        "backup",
        state,
        directory=directory,
        latest=latest.isoformat(),
        age_hours=age_hours,
        checksums=checksums,
        count=len(stamps),
    )


def check_tls(hostname: str | None, address: str, now: datetime) -> dict:
    if not hostname:
        return _check("tls", "unconfigured", setting="STATUS_TLS_HOSTNAME")
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host.strip("[]"), int(port)), timeout=5) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=hostname) as tls:
                certificate = tls.getpeercert()
    except (OSError, ValueError) as exc:
        return _check("tls", "error", hostname=hostname, message=_message(exc))
    not_after = datetime.fromtimestamp(
        ssl.cert_time_to_seconds(certificate["notAfter"]), timezone.utc
    )
    days_left = round((not_after - now).total_seconds() / 86400, 1)
    issuer = dict(part[0] for part in certificate.get("issuer", ())).get("organizationName")
    if days_left < CERT_ERROR_DAYS:
        state = "error"
    elif days_left < CERT_WARNING_DAYS:
        state = "warning"
    else:
        state = "ok"
    return _check(
        "tls", state, hostname=hostname, not_after=not_after.isoformat(),
        days_left=days_left, issuer=issuer,
    )


def check_ddns(log_path: str | None, now: datetime) -> dict:
    if not log_path:
        return _check("ddns", "unconfigured", setting="STATUS_DDNS_LOG")
    try:
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return _check("ddns", "error", message=_message(exc))
    latest: dict[str, tuple[str, str]] = {}
    for line in lines[-50:]:
        match = DDNS_LINE.match(line)
        if match:
            latest[match.group(2)] = (match.group(1), match.group(3))
    if not latest:
        return _check("ddns", "error", message="No update recorded yet.")
    state = "ok"
    entries = []
    for family in sorted(latest):
        at_text, result = latest[family]
        try:
            at = datetime.strptime(at_text, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return _check("ddns", "error", message=f"Unreadable timestamp: {at_text}")
        age_hours = _hours_since(at, now)
        if not result.startswith("addresses ") or age_hours > DDNS_WARNING_HOURS:
            state = "warning"
        entries.append(
            {"family": family, "at": at.isoformat(), "age_hours": age_hours, "result": result[:200]}
        )
    return _check("ddns", state, entries=entries)


def check_disk(paths: list[str]) -> dict:
    state = "ok"
    volumes = []
    for path in paths:
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            state = "error"
            volumes.append({"path": path, "error": _message(exc)})
            continue
        ratio = round(usage.used / usage.total, 4) if usage.total else 0.0
        if ratio >= DISK_ERROR_RATIO:
            state = "error"
        elif ratio >= DISK_WARNING_RATIO and state == "ok":
            state = "warning"
        volumes.append(
            {"path": path, "total_bytes": usage.total, "used_bytes": usage.used, "used_ratio": ratio}
        )
    return _check("disk", state, volumes=volumes)


def collect_status() -> dict:
    config = current_app.config
    now = datetime.now(timezone.utc)
    checks = [
        check_app(now),
        check_database(),
        check_object_storage(),
        check_backup(config["STATUS_BACKUP_DIR"], now),
        check_tls(config["STATUS_TLS_HOSTNAME"], config["STATUS_TLS_ADDRESS"], now),
        check_ddns(config["STATUS_DDNS_LOG"], now),
        check_disk([path.strip() for path in config["STATUS_DISK_PATHS"].split(",") if path.strip()]),
    ]
    worst = max(_SEVERITY[check["state"]] for check in checks)
    overall = {0: "ok", 1: "warning", 2: "error"}[worst]
    return {"generated_at": now.isoformat(), "overall": overall, "checks": checks}
