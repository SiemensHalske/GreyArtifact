from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from flask import jsonify
from flask_jwt_extended import current_user, jwt_required
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.api import error_response
from app.blueprints.recon import bp
from app.extensions import db
from app.models import (
    Engagement,
    EngagementTarget,
    Project,
    ReconRun,
    ReconRunStep,
)
from app.schemas import (
    EngagementEnvelopeSchema,
    EngagementsEnvelopeSchema,
    EngagementWriteSchema,
    CursorPaginationQuerySchema,
    ReconRunEnvelopeSchema,
    ReconRunsEnvelopeSchema,
)
from app.services.authorization import principal_has_scope_permission
from app.services.parsers import ParserError
from app.services.recon_scope import target_snapshot


PROFILE = "domain_basic_v1"
PROFILE_LIMITS = {
    "max_hosts": 10_000,
    "total_timeout_seconds": 1_200,
    "subfinder_timeout_seconds": 300,
    "dnsx_timeout_seconds": 300,
    "httpx_timeout_seconds": 600,
    "dnsx_rate_limit": 100,
    "httpx_rate_limit": 50,
    "max_output_bytes": 100 * 1024 * 1024,
    "max_total_output_bytes": 100 * 1024 * 1024,
    "max_memory_bytes": 512 * 1024 * 1024,
    "max_parallelism": 20,
}


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _timestamp(value):
    return value.isoformat() if value is not None else None


def _project(project_id: str, permission: str) -> Project | None:
    parsed = _uuid_or_none(project_id)
    project = db.session.get(Project, parsed) if parsed else None
    if project is None or not principal_has_scope_permission(
        current_user.principal_id, project.scope_id, permission
    ):
        return None
    return project


def _engagement_targets(engagement_id: UUID) -> list[EngagementTarget]:
    return list(
        db.session.execute(
            select(EngagementTarget)
            .where(EngagementTarget.engagement_id == engagement_id)
            .order_by(EngagementTarget.is_allowed.desc(), EngagementTarget.domain)
        ).scalars()
    )


def _serialize_engagement(engagement: Engagement) -> dict:
    targets = _engagement_targets(engagement.engagement_id)

    def serialize(target):
        return {
            "target_id": str(target.target_id),
            "domain": target.domain,
            "include_subdomains": target.include_subdomains,
        }

    return {
        "engagement_id": str(engagement.engagement_id),
        "project_id": str(engagement.project_id),
        "name": engagement.name,
        "authorization_reference": engagement.authorization_reference,
        "valid_from": engagement.valid_from.isoformat(),
        "valid_until": engagement.valid_until.isoformat(),
        "created_by": str(engagement.created_by),
        "created_at": _timestamp(engagement.created_at),
        "allowed_targets": [serialize(item) for item in targets if item.is_allowed],
        "excluded_targets": [serialize(item) for item in targets if not item.is_allowed],
    }


def _replace_targets(engagement: Engagement, payload: dict) -> None:
    db.session.query(EngagementTarget).filter_by(
        engagement_id=engagement.engagement_id
    ).delete()
    for is_allowed, key in ((True, "allowed_targets"), (False, "excluded_targets")):
        for target in target_snapshot(payload[key]):
            db.session.add(
                EngagementTarget(
                    target_id=uuid4(),
                    engagement_id=engagement.engagement_id,
                    domain=target["domain"],
                    is_allowed=is_allowed,
                    include_subdomains=target["include_subdomains"],
                )
            )


@bp.post("/projects/<project_id>/engagements")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(EngagementWriteSchema, error_status_code=400)
@bp.response(201, EngagementEnvelopeSchema)
@bp.alt_response(409, schema="Error", description="Engagement conflict")
def create_engagement(payload: dict, project_id: str):
    project = _project(project_id, "scope.manage")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    engagement = Engagement(
        engagement_id=uuid4(),
        project_id=project.project_id,
        name=payload["name"].strip(),
        authorization_reference=payload["authorization_reference"],
        valid_from=payload["valid_from"],
        valid_until=payload["valid_until"],
        created_by=current_user.principal_id,
    )
    try:
        db.session.add(engagement)
        db.session.flush()
        _replace_targets(engagement, payload)
        db.session.commit()
    except (IntegrityError, ParserError):
        db.session.rollback()
        return error_response(
            "engagement_conflict", "Engagement could not be created.", 409
        )
    return jsonify({"engagement": _serialize_engagement(engagement)}), 201


