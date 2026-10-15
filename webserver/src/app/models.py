from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


SCHEMA = "recon"


class Scope(db.Model):
    __tablename__ = "scopes"
    __table_args__ = (
        UniqueConstraint("name", name="scopes_name_key"),
        CheckConstraint("btrim(name) <> ''", name="scopes_name_not_blank"),
        {"schema": SCHEMA},
    )

    scope_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(db.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class Project(db.Model):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("scope_id", "slug", name="projects_scope_slug_unique"),
        CheckConstraint("btrim(slug) <> ''", name="projects_slug_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="projects_name_not_blank"),
        {"schema": SCHEMA},
    )

    project_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(db.Text, nullable=False)
    name: Mapped[str] = mapped_column(db.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    scope_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.scopes.scope_id"),
        nullable=False,
    )


class Principal(db.Model):
    __tablename__ = "principals"
    __table_args__ = (
        UniqueConstraint("username", name="principals_username_key"),
        CheckConstraint(
            "btrim(username) <> ''",
            name="principals_username_not_blank",
        ),
        CheckConstraint(
            "btrim(password_hash) <> ''",
            name="principals_password_hash_not_blank",
        ),
        {"schema": SCHEMA},
    )

    principal_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    username: Mapped[str] = mapped_column(db.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(db.Text)
    is_active: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, server_default=db.true()
    )
    credentials_version: Mapped[int] = mapped_column(
        db.Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class Role(db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("code", name="roles_code_key"),
        CheckConstraint("btrim(code) <> ''", name="roles_code_not_blank"),
        CheckConstraint("btrim(label) <> ''", name="roles_label_not_blank"),
        {"schema": SCHEMA},
    )

    role_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        Identity(),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(db.Text, nullable=False)
    label: Mapped[str] = mapped_column(db.Text, nullable=False)


class Permission(db.Model):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code", name="permissions_code_key"),
        CheckConstraint("btrim(code) <> ''", name="permissions_code_not_blank"),
        CheckConstraint("btrim(label) <> ''", name="permissions_label_not_blank"),
        {"schema": SCHEMA},
    )

    permission_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        Identity(),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(db.Text, nullable=False)
    label: Mapped[str] = mapped_column(db.Text, nullable=False)


class RolePermission(db.Model):
    __tablename__ = "role_permissions"
    __table_args__ = {"schema": SCHEMA}

    role_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        ForeignKey(f"{SCHEMA}.roles.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        ForeignKey(f"{SCHEMA}.permissions.permission_id", ondelete="CASCADE"),
        primary_key=True,
    )


class ScopeMembership(db.Model):
    __tablename__ = "scope_memberships"
    __table_args__ = {"schema": SCHEMA}

    scope_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.scopes.scope_id", ondelete="CASCADE"),
        primary_key=True,
    )
    principal_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        ForeignKey(f"{SCHEMA}.roles.role_id"),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    granted_by: Mapped[UUID | None] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id"),
    )


class RoleAssignmentAudit(db.Model):
    __tablename__ = "role_assignment_audit"
    __table_args__ = (
        Index(
            "role_assignment_audit_scope_changed_idx",
            "scope_id",
            text("changed_at DESC"),
            text("audit_id DESC"),
        ),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    scope_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.scopes.scope_id", ondelete="RESTRICT"),
        nullable=False,
    )
    principal_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_by: Mapped[UUID | None] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="RESTRICT"),
    )
    event_type: Mapped[str] = mapped_column(db.Text, nullable=False)
    roles_before: Mapped[list[str]] = mapped_column(db.JSON, nullable=False)
    roles_after: Mapped[list[str]] = mapped_column(db.JSON, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class RegistrationRequest(db.Model):
    __tablename__ = "registration_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="registration_requests_status_valid",
        ),
        CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL "
            "AND reviewed_by IS NULL) OR "
            "(status IN ('approved', 'rejected') "
            "AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="registration_requests_review_consistency",
        ),
        Index(
            "registration_requests_scope_status_requested_idx",
            "scope_id",
            "status",
            "requested_at",
        ),
        {"schema": SCHEMA},
    )

    principal_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.scopes.scope_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        db.Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    requested_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        db.DateTime(timezone=True)
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id"),
    )


