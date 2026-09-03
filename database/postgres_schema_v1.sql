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
    compensation_type text NOT NULL DEFAULT 'none',
    salary_amount numeric(18,6) NOT NULL DEFAULT 0,
    salary_currency text NOT NULL DEFAULT 'ARS',
    salary_frequency text NOT NULL DEFAULT 'monthly',
    salary_notes text,
    notes text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    legacy_sqlite_id bigint UNIQUE,
    CONSTRAINT employees_compensation_type_chk CHECK (compensation_type IN ('none', 'salary', 'salary_plus_booking_commission', 'booking_commission_only')),
    CONSTRAINT employees_salary_currency_chk CHECK (salary_currency IN ('ARS', 'USD')),
    CONSTRAINT employees_salary_frequency_chk CHECK (salary_frequency IN ('monthly'))
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

CREATE TABLE IF NOT EXISTS booking_events (
    id bigserial PRIMARY KEY,
    event_type text NOT NULL DEFAULT 'show',
    event_date date NOT NULL,
    start_time time,
    venue text NOT NULL,
    city text,
    booking_mode text NOT NULL,
    commercial_status text NOT NULL DEFAULT 'confirmado',
    operational_status text NOT NULL DEFAULT 'programado',
    deposit_status text NOT NULL DEFAULT 'sin_sena',
    settlement_status text NOT NULL DEFAULT 'no_iniciada',
    contracted_cachet_amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    tour_manager text,
    seller text,
    group_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL,
    group_position integer,
    duplicate_override boolean NOT NULL DEFAULT false,
    duplicate_override_notes text,
    notes text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_events_mode_chk CHECK (booking_mode IN ('individual', 'shared')),
    CONSTRAINT booking_events_event_type_chk CHECK (event_type IN ('show', 'show_group', 'availability_block', 'logistics', 'prospect')),
    CONSTRAINT booking_events_commercial_chk CHECK (commercial_status IN ('confirmado', 'cancelado', 'prospecto', 'no_aplica')),
    CONSTRAINT booking_events_operational_chk CHECK (operational_status IN ('programado', 'realizado', 'bloqueado', 'informativo')),
    CONSTRAINT booking_events_deposit_chk CHECK (deposit_status IN ('no_informada', 'sin_sena', 'sena_parcial', 'sena_recibida')),
    CONSTRAINT booking_events_settlement_chk CHECK (settlement_status IN ('no_iniciada', 'pendiente', 'rendida', 'observada', 'cerrada', 'no_aplica')),
    CONSTRAINT booking_events_currency_chk CHECK (currency IN ('ARS', 'USD')),
    CONSTRAINT booking_events_cachet_chk CHECK (contracted_cachet_amount >= 0),
    CONSTRAINT booking_events_fx_chk CHECK (fx_rate IS NULL OR fx_rate > 0),
    CONSTRAINT booking_events_override_note_chk CHECK (NOT duplicate_override OR duplicate_override_notes IS NOT NULL),
    CONSTRAINT booking_events_group_chk CHECK (
        (group_event_id IS NULL AND group_position IS NULL)
        OR (event_type = 'show' AND group_event_id IS NOT NULL AND group_position > 0)
    ),
    CONSTRAINT booking_events_non_show_settlement_chk CHECK (event_type = 'show' OR settlement_status = 'no_aplica')
);

CREATE INDEX IF NOT EXISTS idx_booking_events_date ON booking_events(event_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_booking_events_status ON booking_events(commercial_status, operational_status, settlement_status);
CREATE INDEX IF NOT EXISTS idx_booking_events_venue_city ON booking_events(lower(venue), lower(COALESCE(city, '')));
CREATE INDEX IF NOT EXISTS idx_booking_events_type_date ON booking_events(event_type, event_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_booking_events_group ON booking_events(group_event_id, group_position) WHERE group_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS booking_event_artists (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES booking_events(id) ON DELETE CASCADE,
    artist_id bigint NOT NULL REFERENCES artists(id),
    artist_name text NOT NULL,
    position integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(event_id, artist_id),
    UNIQUE(event_id, position),
    CONSTRAINT booking_event_artists_position_chk CHECK (position > 0)
);

CREATE INDEX IF NOT EXISTS idx_booking_event_artists_artist ON booking_event_artists(artist_id, event_id);

CREATE TABLE IF NOT EXISTS booking_event_deposits (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES booking_events(id) ON DELETE CASCADE,
    movement_date date NOT NULL,
    amount numeric(18, 6) NOT NULL,
    currency text NOT NULL,
    fx_rate numeric(18, 6),
    received_by text NOT NULL,
    received_by_name text,
    payment_method text NOT NULL DEFAULT 'transferencia',
    counterparty text,
    proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_event_deposits_amount_chk CHECK (amount > 0),
    CONSTRAINT booking_event_deposits_currency_chk CHECK (currency IN ('ARS', 'USD')),
    CONSTRAINT booking_event_deposits_fx_chk CHECK (fx_rate IS NULL OR fx_rate > 0),
    CONSTRAINT booking_event_deposits_receiver_chk CHECK (received_by IN ('indyana', 'artista', 'empleado', 'tercero')),
    CONSTRAINT booking_event_deposits_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'otro'))
);