@bp.get("/projects/<project_id>/engagements")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, EngagementsEnvelopeSchema)
@jwt_required()
def list_engagements(project_id: str):
    project = _project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    engagements = db.session.execute(
        select(Engagement)
        .where(Engagement.project_id == project.project_id)
        .order_by(Engagement.created_at.desc(), Engagement.engagement_id.desc())
    ).scalars().all()
    return jsonify(
        {"engagements": [_serialize_engagement(item) for item in engagements]}
    )


def _authorized_engagement(engagement_id: str, permission: str):
    parsed = _uuid_or_none(engagement_id)
    engagement = db.session.get(Engagement, parsed) if parsed else None
    project = db.session.get(Project, engagement.project_id) if engagement else None
    if project is None or not principal_has_scope_permission(
        current_user.principal_id, project.scope_id, permission
    ):
        return None, None
    return engagement, project


@bp.put("/engagements/<engagement_id>")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(EngagementWriteSchema, error_status_code=400)
@bp.response(200, EngagementEnvelopeSchema)
def update_engagement(payload: dict, engagement_id: str):
    engagement, _project_value = _authorized_engagement(
        engagement_id, "scope.manage"
    )
    if engagement is None:
        return error_response("not_found", "Engagement not found.", 404)
    if db.session.execute(
        select(ReconRun.run_id).where(ReconRun.engagement_id == engagement.engagement_id).limit(1)
    ).scalar_one_or_none() is not None:
        return error_response(
            "engagement_locked", "Engagements with runs cannot be changed.", 409
        )
    engagement.name = payload["name"].strip()
    engagement.authorization_reference = payload["authorization_reference"]
    engagement.valid_from = payload["valid_from"]
    engagement.valid_until = payload["valid_until"]
    try:
        _replace_targets(engagement, payload)
        db.session.commit()
    except (IntegrityError, ParserError):
        db.session.rollback()
        return error_response(
            "engagement_conflict", "Engagement could not be updated.", 409
        )
    return jsonify({"engagement": _serialize_engagement(engagement)})


def _serialize_run(run: ReconRun) -> dict:
    steps = db.session.execute(
        select(ReconRunStep)
        .where(ReconRunStep.run_id == run.run_id)
        .order_by(ReconRunStep.step_number)
    ).scalars().all()
    return {
        "run_id": str(run.run_id),
        "project_id": str(run.project_id),
        "engagement_id": str(run.engagement_id),
        "requested_by": str(run.requested_by),
        "profile_code": run.profile_code,
        "status": run.status,
        "cancel_requested": run.cancel_requested,
        "configuration_snapshot": run.configuration_snapshot,
        "created_at": _timestamp(run.created_at),
        "started_at": _timestamp(run.started_at),
        "finished_at": _timestamp(run.finished_at),
        "error_message": run.error_message,
        "steps": [
            {
                "step_id": str(step.step_id),
                "step_number": step.step_number,
                "operation_code": step.operation_code,
                "tool_version": step.tool_version,
                "status": step.status,
                "artifact_id": str(step.artifact_id) if step.artifact_id else None,
                "started_at": _timestamp(step.started_at),
                "finished_at": _timestamp(step.finished_at),
                "error_message": step.error_message,
            }
            for step in steps
        ],
    }


