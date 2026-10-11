from __future__ import annotations

import io
import json
import os
import resource
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Artifact,
    ImportRecord,
    ReconRun,
    ReconRunStep,
    Tool,
)
from app.services.artifact_storage import get_artifact_storage
from app.services.imports import process_import
from app.services.parsers import ParserError, canonical_domain
from app.services.recon_scope import domain_is_authorized


class RunCancelled(RuntimeError):
    pass


class StepFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    output: bytes
    version: str


class ControlledProcessRunner:
    def __init__(self, max_memory_bytes: int, max_output_bytes: int):
        self.max_memory_bytes = max_memory_bytes
        self.max_output_bytes = max_output_bytes

    def _resource_limits(self, timeout_seconds: int):
        memory = self.max_memory_bytes
        output = self.max_output_bytes

        def apply_limits():
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_FSIZE, (output, output))
            cpu = max(1, timeout_seconds)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

        return apply_limits

    @staticmethod
    def _terminate_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    @staticmethod
    def version(binary: str) -> str:
        try:
            result = subprocess.run(
                [binary, "-version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=10,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StepFailed("Tool version check failed.") from exc
        if result.returncode != 0:
            raise StepFailed("Tool version check failed.")
        text = (result.stdout or result.stderr).decode("utf-8", "replace").strip()
        return text.splitlines()[0][:255] if text else Path(binary).name

    def execute(
        self,
        arguments: list[str],
        input_bytes: bytes,
        timeout_seconds: int,
        cancel_check,
    ) -> ProcessResult:
        if not arguments or not Path(arguments[0]).is_absolute():
            raise StepFailed("Runner binary path must be absolute.")
        version = self.version(arguments[0])
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(
                    arguments,
                    stdin=subprocess.PIPE,
                    stdout=output,
                    stderr=errors,
                    shell=False,
                    start_new_session=True,
                    preexec_fn=self._resource_limits(timeout_seconds),
                    close_fds=True,
                )
            except OSError as exc:
                raise StepFailed("Tool process could not be started.") from exc
            started = time.monotonic()
            sent_input = False
            while True:
                if cancel_check():
                    self._terminate_group(process)
                    raise RunCancelled("Cancellation requested.")
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    self._terminate_group(process)
                    raise StepFailed("Tool step exceeded its time limit.")
                try:
                    process.communicate(
                        input=input_bytes if not sent_input else None,
                        timeout=min(0.5, remaining),
                    )
                    break
                except subprocess.TimeoutExpired:
                    sent_input = True
            if process.returncode != 0:
                raise StepFailed(f"Tool step exited with status {process.returncode}.")
            size = output.tell()
            if size > self.max_output_bytes:
                raise StepFailed("Tool output exceeded its size limit.")
            output.seek(0)
            return ProcessResult(output.read(), version)


def claim_next_run() -> UUID | None:
    run = db.session.execute(
        select(ReconRun)
        .where(ReconRun.status == "pending", ReconRun.cancel_requested.is_(False))
        .order_by(ReconRun.created_at, ReconRun.run_id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        db.session.rollback()
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.session.commit()
    return run.run_id


def _cancel_requested(run_id: UUID) -> bool:
    db.session.expire_all()
    run = db.session.get(ReconRun, run_id)
    return run is None or run.cancel_requested


def _json_objects(output: bytes):
    for number, raw in enumerate(output.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StepFailed(f"Tool returned invalid JSONL at line {number}.") from exc
        if not isinstance(value, dict):
            raise StepFailed(f"Tool returned invalid JSONL at line {number}.")
        yield value


def _authorized_subfinder_hosts(output: bytes, snapshot: dict) -> list[str]:
    hosts = set()
    maximum = snapshot["limits"]["max_hosts"]
    for value in _json_objects(output):
        try:
            host = canonical_domain(value.get("host"))
        except ParserError as exc:
            raise StepFailed("Subfinder returned an invalid host.") from exc
        if domain_is_authorized(host, snapshot):
            hosts.add(host)
        if len(hosts) > maximum:
            raise StepFailed("Authorized host limit exceeded.")
    return sorted(hosts)


def _resolved_hosts(output: bytes, snapshot: dict) -> list[str]:
    hosts = set()
    maximum = snapshot["limits"]["max_hosts"]
    for value in _json_objects(output):
        addresses = value.get("a", []) or []
        addresses_v6 = value.get("aaaa", []) or []
        if not isinstance(addresses, list) or not isinstance(addresses_v6, list):
            raise StepFailed("DNSx returned invalid address data.")
        if not addresses and not addresses_v6:
            continue
        try:
            host = canonical_domain(value.get("host"))
        except ParserError as exc:
            raise StepFailed("DNSx returned an invalid host.") from exc
        if domain_is_authorized(host, snapshot):
            hosts.add(host)
        if len(hosts) > maximum:
            raise StepFailed("Resolved host limit exceeded.")
    return sorted(hosts)


def _store_step_output(
    run: ReconRun,
    step: ReconRunStep,
    output: bytes,
    version: str,
) -> ImportRecord:
    stored = get_artifact_storage().store(io.BytesIO(output), "application/x-ndjson")
    artifact = db.session.execute(
        select(Artifact).where(Artifact.sha256 == stored.sha256)
    ).scalar_one_or_none()
    if artifact is None:
        artifact = Artifact(
            artifact_id=uuid4(),
            sha256=stored.sha256,
            storage_key=stored.storage_key,
            byte_size=stored.byte_size,
        )
        db.session.add(artifact)
        db.session.flush()
    tool = db.session.execute(
        select(Tool).where(Tool.name == step.operation_code)
    ).scalar_one_or_none()
    if tool is None:
        tool = Tool(tool_id=uuid4(), name=step.operation_code, vendor="ProjectDiscovery")
        db.session.add(tool)
        db.session.flush()
    step.artifact_id = artifact.artifact_id
    step.tool_version = version
    import_record = ImportRecord(
        import_id=uuid4(),
        project_id=run.project_id,
        artifact_id=artifact.artifact_id,
        tool_id=tool.tool_id,
        tool_version=version,
        original_filename=f"{run.run_id}-{step.operation_code}.jsonl",
        media_type="application/x-ndjson",
        parser_name=step.operation_code,
        status="pending",
        uploaded_by=run.requested_by,
        recon_run_step_id=step.step_id,
    )
    db.session.add(import_record)
    db.session.commit()
    return import_record


def _commands(snapshot: dict, binaries: dict[str, str]):
    limits = snapshot["limits"]
    roots = sorted({item["domain"] for item in snapshot["allowed_targets"]})
    return {
        "subfinder": [
            binaries["subfinder"],
            "-d",
            ",".join(roots),
            "-oJ",
            "-silent",
            "-duc",
            "-rl",
            "20",
            "-t",
            "5",
            "-max-time",
            "5",
        ],
        "dnsx": [
            binaries["dnsx"],
            "-json",
            "-silent",
            "-a",
            "-aaaa",
            "-omit-raw",
            "-duc",
            "-rl",
            str(limits["dnsx_rate_limit"]),
            "-t",
            str(limits["max_parallelism"]),
            "-retry",
            "1",
        ],
        "httpx": [
            binaries["httpx"],
            "-json",
            "-silent",
            "-sc",
            "-title",
            "-server",
            "-ct",
            "-tls-grab",
            "-ip",
            "-ob",
            "-duc",
            "-rl",
            str(limits["httpx_rate_limit"]),
            "-t",
            str(limits["max_parallelism"]),
            "-timeout",
            "10",
            "-retries",
            "1",
        ],
    }


def execute_run(run_id: UUID, process_runner: ControlledProcessRunner | None = None) -> None:
    run = db.session.get(ReconRun, run_id)
    if run is None or run.status != "running":
        return
    snapshot = run.configuration_snapshot
    limits = snapshot["limits"]
    process_runner = process_runner or ControlledProcessRunner(
        limits["max_memory_bytes"], limits["max_output_bytes"]
    )
    binaries = {
        "subfinder": current_app.config["RUNNER_SUBFINDER_PATH"],
        "dnsx": current_app.config["RUNNER_DNSX_PATH"],
        "httpx": current_app.config["RUNNER_HTTPX_PATH"],
    }
    commands = _commands(snapshot, binaries)
    inputs = {"subfinder": b""}
    run_started = time.monotonic()
    total_output_bytes = 0
    try:
        steps = db.session.execute(
            select(ReconRunStep)
            .where(ReconRunStep.run_id == run.run_id)
            .order_by(ReconRunStep.step_number)
        ).scalars().all()
        for step in steps:
            if _cancel_requested(run.run_id):
                raise RunCancelled("Cancellation requested.")
            step.status = "running"
            step.started_at = datetime.now(timezone.utc)
            db.session.commit()
            remaining_total = limits["total_timeout_seconds"] - (
                time.monotonic() - run_started
            )
            if remaining_total <= 0:
                raise StepFailed("Recon run exceeded its total time limit.")
            timeout = min(
                limits[f"{step.operation_code}_timeout_seconds"],
                max(1, int(remaining_total)),
            )
            result = process_runner.execute(
                commands[step.operation_code],
                inputs[step.operation_code],
                timeout,
                lambda: _cancel_requested(run.run_id),
            )
            total_output_bytes += len(result.output)
            if total_output_bytes > limits["max_total_output_bytes"]:
                raise StepFailed("Recon run exceeded its total output limit.")
            import_record = _store_step_output(run, step, result.output, result.version)
            try:
                process_import(import_record.import_id)
            except (ParserError, RuntimeError) as exc:
                raise StepFailed("Tool output could not be normalized.") from exc
            step = db.session.get(ReconRunStep, step.step_id)
            step.status = "succeeded"
            step.finished_at = datetime.now(timezone.utc)
            db.session.commit()
            if step.operation_code == "subfinder":
                hosts = _authorized_subfinder_hosts(result.output, snapshot)
                inputs["dnsx"] = ("\n".join(hosts) + "\n").encode() if hosts else b""
            elif step.operation_code == "dnsx":
                hosts = _resolved_hosts(result.output, snapshot)
                inputs["httpx"] = ("\n".join(hosts) + "\n").encode() if hosts else b""
        run = db.session.get(ReconRun, run_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
    except RunCancelled:
        _finish_run(run_id, "cancelled", None)
    except Exception as exc:
        current = db.session.get(ReconRun, run_id)
        message = str(exc) if isinstance(exc, StepFailed) else "Runner step failed."
        _finish_run(current.run_id, "failed", message[:2000])


def _finish_run(run_id: UUID, status: str, error: str | None) -> None:
    db.session.rollback()
    run = db.session.get(ReconRun, run_id)
    if run is None:
        return
    now = datetime.now(timezone.utc)
    run.status = status
    run.error_message = error
    run.finished_at = now
    steps = db.session.execute(
        select(ReconRunStep)
        .where(ReconRunStep.run_id == run.run_id)
        .order_by(ReconRunStep.step_number)
    ).scalars().all()
    for step in steps:
        if step.status == "running":
            step.status = status
            step.finished_at = now
            step.error_message = error
        elif step.status == "pending":
            step.status = "cancelled" if status == "cancelled" else "skipped"
            step.finished_at = now
    db.session.commit()
