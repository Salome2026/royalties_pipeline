BEGIN;

CREATE TABLE IF NOT EXISTS master_distribution_contract_counter (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_number BIGINT NOT NULL
);
INSERT INTO master_distribution_contract_counter VALUES (1, 10009) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS master_distribution_contracts (
    number BIGINT PRIMARY KEY,
    label_key TEXT NOT NULL,
    sublabel_key TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (label_key, sublabel_key)
);
CREATE TABLE IF NOT EXISTS master_distribution_contract_history (
    number BIGINT NOT NULL REFERENCES master_distribution_contracts(number),
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (number, version)
);

INSERT INTO schema_migrations(version, notes)
VALUES ('018_distribution_contracts', 'Versioned reusable distribution initial allocations with unique automatic numbering.')
ON CONFLICT (version) DO NOTHING;
COMMIT;
