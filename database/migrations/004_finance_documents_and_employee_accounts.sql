-- Financial documents, employee reimbursements and their applications are
-- operational Cloud SQL structures. No SQLite compatibility is created.

BEGIN;

ALTER TABLE finance_movements
    ADD COLUMN IF NOT EXISTS paid_by_employee_id bigint REFERENCES employees(id) ON DELETE SET NULL;
ALTER TABLE finance_movements
    ADD COLUMN IF NOT EXISTS paid_by_employee_name text;
ALTER TABLE finance_movements
    ADD COLUMN IF NOT EXISTS created_by text;

CREATE INDEX IF NOT EXISTS idx_finance_movements_paid_by_employee
    ON finance_movements(paid_by_employee_id, movement_date DESC);

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
    CONSTRAINT finance_account_direction_chk CHECK (
        direction IN (
            'artist_owes_indyana',
            'indyana_owes_artist',
            'third_party_owes_indyana',
            'indyana_owes_third_party'
        )
    ),
    CONSTRAINT finance_account_status_chk CHECK (
        status IN ('open', 'partial', 'settled', 'void', 'observed')
    )
);

ALTER TABLE finance_account_entries
    ADD COLUMN IF NOT EXISTS counterparty_employee_id bigint REFERENCES employees(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_finance_account_entries_counterparty
    ON finance_account_entries(counterparty, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_finance_account_entries_employee
    ON finance_account_entries(counterparty_employee_id, entry_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_account_employee_reimbursement_origin
    ON finance_account_entries(origin_type, origin_id)
    WHERE origin_type = 'finance_employee_reimbursement';

UPDATE finance_account_entries fae
SET counterparty_employee_id = e.id
FROM employees e
WHERE fae.origin_type = 'finance_employee_reimbursement'
  AND fae.counterparty_employee_id IS NULL
  AND fae.counterparty = e.display_name;

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

CREATE INDEX IF NOT EXISTS idx_finance_account_applications_entry
    ON finance_account_applications(account_entry_id);
CREATE INDEX IF NOT EXISTS idx_finance_account_applications_movement
    ON finance_account_applications(payment_movement_id);

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
    CONSTRAINT finance_documents_type_chk CHECK (
        document_type IN ('show_deposit_receipt', 'payment_order', 'collection_receipt')
    ),
    CONSTRAINT finance_documents_currency_chk CHECK (currency IN ('ARS', 'USD')),
    CONSTRAINT finance_documents_vat_mode_chk CHECK (
        vat_mode IN ('no_aplica', 'mas_iva', 'iva_incluido')
    ),
    CONSTRAINT finance_documents_status_chk CHECK (
        status IN ('borrador', 'emitido', 'anulado', 'aplicado')
    )
);

ALTER TABLE finance_documents
    ALTER COLUMN document_number
    SET DEFAULT nextval('finance_documents_document_number_seq');

SELECT setval(
    'finance_documents_document_number_seq',
    GREATEST(
        1,
        COALESCE((SELECT MAX(document_number) FROM finance_documents), 0),
        (SELECT last_value FROM finance_documents_document_number_seq)
    ),
    COALESCE((SELECT MAX(document_number) FROM finance_documents), 0) > 0
        OR (SELECT is_called FROM finance_documents_document_number_seq)
);

CREATE INDEX IF NOT EXISTS idx_finance_documents_date
    ON finance_documents(document_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_finance_documents_show_date
    ON finance_documents(show_date);

INSERT INTO schema_migrations(version, notes)
VALUES (
    '004_finance_documents_and_employee_accounts',
    'Cloud SQL structures for financial documents, employee reimbursements and account applications.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
