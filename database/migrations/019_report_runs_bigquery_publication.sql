BEGIN;

ALTER TABLE report_runs DROP CONSTRAINT report_runs_active_context_chk;
ALTER TABLE report_runs ADD CONSTRAINT report_runs_active_context_chk CHECK (
    status NOT IN ('queued', 'running')
    OR (
        policy_version IS NOT NULL
        AND CASE WHEN jsonb_typeof(policy_snapshot_json -> 'entries') = 'array'
            THEN jsonb_array_length(policy_snapshot_json -> 'entries') > 0 ELSE false END
        AND (
            COALESCE(
                jsonb_typeof(input_manifest_json -> 'objects') = 'object'
                AND input_manifest_json -> 'objects' <> '{}'::jsonb,
                false
            )
            OR COALESCE(
                jsonb_typeof(input_manifest_json -> 'report_publication') = 'object'
                AND input_manifest_json ->> 'release_id' <> ''
                AND input_manifest_json #>> '{report_publication,publication_id}' ~ '^[a-z0-9_]{1,80}$'
                AND input_manifest_json #>> '{report_publication,envelope_sha256}' ~ '^[0-9a-f]{64}$'
                AND input_manifest_json #>> '{report_publication,scope}' = COALESCE(params_json ->> 'royalty_scope', 'regular')
                AND input_manifest_json #>> '{report_publication,scope}' IN ('regular', 'wml'),
                false
            )
        )
    )
);

INSERT INTO schema_migrations(version, notes)
VALUES ('019_report_runs_bigquery_publication', 'Allow report jobs to pin a verified BigQuery publication.')
ON CONFLICT DO NOTHING;
COMMIT;
