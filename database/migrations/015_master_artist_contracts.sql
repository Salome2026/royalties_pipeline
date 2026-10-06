-- Artist-level master terms are reference data for new ISRC drafts only.
BEGIN;

CREATE TABLE IF NOT EXISTS master_artist_contracts (
    artist_key TEXT PRIMARY KEY,
    artist_name TEXT NOT NULL,
    indyana_percent REAL NOT NULL CHECK (indyana_percent >= 0 AND indyana_percent <= 100),
    has_contract INTEGER NOT NULL,
    effective_from TEXT,
    is_project INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS master_artist_contract_history (
    artist_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (artist_key, version)
);

INSERT INTO schema_migrations(version, notes)
VALUES ('015_master_artist_contracts', 'Adds versioned artist-level master terms for new ISRC suggestions only.')
ON CONFLICT (version) DO NOTHING;

COMMIT;
