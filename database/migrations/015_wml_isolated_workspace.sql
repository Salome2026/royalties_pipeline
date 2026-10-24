BEGIN;
CREATE TABLE IF NOT EXISTS royalty_workspaces (
    scope_key TEXT PRIMARY KEY CHECK (scope_key = 'wml'),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{"frequency":"semiannual","delivery_lag_months":3}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT NOT NULL DEFAULT 'migration',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS royalty_workspace_records (
    scope_key TEXT NOT NULL REFERENCES royalty_workspaces(scope_key),
    record_type TEXT NOT NULL CHECK (record_type IN ('master_split','catalog_status','reference')),
    record_key TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope_key,record_type,record_key)
);
CREATE TABLE IF NOT EXISTS royalty_workspace_audit (
    id BIGSERIAL PRIMARY KEY,
    scope_key TEXT NOT NULL REFERENCES royalty_workspaces(scope_key),
    record_type TEXT NOT NULL,
    record_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    before_json JSONB,
    after_json JSONB NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO royalty_workspaces(scope_key,enabled) VALUES ('wml',FALSE) ON CONFLICT DO NOTHING;
INSERT INTO schema_migrations(version,notes) VALUES ('015_wml_isolated_workspace',
    'WML 91230: disabled by default, separate operational records and immutable audit history.')
ON CONFLICT DO NOTHING;
COMMIT;
