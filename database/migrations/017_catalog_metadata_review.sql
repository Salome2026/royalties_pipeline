BEGIN;
-- Reviewed Spotify metadata stays separate from raw statements and financial facts.
CREATE TABLE IF NOT EXISTS catalog_metadata_observations (
 catalog_key TEXT PRIMARY KEY, payload_json JSONB NOT NULL,
 version INTEGER NOT NULL CHECK(version>0), fetched_at TIMESTAMPTZ NOT NULL,
 origin TEXT NOT NULL, updated_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_metadata_reviews (
 catalog_key TEXT PRIMARY KEY, observation_version INTEGER NOT NULL,
 version INTEGER NOT NULL CHECK(version>0), decisions_json JSONB NOT NULL,
 overrides_json JSONB NOT NULL, updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_metadata_review_history (
 id BIGSERIAL PRIMARY KEY, catalog_key TEXT NOT NULL, version INTEGER NOT NULL,
 observation_version INTEGER NOT NULL, payload_json JSONB NOT NULL,
 updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(catalog_key,version)
);
INSERT INTO schema_migrations(version,notes) VALUES ('017_catalog_metadata_review','Spotify observations and explicit metadata reviews; no financial changes') ON CONFLICT(version) DO NOTHING;
COMMIT;
