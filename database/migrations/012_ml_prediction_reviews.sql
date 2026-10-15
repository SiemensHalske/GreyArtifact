BEGIN;

CREATE TABLE recon.ml_prediction_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id UUID NOT NULL
        REFERENCES recon.ml_predictions (prediction_id) ON DELETE RESTRICT,
    reviewer_id UUID NOT NULL
        REFERENCES recon.principals (principal_id) ON DELETE RESTRICT,
    decision TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ml_prediction_reviews_decision_valid CHECK (
        decision IN (
            'expected', 'data_artifact', 'review_worthy', 'confirmed_finding'
        )
    ),
    CONSTRAINT ml_prediction_reviews_note_length
        CHECK (note IS NULL OR char_length(note) <= 4000)
);

CREATE INDEX ml_prediction_reviews_prediction_created_idx
    ON recon.ml_prediction_reviews (prediction_id, created_at DESC, review_id DESC);
CREATE INDEX ml_prediction_reviews_reviewer_idx
    ON recon.ml_prediction_reviews (reviewer_id);

COMMENT ON TABLE recon.ml_prediction_reviews IS
    'Append-only analyst triage decisions (Stage-7 classes) exported back to recon_ml. The application role must not receive UPDATE or DELETE privileges.';

COMMIT;
