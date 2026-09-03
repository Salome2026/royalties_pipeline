-- Final cutover from Cloud Tasks and API workers to Cloud Run Jobs.

BEGIN;

LOCK TABLE report_runs IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE report_runs
    DROP COLUMN IF EXISTS task_name;

ALTER TABLE report_runs
    DROP CONSTRAINT IF EXISTS report_runs_active_context_chk;

ALTER TABLE report_runs
    ADD CONSTRAINT report_runs_active_context_chk
        CHECK (
            status NOT IN ('queued', 'running')
            OR (
                policy_version IS NOT NULL
                AND input_manifest_json ? 'objects'
                AND jsonb_typeof(input_manifest_json -> 'objects') = 'object'
                AND input_manifest_json -> 'objects' <> '{}'::jsonb
                AND policy_snapshot_json ? 'entries'
                AND jsonb_typeof(policy_snapshot_json -> 'entries') = 'array'
                AND jsonb_array_length(policy_snapshot_json -> 'entries') > 0
            )
        );

INSERT INTO schema_migrations(version, notes)
VALUES (
    '012_cloud_run_report_job_cutover',
    'Removes Cloud Tasks metadata and requires immutable data and policy context for active Cloud Run report jobs.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
