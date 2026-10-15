BEGIN;

CREATE TABLE recon.findings (
    finding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES recon.projects (project_id),
    import_id UUID NOT NULL REFERENCES recon.imports (import_id),
    asset_id UUID REFERENCES recon.assets (asset_id),
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    matcher_name TEXT NOT NULL DEFAULT '',
    matched_at TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_locator TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT findings_import_match_unique
        UNIQUE (import_id, external_id, matcher_name, matched_at),
    CONSTRAINT findings_source_not_blank CHECK (btrim(source) <> ''),
    CONSTRAINT findings_external_id_not_blank CHECK (btrim(external_id) <> ''),
    CONSTRAINT findings_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT findings_matched_at_not_blank CHECK (btrim(matched_at) <> ''),
    CONSTRAINT findings_evidence_locator_not_blank
        CHECK (btrim(evidence_locator) <> ''),
    CONSTRAINT findings_severity_valid CHECK (
        severity IN ('info', 'low', 'medium', 'high', 'critical', 'unknown')
    ),
    CONSTRAINT findings_status_valid CHECK (
        status IN ('new', 'confirmed', 'false_positive', 'remediated', 'accepted')
    ),
    CONSTRAINT findings_metadata_object
        CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE INDEX findings_project_created_idx
    ON recon.findings (project_id, created_at DESC, finding_id DESC);
CREATE INDEX findings_project_severity_idx
    ON recon.findings (project_id, severity, status);

INSERT INTO recon.tools (name, vendor)
VALUES ('nuclei', 'ProjectDiscovery')
ON CONFLICT (name) DO UPDATE SET vendor = EXCLUDED.vendor;

COMMENT ON TABLE recon.findings IS
    'Normalized security findings linked to their immutable import artifact.';
COMMENT ON COLUMN recon.findings.metadata_json IS
    'Sanitized metadata only; raw matcher output remains in the protected artifact.';

COMMIT;