CREATE INDEX IF NOT EXISTS idx_booking_event_deposits_event_date ON booking_event_deposits(event_id, movement_date, id);

CREATE TABLE IF NOT EXISTS booking_event_source_links (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES booking_events(id) ON DELETE CASCADE,
    source_system text NOT NULL,
    source_reference text NOT NULL,
    source_role text NOT NULL DEFAULT 'imported',
    source_text text,
    source_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(event_id, source_system, source_reference)
);

CREATE INDEX IF NOT EXISTS idx_booking_event_source_reference
    ON booking_event_source_links(source_system, source_reference);
CREATE INDEX IF NOT EXISTS idx_booking_event_source_event
    ON booking_event_source_links(event_id, id DESC);

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
    legacy_sqlite_id bigint UNIQUE,
    booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_booking_shows_artist_date ON booking_shows(artist, show_date DESC);
CREATE INDEX IF NOT EXISTS idx_booking_shows_origin ON booking_shows(origin_type, origin_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_shows_booking_event ON booking_shows(booking_event_id) WHERE booking_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS booking_commission_rules (
    id bigserial PRIMARY KEY,
    employee_id bigint NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    artist text NOT NULL,
    percentage numeric(9, 4) NOT NULL DEFAULT 0,
    calculation_base text NOT NULL DEFAULT 'commissionable',
    include_booking_fee_paid_shows boolean NOT NULL DEFAULT false,
    priority_order integer,
    active_from_month text,
    active_to_month text,
    active boolean NOT NULL DEFAULT true,
    notes text,
    created_by text,
    updated_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(employee_id, artist),
    CONSTRAINT booking_commission_rules_base_chk CHECK (calculation_base IN ('commissionable', 'total')),
    CONSTRAINT booking_commission_rules_priority_chk CHECK (priority_order BETWEEN 1 AND 5)
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

CREATE INDEX IF NOT EXISTS idx_booking_show_expenses_show
    ON booking_show_expenses(show_id, id);

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

CREATE INDEX IF NOT EXISTS idx_booking_movements_show
    ON booking_movements(show_id, id);

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
    legacy_sqlite_id bigint UNIQUE,
    booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_composite_events_booking_event ON booking_composite_events(booking_event_id) WHERE booking_event_id IS NOT NULL;

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

CREATE TABLE IF NOT EXISTS booking_account_movements (
    id bigserial PRIMARY KEY,
    movement_date date NOT NULL,
    artist text NOT NULL,
    movement_type text NOT NULL,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    applied_amount numeric(18, 6) NOT NULL DEFAULT 0,
    unapplied_amount numeric(18, 6) NOT NULL DEFAULT 0,
    payment_method text NOT NULL DEFAULT 'transferencia',
    counterparty text,
    proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_account_mov_type_chk CHECK (movement_type IN ('cobro_deuda_booking', 'pago_saldo_artista', 'compensacion_booking', 'pago_deuda_boliche', 'ajuste_booking')),
    CONSTRAINT booking_account_mov_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'compensacion', 'ajuste', 'otro'))
);
CREATE INDEX IF NOT EXISTS idx_booking_account_mov_artist ON booking_account_movements(artist, movement_date);

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
    movement_id bigint REFERENCES booking_account_movements(id) ON DELETE SET NULL,
    proof_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_account_app_target_chk CHECK (target_balance IN ('artist', 'producer', 'venue')),
    CONSTRAINT booking_account_app_type_chk CHECK (application_type IN ('artist_payment', 'artist_reimbursement', 'producer_reimbursement', 'venue_payment', 'compensation', 'adjustment')),
    CONSTRAINT booking_account_app_method_chk CHECK (payment_method IN ('transferencia', 'efectivo', 'compensacion', 'ajuste', 'otro'))
);
CREATE INDEX IF NOT EXISTS idx_booking_account_app_show ON booking_account_applications(show_id, application_date);
CREATE INDEX IF NOT EXISTS idx_booking_account_app_movement ON booking_account_applications(movement_id);

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
    legacy_sqlite_id bigint UNIQUE,
    booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_caserio_events_booking_event ON caserio_events(booking_event_id) WHERE booking_event_id IS NOT NULL;

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
    paid_by_employee_id bigint REFERENCES employees(id) ON DELETE SET NULL,
    paid_by_employee_name text,
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
    created_by text,
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
CREATE INDEX IF NOT EXISTS idx_finance_movements_paid_by_employee ON finance_movements(paid_by_employee_id, movement_date DESC);

