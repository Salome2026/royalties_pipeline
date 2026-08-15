-- Distributor policies become operational Cloud SQL data.
-- The previous table was an unused draft and was verified empty before this migration.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.distributor_account_policies') IS NOT NULL
       AND EXISTS (SELECT 1 FROM distributor_account_policies LIMIT 1) THEN
        RAISE EXCEPTION 'distributor_account_policies is not empty; aborting clean migration';
    END IF;
END
$$;

DROP TABLE IF EXISTS distributor_account_policies;

CREATE TABLE distributor_account_policies (
    policy_id text PRIMARY KEY,
    source text NOT NULL,
    account text NOT NULL,
    display_name text NOT NULL,
    policy_payload jsonb NOT NULL,
    report_net_adjustment_pct numeric(7,4) NOT NULL DEFAULT 0
        CHECK (report_net_adjustment_pct >= 0 AND report_net_adjustment_pct <= 100),
    active boolean NOT NULL DEFAULT true,
    policy_version bigint NOT NULL DEFAULT 1,
    updated_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, account)
);

CREATE TABLE distributor_policy_settings (
    singleton_id smallint PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
    personalization_enabled boolean NOT NULL DEFAULT false,
    amount_basis text NOT NULL DEFAULT 'net_amount_after_distributor',
    scope text NOT NULL DEFAULT 'royalty_reports',
    policy_version bigint NOT NULL DEFAULT 1,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE distributor_policy_audit (
    id bigserial PRIMARY KEY,
    policy_version bigint NOT NULL,
    action text NOT NULL,
    changed_by text,
    before_json jsonb,
    after_json jsonb NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO distributor_policy_settings(singleton_id)
VALUES (1)
ON CONFLICT (singleton_id) DO NOTHING;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '002_distributor_policies_cloudsql',
    'Distributor policies and report personalization moved to the single operational Cloud SQL database.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
