-- VPO Corp operational core draft
-- Status: DRAFT ONLY. Do not run against production without review.
-- Target: PostgreSQL / Cloud SQL

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS vpo;

-- ---------------------------------------------------------------------------
-- Identity, users, permissions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.employees (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name text NOT NULL,
    legal_name text,
    email text,
    phone text,
    tax_id text,
    address text,
    active boolean NOT NULL DEFAULT true,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.employee_functions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES vpo.employees(id) ON DELETE CASCADE,
    function_code text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (employee_id, function_code)
);

CREATE TABLE IF NOT EXISTS vpo.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid REFERENCES vpo.employees(id) ON DELETE SET NULL,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    global_role text NOT NULL DEFAULT 'viewer',
    active boolean NOT NULL DEFAULT true,
    is_super_admin boolean NOT NULL DEFAULT false,
    auth_source text NOT NULL DEFAULT 'operational',
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.modules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module_key text NOT NULL UNIQUE,
    label text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.module_permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES vpo.users(id) ON DELETE CASCADE,
    employee_id uuid REFERENCES vpo.employees(id) ON DELETE CASCADE,
    module_key text NOT NULL REFERENCES vpo.modules(module_key),
    can_access boolean NOT NULL DEFAULT false,
    can_create boolean NOT NULL DEFAULT false,
    can_view_history boolean NOT NULL DEFAULT false,
    can_edit boolean NOT NULL DEFAULT false,
    can_approve boolean NOT NULL DEFAULT false,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (user_id IS NOT NULL OR employee_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS vpo.permission_scopes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_id uuid NOT NULL REFERENCES vpo.module_permissions(id) ON DELETE CASCADE,
    scope_type text NOT NULL, -- artist, project, area, all
    scope_ref text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (permission_id, scope_type, scope_ref)
);

-- ---------------------------------------------------------------------------
-- Master data
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.artists (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_name text NOT NULL,
    legal_name text,
    tax_id text,
    email text,
    phone text,
    address text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (stage_name)
);

CREATE TABLE IF NOT EXISTS vpo.artist_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artist_id uuid NOT NULL REFERENCES vpo.artists(id) ON DELETE CASCADE,
    alias text NOT NULL,
    source text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (artist_id, alias)
);

CREATE TABLE IF NOT EXISTS vpo.business_areas (
    code text PRIMARY KEY,
    label text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS vpo.categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    area_code text REFERENCES vpo.business_areas(code),
    label text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    UNIQUE (area_code, label)
);

CREATE TABLE IF NOT EXISTS vpo.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    project_name text NOT NULL,
    area_code text REFERENCES vpo.business_areas(code),
    status text NOT NULL DEFAULT 'active',
    budget_amount_ars numeric(14,2),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.counterparties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name text NOT NULL,
    counterparty_type text NOT NULL DEFAULT 'other',
    employee_id uuid REFERENCES vpo.employees(id) ON DELETE SET NULL,
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    active boolean NOT NULL DEFAULT true,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.fx_rates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rate_date date NOT NULL,
    currency text NOT NULL,
    fx_rate_ars numeric(14,6) NOT NULL,
    source text NOT NULL DEFAULT 'manual',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rate_date, currency, source)
);

