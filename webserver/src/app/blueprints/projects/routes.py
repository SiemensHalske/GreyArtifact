from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePath
from uuid import UUID, uuid4

from flask import Response, jsonify, request, stream_with_context
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api import error_response
from app.blueprints.projects import bp
from app.extensions import db
from app.models import (
    Artifact,
    Asset,
    AssetPropertyObservation,
    AssetRelationshipObservation,
    AssetType,
    Finding,
    FindingNote,
    FindingStatusAudit,
    ImportBatch,
    ImportRecord,
    MlClaim,
    MlPrediction,
    MlPredictionReview,
    Principal,
    Project,
    ProjectAsset,
    PropertyType,
    ReconRunStep,
    RelationshipType,
)
from app.schemas import (
    AssetDetailEnvelopeSchema,
    AssetListQuerySchema,
    AssetsEnvelopeSchema,
    CursorPaginationQuerySchema,
    ErrorSchema,
    FindingEnvelopeSchema,
    FindingHistoryEnvelopeSchema,
    ImportBatchEnvelopeSchema,
    ImportBatchesEnvelopeSchema,
    MlClaimsEnvelopeSchema,
    MlClaimsQuerySchema,
    MlPredictionReviewCreateSchema,
    MlPredictionReviewEnvelopeSchema,
    MlPredictionsEnvelopeSchema,
    FindingHistoryEventEnvelopeSchema,
    FindingListQuerySchema,
    FindingNoteCreateSchema,
    FindingStatusUpdateSchema,
    FindingsEnvelopeSchema,
    ImportEnvelopeSchema,
    ImportsEnvelopeSchema,
    ProjectEnvelopeSchema,
    ProjectUpdateSchema,
)
from app.services.artifact_storage import (
    ArtifactStorageUnavailable,
    ArtifactTooLarge,
    get_artifact_storage,
)
from app.services.authorization import principal_has_scope_permission
from app.services.imports import ImportConfigurationError, process_import
from app.services.import_batches import ManifestError, create_import_batch
from app.services.parsers import PARSER_VERSIONS, ParserError


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _serialize_project(project: Project) -> dict:
    return {
        "project_id": str(project.project_id),
        "scope_id": str(project.scope_id),
        "slug": project.slug,
        "name": project.name,
        "description": project.description,
        "created_at": _timestamp(project.created_at),
    }


def _authorized_project(project_id: str, permission: str) -> Project | None:
    parsed = _uuid_or_none(project_id)
    if parsed is None:
        return None
    project = db.session.get(Project, parsed)
    if project is None or not principal_has_scope_permission(
        current_user.principal_id, project.scope_id, permission
    ):
        return None
    return project


def _requires_sensitive_access(import_record: ImportRecord) -> bool:
    # Unprocessed content is unclassified, and identical bytes share one artifact
    # across imports, so any sensitive finding on that artifact restricts it.
    if import_record.status != "completed":
        return True
    return db.session.scalar(
        select(
            exists().where(
                Finding.import_id == ImportRecord.import_id,
                ImportRecord.artifact_id == import_record.artifact_id,
                Finding.is_sensitive.is_(True),
            )
        )
    )


def _serialize_import(import_record: ImportRecord, artifact: Artifact) -> dict:
    return {
        "import_id": str(import_record.import_id),
        "project_id": str(import_record.project_id),
        "artifact_id": str(artifact.artifact_id),
        "sha256": artifact.sha256,
        "byte_size": artifact.byte_size,
        "original_filename": import_record.original_filename,
        "media_type": import_record.media_type,
        "parser_name": import_record.parser_name,
        "parser_version": import_record.parser_version,
        "tool_version": import_record.tool_version,
        "status": import_record.status,
        "error_message": import_record.error_message,
        "imported_at": _timestamp(import_record.imported_at),
        "requires_sensitive_access": _requires_sensitive_access(import_record),
    }


