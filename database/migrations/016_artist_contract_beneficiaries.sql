-- Percentages apply to the artist allocation, independently of project ownership.
BEGIN;
ALTER TABLE master_artist_contracts ADD COLUMN IF NOT EXISTS beneficiaries_json TEXT;
INSERT INTO schema_migrations(version, notes)
VALUES ('016_artist_contract_beneficiaries', 'Versioned named beneficiaries for artist contracts; preserves legacy splits.')
ON CONFLICT (version) DO NOTHING;
COMMIT;
