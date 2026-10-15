from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Artifact,
    ImportBatch,
    ImportRecord,
    MlClaim,
    MlPrediction,
    ProjectAsset,
    Project,
)
from app.services.artifact_storage import get_artifact_storage
from app.services.imports import _get_or_create_asset, process_import
from app.services.parsers import (
    ParserError,
    domain_asset,
    ip_asset,
    url_asset,
)

MANIFEST_VERSION = "greyartifact-run-manifest/v1"
ML_PARSER_VERSION = "recon_ml_predictions_v1"
ML_PARSER_NAME = "recon_ml_predictions"
CLAIMS_PARSER_VERSION = "recon_ml_claims_v1"
CLAIMS_PARSER_NAME = "recon_ml_claims"
CLAIM_STATES = {"supported", "contradicted", "unknown", "insufficient_evidence", "abstain"}
MODEL_STATUSES = {"candidate", "validated", "approved", "retired"}
TOOL_PARSERS = {"simple_list", "subfinder", "dnsx", "httpx", "nuclei", "greyartifact_observations"}
_HEX = set("0123456789abcdef")


class ManifestError(ValueError):
    """The manifest or its referenced files are invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def _text(container: dict, key: str, where: str) -> str:
    value = container.get(key)
    _require(isinstance(value, str) and value.strip() != "", f"{where}.{key} must be a non-empty string")
    return value


def _sha256(container: dict, where: str) -> str:
    value = container.get("sha256")
    _require(
        isinstance(value, str) and len(value) == 64 and set(value) <= _HEX,
        f"{where}.sha256 must be a lowercase hex SHA-256",
    )
    return value


def _relative_path(container: dict, where: str) -> str:
    value = _text(container, "file", where)
    _require(
        not value.startswith("/") and "\\" not in value and ".." not in value.split("/"),
        f"{where}.file must be a safe relative path",
    )
    return value


def validate_manifest(manifest: object) -> None:
    _require(isinstance(manifest, dict), "manifest must be an object")
    _require(
        manifest.get("manifest_version") == MANIFEST_VERSION,
        f"manifest_version must be {MANIFEST_VERSION!r}",
    )
    _text(manifest, "source", "manifest")

    run = manifest.get("run")
    _require(isinstance(run, dict), "manifest.run must be an object")
    _text(run, "external_ref", "run")

    tools = manifest.get("tools", [])
    _require(isinstance(tools, list), "manifest.tools must be an array")
    for index, entry in enumerate(tools):
        where = f"tools[{index}]"
        _require(isinstance(entry, dict), f"{where} must be an object")
        _text(entry, "name", where)
        _text(entry, "version", where)
        _relative_path(entry, where)
        parser = _text(entry, "parser", where)
        _require(parser in TOOL_PARSERS, f"{where}.parser is not a known tool parser")
        _sha256(entry, where)
        _require(
            entry.get("redaction") in {"raw", "redacted"},
            f"{where}.redaction must be 'raw' or 'redacted'",
        )

    ml = manifest.get("ml")
    _require(isinstance(ml, dict), "manifest.ml is mandatory and must be an object")
    _text(ml, "model", "ml")
    _text(ml, "version", "ml")
    _require(ml.get("status") in MODEL_STATUSES, "ml.status is not a valid model status")
    _text(ml, "pipeline_release", "ml")
    _text(ml, "inference_run_ref", "ml")
    _relative_path(ml, "ml")
    _require(ml.get("parser") == ML_PARSER_VERSION, f"ml.parser must be {ML_PARSER_VERSION!r}")
    _sha256(ml, "ml")

    claims = manifest.get("claims")
    if claims is not None:
        _require(isinstance(claims, dict), "manifest.claims must be an object")
        _relative_path(claims, "claims")
        _require(
            claims.get("parser") == CLAIMS_PARSER_VERSION,
            f"claims.parser must be {CLAIMS_PARSER_VERSION!r}",
        )
        _sha256(claims, "claims")


def _entity_asset(entity_type: str, value: object):
    if entity_type == "domain":
        return domain_asset(value)
    if entity_type in {"ipv4", "ipv6"}:
        asset = ip_asset(value)
        if asset.type_code != entity_type:
            raise ParserError(f"entity_value is not {entity_type}")
        return asset
    if entity_type == "url":
        return url_asset(value)
    raise ParserError(f"unsupported entity_type: {entity_type}")


def _ml_lines(chunks):
    buffer = b"".join(chunks)
    for number, raw in enumerate(buffer.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ParserError(f"line {number}: invalid JSON") from exc
        if not isinstance(obj, dict):
            raise ParserError(f"line {number}: expected an object")
        yield number, obj


def _process_ml_file(import_id: UUID, parser_version: str, apply_line) -> ImportRecord:
    import_record = db.session.execute(
        select(ImportRecord).where(ImportRecord.import_id == import_id).with_for_update()
    ).scalar_one()
    if import_record.status == "completed":
        return import_record
    artifact = db.session.get(Artifact, import_record.artifact_id)
    storage = get_artifact_storage()
    try:
        for number, obj in _ml_lines(storage.iter_bytes(artifact.storage_key)):
            apply_line(import_record, number, obj)
        import_record.parser_version = parser_version
        import_record.status = "completed"
        import_record.error_message = None
        db.session.commit()
        return import_record
    except ParserError as exc:
        db.session.rollback()
        failed = db.session.get(ImportRecord, import_id)
        failed.parser_version = parser_version
        failed.status = "failed"
        failed.error_message = str(exc)[:2000]
        db.session.commit()
        raise


def _link_project_asset(project_id: UUID, asset) -> None:
    if db.session.get(ProjectAsset, (project_id, asset.asset_id)) is None:
        db.session.add(ProjectAsset(project_id=project_id, asset_id=asset.asset_id))


def process_ml_predictions(import_id: UUID, batch: ImportBatch) -> ImportRecord:
    seen_assets: set[UUID] = set()

    def apply_line(import_record: ImportRecord, number: int, obj: dict) -> None:
        entity_type = obj.get("entity_type")
        parsed = _entity_asset(entity_type, obj.get("entity_value"))
        percentile = obj.get("percentile")
        rank = obj.get("rank")
        if not isinstance(percentile, (int, float)) or isinstance(percentile, bool):
            raise ParserError(f"line {number}: percentile must be a number")
        if not (0 <= percentile <= 100):
            raise ParserError(f"line {number}: percentile must be in [0, 100]")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0:
            raise ParserError(f"line {number}: rank must be a positive integer")
        explanation = obj.get("explanation", {})
        if not isinstance(explanation, dict):
            raise ParserError(f"line {number}: explanation must be an object")
        asset = _get_or_create_asset(parsed)
        if asset.asset_id in seen_assets:
            raise ParserError(f"line {number}: duplicate entity in predictions")
        seen_assets.add(asset.asset_id)
        _link_project_asset(import_record.project_id, asset)
        db.session.add(
            MlPrediction(
                prediction_id=uuid4(),
                batch_id=batch.batch_id,
                import_id=import_record.import_id,
                asset_id=asset.asset_id,
                model_version=batch.ml_model_version,
                model_status=batch.ml_model_status,
                percentile=float(percentile),
                rank=rank,
                explanation_json=explanation,
                evidence_locator=f"line:{number}",
                is_sensitive=False,
            )
        )

    return _process_ml_file(import_id, ML_PARSER_VERSION, apply_line)


def _claim_text(claim: dict, key: str, where: str) -> str:
    value = claim.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ParserError(f"{where}.{key} must be a non-empty string")
    return value


def _claim_objects(claim: dict, key: str, where: str) -> list:
    value = claim.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ParserError(f"{where}.{key} must be an array of objects")
    return value


def _claim_timestamp(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise ParserError(f"{where}.as_of must be an ISO 8601 timestamp with timezone")
    return parsed


def process_ml_claims(import_id: UUID, batch: ImportBatch) -> ImportRecord:
    """Store Stage-8 claim states for display; candidates are never executed."""
    seen: set[tuple[UUID, str]] = set()

    def apply_line(import_record: ImportRecord, number: int, obj: dict) -> None:
        parsed = _entity_asset(obj.get("entity_type"), obj.get("entity_value"))
        claims = obj.get("claims")
        if not isinstance(claims, list) or not claims:
            raise ParserError(f"line {number}: claims must be a non-empty array")
        asset = _get_or_create_asset(parsed)
        _link_project_asset(import_record.project_id, asset)
        for index, claim in enumerate(claims):
            where = f"line {number}: claims[{index}]"
            if not isinstance(claim, dict):
                raise ParserError(f"{where} must be an object")
            claim_key = _claim_text(claim, "claim", where)
            if (asset.asset_id, claim_key) in seen:
                raise ParserError(f"{where}: duplicate claim for this entity")
            seen.add((asset.asset_id, claim_key))
            state = claim.get("state")
            if state not in CLAIM_STATES:
                raise ParserError(f"{where}.state is not a valid claim state")
            db.session.add(
                MlClaim(
                    claim_id=uuid4(),
                    batch_id=batch.batch_id,
                    import_id=import_record.import_id,
                    asset_id=asset.asset_id,
                    claim_key=claim_key,
                    claim_version=_claim_text(claim, "version", where),
                    state=state,
                    as_of=_claim_timestamp(claim.get("as_of"), where),
                    engine_version=_claim_text(claim, "engine_version", where),
                    evidence_json=_claim_objects(claim, "evidence", where),
                    candidates_json=_claim_objects(claim, "candidates", where),
                )
            )

    return _process_ml_file(import_id, CLAIMS_PARSER_VERSION, apply_line)


def _store_import(project: Project, batch: ImportBatch, entry: dict, upload, parser_name: str) -> ImportRecord:
    stored = get_artifact_storage().store(upload.stream, upload.mimetype)
    if stored.sha256 != entry["sha256"]:
        raise ManifestError(f"{entry['file']}: content does not match the declared SHA-256")
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
    import_record = ImportRecord(
        import_id=uuid4(),
        project_id=project.project_id,
        artifact_id=artifact.artifact_id,
        original_filename=entry["file"],
        media_type=upload.mimetype or None,
        parser_name=parser_name,
        status="pending",
        uploaded_by=batch.created_by,
        batch_id=batch.batch_id,
    )
    db.session.add(import_record)
    db.session.flush()
    return import_record


def create_import_batch(project: Project, manifest: dict, files: dict, principal_id: UUID):
    """Store a run package and process every artifact. Returns (batch, results).

    Raises ManifestError for invalid input before any batch row is committed.
    """
    validate_manifest(manifest)
    tools = manifest.get("tools", [])
    ml = manifest["ml"]
    claims = manifest.get("claims")
    for entry in [*tools, ml, *([claims] if claims else [])]:
        if entry["file"] not in files or not files[entry["file"]].filename:
            raise ManifestError(f"missing file for manifest entry: {entry['file']}")

    batch = ImportBatch(
        batch_id=uuid4(),
        project_id=project.project_id,
        source=manifest["source"],
        manifest_version=MANIFEST_VERSION,
        external_run_ref=manifest["run"]["external_ref"],
        engagement_reference=manifest["run"].get("engagement_reference"),
        ml_model=ml["model"],
        ml_model_version=ml["version"],
        ml_model_status=ml["status"],
        ml_inference_run_ref=ml["inference_run_ref"],
        manifest_json=manifest,
        created_by=principal_id,
    )
    db.session.add(batch)
    db.session.flush()

    tool_records = [
        (_store_import(project, batch, entry, files[entry["file"]], entry["parser"]), entry["parser"])
        for entry in tools
    ]
    ml_record = _store_import(project, batch, ml, files[ml["file"]], ML_PARSER_NAME)
    claims_record = (
        _store_import(project, batch, claims, files[claims["file"]], CLAIMS_PARSER_NAME)
        if claims
        else None
    )
    db.session.commit()

    results: list[ImportRecord] = []
    for record, _parser in tool_records:
        try:
            results.append(process_import(record.import_id))
        except Exception:  # noqa: BLE001 - status is persisted; report per file
            results.append(db.session.get(ImportRecord, record.import_id))
    try:
        results.append(process_ml_predictions(ml_record.import_id, batch))
    except Exception:  # noqa: BLE001 - status is persisted; report per file
        results.append(db.session.get(ImportRecord, ml_record.import_id))
    if claims_record is not None:
        try:
            results.append(process_ml_claims(claims_record.import_id, batch))
        except Exception:  # noqa: BLE001 - status is persisted; report per file
            results.append(db.session.get(ImportRecord, claims_record.import_id))
    return batch, results