@bp.get("/<project_id>")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ProjectEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Project not found")
@jwt_required()
def get_project(project_id: str):
    project = _authorized_project(project_id, "scope.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    return jsonify({"project": _serialize_project(project)})


@bp.put("/<project_id>")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(ProjectUpdateSchema, error_status_code=400)
@bp.response(200, ProjectEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Project not found")
@bp.alt_response(409, schema="Error", description="Slug already exists")
def update_project(payload: dict, project_id: str):
    project = _authorized_project(project_id, "project.manage")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    for field in ("slug", "name", "description"):
        if field in payload:
            value = payload[field]
            setattr(project, field, value.strip() if isinstance(value, str) else value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("project_conflict", "Project slug already exists.", 409)
    return jsonify({"project": _serialize_project(project)})


@bp.post("/<project_id>/imports")
@bp.doc(
    security=[{"bearerAuth": []}],
    requestBody={
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "oneOf": [
                        {"required": ["file", "tool"]},
                        {
                            "required": ["format"],
                            "anyOf": [
                                {"required": ["file"]},
                                {"required": ["text"]},
                            ],
                        },
                    ],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "text": {
                            "type": "string",
                            "description": "UTF-8 asset list pasted without a source file.",
                        },
                        "format": {
                            "type": "string",
                            "enum": [
                                "simple_list",
                                "subfinder",
                                "dnsx",
                                "httpx",
                                "nuclei",
                                "greyartifact_observations",
                            ],
                        },
                        "tool": {
                            "type": "string",
                            "enum": ["subfinder", "dnsx", "httpx", "nuclei"],
                            "deprecated": True,
                            "description": "Legacy alias for format.",
                        },
                        "tool_version": {"type": "string", "maxLength": 255},
                    },
                }
            }
        },
    },
)
@bp.response(201, ImportEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Project not found")
@bp.alt_response(413, schema="Error", description="Artifact too large")
@jwt_required()
def create_import(project_id: str):
    project = _authorized_project(project_id, "data.import")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    upload = request.files.get("file")
    parser_name = request.form.get("format") or request.form.get("tool", "")
    pasted_text = request.form.get("text")
    tool_version = request.form.get("tool_version")
    has_upload = upload is not None and bool(upload.filename)
    has_text = pasted_text is not None and bool(pasted_text.strip())
    if (
        parser_name not in PARSER_VERSIONS
        or parser_name != "simple_list" and not has_upload
        or parser_name == "simple_list" and has_upload == has_text
        or tool_version is not None
        and len(tool_version) > 255
    ):
        return error_response("invalid_request", "Invalid import data.", 400)

    if has_text:
        source = BytesIO(pasted_text.encode("utf-8"))
        filename = "pasted-assets.txt"
        media_type = "text/plain; charset=utf-8"
    else:
        filename = PurePath(upload.filename).name
        if not filename or len(filename) > 255:
            return error_response("invalid_request", "Invalid import data.", 400)
        source = upload.stream
        media_type = upload.mimetype
    try:
        stored = get_artifact_storage().store(source, media_type)
    except ArtifactTooLarge:
        return error_response("artifact_too_large", "Artifact exceeds upload limit.", 413)
    except ArtifactStorageUnavailable:
        return error_response(
            "artifact_storage_unavailable", "Artifact storage is unavailable.", 503
        )

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
        original_filename=filename,
        media_type=media_type or None,
        parser_name=parser_name,
        tool_version=tool_version.strip() if tool_version else None,
        status="pending",
        uploaded_by=current_user.principal_id,
    )
    db.session.add(import_record)
    db.session.commit()
    return jsonify({"import": _serialize_import(import_record, artifact)}), 201


def _serialize_batch(batch) -> dict:
    return {
        "batch_id": str(batch.batch_id),
        "project_id": str(batch.project_id),
        "source": batch.source,
        "manifest_version": batch.manifest_version,
        "external_run_ref": batch.external_run_ref,
        "engagement_reference": batch.engagement_reference,
        "ml_model": batch.ml_model,
        "ml_model_version": batch.ml_model_version,
        "ml_model_status": batch.ml_model_status,
        "ml_inference_run_ref": batch.ml_inference_run_ref,
        "created_at": _timestamp(batch.created_at),
    }


def _serialize_batch_import(record: ImportRecord) -> dict:
    return {
        "import_id": str(record.import_id),
        "original_filename": record.original_filename,
        "parser_name": record.parser_name,
        "status": record.status,
        "error_message": record.error_message,
    }


@bp.post("/<project_id>/import-batches")
@bp.doc(
    security=[{"bearerAuth": []}],
    requestBody={
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["manifest"],
                    "properties": {
                        "manifest": {
                            "type": "string",
                            "format": "binary",
                            "description": "greyartifact-run-manifest/v1 JSON.",
                        }
                    },
                    "additionalProperties": {
                        "type": "string",
                        "format": "binary",
                    },
                }
            }
        },
    },
)
@bp.response(201, ImportBatchEnvelopeSchema)
@bp.alt_response(400, schema="Error", description="Invalid manifest or files")
@bp.alt_response(404, schema="Error", description="Project not found")
@bp.alt_response(409, schema="Error", description="Run already imported")
@bp.alt_response(413, schema="Error", description="Artifact too large")
@jwt_required()
def create_import_batch_route(project_id: str):
    project = _authorized_project(project_id, "data.import")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    raw_manifest = request.files.get("manifest")
    try:
        if raw_manifest is not None and raw_manifest.filename:
            manifest = json.loads(raw_manifest.read().decode("utf-8"))
        elif request.form.get("manifest"):
            manifest = json.loads(request.form["manifest"])
        else:
            return error_response("invalid_request", "A manifest is required.", 400)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error_response("invalid_request", "The manifest is not valid JSON.", 400)
    files = {name: handle for name, handle in request.files.items() if name != "manifest"}
    try:
        batch, results = create_import_batch(
            project, manifest, files, current_user.principal_id
        )
    except ManifestError as exc:
        db.session.rollback()
        return error_response("invalid_manifest", str(exc), 400)
    except ArtifactTooLarge:
        db.session.rollback()
        return error_response("artifact_too_large", "Artifact exceeds upload limit.", 413)
    except ArtifactStorageUnavailable:
        db.session.rollback()
        return error_response(
            "artifact_storage_unavailable", "Artifact storage is unavailable.", 503
        )
    except IntegrityError:
        db.session.rollback()
        return error_response("batch_conflict", "This run has already been imported.", 409)
    return (
        jsonify(
            {
                "batch": _serialize_batch(batch),
                "imports": [_serialize_batch_import(record) for record in results],
            }
        ),
        201,
    )


