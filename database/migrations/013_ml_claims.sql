BEGIN;

CREATE TABLE recon.ml_claims (
    claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES recon.import_batches (batch_id),
    import_id UUID NOT NULL REFERENCES recon.imports (import_id),
    asset_id UUID NOT NULL REFERENCES recon.assets (asset_id),
    claim_key TEXT NOT NULL,
    claim_version TEXT NOT NULL,
    state TEXT NOT NULL,
    as_of TIMESTAMPTZ,
    engine_version TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    candidates_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ml_claims_claim_key_not_blank CHECK (btrim(claim_key) <> ''),
    CONSTRAINT ml_claims_claim_version_not_blank CHECK (btrim(claim_version) <> ''),
    CONSTRAINT ml_claims_engine_version_not_blank CHECK (btrim(engine_version) <> ''),
    CONSTRAINT ml_claims_state_valid CHECK (
        state IN (
            'supported', 'contradicted', 'unknown', 'insufficient_evidence', 'abstain'
        )
    ),
    CONSTRAINT ml_claims_evidence_array CHECK (jsonb_typeof(evidence_json) = 'array'),
    CONSTRAINT ml_claims_candidates_array CHECK (jsonb_typeof(candidates_json) = 'array'),
    CONSTRAINT ml_claims_import_asset_claim_unique UNIQUE (import_id, asset_id, claim_key)
);

CREATE INDEX ml_claims_batch_asset_idx ON recon.ml_claims (batch_id, asset_id);

COMMENT ON TABLE recon.ml_claims IS
    'Stage-8 claim states exported by recon_ml, for display only. Acquisition candidates and recommendations are never executed from GreyArtifact; execution stays with engagements and the controlled runner.';

COMMIT;