class Tool(db.Model):
    __tablename__ = "tools"
    __table_args__ = {"schema": SCHEMA}

    tool_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(db.Text, nullable=False, unique=True)
    vendor: Mapped[str | None] = mapped_column(db.Text)


class Artifact(db.Model):
    __tablename__ = "artifacts"
    __table_args__ = {"schema": SCHEMA}

    artifact_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    sha256: Mapped[str] = mapped_column(db.String(64), nullable=False, unique=True)
    storage_key: Mapped[str] = mapped_column(db.Text, nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class ImportRecord(db.Model):
    __tablename__ = "imports"
    __table_args__ = (
        Index("imports_project_imported_at_idx", "project_id", text("imported_at DESC")),
        {"schema": SCHEMA},
    )

    import_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.projects.project_id"), nullable=False
    )
    artifact_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.artifacts.artifact_id"), nullable=False
    )
    tool_id: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.tools.tool_id")
    )
    tool_version: Mapped[str | None] = mapped_column(db.Text)
    original_filename: Mapped[str] = mapped_column(db.Text, nullable=False)
    media_type: Mapped[str | None] = mapped_column(db.Text)
    parser_name: Mapped[str | None] = mapped_column(db.Text)
    parser_version: Mapped[str | None] = mapped_column(db.Text)
    imported_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    status: Mapped[str] = mapped_column(
        db.Text, nullable=False, server_default=text("'pending'")
    )
    error_message: Mapped[str | None] = mapped_column(db.Text)
    uploaded_by: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.principals.principal_id")
    )
    recon_run_step_id: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.recon_run_steps.step_id")
    )
    batch_id: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.import_batches.batch_id")
    )


class AssetType(db.Model):
    __tablename__ = "asset_types"
    __table_args__ = {"schema": SCHEMA}

    asset_type_id: Mapped[int] = mapped_column(db.SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(db.Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(db.Text, nullable=False)


class Asset(db.Model):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint(
            "asset_type_id", "canonical_value", name="assets_type_canonical_value_unique"
        ),
        {"schema": SCHEMA},
    )

    asset_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    asset_type_id: Mapped[int] = mapped_column(
        db.SmallInteger, ForeignKey(f"{SCHEMA}.asset_types.asset_type_id"), nullable=False
    )
    canonical_value: Mapped[str] = mapped_column(db.Text, nullable=False)
    display_value: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class ProjectAsset(db.Model):
    __tablename__ = "project_assets"
    __table_args__ = {"schema": SCHEMA}

    project_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.projects.project_id"), primary_key=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class PropertyType(db.Model):
    __tablename__ = "property_types"
    __table_args__ = {"schema": SCHEMA}

    property_type_id: Mapped[int] = mapped_column(db.SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(db.Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(db.Text, nullable=False)
    value_kind: Mapped[str] = mapped_column(db.Text, nullable=False)


class AssetPropertyObservation(db.Model):
    __tablename__ = "asset_property_observations"
    __table_args__ = {"schema": SCHEMA}

    observation_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    import_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.imports.import_id"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), nullable=False
    )
    property_type_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        ForeignKey(f"{SCHEMA}.property_types.property_type_id"),
        nullable=False,
    )
    value_text: Mapped[str] = mapped_column(db.Text, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(db.Numeric(5, 4))
    evidence_locator: Mapped[str | None] = mapped_column(db.Text)


class RelationshipType(db.Model):
    __tablename__ = "relationship_types"
    __table_args__ = {"schema": SCHEMA}

    relationship_type_id: Mapped[int] = mapped_column(db.SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(db.Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(db.Text, nullable=False)


class AssetRelationshipObservation(db.Model):
    __tablename__ = "asset_relationship_observations"
    __table_args__ = {"schema": SCHEMA}

    observation_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    import_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.imports.import_id"), nullable=False
    )
    source_asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), nullable=False
    )
    relationship_type_id: Mapped[int] = mapped_column(
        db.SmallInteger,
        ForeignKey(f"{SCHEMA}.relationship_types.relationship_type_id"),
        nullable=False,
    )
    target_asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), nullable=False
    )
    observed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(db.Numeric(5, 4))
    evidence_locator: Mapped[str | None] = mapped_column(db.Text)