def _serialize_review(review: MlPredictionReview, reviewer) -> dict:
    return {
        "review_id": str(review.review_id),
        "prediction_id": str(review.prediction_id),
        "decision": review.decision,
        "note": review.note,
        "reviewer": _serialize_principal(reviewer),
        "created_at": _timestamp(review.created_at),
    }


def _latest_reviews(prediction_ids: list) -> dict:
    if not prediction_ids:
        return {}
    rows = db.session.execute(
        select(MlPredictionReview, Principal)
        .join(Principal, Principal.principal_id == MlPredictionReview.reviewer_id)
        .where(MlPredictionReview.prediction_id.in_(prediction_ids))
        .order_by(
            MlPredictionReview.prediction_id,
            MlPredictionReview.created_at.desc(),
            MlPredictionReview.review_id.desc(),
        )
    ).all()
    latest: dict = {}
    for review, reviewer in rows:
        latest.setdefault(review.prediction_id, _serialize_review(review, reviewer))
    return latest


def _serialize_prediction(
    prediction: MlPrediction,
    asset: Asset,
    asset_type: AssetType,
    review: dict | None = None,
) -> dict:
    return {
        "prediction_id": str(prediction.prediction_id),
        "batch_id": str(prediction.batch_id),
        "asset": _serialize_asset(asset, asset_type),
        "model_version": prediction.model_version,
        "model_status": prediction.model_status,
        "percentile": prediction.percentile,
        "rank": prediction.rank,
        "explanation": prediction.explanation_json,
        "evidence_locator": prediction.evidence_locator,
        "is_sensitive": prediction.is_sensitive,
        "created_at": _timestamp(prediction.created_at),
        "review": review,
    }


@bp.get("/<project_id>/import-batches")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.response(200, ImportBatchesEnvelopeSchema)
def list_import_batches(project_id: str):
    project = _authorized_project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    rows = (
        db.session.execute(
            select(ImportBatch)
            .where(ImportBatch.project_id == project.project_id)
            .order_by(ImportBatch.created_at.desc(), ImportBatch.batch_id.desc())
        )
        .scalars()
        .all()
    )
    return jsonify({"batches": [_serialize_batch(batch) for batch in rows]})


