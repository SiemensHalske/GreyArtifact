BEGIN;

CREATE TABLE recon.import_batches (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES recon.projects (project_id),
    source TEXT NOT NULL,
    manifest_version TEXT NOT NULL,
    external_run_ref TEXT NOT NULL,
    engagement_reference TEXT,
    ml_model TEXT NOT NULL,
    ml_model_version TEXT NOT NULL,
    ml_model_status TEXT NOT NULL,
    ml_inference_run_ref TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    created_by UUID REFERENCES recon.principals (principal_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT import_batches_source_not_blank CHECK (btrim(source) <> ''),
    CONSTRAINT import_batches_external_run_ref_not_blank
        CHECK (btrim(external_run_ref) <> ''),
    CONSTRAINT import_batches_ml_model_not_blank CHECK (btrim(ml_model) <> ''),
    CONSTRAINT import_batches_ml_model_version_not_blank
        CHECK (btrim(ml_model_version) <> ''),
    CONSTRAINT import_batches_ml_inference_run_ref_not_blank
        CHECK (btrim(ml_inference_run_ref) <> ''),
    CONSTRAINT import_batches_ml_model_status_valid CHECK (
        ml_model_status IN ('candidate', 'validated', 'approved', 'retired')
    ),
    CONSTRAINT import_batches_manifest_object
        CHECK (jsonb_typeof(manifest_json) = 'object'),
    CONSTRAINT import_batches_run_unique
        UNIQUE (project_id, source, external_run_ref)
);

CREATE INDEX import_batches_project_created_idx
    ON recon.import_batches (project_id, created_at DESC, batch_id DESC);

ALTER TABLE recon.imports
    ADD COLUMN batch_id UUID REFERENCES recon.import_batches (batch_id);

CREATE INDEX imports_batch_id_idx ON recon.imports (batch_id);

CREATE TABLE recon.ml_predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES recon.import_batches (batch_id),
    import_id UUID NOT NULL REFERENCES recon.imports (import_id),
    asset_id UUID NOT NULL REFERENCES recon.assets (asset_id),
    model_version TEXT NOT NULL,
    model_status TEXT NOT NULL,
    percentile DOUBLE PRECISION NOT NULL,
    rank INTEGER NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_locator TEXT NOT NULL,
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ml_predictions_model_version_not_blank
        CHECK (btrim(model_version) <> ''),
    CONSTRAINT ml_predictions_model_status_valid CHECK (
        model_status IN ('candidate', 'validated', 'approved', 'retired')
    ),
    CONSTRAINT ml_predictions_percentile_range
        CHECK (percentile >= 0 AND percentile <= 100),
    CONSTRAINT ml_predictions_rank_positive CHECK (rank > 0),
    CONSTRAINT ml_predictions_evidence_locator_not_blank
        CHECK (btrim(evidence_locator) <> ''),
    CONSTRAINT ml_predictions_explanation_object
        CHECK (jsonb_typeof(explanation_json) = 'object'),
    CONSTRAINT ml_predictions_import_asset_unique UNIQUE (import_id, asset_id)
);

CREATE INDEX ml_predictions_batch_rank_idx
    ON recon.ml_predictions (batch_id, rank);
CREATE INDEX ml_predictions_asset_idx
    ON recon.ml_predictions (asset_id);

COMMENT ON TABLE recon.import_batches IS
    'A reconnaissance run imported as one package; always carries a mandatory recon_ml result.';
COMMENT ON TABLE recon.ml_predictions IS
    'Per-asset recon_ml triage output. A prediction is a ranking hint, never an automatic finding.';
COMMENT ON COLUMN recon.ml_predictions.percentile IS
    'Triage rank percentile in [0, 100]; higher means reviewed earlier. Not a compromise probability.';

COMMIT;
