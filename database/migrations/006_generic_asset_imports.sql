BEGIN;

INSERT INTO recon.property_types (code, label, value_kind)
VALUES ('source_value', 'Original imported value', 'text')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    value_kind = EXCLUDED.value_kind;

COMMENT ON COLUMN recon.imports.parser_name IS
    'Versioned import format/parser identifier; it is not required to represent a tool.';

COMMIT;