@bp.get("/<project_id>/import-batches/<batch_id>/predictions")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(CursorPaginationQuerySchema, location="query", error_status_code=400)
@bp.response(200, MlPredictionsEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Batch not found")
def list_batch_predictions(pagination: dict, project_id: str, batch_id: str):
    project = _authorized_project(project_id, "data.read")
    parsed_batch_id = _uuid_or_none(batch_id)
    batch = (
        db.session.get(ImportBatch, parsed_batch_id)
        if project is not None and parsed_batch_id is not None
        else None
    )
    if project is None or batch is None or batch.project_id != project.project_id:
        return error_response("not_found", "Batch not found.", 404)
    limit = pagination["limit"]
    statement = (
        select(MlPrediction, Asset, AssetType)
        .join(Asset, Asset.asset_id == MlPrediction.asset_id)
        .join(AssetType, AssetType.asset_type_id == Asset.asset_type_id)
        .where(MlPrediction.batch_id == batch.batch_id)
        .order_by(MlPrediction.rank, MlPrediction.prediction_id)
    )
    cursor = pagination["cursor"]
    if cursor:
        cursor_row = db.session.get(MlPrediction, cursor)
        if cursor_row is None or cursor_row.batch_id != batch.batch_id:
            return error_response("invalid_request", "Invalid cursor.", 400)
        statement = statement.where(
            or_(
                MlPrediction.rank > cursor_row.rank,
                and_(
                    MlPrediction.rank == cursor_row.rank,
                    MlPrediction.prediction_id > cursor_row.prediction_id,
                ),
            )
        )
    rows = db.session.execute(statement.limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    reviews = _latest_reviews([prediction.prediction_id for prediction, _a, _t in rows])
    return jsonify(
        {
            "predictions": [
                _serialize_prediction(
                    prediction, asset, asset_type, reviews.get(prediction.prediction_id)
                )
                for prediction, asset, asset_type in rows
            ],
            "next_cursor": str(rows[-1][0].prediction_id) if has_more else None,
        }
    )


def _batch_in_project(project, batch_id: str):
    parsed = _uuid_or_none(batch_id)
    batch = db.session.get(ImportBatch, parsed) if parsed is not None else None
    if batch is None or batch.project_id != project.project_id:
        return None
    return batch


@bp.post("/<project_id>/ml-predictions/<prediction_id>/review")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(MlPredictionReviewCreateSchema, error_status_code=400)
@bp.response(201, MlPredictionReviewEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Prediction not found")
def create_prediction_review(payload: dict, project_id: str, prediction_id: str):
    project = _authorized_project(project_id, "data.import")
    parsed = _uuid_or_none(prediction_id)
    prediction = (
        db.session.execute(
            select(MlPrediction)
            .join(ImportBatch, ImportBatch.batch_id == MlPrediction.batch_id)
            .where(
                MlPrediction.prediction_id == parsed,
                ImportBatch.project_id == project.project_id,
            )
        ).scalar_one_or_none()
        if project is not None and parsed is not None
        else None
    )
    if prediction is None:
        return error_response("not_found", "Prediction not found.", 404)
    note = (payload.get("note") or "").strip() or None
    review = MlPredictionReview(
        review_id=uuid4(),
        prediction_id=prediction.prediction_id,
        reviewer_id=current_user.principal_id,
        decision=payload["decision"],
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(review)
    db.session.commit()
    return jsonify({"review": _serialize_review(review, current_user)}), 201


@bp.get("/<project_id>/import-batches/<batch_id>/review-feedback")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(
    200,
    description="Latest analyst decision per reviewed prediction, as JSONL for recon_ml.",
    content_type="application/x-ndjson",
)
@bp.alt_response(404, schema="Error", description="Batch not found")
@jwt_required()
def export_review_feedback(project_id: str, batch_id: str):
    project = _authorized_project(project_id, "data.read")
    batch = _batch_in_project(project, batch_id) if project is not None else None
    if project is None or batch is None:
        return error_response("not_found", "Batch not found.", 404)
    rows = db.session.execute(
        select(MlPrediction, Asset, AssetType, MlPredictionReview)
        .join(Asset, Asset.asset_id == MlPrediction.asset_id)
        .join(AssetType, AssetType.asset_type_id == Asset.asset_type_id)
        .join(
            MlPredictionReview,
            MlPredictionReview.prediction_id == MlPrediction.prediction_id,
        )
        .where(MlPrediction.batch_id == batch.batch_id)
        .order_by(
            MlPrediction.prediction_id,
            MlPredictionReview.created_at.desc(),
            MlPredictionReview.review_id.desc(),
        )
    ).all()
    seen: set = set()
    lines: list[str] = []
    for prediction, asset, asset_type, review in rows:
        if prediction.prediction_id in seen:
            continue
        seen.add(prediction.prediction_id)
        lines.append(
            json.dumps(
                {
                    "engagement_ref": batch.external_run_ref,
                    "inference_run_ref": batch.ml_inference_run_ref,
                    "entity_type": asset_type.code,
                    "entity_value": asset.canonical_value,
                    "decision": review.decision,
                    "note": review.note,
                    "decided_at": _timestamp(review.created_at),
                },
                ensure_ascii=False,
            )
        )
    body = ("\n".join(lines) + "\n") if lines else ""
    response = Response(body, content_type="application/x-ndjson")
    safe = batch.external_run_ref.replace(chr(34), "").replace("/", "_")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="review-feedback-{safe}.jsonl"'
    )
    return response


def _serialize_claim(claim: MlClaim) -> dict:
    return {
        "claim_id": str(claim.claim_id),
        "asset_id": str(claim.asset_id),
        "claim": claim.claim_key,
        "version": claim.claim_version,
        "state": claim.state,
        "as_of": _timestamp(claim.as_of),
        "engine_version": claim.engine_version,
        "evidence": claim.evidence_json,
        "candidates": claim.candidates_json,
    }


@bp.get("/<project_id>/import-batches/<batch_id>/claims")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(MlClaimsQuerySchema, location="query", error_status_code=400)
@bp.response(200, MlClaimsEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Batch not found")
def list_batch_claims(query: dict, project_id: str, batch_id: str):
    """Stage-8 claim states of a run, for display only.

    `summary` counts claims per claim and state; `claims` lists one asset's
    claims when `asset_id` is given. Acquisition candidates and recommendations
    are never executed from GreyArtifact.
    """
    project = _authorized_project(project_id, "data.read")
    batch = _batch_in_project(project, batch_id) if project is not None else None
    if project is None or batch is None:
        return error_response("not_found", "Batch not found.", 404)
    summary = db.session.execute(
        select(MlClaim.claim_key, MlClaim.state, func.count())
        .where(MlClaim.batch_id == batch.batch_id)
        .group_by(MlClaim.claim_key, MlClaim.state)
        .order_by(MlClaim.claim_key, MlClaim.state)
    ).all()
    claims = []
    if query["asset_id"] is not None:
        claims = (
            db.session.execute(
                select(MlClaim)
                .where(
                    MlClaim.batch_id == batch.batch_id,
                    MlClaim.asset_id == query["asset_id"],
                )
                .order_by(MlClaim.claim_key)
            )
            .scalars()
            .all()
        )
    return jsonify(
        {
            "summary": [
                {"claim": claim_key, "state": state, "count": count}
                for claim_key, state, count in summary
            ],
            "claims": [_serialize_claim(claim) for claim in claims],
        }
    )


@bp.get("/<project_id>/imports")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(CursorPaginationQuerySchema, location="query", error_status_code=400)
@bp.response(200, ImportsEnvelopeSchema)
def list_imports(pagination: dict, project_id: str):
    project = _authorized_project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    limit = pagination["limit"]
    statement = (
        select(ImportRecord, Artifact)
        .join(Artifact, Artifact.artifact_id == ImportRecord.artifact_id)
        .where(ImportRecord.project_id == project.project_id)
        .order_by(ImportRecord.imported_at.desc(), ImportRecord.import_id.desc())
        .limit(limit + 1)
    )
    cursor = pagination["cursor"]
    if cursor:
        cursor_row = db.session.get(ImportRecord, cursor)
        if cursor_row is None or cursor_row.project_id != project.project_id:
            return error_response("invalid_request", "Invalid cursor.", 400)
        statement = statement.where(
            or_(
                ImportRecord.imported_at < cursor_row.imported_at,
                and_(
                    ImportRecord.imported_at == cursor_row.imported_at,
                    ImportRecord.import_id < cursor_row.import_id,
                ),
            )
        )
    rows = db.session.execute(statement).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return jsonify(
        {
            "imports": [_serialize_import(item, artifact) for item, artifact in rows],
            "next_cursor": str(rows[-1][0].import_id) if has_more else None,
        }
    )


@bp.post("/<project_id>/imports/<import_id>/process")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ImportEnvelopeSchema)
@bp.alt_response(409, schema="Error", description="Report parsing failed")
@jwt_required()
def parse_import(project_id: str, import_id: str):
    project = _authorized_project(project_id, "data.import")
    parsed_import_id = _uuid_or_none(import_id)
    import_record = db.session.get(ImportRecord, parsed_import_id) if parsed_import_id else None
    if (
        project is None
        or import_record is None
        or import_record.project_id != project.project_id
    ):
        return error_response("not_found", "Import not found.", 404)
    try:
        import_record = process_import(import_record.import_id)
    except (ParserError, ImportConfigurationError):
        failed = db.session.get(ImportRecord, import_record.import_id)
        artifact = db.session.get(Artifact, failed.artifact_id)
        return (
            jsonify(
                {
                    "error": {
                        "code": "import_failed",
                        "message": failed.error_message,
                    },
                    "import": _serialize_import(failed, artifact),
                }
            ),
            409,
        )
    artifact = db.session.get(Artifact, import_record.artifact_id)
    return jsonify({"import": _serialize_import(import_record, artifact)})


@bp.get("/<project_id>/imports/<import_id>/artifact")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(
    200,
    description="The unchanged source artifact.",
    content_type="application/octet-stream",
)
@bp.alt_response(403, schema="Error", description="Sensitive artifact")
@bp.alt_response(404, schema="Error", description="Import not found")
@jwt_required()
def download_artifact(project_id: str, import_id: str):
    project = _authorized_project(project_id, "data.read")
    parsed_import_id = _uuid_or_none(import_id)
    import_record = db.session.get(ImportRecord, parsed_import_id) if parsed_import_id else None
    if (
        project is None
        or import_record is None
        or import_record.project_id != project.project_id
    ):
        return error_response("not_found", "Import not found.", 404)
    if _requires_sensitive_access(import_record) and not principal_has_scope_permission(
        current_user.principal_id, project.scope_id, "sensitive.read"
    ):
        return error_response(
            "sensitive_artifact",
            "This artifact may contain sensitive values and requires sensitive.read.",
            403,
        )
    artifact = db.session.get(Artifact, import_record.artifact_id)
    try:
        chunks = get_artifact_storage().iter_bytes(artifact.storage_key)
    except ArtifactStorageUnavailable:
        return error_response(
            "artifact_storage_unavailable", "Artifact storage is unavailable.", 503
        )
    response = Response(
        stream_with_context(chunks),
        content_type=import_record.media_type or "application/octet-stream",
    )
    response.headers["Content-Length"] = str(artifact.byte_size)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{import_record.original_filename.replace(chr(34), "")}"'
    )
    return response


def _serialize_asset(asset: Asset, asset_type: AssetType) -> dict:
    return {
        "asset_id": str(asset.asset_id),
        "type": asset_type.code,
        "canonical_value": asset.canonical_value,
        "display_value": asset.display_value,
        "created_at": _timestamp(asset.created_at),
    }


def _serialize_finding(
    finding: Finding,
    import_record: ImportRecord,
    artifact: Artifact,
    asset: Asset | None,
    asset_type: AssetType | None,
) -> dict:
    return {
        "finding_id": str(finding.finding_id),
        "project_id": str(finding.project_id),
        "import_id": str(finding.import_id),
        "artifact_id": str(artifact.artifact_id),
        "artifact_sha256": artifact.sha256,
        "asset": _serialize_asset(asset, asset_type) if asset and asset_type else None,
        "source": finding.source,
        "external_id": finding.external_id,
        "title": finding.title,
        "description": finding.description,
        "severity": finding.severity,
        "status": finding.status,
        "matcher_name": finding.matcher_name,
        "matched_at": finding.matched_at,
        "metadata": finding.metadata_json,
        "is_sensitive": finding.is_sensitive,
        "evidence_locator": finding.evidence_locator,
        "parser_name": import_record.parser_name,
        "parser_version": import_record.parser_version,
        "created_at": _timestamp(finding.created_at),
        "updated_at": _timestamp(finding.updated_at),
    }


def _finding_statement(project: Project):
    return (
        select(Finding, ImportRecord, Artifact, Asset, AssetType)
        .join(ImportRecord, ImportRecord.import_id == Finding.import_id)
        .join(Artifact, Artifact.artifact_id == ImportRecord.artifact_id)
        .outerjoin(Asset, Asset.asset_id == Finding.asset_id)
        .outerjoin(AssetType, AssetType.asset_type_id == Asset.asset_type_id)
        .where(Finding.project_id == project.project_id)
    )


@bp.get("/<project_id>/findings")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(FindingListQuerySchema, location="query", error_status_code=400)
@bp.response(200, FindingsEnvelopeSchema)
def list_findings(filters: dict, project_id: str):
    project = _authorized_project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    limit = filters["limit"]
    statement = _finding_statement(project).order_by(
        Finding.created_at.desc(), Finding.finding_id.desc()
    )
    if filters["severity"]:
        statement = statement.where(Finding.severity == filters["severity"])
    if filters["status"]:
        statement = statement.where(Finding.status == filters["status"])
    if filters["q"]:
        search = f"%{filters['q']}%"
        statement = statement.where(
            or_(
                Finding.title.ilike(search),
                Finding.external_id.ilike(search),
                Finding.matched_at.ilike(search),
            )
        )
    cursor = filters["cursor"]
    if cursor:
        cursor_row = db.session.get(Finding, cursor)
        if cursor_row is None or cursor_row.project_id != project.project_id:
            return error_response("invalid_request", "Invalid cursor.", 400)
        statement = statement.where(
            or_(
                Finding.created_at < cursor_row.created_at,
                and_(
                    Finding.created_at == cursor_row.created_at,
                    Finding.finding_id < cursor_row.finding_id,
                ),
            )
        )
    rows = db.session.execute(statement.limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return jsonify(
        {
            "findings": [_serialize_finding(*row) for row in rows],
            "next_cursor": str(rows[-1][0].finding_id) if has_more else None,
        }
    )


@bp.get("/<project_id>/findings/<finding_id>")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, FindingEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Finding not found")
@jwt_required()
def get_finding(project_id: str, finding_id: str):
    project = _authorized_project(project_id, "data.read")
    parsed_finding_id = _uuid_or_none(finding_id)
    row = (
        db.session.execute(
            _finding_statement(project).where(
                Finding.finding_id == parsed_finding_id
            )
        ).one_or_none()
        if project is not None and parsed_finding_id is not None
        else None
    )
    if row is None:
        return error_response("not_found", "Finding not found.", 404)
    return jsonify({"finding": _serialize_finding(*row)})


@bp.put("/<project_id>/findings/<finding_id>/status")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(FindingStatusUpdateSchema, error_status_code=400)
@bp.response(200, FindingEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Finding not found")
def update_finding_status(payload: dict, project_id: str, finding_id: str):
    project = _authorized_project(project_id, "data.import")
    parsed_finding_id = _uuid_or_none(finding_id)
    finding = (
        db.session.execute(
            select(Finding)
            .where(
                Finding.finding_id == parsed_finding_id,
                Finding.project_id == project.project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if project is not None and parsed_finding_id is not None
        else None
    )
    if finding is None:
        return error_response("not_found", "Finding not found.", 404)
    if finding.status != payload["status"]:
        now = datetime.now(timezone.utc)
        db.session.add(
            FindingStatusAudit(
                audit_id=uuid4(),
                finding_id=finding.finding_id,
                changed_by=current_user.principal_id,
                status_before=finding.status,
                status_after=payload["status"],
                changed_at=now,
            )
        )
        finding.status = payload["status"]
        finding.updated_at = now
        db.session.commit()
    row = db.session.execute(
        _finding_statement(project).where(Finding.finding_id == finding.finding_id)
    ).one()
    return jsonify({"finding": _serialize_finding(*row)})


def _authorized_finding(project_id: str, finding_id: str, permission: str) -> Finding | None:
    project = _authorized_project(project_id, permission)
    parsed_finding_id = _uuid_or_none(finding_id)
    if project is None or parsed_finding_id is None:
        return None
    finding = db.session.get(Finding, parsed_finding_id)
    if finding is None or finding.project_id != project.project_id:
        return None
    return finding


def _serialize_principal(principal: Principal) -> dict:
    return {
        "principal_id": str(principal.principal_id),
        "username": principal.username,
        "display_name": principal.display_name,
    }


def _serialize_note_event(note: FindingNote, author: Principal) -> dict:
    return {
        "kind": "note",
        "event_id": str(note.note_id),
        "actor": _serialize_principal(author),
        "occurred_at": _timestamp(note.created_at),
        "status_before": None,
        "status_after": None,
        "body": note.body,
    }


@bp.get("/<project_id>/findings/<finding_id>/history")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, FindingHistoryEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Finding not found")
@jwt_required()
def get_finding_history(project_id: str, finding_id: str):
    finding = _authorized_finding(project_id, finding_id, "data.read")
    if finding is None:
        return error_response("not_found", "Finding not found.", 404)
    status_rows = db.session.execute(
        select(FindingStatusAudit, Principal)
        .join(Principal, Principal.principal_id == FindingStatusAudit.changed_by)
        .where(FindingStatusAudit.finding_id == finding.finding_id)
    ).all()
    note_rows = db.session.execute(
        select(FindingNote, Principal)
        .join(Principal, Principal.principal_id == FindingNote.author_id)
        .where(FindingNote.finding_id == finding.finding_id)
    ).all()
    events = [
        (
            audit.changed_at,
            {
                "kind": "status",
                "event_id": str(audit.audit_id),
                "actor": _serialize_principal(actor),
                "occurred_at": _timestamp(audit.changed_at),
                "status_before": audit.status_before,
                "status_after": audit.status_after,
                "body": None,
            },
        )
        for audit, actor in status_rows
    ] + [(note.created_at, _serialize_note_event(note, author)) for note, author in note_rows]
    events.sort(key=lambda item: (item[0], item[1]["event_id"]))
    return jsonify({"events": [event for _, event in events]})


@bp.post("/<project_id>/findings/<finding_id>/notes")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(FindingNoteCreateSchema, error_status_code=400)
@bp.response(201, FindingHistoryEventEnvelopeSchema)
@bp.alt_response(404, schema="Error", description="Finding not found")
def create_finding_note(payload: dict, project_id: str, finding_id: str):
    finding = _authorized_finding(project_id, finding_id, "data.import")
    if finding is None:
        return error_response("not_found", "Finding not found.", 404)
    note = FindingNote(
        note_id=uuid4(),
        finding_id=finding.finding_id,
        author_id=current_user.principal_id,
        body=payload["body"].strip(),
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"event": _serialize_note_event(note, current_user)}), 201


def _serialize_property_value(value: str, value_kind: str):
    if value_kind == "number":
        try:
            number = Decimal(value)
        except InvalidOperation:
            return value
        if not number.is_finite():
            return value
        return int(number) if number == number.to_integral_value() else float(number)
    if value_kind == "boolean":
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return value


@bp.get("/<project_id>/assets")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(AssetListQuerySchema, location="query", error_status_code=400)
@bp.response(200, AssetsEnvelopeSchema)
def list_assets(filters: dict, project_id: str):
    project = _authorized_project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    limit = filters["limit"]
    statement = (
        select(Asset, AssetType)
        .join(ProjectAsset, ProjectAsset.asset_id == Asset.asset_id)
        .join(AssetType, AssetType.asset_type_id == Asset.asset_type_id)
        .where(ProjectAsset.project_id == project.project_id)
        .order_by(Asset.asset_id)
        .limit(limit + 1)
    )
    type_filter = filters["type"]
    search = filters["q"]
    cursor = filters["cursor"]
    if type_filter:
        statement = statement.where(AssetType.code == type_filter)
    if search:
        statement = statement.where(Asset.canonical_value.ilike(f"%{search}%"))
    if cursor:
        statement = statement.where(Asset.asset_id > cursor)
    rows = db.session.execute(statement).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return jsonify(
        {
            "assets": [_serialize_asset(asset, kind) for asset, kind in rows],
            "next_cursor": str(rows[-1][0].asset_id) if has_more else None,
        }
    )


@bp.get("/<project_id>/assets/<asset_id>")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, AssetDetailEnvelopeSchema)
@jwt_required()
def get_asset(project_id: str, asset_id: str):
    project = _authorized_project(project_id, "data.read")
    parsed_asset_id = _uuid_or_none(asset_id)
    row = (
        db.session.execute(
            select(Asset, AssetType)
            .join(ProjectAsset, ProjectAsset.asset_id == Asset.asset_id)
            .join(AssetType, AssetType.asset_type_id == Asset.asset_type_id)
            .where(
                ProjectAsset.project_id == project.project_id,
                Asset.asset_id == parsed_asset_id,
            )
        ).one_or_none()
        if project is not None and parsed_asset_id is not None
        else None
    )
    if row is None:
        return error_response("not_found", "Asset not found.", 404)
    asset, asset_type = row
    properties = db.session.execute(
        select(
            AssetPropertyObservation,
            PropertyType,
            ImportRecord,
            Artifact,
            ReconRunStep,
        )
        .join(PropertyType, PropertyType.property_type_id == AssetPropertyObservation.property_type_id)
        .join(ImportRecord, ImportRecord.import_id == AssetPropertyObservation.import_id)
        .join(Artifact, Artifact.artifact_id == ImportRecord.artifact_id)
        .outerjoin(
            ReconRunStep,
            ReconRunStep.step_id == ImportRecord.recon_run_step_id,
        )
        .where(
            AssetPropertyObservation.asset_id == asset.asset_id,
            ImportRecord.project_id == project.project_id,
        )
    ).all()
    relationships = db.session.execute(
        select(
            AssetRelationshipObservation,
            RelationshipType,
            ImportRecord,
            Artifact,
            ReconRunStep,
        )
        .join(RelationshipType, RelationshipType.relationship_type_id == AssetRelationshipObservation.relationship_type_id)
        .join(ImportRecord, ImportRecord.import_id == AssetRelationshipObservation.import_id)
        .join(Artifact, Artifact.artifact_id == ImportRecord.artifact_id)
        .outerjoin(
            ReconRunStep,
            ReconRunStep.step_id == ImportRecord.recon_run_step_id,
        )
        .where(
            ImportRecord.project_id == project.project_id,
            or_(
                AssetRelationshipObservation.source_asset_id == asset.asset_id,
                AssetRelationshipObservation.target_asset_id == asset.asset_id,
            ),
        )
    ).all()

    observations = []
    for observation, kind, import_record, artifact, recon_step in properties:
        observations.append(
            {
                "kind": "property",
                "observation_id": str(observation.observation_id),
                "code": kind.code,
                "value": _serialize_property_value(
                    observation.value_text,
                    kind.value_kind,
                ),
                "evidence_locator": observation.evidence_locator,
                "import_id": str(import_record.import_id),
                "artifact_id": str(artifact.artifact_id),
                "artifact_sha256": artifact.sha256,
                "parser_name": import_record.parser_name,
                "parser_version": import_record.parser_version,
                "recon_run_id": str(recon_step.run_id) if recon_step else None,
                "recon_run_step_id": (
                    str(recon_step.step_id) if recon_step else None
                ),
                "recon_operation": (
                    recon_step.operation_code if recon_step else None
                ),
            }
        )
    for observation, kind, import_record, artifact, recon_step in relationships:
        counterpart = (
            observation.target_asset_id
            if observation.source_asset_id == asset.asset_id
            else observation.source_asset_id
        )
        observations.append(
            {
                "kind": "relationship",
                "observation_id": str(observation.observation_id),
                "code": kind.code,
                "value": {"asset_id": str(counterpart)},
                "evidence_locator": observation.evidence_locator,
                "import_id": str(import_record.import_id),
                "artifact_id": str(artifact.artifact_id),
                "artifact_sha256": artifact.sha256,
                "parser_name": import_record.parser_name,
                "parser_version": import_record.parser_version,
                "recon_run_id": str(recon_step.run_id) if recon_step else None,
                "recon_run_step_id": (
                    str(recon_step.step_id) if recon_step else None
                ),
                "recon_operation": (
                    recon_step.operation_code if recon_step else None
                ),
            }
        )
    return jsonify(
        {"asset": _serialize_asset(asset, asset_type), "observations": observations}
    )