class Finding(db.Model):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "external_id",
            "matcher_name",
            "matched_at",
            name="findings_import_match_unique",
        ),
        Index("findings_project_created_idx", "project_id", text("created_at DESC")),
        Index("findings_project_severity_idx", "project_id", "severity", "status"),
        {"schema": SCHEMA},
    )

    finding_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.projects.project_id"), nullable=False
    )
    import_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.imports.import_id"), nullable=False
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id")
    )
    source: Mapped[str] = mapped_column(db.Text, nullable=False)
    external_id: Mapped[str] = mapped_column(db.Text, nullable=False)
    title: Mapped[str] = mapped_column(db.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text)
    severity: Mapped[str] = mapped_column(db.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        db.Text, nullable=False, server_default=text("'new'")
    )
    matcher_name: Mapped[str] = mapped_column(
        db.Text, nullable=False, server_default=text("''")
    )
    matched_at: Mapped[str] = mapped_column(db.Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        db.JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    is_sensitive: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, server_default=db.false()
    )
    evidence_locator: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class FindingStatusAudit(db.Model):
    __tablename__ = "finding_status_audit"
    __table_args__ = (
        Index(
            "finding_status_audit_finding_changed_idx",
            "finding_id",
            text("changed_at DESC"),
            text("audit_id DESC"),
        ),
        {"schema": SCHEMA},
    )

    audit_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    finding_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.findings.finding_id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_by: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status_before: Mapped[str] = mapped_column(db.Text, nullable=False)
    status_after: Mapped[str] = mapped_column(db.Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class FindingNote(db.Model):
    __tablename__ = "finding_notes"
    __table_args__ = (
        CheckConstraint("btrim(body) <> ''", name="finding_notes_body_not_blank"),
        Index("finding_notes_finding_created_idx", "finding_id", "created_at", "note_id"),
        {"schema": SCHEMA},
    )

    note_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    finding_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.findings.finding_id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class ImportBatch(db.Model):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source",
            "external_run_ref",
            name="import_batches_run_unique",
        ),
        Index(
            "import_batches_project_created_idx",
            "project_id",
            text("created_at DESC"),
            text("batch_id DESC"),
        ),
        {"schema": SCHEMA},
    )

    batch_id: Mapped[UUID] = mapped_column(
        db.Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.projects.project_id"), nullable=False
    )
    source: Mapped[str] = mapped_column(db.Text, nullable=False)
    manifest_version: Mapped[str] = mapped_column(db.Text, nullable=False)
    external_run_ref: Mapped[str] = mapped_column(db.Text, nullable=False)
    engagement_reference: Mapped[str | None] = mapped_column(db.Text)
    ml_model: Mapped[str] = mapped_column(db.Text, nullable=False)
    ml_model_version: Mapped[str] = mapped_column(db.Text, nullable=False)
    ml_model_status: Mapped[str] = mapped_column(db.Text, nullable=False)
    ml_inference_run_ref: Mapped[str] = mapped_column(db.Text, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.principals.principal_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class MlPrediction(db.Model):
    __tablename__ = "ml_predictions"
    __table_args__ = (
        UniqueConstraint(
            "import_id", "asset_id", name="ml_predictions_import_asset_unique"
        ),
        Index("ml_predictions_batch_rank_idx", "batch_id", "rank"),
        Index("ml_predictions_asset_idx", "asset_id"),
        {"schema": SCHEMA},
    )

    prediction_id: Mapped[UUID] = mapped_column(
        db.Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.import_batches.batch_id"), nullable=False
    )
    import_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.imports.import_id"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(db.Text, nullable=False)
    model_status: Mapped[str] = mapped_column(db.Text, nullable=False)
    percentile: Mapped[float] = mapped_column(db.Float, nullable=False)
    rank: Mapped[int] = mapped_column(db.Integer, nullable=False)
    explanation_json: Mapped[dict] = mapped_column(
        db.JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    evidence_locator: Mapped[str] = mapped_column(db.Text, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, server_default=db.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class MlPredictionReview(db.Model):
    __tablename__ = "ml_prediction_reviews"
    __table_args__ = (
        Index(
            "ml_prediction_reviews_prediction_created_idx",
            "prediction_id",
            text("created_at DESC"),
            text("review_id DESC"),
        ),
        Index("ml_prediction_reviews_reviewer_idx", "reviewer_id"),
        {"schema": SCHEMA},
    )

    review_id: Mapped[UUID] = mapped_column(
        db.Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    prediction_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.ml_predictions.prediction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.principals.principal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(db.Text, nullable=False)
    note: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class MlClaim(db.Model):
    __tablename__ = "ml_claims"
    __table_args__ = (
        UniqueConstraint(
            "import_id", "asset_id", "claim_key", name="ml_claims_import_asset_claim_unique"
        ),
        Index("ml_claims_batch_asset_idx", "batch_id", "asset_id"),
        {"schema": SCHEMA},
    )

    claim_id: Mapped[UUID] = mapped_column(
        db.Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.import_batches.batch_id"), nullable=False
    )
    import_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.imports.import_id"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.assets.asset_id"), nullable=False
    )
    claim_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    claim_version: Mapped[str] = mapped_column(db.Text, nullable=False)
    state: Mapped[str] = mapped_column(db.Text, nullable=False)
    as_of: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(db.Text, nullable=False)
    evidence_json: Mapped[list] = mapped_column(
        db.JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    candidates_json: Mapped[list] = mapped_column(
        db.JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class Engagement(db.Model):
    __tablename__ = "engagements"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="engagements_project_name_unique"),
        {"schema": SCHEMA},
    )

    engagement_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.projects.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(db.Text, nullable=False)
    authorization_reference: Mapped[str] = mapped_column(db.Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(db.Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(db.Date, nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.principals.principal_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class EngagementTarget(db.Model):
    __tablename__ = "engagement_targets"
    __table_args__ = (
        UniqueConstraint(
            "engagement_id", "domain", "is_allowed", name="engagement_targets_unique"
        ),
        {"schema": SCHEMA},
    )

    target_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    engagement_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.engagements.engagement_id", ondelete="CASCADE"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(db.Text, nullable=False)
    is_allowed: Mapped[bool] = mapped_column(db.Boolean, nullable=False)
    include_subdomains: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, server_default=db.true()
    )


class ReconRun(db.Model):
    __tablename__ = "recon_runs"
    __table_args__ = (
        Index("recon_runs_status_created_idx", "status", "created_at"),
        {"schema": SCHEMA},
    )

    run_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.projects.project_id"), nullable=False
    )
    engagement_id: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.engagements.engagement_id"), nullable=False
    )
    requested_by: Mapped[UUID] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.principals.principal_id"), nullable=False
    )
    profile_code: Mapped[str] = mapped_column(db.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        db.Text, nullable=False, server_default=text("'pending'")
    )
    cancel_requested: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, server_default=db.false()
    )
    configuration_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(db.Text)


class ReconRunStep(db.Model):
    __tablename__ = "recon_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_number", name="recon_run_steps_run_number_unique"),
        {"schema": SCHEMA},
    )

    step_id: Mapped[UUID] = mapped_column(db.Uuid, primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        db.Uuid,
        ForeignKey(f"{SCHEMA}.recon_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    step_number: Mapped[int] = mapped_column(db.Integer, nullable=False)
    operation_code: Mapped[str] = mapped_column(db.Text, nullable=False)
    tool_version: Mapped[str | None] = mapped_column(db.Text)
    status: Mapped[str] = mapped_column(
        db.Text, nullable=False, server_default=text("'pending'")
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        db.Uuid, ForeignKey(f"{SCHEMA}.artifacts.artifact_id")
    )
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(db.Text)

