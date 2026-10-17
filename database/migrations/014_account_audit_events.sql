BEGIN;

-- Account administration (remove from a scope, deactivate/reactivate, password
-- reset, display name) is recorded in the same append-only audit as role
-- changes. Account-wide events add one row per scope the account belongs to.
ALTER TABLE recon.role_assignment_audit
    DROP CONSTRAINT role_assignment_audit_event_type_valid,
    ADD CONSTRAINT role_assignment_audit_event_type_valid CHECK (
        event_type IN (
            'migration_baseline',
            'bootstrap',
            'member_created',
            'registration_approved',
            'roles_updated',
            'member_removed',
            'account_deactivated',
            'account_reactivated',
            'password_reset',
            'display_name_updated'
        )
    );

COMMIT;
