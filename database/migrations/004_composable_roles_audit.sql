BEGIN;

INSERT INTO recon.roles (code, label)
VALUES
    ('researcher', 'Researcher'),
    ('pipeline_operator', 'Pipeline operator')
ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label;

DELETE FROM recon.role_permissions AS rp
USING recon.roles AS r
WHERE rp.role_id = r.role_id
  AND r.code IN (
      'viewer',
      'researcher',
      'analyst',
      'owner',
      'pipeline_operator'
  );

INSERT INTO recon.role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM recon.roles AS r
CROSS JOIN recon.permissions AS p
WHERE (r.code = 'viewer'
       AND p.code IN ('scope.read', 'data.read'))
   OR (r.code = 'researcher'
       AND p.code IN (
           'scope.read',
           'data.read',
           'data.import',
           'data.delete'
       ))
   OR (r.code = 'analyst'
       AND p.code IN (
           'scope.read',
           'project.manage',
           'data.read',
           'data.import',
           'data.delete'
       ))
   OR (r.code = 'owner'
       AND p.code IN (
           'scope.read',
           'scope.manage',
           'membership.manage',
           'project.manage',
           'data.read',
           'data.import',
           'data.delete',
           'pipeline.manage'
       ))
   OR (r.code = 'pipeline_operator'
       AND p.code = 'pipeline.execute')
ON CONFLICT DO NOTHING;

CREATE TABLE recon.role_assignment_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_id UUID NOT NULL
        REFERENCES recon.scopes (scope_id) ON DELETE RESTRICT,
    principal_id UUID NOT NULL
        REFERENCES recon.principals (principal_id) ON DELETE RESTRICT,
    changed_by UUID
        REFERENCES recon.principals (principal_id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    roles_before JSONB NOT NULL,
    roles_after JSONB NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT role_assignment_audit_event_type_valid CHECK (
        event_type IN (
            'migration_baseline',
            'bootstrap',
            'member_created',
            'registration_approved',
            'roles_updated'
        )
    ),
    CONSTRAINT role_assignment_audit_roles_before_array CHECK (
        jsonb_typeof(roles_before) = 'array'
    ),
    CONSTRAINT role_assignment_audit_roles_after_array CHECK (
        jsonb_typeof(roles_after) = 'array'
    )
);

CREATE INDEX role_assignment_audit_scope_changed_idx
    ON recon.role_assignment_audit (scope_id, changed_at DESC, audit_id DESC);

INSERT INTO recon.role_assignment_audit
    (scope_id, principal_id, changed_by, event_type, roles_before, roles_after)
SELECT sm.scope_id,
       sm.principal_id,
       NULL,
       'migration_baseline',
       '[]'::jsonb,
       jsonb_agg(r.code ORDER BY
           CASE r.code
               WHEN 'viewer' THEN 1
               WHEN 'researcher' THEN 2
               WHEN 'analyst' THEN 3
               WHEN 'owner' THEN 4
               WHEN 'pipeline_operator' THEN 5
               ELSE 99
           END,
           r.code
       )
FROM recon.scope_memberships AS sm
JOIN recon.roles AS r ON r.role_id = sm.role_id
GROUP BY sm.scope_id, sm.principal_id;

COMMENT ON TABLE recon.role_assignment_audit IS
    'Append-only history of atomic scope-role assignments. The application role must not receive UPDATE or DELETE privileges.';

COMMIT;
