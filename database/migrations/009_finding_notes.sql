BEGIN;

CREATE TABLE recon.finding_notes (
    note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL
        REFERENCES recon.findings (finding_id) ON DELETE RESTRICT,
    author_id UUID NOT NULL
        REFERENCES recon.principals (principal_id) ON DELETE RESTRICT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT finding_notes_body_not_blank CHECK (btrim(body) <> ''),
    CONSTRAINT finding_notes_body_length CHECK (char_length(body) <= 4000)
);

CREATE INDEX finding_notes_finding_created_idx
    ON recon.finding_notes (finding_id, created_at, note_id);

COMMENT ON TABLE recon.finding_notes IS
    'Append-only analyst notes on findings. The application role must not receive UPDATE or DELETE privileges.';

COMMIT;
