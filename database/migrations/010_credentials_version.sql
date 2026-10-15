BEGIN;

ALTER TABLE recon.principals
    ADD COLUMN credentials_version INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT principals_credentials_version_not_negative
        CHECK (credentials_version >= 0);

COMMENT ON COLUMN recon.principals.credentials_version IS
    'Incremented on every password change; access tokens carrying an older value are rejected.';

COMMIT;
