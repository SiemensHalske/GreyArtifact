BEGIN;

INSERT INTO recon.permissions (code, label)
VALUES ('sensitive.read', 'Read raw artifacts containing sensitive findings')
ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label;

INSERT INTO recon.role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM recon.roles AS r
JOIN recon.permissions AS p ON p.code = 'sensitive.read'
WHERE r.code = 'owner'
ON CONFLICT DO NOTHING;

CREATE TABLE recon.finding_status_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL
        REFERENCES recon.findings (finding_id) ON DELETE RESTRICT,
    changed_by UUID NOT NULL
        REFERENCES recon.principals (principal_id) ON DELETE RESTRICT,
    status_before TEXT NOT NULL,
    status_after TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT finding_status_audit_status_before_valid CHECK (
        status_before IN ('new', 'confirmed', 'false_positive', 'remediated', 'accepted')
    ),
    CONSTRAINT finding_status_audit_status_after_valid CHECK (
        status_after IN ('new', 'confirmed', 'false_positive', 'remediated', 'accepted')
    ),
    CONSTRAINT finding_status_audit_status_changed
        CHECK (status_before <> status_after)
);

CREATE INDEX finding_status_audit_finding_changed_idx
    ON recon.finding_status_audit (finding_id, changed_at DESC, audit_id DESC);

COMMENT ON TABLE recon.finding_status_audit IS
    'Append-only history of finding triage decisions. The application role must not receive UPDATE or DELETE privileges.';

COMMIT;
