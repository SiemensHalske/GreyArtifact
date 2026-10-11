BEGIN;

INSERT INTO recon.permissions (code, label)
VALUES ('recon.execute', 'Execute controlled recon runs')
ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label;

INSERT INTO recon.role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM recon.roles AS r
JOIN recon.permissions AS p ON p.code = 'recon.execute'
WHERE r.code = 'owner'
ON CONFLICT DO NOTHING;

CREATE TABLE recon.engagements (
    engagement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES recon.projects (project_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    authorization_reference TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    created_by UUID NOT NULL REFERENCES recon.principals (principal_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT engagements_project_name_unique UNIQUE (project_id, name),
    CONSTRAINT engagements_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT engagements_authorization_not_blank
        CHECK (btrim(authorization_reference) <> ''),
    CONSTRAINT engagements_validity_order CHECK (valid_until >= valid_from)
);

CREATE TABLE recon.engagement_targets (
    target_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL
        REFERENCES recon.engagements (engagement_id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    is_allowed BOOLEAN NOT NULL,
    include_subdomains BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT engagement_targets_unique
        UNIQUE (engagement_id, domain, is_allowed),
    CONSTRAINT engagement_targets_domain_not_blank CHECK (btrim(domain) <> '')
);

CREATE TABLE recon.recon_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES recon.projects (project_id),
    engagement_id UUID NOT NULL REFERENCES recon.engagements (engagement_id),
    requested_by UUID NOT NULL REFERENCES recon.principals (principal_id),
    profile_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    configuration_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT recon_runs_profile_fixed CHECK (profile_code = 'domain_basic_v1'),
    CONSTRAINT recon_runs_status_valid CHECK (
        status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')
    ),
    CONSTRAINT recon_runs_snapshot_object
        CHECK (jsonb_typeof(configuration_snapshot) = 'object'),
    CONSTRAINT recon_runs_time_order CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    )
);

CREATE INDEX recon_runs_status_created_idx
    ON recon.recon_runs (status, created_at, run_id);
CREATE INDEX recon_runs_project_created_idx
    ON recon.recon_runs (project_id, created_at DESC, run_id DESC);

CREATE TABLE recon.recon_run_steps (
    step_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL
        REFERENCES recon.recon_runs (run_id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    operation_code TEXT NOT NULL,
    tool_version TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    artifact_id UUID REFERENCES recon.artifacts (artifact_id),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT recon_run_steps_run_number_unique UNIQUE (run_id, step_number),
    CONSTRAINT recon_run_steps_number_positive CHECK (step_number > 0),
    CONSTRAINT recon_run_steps_operation_allowed CHECK (
        operation_code IN ('subfinder', 'dnsx', 'httpx')
    ),
    CONSTRAINT recon_run_steps_status_valid CHECK (
        status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', 'skipped')
    ),
    CONSTRAINT recon_run_steps_time_order CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    )
);

ALTER TABLE recon.imports
    ADD COLUMN uploaded_by UUID REFERENCES recon.principals (principal_id),
    ADD COLUMN recon_run_step_id UUID
        REFERENCES recon.recon_run_steps (step_id);

CREATE INDEX imports_recon_run_step_id_idx
    ON recon.imports (recon_run_step_id);

INSERT INTO recon.property_types (code, label, value_kind)
VALUES
    ('http_status', 'HTTP status code', 'number'),
    ('title', 'Page title', 'text'),
    ('server', 'Server header', 'text'),
    ('content_type', 'Content type', 'text'),
    ('tls_subject_cn', 'TLS subject common name', 'text'),
    ('tls_issuer_cn', 'TLS issuer common name', 'text'),
    ('tls_not_before', 'TLS valid from', 'text'),
    ('tls_not_after', 'TLS valid until', 'text')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    value_kind = EXCLUDED.value_kind;

INSERT INTO recon.tools (name, vendor)
VALUES
    ('subfinder', 'ProjectDiscovery'),
    ('dnsx', 'ProjectDiscovery'),
    ('httpx', 'ProjectDiscovery')
ON CONFLICT (name) DO UPDATE SET vendor = EXCLUDED.vendor;

COMMENT ON TABLE recon.engagements IS
    'Authorization boundary and validity period captured before any recon run.';
COMMENT ON COLUMN recon.recon_runs.configuration_snapshot IS
    'Immutable allow/exclude targets, authorization reference, validity and fixed limits used for this run.';
COMMENT ON TABLE recon.recon_run_steps IS
    'Fixed domain_basic_v1 steps; operation_code is never interpreted as a free command.';

COMMIT;
