BEGIN;

CREATE TABLE recon.registration_requests (
    principal_id UUID PRIMARY KEY
        REFERENCES recon.principals (principal_id) ON DELETE CASCADE,
    scope_id UUID NOT NULL
        REFERENCES recon.scopes (scope_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES recon.principals (principal_id),
    CONSTRAINT registration_requests_status_valid
        CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT registration_requests_review_consistency CHECK (
        (status = 'pending' AND reviewed_at IS NULL AND reviewed_by IS NULL)
        OR
        (status IN ('approved', 'rejected')
         AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)
    )
);

CREATE INDEX registration_requests_scope_status_requested_idx
    ON recon.registration_requests (scope_id, status, requested_at);

COMMENT ON TABLE recon.registration_requests IS
    'Self-registration requests that require approval by a scope member with membership.manage.';

COMMIT;
