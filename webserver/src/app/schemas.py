from marshmallow import Schema, ValidationError, fields, validate, validates_schema


def nonblank(value: str) -> None:
    if not value.strip() or "\x00" in value:
        raise ValidationError("Value must not be blank.")


class ErrorDetailSchema(Schema):
    code = fields.String(required=True)
    message = fields.String(required=True)


class ErrorSchema(Schema):
    error = fields.Nested(ErrorDetailSchema, required=True)


class RegistrationInputSchema(Schema):
    username = fields.String(
        required=True, validate=[validate.Length(min=1, max=255), nonblank]
    )
    password = fields.String(
        required=True,
        load_only=True,
        validate=[validate.Length(min=12, max=4096), nonblank],
    )
    display_name = fields.String(
        allow_none=True,
        validate=[validate.Length(min=1, max=255), nonblank],
    )
    scope_name = fields.String(
        required=True, validate=[validate.Length(min=1, max=255), nonblank]
    )


class RegistrationAcceptedSchema(Schema):
    message = fields.String(required=True)


class LoginInputSchema(Schema):
    username = fields.String(
        required=True, validate=[validate.Length(min=1, max=255), nonblank]
    )
    password = fields.String(
        required=True, load_only=True, validate=validate.Length(min=1, max=4096)
    )


class TokenSchema(Schema):
    access_token = fields.String(required=True)
    token_type = fields.Constant("Bearer")


class PrincipalSchema(Schema):
    principal_id = fields.UUID(required=True)
    username = fields.String(required=True)
    display_name = fields.String(allow_none=True)


class PrincipalEnvelopeSchema(Schema):
    principal = fields.Nested(PrincipalSchema, required=True)


class ScopeSchema(Schema):
    scope_id = fields.UUID(required=True)
    name = fields.String(required=True)
    description = fields.String(allow_none=True)
    created_at = fields.DateTime(required=True)


class ScopesEnvelopeSchema(Schema):
    scopes = fields.List(fields.Nested(ScopeSchema), required=True)


class RoleSelectionSchema(Schema):
    role = fields.String(
        required=True,
        validate=validate.OneOf(["viewer", "researcher", "analyst", "owner"]),
    )
    additional_roles = fields.List(
        fields.String(validate=validate.OneOf(["pipeline_operator"])),
        load_default=list,
        validate=validate.Length(max=1),
    )


class MemberCreateSchema(RoleSelectionSchema):
    username = fields.String(
        required=True, validate=[validate.Length(min=1, max=255), nonblank]
    )
    password = fields.String(
        required=True, load_only=True, validate=validate.Length(min=12, max=4096)
    )
    display_name = fields.String(
        allow_none=True,
        validate=[validate.Length(min=1, max=255), nonblank],
    )


class RoleUpdateSchema(RoleSelectionSchema):
    additional_roles = fields.List(
        fields.String(validate=validate.OneOf(["pipeline_operator"])),
        required=True,
        validate=validate.Length(max=1),
    )


class MemberSchema(Schema):
    principal_id = fields.UUID(required=True)
    username = fields.String(required=True)
    display_name = fields.String(allow_none=True)
    is_active = fields.Boolean(required=True)
    role = fields.String(required=True)
    additional_roles = fields.List(fields.String(), required=True)


class MemberEnvelopeSchema(Schema):
    member = fields.Nested(MemberSchema, required=True)


class MembersEnvelopeSchema(Schema):
    members = fields.List(fields.Nested(MemberSchema), required=True)


class RegistrationReviewSchema(Schema):
    principal_id = fields.UUID(required=True)
    username = fields.String(required=True)
    display_name = fields.String(allow_none=True)
    requested_at = fields.DateTime(required=True)


class RegistrationsEnvelopeSchema(Schema):
    registrations = fields.List(fields.Nested(RegistrationReviewSchema), required=True)


class RoleAuditEventSchema(Schema):
    audit_id = fields.UUID(required=True)
    event_type = fields.String(required=True)
    principal = fields.Nested(PrincipalSchema, required=True)
    changed_by = fields.Nested(PrincipalSchema, allow_none=True)
    roles_before = fields.List(fields.String(), required=True)
    roles_after = fields.List(fields.String(), required=True)
    changed_at = fields.DateTime(required=True)


class PaginationSchema(Schema):
    page = fields.Integer(required=True)
    per_page = fields.Integer(required=True)
    total = fields.Integer(required=True)
    pages = fields.Integer(required=True)


class PagePaginationQuerySchema(Schema):
    page = fields.Integer(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Integer(
        load_default=50, validate=validate.Range(min=1, max=100)
    )


class CursorPaginationQuerySchema(Schema):
    limit = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    cursor = fields.UUID(load_default=None, allow_none=True)


class AssetListQuerySchema(CursorPaginationQuerySchema):
    q = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(max=255)
    )
    type = fields.String(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(["domain", "ipv4", "ipv6", "url", "service_endpoint"]),
    )


