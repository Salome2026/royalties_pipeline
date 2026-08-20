-- Register ADA / Indyana Records as an independent production account.
-- Raw identity: Account 99500 / INDYANA RECORDS LLC.

BEGIN;

DO $$
DECLARE
    next_version bigint;
    policy_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM distributor_account_policies
        WHERE policy_id = 'ada_indyana_records'
           OR (source = 'ada' AND account = 'indyana_records')
    ) INTO policy_exists;

    IF NOT policy_exists THEN
        SELECT policy_version + 1
        INTO next_version
        FROM distributor_policy_settings
        WHERE singleton_id = 1
        FOR UPDATE;

        INSERT INTO distributor_account_policies(
            policy_id,
            source,
            account,
            display_name,
            policy_payload,
            report_net_adjustment_pct,
            policy_version,
            updated_by
        ) VALUES (
            'ada_indyana_records',
            'ada',
            'indyana_records',
            'ADA / Indyana Records',
            jsonb_build_object(
                'notes', 'ADA TXT detail for Account 99500 / INDYANA RECORDS LLC. Net Royalty Payable is the reportable net amount.',
                'sheet_rules', jsonb_build_object(
                    'royalty_detail', jsonb_build_object(
                        'cash_view', true,
                        'catalog_view', true,
                        'revenue_basis', 'generation',
                        'statement_view', true
                    )
                ),
                'account_type', 'owned',
                'shares_policy', 'not_applicable',
                'cash_view_mode', 'complete',
                'cash_view_label', 'Caja completa',
                'cash_view_enabled', true,
                'monitoring_active', true,
                'ownership_default', 'vpo',
                'contract_cutoff_id', null,
                'default_time_basis', 'statement_period',
                'catalog_view_enabled', true,
                'cash_view_description', 'La cuenta ADA Indyana Records se considera caja propia para todo el detalle reportable.',
                'statement_view_enabled', true
            ),
            0,
            next_version,
            'codex_ada_indyana_records'
        );

        UPDATE distributor_policy_settings
        SET policy_version = next_version,
            updated_by = 'codex_ada_indyana_records',
            updated_at = now()
        WHERE singleton_id = 1;

        INSERT INTO distributor_policy_audit(
            policy_version,
            action,
            changed_by,
            after_json
        ) VALUES (
            next_version,
            'add_account_ada_indyana_records',
            'codex_ada_indyana_records',
            jsonb_build_object(
                'policy_id', 'ada_indyana_records',
                'source', 'ada',
                'account', 'indyana_records',
                'display_name', 'ADA / Indyana Records',
                'report_net_adjustment_pct', 0
            )
        );
    END IF;
END
$$;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '010_add_ada_indyana_records_policy',
    'Registers ADA Account 99500 / Indyana Records as an owned generation and cash account.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
