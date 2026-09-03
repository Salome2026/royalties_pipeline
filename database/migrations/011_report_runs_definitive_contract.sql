-- Definitive persistence contract for asynchronous royalty report jobs.
-- Execution transport is migrated separately; task_name remains only until
-- the Cloud Tasks cutover removes the old transport in the same release.

BEGIN;

LOCK TABLE report_runs IN SHARE ROW EXCLUSIVE MODE;

UPDATE report_runs
SET status = 'queued'
WHERE status = 'created';

ALTER TABLE report_runs
    ADD COLUMN IF NOT EXISTS input_manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS policy_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS policy_version bigint,
    ADD COLUMN IF NOT EXISTS engine_version text,
    ADD COLUMN IF NOT EXISTS execution_name text,
    ADD COLUMN IF NOT EXISTS result_size_bytes bigint,
    ADD COLUMN IF NOT EXISTS result_sha256 text,
    ADD COLUMN IF NOT EXISTS error_log_ref text,
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;

UPDATE report_runs
SET execution_name = task_name
WHERE execution_name IS NULL
  AND task_name IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM report_runs
        WHERE report_key IS NULL
           OR btrim(report_key) = ''
           OR report_key NOT IN (
               'royalty_keyword',
               'royalty_executive',
               'royalty_google_sheet'
           )
    ) THEN
        RAISE EXCEPTION 'report_runs contains an invalid report_key';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM report_runs
        WHERE requested_by IS NULL OR btrim(requested_by) = ''
    ) THEN
        RAISE EXCEPTION 'report_runs contains an invalid requested_by';
    END IF;
END
$$;

ALTER TABLE report_runs
    ALTER COLUMN report_key SET NOT NULL,
    ALTER COLUMN requested_by SET NOT NULL,
    ALTER COLUMN status SET DEFAULT 'queued';

ALTER TABLE report_runs
    DROP CONSTRAINT IF EXISTS report_runs_output_chk,
    DROP CONSTRAINT IF EXISTS report_runs_status_chk,
    DROP CONSTRAINT IF EXISTS report_runs_stage_chk,
    DROP CONSTRAINT IF EXISTS report_runs_report_key_chk,
    DROP CONSTRAINT IF EXISTS report_runs_requested_by_chk,
    DROP CONSTRAINT IF EXISTS report_runs_params_json_chk,
    DROP CONSTRAINT IF EXISTS report_runs_input_manifest_chk,
    DROP CONSTRAINT IF EXISTS report_runs_policy_snapshot_chk,
    DROP CONSTRAINT IF EXISTS report_runs_policy_version_chk,
    DROP CONSTRAINT IF EXISTS report_runs_attempt_count_chk,
    DROP CONSTRAINT IF EXISTS report_runs_result_size_chk,
    DROP CONSTRAINT IF EXISTS report_runs_result_sha256_chk,
    DROP CONSTRAINT IF EXISTS report_runs_request_hash_chk,
    DROP CONSTRAINT IF EXISTS report_runs_running_started_chk,
    DROP CONSTRAINT IF EXISTS report_runs_terminal_finished_chk,
    DROP CONSTRAINT IF EXISTS report_runs_completed_result_chk;

ALTER TABLE report_runs
    ADD CONSTRAINT report_runs_output_chk
        CHECK (output_format IN ('excel', 'executive_pdf', 'google_sheet')),
    ADD CONSTRAINT report_runs_status_chk
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    ADD CONSTRAINT report_runs_stage_chk
        CHECK (progress_stage IN (
            'queued', 'preparing', 'reading_data', 'building', 'uploading',
            'completed', 'failed'
        )),
    ADD CONSTRAINT report_runs_report_key_chk
        CHECK (report_key IN (
            'royalty_keyword', 'royalty_executive', 'royalty_google_sheet'
        )),
    ADD CONSTRAINT report_runs_requested_by_chk
        CHECK (btrim(requested_by) <> ''),
    ADD CONSTRAINT report_runs_params_json_chk
        CHECK (jsonb_typeof(params_json) = 'object'),
    ADD CONSTRAINT report_runs_input_manifest_chk
        CHECK (jsonb_typeof(input_manifest_json) = 'object'),
    ADD CONSTRAINT report_runs_policy_snapshot_chk
        CHECK (jsonb_typeof(policy_snapshot_json) = 'object'),
    ADD CONSTRAINT report_runs_policy_version_chk
        CHECK (policy_version IS NULL OR policy_version > 0),
    ADD CONSTRAINT report_runs_attempt_count_chk
        CHECK (attempt_count >= 0),
    ADD CONSTRAINT report_runs_result_size_chk
        CHECK (result_size_bytes IS NULL OR result_size_bytes >= 0),
    ADD CONSTRAINT report_runs_result_sha256_chk
        CHECK (result_sha256 IS NULL OR result_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT report_runs_request_hash_chk
        CHECK (request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT report_runs_running_started_chk
        CHECK (status <> 'running' OR started_at IS NOT NULL),
    ADD CONSTRAINT report_runs_terminal_finished_chk
        CHECK (status NOT IN ('completed', 'failed') OR finished_at IS NOT NULL),
    ADD CONSTRAINT report_runs_completed_result_chk
        CHECK (
            status <> 'completed'
            OR output_uri IS NOT NULL
            OR result_url IS NOT NULL
        );

DROP INDEX IF EXISTS idx_report_runs_active_hash;

CREATE UNIQUE INDEX idx_report_runs_active_hash
    ON report_runs (lower(requested_by), request_hash)
    WHERE status IN ('queued', 'running') AND request_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_report_runs_status_updated
    ON report_runs (status, updated_at);

INSERT INTO schema_migrations(version, notes)
VALUES (
    '011_report_runs_definitive_contract',
    'Moves report job schema ownership to migrations and adds reproducibility, execution, result integrity, lease, and strict state metadata.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
