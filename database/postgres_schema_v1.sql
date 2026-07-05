-- VPO Corp operational cloud schema v1
-- Fecha: 2026-06-24
-- Borrador de diseño. No ejecutar en produccion sin revision.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================================================
-- Helpers
-- =========================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now(),
    notes text
);

-- =========================================================
-- Identidad y permisos
-- =========================================================

CREATE TABLE IF NOT EXISTS employees (
    id bigserial PRIMARY KEY,
    display_name text NOT NULL,
    legal_name text,
    cuit text,
    phone text,
    email text,
    address text,
    notes text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS employee_functions (
    id bigserial PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    function_code text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (employee_id, function_code)
);

CREATE TABLE IF NOT EXISTS app_users (
    id bigserial PRIMARY KEY,
    employee_id bigint REFERENCES employees(id) ON DELETE SET NULL,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    global_role text NOT NULL DEFAULT 'viewer',
    active boolean NOT NULL DEFAULT true,
    auth_source text NOT NULL DEFAULT 'operational',
    notes text,
    must_change_password boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE,
    CONSTRAINT app_users_role_chk CHECK (global_role IN ('viewer', 'editor', 'admin'))
);

CREATE TABLE IF NOT EXISTS app_modules (
    id bigserial PRIMARY KEY,
    module_key text NOT NULL UNIQUE,
    label text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module_permissions (
    id bigserial PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    module_key text NOT NULL REFERENCES app_modules(module_key),
    can_access boolean NOT NULL DEFAULT false,
    can_create boolean NOT NULL DEFAULT false,
    can_view_history boolean NOT NULL DEFAULT false,
    can_edit boolean NOT NULL DEFAULT false,
    can_approve boolean NOT NULL DEFAULT false,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_scope_json jsonb,
    UNIQUE (employee_id, module_key)
);

CREATE TABLE IF NOT EXISTS permission_scopes (
    id bigserial PRIMARY KEY,
    permission_id bigint NOT NULL REFERENCES module_permissions(id) ON DELETE CASCADE,
    scope_type text NOT NULL,
    scope_ref text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (permission_id, scope_type, scope_ref),
    CONSTRAINT permission_scope_type_chk CHECK (scope_type IN ('all', 'artist', 'project', 'area'))
);

CREATE TABLE IF NOT EXISTS app_audit_log (
    id bigserial PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_username text,
    employee_id bigint REFERENCES employees(id) ON DELETE SET NULL,
    module_key text,
    action text NOT NULL,
    entity_table text,
    entity_id text,
    before_json jsonb,
    after_json jsonb,
    source text NOT NULL DEFAULT 'web',
    notes text
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON app_audit_log(entity_table, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON app_audit_log(actor_username, occurred_at DESC);

-- =========================================================
-- Referencias maestras
-- =========================================================

CREATE TABLE IF NOT EXISTS artists (
    id bigserial PRIMARY KEY,
    stage_name text NOT NULL UNIQUE,
    legal_name text,
    cuit text,
    phone text,
    email text,
    address text,
    notes text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS artist_aliases (
    id bigserial PRIMARY KEY,
    artist_id bigint NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    alias text NOT NULL,
    source text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (artist_id, alias)
);

CREATE TABLE IF NOT EXISTS business_areas (
    code text PRIMARY KEY,
    label text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS categories (
    id bigserial PRIMARY KEY,
    area_code text REFERENCES business_areas(code),
    category text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    UNIQUE (area_code, category)
);

CREATE TABLE IF NOT EXISTS counterparties (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    counterparty_type text,
    cuit text,
    email text,
    phone text,
    notes text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fx_rates (
    id bigserial PRIMARY KEY,
    rate_date date NOT NULL,
    currency text NOT NULL,
    fx_rate numeric(18, 6) NOT NULL,
    source text,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rate_date, currency, source)
);

CREATE TABLE IF NOT EXISTS attachments (
    id bigserial PRIMARY KEY,
    storage_provider text NOT NULL DEFAULT 'gcs',
    storage_uri text NOT NULL,
    original_filename text,
    content_type text,
    size_bytes bigint,
    checksum text,
    uploaded_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    notes text
);

-- =========================================================
-- Booking
-- =========================================================

CREATE TABLE IF NOT EXISTS booking_shows (
    id bigserial PRIMARY KEY,
    artist text NOT NULL,
    show_date date,
    venue text,
    city text,
    tour_manager text,
    seller text,
    status text NOT NULL DEFAULT 'realizado',
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    cachet_amount numeric(18, 6) NOT NULL DEFAULT 0,
    contracted_cachet_amount numeric(18, 6),
    venue_collected_amount numeric(18, 6),
    venue_balance_amount numeric(18, 6) NOT NULL DEFAULT 0,
    venue_payment_status text,
    venue_payment_notes text,
    expenses_amount numeric(18, 6) NOT NULL DEFAULT 0,
    pre_split_adjustments_amount numeric(18, 6) NOT NULL DEFAULT 0,
    net_amount numeric(18, 6) NOT NULL DEFAULT 0,
    split_base_amount numeric(18, 6) NOT NULL DEFAULT 0,
    artist_percent numeric(9, 4) NOT NULL DEFAULT 70,
    producer_percent numeric(9, 4) NOT NULL DEFAULT 30,
    artist_share_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_share_amount numeric(18, 6) NOT NULL DEFAULT 0,
    artist_cash_target_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_cash_target_amount numeric(18, 6) NOT NULL DEFAULT 0,
    artist_paid_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_received_amount numeric(18, 6) NOT NULL DEFAULT 0,
    balance_artist_amount numeric(18, 6) NOT NULL DEFAULT 0,
    balance_producer_amount numeric(18, 6) NOT NULL DEFAULT 0,
    settlement_status text,
    settlement_group text,
    settlement_closed_at timestamptz,
    settlement_notes text,
    origin_type text,
    origin_id bigint,
    booking_commission_exempt boolean NOT NULL DEFAULT false,
    booking_commission_notes text,
    venue_shortfall_policy text NOT NULL DEFAULT 'debt',
    receipt_refs_json jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_booking_shows_artist_date ON booking_shows(artist, show_date DESC);
CREATE INDEX IF NOT EXISTS idx_booking_shows_origin ON booking_shows(origin_type, origin_id);

CREATE TABLE IF NOT EXISTS booking_commission_rules (
    id bigserial PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    artist text NOT NULL,
    percentage numeric(9, 4) NOT NULL DEFAULT 0,
    calculation_base text NOT NULL DEFAULT 'commissionable',
    active_from_month text,
    active_to_month text,
    active boolean NOT NULL DEFAULT true,
    notes text,
    created_by text,
    updated_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(employee_id, artist),
    CONSTRAINT booking_commission_rules_base_chk CHECK (calculation_base IN ('commissionable', 'total'))
);

CREATE INDEX IF NOT EXISTS idx_booking_commission_rules_employee ON booking_commission_rules(employee_id);

CREATE TABLE IF NOT EXISTS booking_show_expenses (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    concept text NOT NULL,
    category text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_movements (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    movement_type text NOT NULL,
    category text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_pre_split_adjustments (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    concept text NOT NULL,
    destination text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    recovery_auto_apply boolean NOT NULL DEFAULT false,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_direct_commissions (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    concept text NOT NULL,
    recipient text,
    destination text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_external_shares (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    name text NOT NULL,
    role text,
    percent numeric(9, 4),
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    cash_handled_by_vpo boolean NOT NULL DEFAULT false,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_artist_adjustments (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    concept text NOT NULL,
    adjustment_type text,
    area text,
    impact text,
    recoverable boolean NOT NULL DEFAULT false,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    applied_amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    artist_percent numeric(9, 4),
    producer_percent numeric(9, 4),
    artist_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_amount numeric(18, 6) NOT NULL DEFAULT 0,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_artist_ledger (
    id bigserial PRIMARY KEY,
    artist text NOT NULL,
    movement_date date NOT NULL,
    movement_type text NOT NULL,
    concept text NOT NULL,
    category text NOT NULL,
    project text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    original_amount numeric(18, 6),
    recoverable boolean NOT NULL DEFAULT true,
    artist_percent numeric(9, 4) NOT NULL DEFAULT 0,
    producer_percent numeric(9, 4) NOT NULL DEFAULT 0,
    show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_booking_artist_ledger_artist_date ON booking_artist_ledger(artist, movement_date DESC);
CREATE INDEX IF NOT EXISTS idx_booking_artist_ledger_show ON booking_artist_ledger(show_id);

CREATE TABLE IF NOT EXISTS booking_composite_events (
    id bigserial PRIMARY KEY,
    event_date date,
    venue text,
    city text,
    responsible text,
    status text NOT NULL DEFAULT 'borrador',
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    gross_amount numeric(18, 6) NOT NULL DEFAULT 0,
    general_expenses_amount numeric(18, 6) NOT NULL DEFAULT 0,
    allocated_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_expected_amount numeric(18, 6) NOT NULL DEFAULT 0,
    received_amount numeric(18, 6) NOT NULL DEFAULT 0,
    balance_amount numeric(18, 6) NOT NULL DEFAULT 0,
    receipt_refs_json jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_composite_event_expenses (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES booking_composite_events(id) ON DELETE CASCADE,
    concept text NOT NULL,
    category text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_composite_event_lines (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES booking_composite_events(id) ON DELETE CASCADE,
    line_type text NOT NULL,
    description text,
    artist text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    artist_percent numeric(9, 4),
    producer_percent numeric(9, 4),
    artist_paid_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_received_amount numeric(18, 6) NOT NULL DEFAULT 0,
    booking_commission_exempt boolean NOT NULL DEFAULT false,
    booking_commission_notes text,
    booking_show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS booking_current_account_entries (
    id bigserial PRIMARY KEY,
    artist text,
    counterparty text,
    entry_date date NOT NULL,
    origin_type text NOT NULL,
    origin_id bigint,
    concept text NOT NULL,
    amount_ars numeric(18, 6) NOT NULL,
    direction text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    settled_by_entry_id bigint,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_ca_direction_chk CHECK (direction IN ('artist_owes_indyana', 'indyana_owes_artist', 'venue_owes_indyana', 'third_party_balance')),
    CONSTRAINT booking_ca_status_chk CHECK (status IN ('open', 'partial', 'settled', 'void', 'observed'))
);

CREATE INDEX IF NOT EXISTS idx_booking_ca_artist_date ON booking_current_account_entries(artist, entry_date);
CREATE INDEX IF NOT EXISTS idx_booking_ca_origin ON booking_current_account_entries(origin_type, origin_id);

CREATE TABLE IF NOT EXISTS booking_account_applications (
    id bigserial PRIMARY KEY,
    show_id bigint NOT NULL REFERENCES booking_shows(id) ON DELETE CASCADE,
    application_date date NOT NULL,
    target_balance text NOT NULL,
    application_type text NOT NULL,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    effect_amount numeric(18, 6) NOT NULL DEFAULT 0,
    payment_method text NOT NULL DEFAULT 'transferencia',
    counterparty text,
    linked_show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
    proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_account_app_target_chk CHECK (target_balance IN ('artist', 'producer', 'venue')),
    CONSTRAINT booking_account_app_type_chk CHECK (application_type IN ('artist_payment', 'artist_reimbursement', 'producer_reimbursement', 'venue_payment', 'compensation', 'adjustment')),
    CONSTRAINT booking_account_app_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'compensacion', 'ajuste', 'otro'))
);
CREATE INDEX IF NOT EXISTS idx_booking_account_app_show ON booking_account_applications(show_id, application_date);

-- =========================================================
-- Caserio
-- =========================================================

CREATE TABLE IF NOT EXISTS caserio_events (
    id bigserial PRIMARY KEY,
    event_date date,
    venue text,
    city text,
    responsible text,
    status text NOT NULL DEFAULT 'borrador',
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    gross_amount numeric(18, 6) NOT NULL DEFAULT 0,
    caserio_expected_amount numeric(18, 6) NOT NULL DEFAULT 0,
    producer_expected_amount numeric(18, 6) NOT NULL DEFAULT 0,
    total_expected_amount numeric(18, 6) NOT NULL DEFAULT 0,
    received_amount numeric(18, 6) NOT NULL DEFAULT 0,
    balance_amount numeric(18, 6) NOT NULL DEFAULT 0,
    receipt_refs_json jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS caserio_event_lines (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES caserio_events(id) ON DELETE CASCADE,
    line_type text NOT NULL,
    description text,
    artist text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    booking_show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

-- =========================================================
-- Finanzas artista
-- =========================================================

CREATE TABLE IF NOT EXISTS finance_projects (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    artist text,
    business_area text,
    status text NOT NULL DEFAULT 'active',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE,
    UNIQUE (name, artist)
);

CREATE TABLE IF NOT EXISTS finance_movements (
    id bigserial PRIMARY KEY,
    movement_date date NOT NULL,
    artist text NOT NULL,
    business_area text,
    movement_type text NOT NULL,
    category text,
    project_id bigint REFERENCES finance_projects(id) ON DELETE SET NULL,
    project_name text,
    concept text,
    counterparty text,
    paid_by text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    recoverable boolean NOT NULL DEFAULT false,
    recoverable_percent numeric(9, 4) NOT NULL DEFAULT 0,
    artist_percent numeric(9, 4),
    producer_percent numeric(9, 4),
    account_effect text,
    status text NOT NULL DEFAULT 'pending_control',
    source_type text,
    source_id text,
    proof_refs_json jsonb,
    paid_amount numeric(18, 6) NOT NULL DEFAULT 0,
    paid_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    pending_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    payment_status text,
    due_date date,
    recovery_method text,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_finance_movements_artist_date ON finance_movements(artist, movement_date DESC);
CREATE INDEX IF NOT EXISTS idx_finance_movements_project ON finance_movements(project_name, artist);

CREATE TABLE IF NOT EXISTS finance_movement_lines (
    id bigserial PRIMARY KEY,
    movement_id bigint NOT NULL REFERENCES finance_movements(id) ON DELETE CASCADE,
    line_date date,
    concept text NOT NULL,
    category text,
    counterparty text,
    paid_by text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    paid_amount numeric(18, 6) NOT NULL DEFAULT 0,
    paid_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    pending_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    payment_status text,
    due_date date,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance_recoverables (
    id bigserial PRIMARY KEY,
    artist text NOT NULL,
    project_id bigint REFERENCES finance_projects(id) ON DELETE SET NULL,
    finance_movement_id bigint REFERENCES finance_movements(id) ON DELETE SET NULL,
    origin_type text,
    origin_id bigint,
    opened_date date NOT NULL,
    concept text NOT NULL,
    total_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    recoverable_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    recovered_amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    recovery_method text,
    status text NOT NULL DEFAULT 'open',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT finance_recoverable_status_chk CHECK (status IN ('open', 'partial', 'closed', 'void', 'pending_control'))
);

CREATE TABLE IF NOT EXISTS finance_recovery_applications (
    id bigserial PRIMARY KEY,
    artist text NOT NULL,
    application_date date NOT NULL,
    finance_movement_id bigint REFERENCES finance_movements(id) ON DELETE SET NULL,
    finance_recoverable_id bigint REFERENCES finance_recoverables(id) ON DELETE SET NULL,
    project_name text,
    source_type text NOT NULL,
    source_id text,
    source_label text,
    amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    recovery_method text,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE
);

CREATE TABLE IF NOT EXISTS finance_account_entries (
    id bigserial PRIMARY KEY,
    artist text,
    counterparty text,
    entry_date date NOT NULL,
    origin_type text NOT NULL,
    origin_id bigint,
    concept text NOT NULL,
    amount_ars numeric(18, 6) NOT NULL,
    direction text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT finance_account_direction_chk CHECK (direction IN ('artist_owes_indyana', 'indyana_owes_artist', 'third_party_owes_indyana', 'indyana_owes_third_party')),
    CONSTRAINT finance_account_status_chk CHECK (status IN ('open', 'partial', 'settled', 'void', 'observed'))
);

-- =========================================================
-- Catalogo / digitales / decisiones humanas
-- =========================================================

CREATE TABLE IF NOT EXISTS catalog_status (
    catalog_key text PRIMARY KEY,
    active boolean NOT NULL DEFAULT true,
    include_in_reports boolean NOT NULL DEFAULT true,
    catalog_business_status text NOT NULL DEFAULT 'vpo_catalog',
    status_notes text,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_label_overrides (
    catalog_key text PRIMARY KEY,
    label_normalized_override text,
    notes text,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS distributor_account_policies (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    account text NOT NULL,
    source_sheet text NOT NULL,
    revenue_basis text,
    include_in_cash_view boolean NOT NULL DEFAULT true,
    include_in_catalog_view boolean NOT NULL DEFAULT true,
    include_in_statement_view boolean NOT NULL DEFAULT true,
    amount_role text NOT NULL DEFAULT 'generation',
    notes text,
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, account, source_sheet, revenue_basis)
);

CREATE TABLE IF NOT EXISTS custom_report_configs (
    id bigserial PRIMARY KEY,
    report_key text NOT NULL UNIQUE,
    title text NOT NULL,
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_runs (
    id bigserial PRIMARY KEY,
    report_key text,
    requested_by text,
    params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_uri text,
    status text NOT NULL DEFAULT 'created',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

INSERT INTO schema_migrations(version, notes)
VALUES ('cloud_operational_schema_v1_draft', 'Initial draft schema for VPO Corp cloud operational database')
ON CONFLICT (version) DO NOTHING;

COMMIT;