class RoleAuditEnvelopeSchema(Schema):
    events = fields.List(fields.Nested(RoleAuditEventSchema), required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class StatusSchema(Schema):
    status = fields.String(required=True)


class ProjectCreateSchema(Schema):
    slug = fields.String(
        required=True,
        validate=validate.Regexp(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
    )
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, validate=validate.Length(max=4000))


class ProjectUpdateSchema(Schema):
    slug = fields.String(
        validate=validate.Regexp(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
    )
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, validate=validate.Length(max=4000))

    @validates_schema
    def require_change(self, data, **_kwargs):
        if not data:
            raise ValidationError("At least one project field is required.")


class ProjectSchema(Schema):
    project_id = fields.UUID(required=True)
    scope_id = fields.UUID(required=True)
    slug = fields.String(required=True)
    name = fields.String(required=True)
    description = fields.String(allow_none=True)
    created_at = fields.DateTime(required=True)


class ProjectEnvelopeSchema(Schema):
    project = fields.Nested(ProjectSchema, required=True)


class ProjectsEnvelopeSchema(Schema):
    projects = fields.List(fields.Nested(ProjectSchema), required=True)


class ImportSchema(Schema):
    import_id = fields.UUID(required=True)
    project_id = fields.UUID(required=True)
    artifact_id = fields.UUID(required=True)
    sha256 = fields.String(required=True)
    byte_size = fields.Integer(required=True)
    original_filename = fields.String(required=True)
    media_type = fields.String(allow_none=True)
    parser_name = fields.String(allow_none=True)
    parser_version = fields.String(allow_none=True)
    tool_version = fields.String(allow_none=True)
    status = fields.String(required=True)
    error_message = fields.String(allow_none=True)
    imported_at = fields.DateTime(required=True)


class ImportEnvelopeSchema(Schema):
    import_record = fields.Nested(ImportSchema, required=True, data_key="import")


class ImportsEnvelopeSchema(Schema):
    imports = fields.List(fields.Nested(ImportSchema), required=True)
    next_cursor = fields.UUID(allow_none=True)


class AssetSchema(Schema):
    asset_id = fields.UUID(required=True)
    type = fields.String(required=True)
    canonical_value = fields.String(required=True)
    display_value = fields.String(required=True)
    created_at = fields.DateTime(required=True)


class AssetsEnvelopeSchema(Schema):
    assets = fields.List(fields.Nested(AssetSchema), required=True)
    next_cursor = fields.UUID(allow_none=True)


class EvidenceSchema(Schema):
    kind = fields.String(required=True)
    observation_id = fields.UUID(required=True)
    code = fields.String(required=True)
    value = fields.Raw(required=True)
    evidence_locator = fields.String(allow_none=True)
    import_id = fields.UUID(required=True)
    artifact_id = fields.UUID(required=True)
    artifact_sha256 = fields.String(required=True)
    parser_name = fields.String(allow_none=True)
    parser_version = fields.String(allow_none=True)
    recon_run_id = fields.UUID(allow_none=True)
    recon_run_step_id = fields.UUID(allow_none=True)
    recon_operation = fields.String(allow_none=True)


class AssetDetailEnvelopeSchema(Schema):
    asset = fields.Nested(AssetSchema, required=True)
    observations = fields.List(fields.Nested(EvidenceSchema), required=True)


class EngagementTargetInputSchema(Schema):
    domain = fields.String(required=True, validate=validate.Length(min=3, max=253))
    include_subdomains = fields.Boolean(load_default=True)


class EngagementWriteSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    authorization_reference = fields.Url(
        required=True, schemes={"http", "https"}, validate=validate.Length(max=2000)
    )
    valid_from = fields.Date(required=True)
    valid_until = fields.Date(required=True)
    allowed_targets = fields.List(
        fields.Nested(EngagementTargetInputSchema), required=True, validate=validate.Length(min=1, max=100)
    )
    excluded_targets = fields.List(
        fields.Nested(EngagementTargetInputSchema), load_default=list, validate=validate.Length(max=100)
    )

    @validates_schema
    def validate_dates(self, data, **_kwargs):
        if data["valid_until"] < data["valid_from"]:
            raise ValidationError("valid_until must not precede valid_from.")


class EngagementTargetSchema(Schema):
    target_id = fields.UUID(required=True)
    domain = fields.String(required=True)
    include_subdomains = fields.Boolean(required=True)


class EngagementSchema(Schema):
    engagement_id = fields.UUID(required=True)
    project_id = fields.UUID(required=True)
    name = fields.String(required=True)
    authorization_reference = fields.String(required=True)
    valid_from = fields.Date(required=True)
    valid_until = fields.Date(required=True)
    created_by = fields.UUID(required=True)
    created_at = fields.DateTime(required=True)
    allowed_targets = fields.List(fields.Nested(EngagementTargetSchema), required=True)
    excluded_targets = fields.List(fields.Nested(EngagementTargetSchema), required=True)


class EngagementEnvelopeSchema(Schema):
    engagement = fields.Nested(EngagementSchema, required=True)


class EngagementsEnvelopeSchema(Schema):
    engagements = fields.List(fields.Nested(EngagementSchema), required=True)


class ReconRunSchema(Schema):
    run_id = fields.UUID(required=True)
    project_id = fields.UUID(required=True)
    engagement_id = fields.UUID(required=True)
    requested_by = fields.UUID(required=True)
    profile_code = fields.String(required=True)
    status = fields.String(required=True)
    cancel_requested = fields.Boolean(required=True)
    configuration_snapshot = fields.Dict(required=True)
    created_at = fields.DateTime(required=True)
    started_at = fields.DateTime(allow_none=True)
    finished_at = fields.DateTime(allow_none=True)
    error_message = fields.String(allow_none=True)
    steps = fields.List(fields.Dict(), required=True)


class ReconRunEnvelopeSchema(Schema):
    run = fields.Nested(ReconRunSchema, required=True)


class ReconRunsEnvelopeSchema(Schema):
    runs = fields.List(fields.Nested(ReconRunSchema), required=True)
    next_cursor = fields.UUID(allow_none=True)