@bp.post("/engagements/<engagement_id>/runs")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(201, ReconRunEnvelopeSchema)
@bp.alt_response(409, schema="Error", description="Engagement not runnable")
@jwt_required()
def start_run(engagement_id: str):
    engagement, project = _authorized_engagement(engagement_id, "recon.execute")
    if engagement is None:
        return error_response("not_found", "Engagement not found.", 404)
    today = date.today()
    if not engagement.valid_from <= today <= engagement.valid_until:
        return error_response(
            "engagement_not_valid", "Engagement is outside its validity period.", 409
        )
    targets = _engagement_targets(engagement.engagement_id)
    allowed = [item for item in targets if item.is_allowed]
    if not allowed:
        return error_response(
            "engagement_has_no_targets", "Engagement has no allowed targets.", 409
        )
    snapshot = {
        "profile_code": PROFILE,
        "authorization_reference": engagement.authorization_reference,
        "valid_from": engagement.valid_from.isoformat(),
        "valid_until": engagement.valid_until.isoformat(),
        "allowed_targets": [
            {"domain": item.domain, "include_subdomains": item.include_subdomains}
            for item in allowed
        ],
        "excluded_targets": [
            {"domain": item.domain, "include_subdomains": item.include_subdomains}
            for item in targets
            if not item.is_allowed
        ],
        "limits": PROFILE_LIMITS,
    }
    run = ReconRun(
        run_id=uuid4(),
        project_id=project.project_id,
        engagement_id=engagement.engagement_id,
        requested_by=current_user.principal_id,
        profile_code=PROFILE,
        status="pending",
        cancel_requested=False,
        configuration_snapshot=snapshot,
    )
    db.session.add(run)
    db.session.flush()
    for number, operation in enumerate(("subfinder", "dnsx", "httpx"), start=1):
        db.session.add(
            ReconRunStep(
                step_id=uuid4(),
                run_id=run.run_id,
                step_number=number,
                operation_code=operation,
                status="pending",
            )
        )
    db.session.commit()
    return jsonify({"run": _serialize_run(run)}), 201


@bp.get("/projects/<project_id>/runs")
@bp.doc(security=[{"bearerAuth": []}])
@jwt_required()
@bp.arguments(CursorPaginationQuerySchema, location="query", error_status_code=400)
@bp.response(200, ReconRunsEnvelopeSchema)
def list_runs(pagination: dict, project_id: str):
    project = _project(project_id, "data.read")
    if project is None:
        return error_response("not_found", "Project not found.", 404)
    limit = pagination["limit"]
    statement = (
        select(ReconRun)
        .where(ReconRun.project_id == project.project_id)
        .order_by(ReconRun.created_at.desc(), ReconRun.run_id.desc())
        .limit(limit + 1)
    )
    cursor = pagination["cursor"]
    if cursor:
        cursor_row = db.session.get(ReconRun, cursor)
        if cursor_row is None or cursor_row.project_id != project.project_id:
            return error_response("invalid_request", "Invalid cursor.", 400)
        statement = statement.where(
            or_(
                ReconRun.created_at < cursor_row.created_at,
                and_(
                    ReconRun.created_at == cursor_row.created_at,
                    ReconRun.run_id < cursor_row.run_id,
                ),
            )
        )
    runs = db.session.execute(statement).scalars().all()
    has_more = len(runs) > limit
    runs = runs[:limit]
    return jsonify(
        {
            "runs": [_serialize_run(run) for run in runs],
            "next_cursor": str(runs[-1].run_id) if has_more else None,
        }
    )


def _authorized_run(run_id: str, permission: str):
    parsed = _uuid_or_none(run_id)
    run = db.session.get(ReconRun, parsed) if parsed else None
    project = db.session.get(Project, run.project_id) if run else None
    if project is None or not principal_has_scope_permission(
        current_user.principal_id, project.scope_id, permission
    ):
        return None
    return run


@bp.get("/runs/<run_id>")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ReconRunEnvelopeSchema)
@jwt_required()
def get_run(run_id: str):
    run = _authorized_run(run_id, "data.read")
    if run is None:
        return error_response("not_found", "Run not found.", 404)
    return jsonify({"run": _serialize_run(run)})


@bp.post("/runs/<run_id>/cancel")
@bp.doc(security=[{"bearerAuth": []}])
@bp.response(200, ReconRunEnvelopeSchema)
@jwt_required()
def cancel_run(run_id: str):
    run = _authorized_run(run_id, "recon.execute")
    if run is None:
        return error_response("not_found", "Run not found.", 404)
    if run.status in {"succeeded", "failed", "cancelled"}:
        return error_response("run_finished", "Run has already finished.", 409)
    run.cancel_requested = True
    if run.status == "pending":
        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)
        for step in db.session.execute(
            select(ReconRunStep).where(ReconRunStep.run_id == run.run_id)
        ).scalars():
            step.status = "cancelled"
            step.finished_at = run.finished_at
    db.session.commit()
    return jsonify({"run": _serialize_run(run)})