CREATE TABLE IF NOT EXISTS finance_movement_allocations (
    id bigserial PRIMARY KEY,
    movement_id bigint NOT NULL REFERENCES finance_movements(id) ON DELETE CASCADE,
    allocation_type text NOT NULL DEFAULT 'indyana_cost',
    target_name text NOT NULL,
    business_area text,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT finance_movement_allocations_type_chk CHECK (allocation_type IN ('indyana_cost', 'third_party_receivable', 'artist_current_account', 'other')),
    CONSTRAINT finance_movement_allocations_currency_chk CHECK (currency IN ('ARS', 'USD'))
);

CREATE INDEX IF NOT EXISTS idx_finance_movement_allocations_movement ON finance_movement_allocations(movement_id);

CREATE SEQUENCE IF NOT EXISTS finance_documents_document_number_seq;

CREATE TABLE IF NOT EXISTS finance_documents (
    id bigserial PRIMARY KEY,
    movement_id bigint NOT NULL UNIQUE REFERENCES finance_movements(id) ON DELETE CASCADE,
    document_number bigint NOT NULL UNIQUE DEFAULT nextval('finance_documents_document_number_seq'),
    document_date date NOT NULL,
    document_type text NOT NULL DEFAULT 'show_deposit_receipt',
    issuer_company text NOT NULL DEFAULT 'VPO Corp',
    counterparty_name text NOT NULL,
    amount numeric(18, 6) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate numeric(18, 6),
    amount_ars numeric(18, 6) NOT NULL DEFAULT 0,
    vat_mode text NOT NULL DEFAULT 'no_aplica',
    concept text NOT NULL,
    show_date date,
    venue text,
    artist_names_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    booking_show_id bigint REFERENCES booking_shows(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'emitido',
    pdf_path text,
    notes text,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT finance_documents_type_chk CHECK (document_type IN ('show_deposit_receipt', 'payment_order', 'collection_receipt')),
    CONSTRAINT finance_documents_currency_chk CHECK (currency IN ('ARS', 'USD')),
    CONSTRAINT finance_documents_vat_mode_chk CHECK (vat_mode IN ('no_aplica', 'mas_iva', 'iva_incluido')),
    CONSTRAINT finance_documents_status_chk CHECK (status IN ('borrador', 'emitido', 'anulado', 'aplicado'))
);

CREATE INDEX IF NOT EXISTS idx_finance_documents_date ON finance_documents(document_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_finance_documents_show_date ON finance_documents(show_date);

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
    counterparty_employee_id bigint REFERENCES employees(id) ON DELETE SET NULL,
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

CREATE INDEX IF NOT EXISTS idx_finance_account_entries_counterparty ON finance_account_entries(counterparty, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_finance_account_entries_employee ON finance_account_entries(counterparty_employee_id, entry_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_account_employee_reimbursement_origin
    ON finance_account_entries(origin_type, origin_id)
    WHERE origin_type = 'finance_employee_reimbursement';

CREATE TABLE IF NOT EXISTS finance_account_applications (
    id bigserial PRIMARY KEY,
    account_entry_id bigint NOT NULL REFERENCES finance_account_entries(id) ON DELETE CASCADE,
    payment_movement_id bigint NOT NULL REFERENCES finance_movements(id) ON DELETE CASCADE,
    application_date date NOT NULL,
    amount_ars numeric(18, 6) NOT NULL,
    notes text,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT finance_account_applications_amount_chk CHECK (amount_ars > 0),
    UNIQUE (account_entry_id, payment_movement_id)
);

CREATE INDEX IF NOT EXISTS idx_finance_account_applications_entry ON finance_account_applications(account_entry_id);
CREATE INDEX IF NOT EXISTS idx_finance_account_applications_movement ON finance_account_applications(payment_movement_id);

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

CREATE TABLE IF NOT EXISTS distributor_policy_settings (
    singleton_id smallint PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
    personalization_enabled boolean NOT NULL DEFAULT false,
    amount_basis text NOT NULL DEFAULT 'net_amount_after_distributor',
    scope text NOT NULL DEFAULT 'royalty_reports',
    policy_version bigint NOT NULL DEFAULT 1,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS distributor_policy_audit (
    id bigserial PRIMARY KEY,
    policy_version bigint NOT NULL,
    action text NOT NULL,
    changed_by text,
    before_json jsonb,
    after_json jsonb NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
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
    report_key text NOT NULL,
    requested_by text NOT NULL,
    params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    policy_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    policy_version bigint,
    engine_version text,
    output_uri text,
    output_format text NOT NULL DEFAULT 'excel',
    request_hash text,
    progress_stage text NOT NULL DEFAULT 'queued',
    result_filename text,
    result_content_type text,
    result_url text,
    result_size_bytes bigint,
    result_sha256 text,
    execution_name text,
    attempt_count integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'queued',
    error_message text,
    error_log_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days'),
    lease_expires_at timestamptz,
    CONSTRAINT report_runs_output_chk CHECK (output_format IN ('excel', 'executive_pdf', 'google_sheet')),
    CONSTRAINT report_runs_status_chk CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    CONSTRAINT report_runs_stage_chk CHECK (progress_stage IN (
        'queued', 'preparing', 'reading_data', 'building', 'uploading',
        'completed', 'failed'
    )),
    CONSTRAINT report_runs_report_key_chk CHECK (report_key IN (
        'royalty_keyword', 'royalty_executive', 'royalty_google_sheet'
    )),
    CONSTRAINT report_runs_requested_by_chk CHECK (btrim(requested_by) <> ''),
    CONSTRAINT report_runs_params_json_chk CHECK (jsonb_typeof(params_json) = 'object'),
    CONSTRAINT report_runs_input_manifest_chk CHECK (jsonb_typeof(input_manifest_json) = 'object'),
    CONSTRAINT report_runs_policy_snapshot_chk CHECK (jsonb_typeof(policy_snapshot_json) = 'object'),
    CONSTRAINT report_runs_policy_version_chk CHECK (policy_version IS NULL OR policy_version > 0),
    CONSTRAINT report_runs_active_context_chk CHECK (
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
    ),
    CONSTRAINT report_runs_attempt_count_chk CHECK (attempt_count >= 0),
    CONSTRAINT report_runs_result_size_chk CHECK (result_size_bytes IS NULL OR result_size_bytes >= 0),
    CONSTRAINT report_runs_result_sha256_chk CHECK (
        result_sha256 IS NULL OR result_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT report_runs_request_hash_chk CHECK (
        request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT report_runs_running_started_chk CHECK (
        status <> 'running' OR started_at IS NOT NULL
    ),
    CONSTRAINT report_runs_terminal_finished_chk CHECK (
        status NOT IN ('completed', 'failed') OR finished_at IS NOT NULL
    ),
    CONSTRAINT report_runs_completed_result_chk CHECK (
        status <> 'completed' OR output_uri IS NOT NULL OR result_url IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_report_runs_requester_time
    ON report_runs(requested_by, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_report_runs_active_hash
    ON report_runs(lower(requested_by), request_hash)
    WHERE status IN ('queued', 'running') AND request_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_report_runs_status_updated
    ON report_runs(status, updated_at);

INSERT INTO schema_migrations(version, notes)
VALUES ('cloud_operational_schema_v1_draft', 'Initial draft schema for VPO Corp cloud operational database')
ON CONFLICT (version) DO NOTHING;

COMMIT;
