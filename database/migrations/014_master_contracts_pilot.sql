-- El piloto de contratos guarda borradores y versiones sin alimentar reportes.
BEGIN;

CREATE TABLE IF NOT EXISTS master_contract_splits (
    isrc TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    is_closed INTEGER NOT NULL DEFAULT 0,
    future_reports_selected INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS master_contract_split_history (
    isrc TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    is_closed INTEGER NOT NULL,
    future_reports_selected INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (isrc, version)
);

CREATE INDEX IF NOT EXISTS idx_master_contract_splits_closed
    ON master_contract_splits(is_closed);

INSERT INTO app_modules (module_key, label, active, created_at)
VALUES ('master_contracts', 'Contratos de masters', TRUE, CURRENT_TIMESTAMP)
ON CONFLICT (module_key) DO UPDATE SET
    label = EXCLUDED.label,
    active = EXCLUDED.active;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '014_master_contracts_pilot',
    'Adds isolated master split drafts, review state, future-report intent, and immutable versions.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