CREATE TABLE IF NOT EXISTS vpo.attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    storage_uri text,
    original_name text,
    content_type text,
    size_bytes bigint,
    uploaded_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Booking operational model
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.booking_shows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    legacy_sqlite_id bigint,
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    show_date date NOT NULL,
    venue text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate_ars numeric(14,6),
    contracted_cachet_amount numeric(14,2) NOT NULL DEFAULT 0,
    effective_cachet_amount numeric(14,2) NOT NULL DEFAULT 0,
    venue_collected_amount numeric(14,2) NOT NULL DEFAULT 0,
    venue_balance_amount numeric(14,2) NOT NULL DEFAULT 0,
    venue_shortfall_policy text NOT NULL DEFAULT 'none',
    gross_expenses_amount numeric(14,2) NOT NULL DEFAULT 0,
    direct_commissions_amount numeric(14,2) NOT NULL DEFAULT 0,
    pre_split_adjustments_amount numeric(14,2) NOT NULL DEFAULT 0,
    split_base_amount numeric(14,2) NOT NULL DEFAULT 0,
    artist_percent numeric(7,4) NOT NULL DEFAULT 70,
    producer_percent numeric(7,4) NOT NULL DEFAULT 30,
    artist_target_amount numeric(14,2) NOT NULL DEFAULT 0,
    producer_target_amount numeric(14,2) NOT NULL DEFAULT 0,
    artist_paid_amount numeric(14,2) NOT NULL DEFAULT 0,
    producer_received_amount numeric(14,2) NOT NULL DEFAULT 0,
    booking_commission_exempt boolean NOT NULL DEFAULT false,
    booking_commission_notes text,
    source_module text NOT NULL DEFAULT 'booking',
    notes text,
    created_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.booking_show_expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    show_id uuid NOT NULL REFERENCES vpo.booking_shows(id) ON DELETE CASCADE,
    category_id uuid REFERENCES vpo.categories(id) ON DELETE SET NULL,
    concept text NOT NULL,
    amount numeric(14,2) NOT NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.booking_direct_commissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    show_id uuid NOT NULL REFERENCES vpo.booking_shows(id) ON DELETE CASCADE,
    description text NOT NULL,
    destination_type text NOT NULL DEFAULT 'outside',
    destination_artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    amount numeric(14,2) NOT NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.booking_cash_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    show_id uuid NOT NULL REFERENCES vpo.booking_shows(id) ON DELETE CASCADE,
    movement_date date,
    receiver_type text NOT NULL, -- indyana, artist, employee, external, venue
    receiver_ref text,
    method text NOT NULL DEFAULT 'transfer',
    amount numeric(14,2) NOT NULL,
    attachment_id uuid REFERENCES vpo.attachments(id) ON DELETE SET NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.booking_current_account_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    show_id uuid REFERENCES vpo.booking_shows(id) ON DELETE SET NULL,
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    counterparty_id uuid REFERENCES vpo.counterparties(id) ON DELETE SET NULL,
    entry_date date NOT NULL,
    entry_type text NOT NULL,
    amount_ars numeric(14,2) NOT NULL,
    direction text NOT NULL, -- owed_to_indyana, owed_by_indyana, venue_debt
    status text NOT NULL DEFAULT 'open',
    source_notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Finance
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.finance_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    project_id uuid REFERENCES vpo.projects(id) ON DELETE SET NULL,
    movement_date date NOT NULL,
    movement_type text NOT NULL,
    area_code text REFERENCES vpo.business_areas(code),
    category_id uuid REFERENCES vpo.categories(id) ON DELETE SET NULL,
    concept text NOT NULL,
    amount_original numeric(14,2) NOT NULL,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate_ars numeric(14,6),
    amount_ars numeric(14,2) NOT NULL,
    paid_by text NOT NULL DEFAULT 'indyana',
    counterparty_id uuid REFERENCES vpo.counterparties(id) ON DELETE SET NULL,
    payment_status text NOT NULL DEFAULT 'paid',
    paid_amount_ars numeric(14,2) NOT NULL DEFAULT 0,
    pending_amount_ars numeric(14,2) NOT NULL DEFAULT 0,
    recoverable boolean NOT NULL DEFAULT false,
    recoverable_percent numeric(7,4) NOT NULL DEFAULT 0,
    recovery_method text NOT NULL DEFAULT 'none',
    control_status text NOT NULL DEFAULT 'pending_control',
    attachment_id uuid REFERENCES vpo.attachments(id) ON DELETE SET NULL,
    notes text,
    created_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.finance_movement_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movement_id uuid NOT NULL REFERENCES vpo.finance_movements(id) ON DELETE CASCADE,
    line_order integer NOT NULL DEFAULT 1,
    concept text NOT NULL,
    amount_original numeric(14,2) NOT NULL,
    currency text NOT NULL DEFAULT 'ARS',
    fx_rate_ars numeric(14,6),
    amount_ars numeric(14,2) NOT NULL,
    paid_by text,
    counterparty_id uuid REFERENCES vpo.counterparties(id) ON DELETE SET NULL,
    payment_status text,
    due_date date,
    notes text
);

