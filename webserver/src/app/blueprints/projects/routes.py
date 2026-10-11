from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from uuid import UUID, uuid4

from flask import Response, jsonify, request, stream_with_context
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import and_, or_, select
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
    ImportRecord,
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
                    "required": ["file", "tool"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "tool": {
                            "type": "string",
                            "enum": ["subfinder", "dnsx", "httpx"],
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
    tool_name = request.form.get("tool", "")
    tool_version = request.form.get("tool_version")
    if (
        upload is None
        or not upload.filename
        or tool_name not in PARSER_VERSIONS
        or tool_version is not None
        and len(tool_version) > 255
    ):
        return error_response("invalid_request", "Invalid import data.", 400)
    filename = PurePath(upload.filename).name
    if not filename or len(filename) > 255:
        return error_response("invalid_request", "Invalid import data.", 400)
    try:
        stored = get_artifact_storage().store(upload.stream, upload.mimetype)
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
        media_type=upload.mimetype or None,
        parser_name=tool_name,
        tool_version=tool_version.strip() if tool_version else None,
        status="pending",
        uploaded_by=current_user.principal_id,
    )
    db.session.add(import_record)
    db.session.commit()
    return jsonify({"import": _serialize_import(import_record, artifact)}), 201


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