CREATE TABLE IF NOT EXISTS vpo.finance_recoverables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    finance_movement_id uuid NOT NULL REFERENCES vpo.finance_movements(id) ON DELETE CASCADE,
    artist_id uuid REFERENCES vpo.artists(id) ON DELETE SET NULL,
    project_id uuid REFERENCES vpo.projects(id) ON DELETE SET NULL,
    original_amount_ars numeric(14,2) NOT NULL,
    recoverable_amount_ars numeric(14,2) NOT NULL,
    recovered_amount_ars numeric(14,2) NOT NULL DEFAULT 0,
    pending_amount_ars numeric(14,2) NOT NULL,
    recovery_method text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.finance_recovery_applications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recoverable_id uuid NOT NULL REFERENCES vpo.finance_recoverables(id) ON DELETE CASCADE,
    source_type text NOT NULL,
    source_ref text NOT NULL,
    application_date date NOT NULL,
    amount_ars numeric(14,2) NOT NULL,
    notes text,
    created_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Catalog/report business decisions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.catalog_status (
    catalog_key text PRIMARY KEY,
    active boolean NOT NULL DEFAULT true,
    include_in_reports boolean NOT NULL DEFAULT true,
    catalog_business_status text NOT NULL DEFAULT 'vpo_catalog',
    label_normalized_override text,
    status_notes text,
    updated_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.custom_report_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_key text NOT NULL UNIQUE,
    title text NOT NULL,
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vpo.report_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_key text NOT NULL,
    requested_by_user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'queued',
    params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_uri text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

-- ---------------------------------------------------------------------------
-- Audit
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vpo.audit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    user_id uuid REFERENCES vpo.users(id) ON DELETE SET NULL,
    employee_id uuid REFERENCES vpo.employees(id) ON DELETE SET NULL,
    module_key text,
    action text NOT NULL,
    entity_table text,
    entity_id text,
    before_json jsonb,
    after_json jsonb,
    source text NOT NULL DEFAULT 'web',
    notes text
);

-- ---------------------------------------------------------------------------
-- Seed baseline codes
-- ---------------------------------------------------------------------------

INSERT INTO vpo.business_areas (code, label) VALUES
    ('booking', 'Booking'),
    ('label', 'Label'),
    ('marketing', 'Marketing'),
    ('digitales', 'Digitales'),
    ('management', 'Management'),
    ('general', 'General')
ON CONFLICT (code) DO NOTHING;

INSERT INTO vpo.modules (module_key, label) VALUES
    ('home', 'Inicio'),
    ('booking', 'Booking Indyana'),
    ('booking_detail', 'Detalle Booking'),
    ('booking_summary', 'Resumen Booking'),
    ('booking_commissions', 'Comisiones'),
    ('caserio', 'Caserio'),
    ('finance_movements', 'Movimientos financieros'),
    ('artist_finance', 'Finanzas Artista'),
    ('artists_abm', 'ABM Artistas'),
    ('employees_abm', 'ABM Empleados'),
    ('catalog', 'Catalogo General'),
    ('digital_income', 'Ingresos Digitales'),
    ('distributor_config', 'Configuracion Distribuidoras'),
    ('custom_reports', 'Reportes Personalizados'),
    ('source_monitor', 'Control Distribuidoras')
ON CONFLICT (module_key) DO NOTHING;
