-- Agenda operativa de Booking.
-- Cloud SQL/Postgres es la unica base viva; no existe implementacion SQLite paralela.

BEGIN;

CREATE TABLE IF NOT EXISTS booking_events (
    id bigserial PRIMARY KEY,
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
    duplicate_override boolean NOT NULL DEFAULT false,
    duplicate_override_notes text,
    notes text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT booking_events_mode_chk CHECK (booking_mode IN ('individual', 'shared')),
    CONSTRAINT booking_events_commercial_chk CHECK (commercial_status IN ('confirmado', 'cancelado')),
    CONSTRAINT booking_events_operational_chk CHECK (operational_status IN ('programado', 'realizado')),
    CONSTRAINT booking_events_deposit_chk CHECK (deposit_status IN ('no_informada', 'sin_sena', 'sena_parcial', 'sena_recibida')),
    CONSTRAINT booking_events_settlement_chk CHECK (settlement_status IN ('no_iniciada', 'pendiente', 'rendida', 'observada', 'cerrada')),
    CONSTRAINT booking_events_currency_chk CHECK (currency IN ('ARS', 'USD')),
    CONSTRAINT booking_events_cachet_chk CHECK (contracted_cachet_amount >= 0),
    CONSTRAINT booking_events_fx_chk CHECK (fx_rate IS NULL OR fx_rate > 0),
    CONSTRAINT booking_events_override_note_chk CHECK (NOT duplicate_override OR duplicate_override_notes IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_booking_events_date ON booking_events(event_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_booking_events_status ON booking_events(commercial_status, operational_status, settlement_status);
CREATE INDEX IF NOT EXISTS idx_booking_events_venue_city ON booking_events(lower(venue), lower(COALESCE(city, '')));

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

ALTER TABLE booking_shows
    ADD COLUMN IF NOT EXISTS booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_shows_booking_event
    ON booking_shows(booking_event_id)
    WHERE booking_event_id IS NOT NULL;

ALTER TABLE booking_composite_events
    ADD COLUMN IF NOT EXISTS booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_composite_events_booking_event
    ON booking_composite_events(booking_event_id)
    WHERE booking_event_id IS NOT NULL;

ALTER TABLE caserio_events
    ADD COLUMN IF NOT EXISTS booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_caserio_events_booking_event
    ON caserio_events(booking_event_id)
    WHERE booking_event_id IS NOT NULL;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '005_booking_agenda_core',
    'Creates the canonical Booking agenda, ordered event artists, deposits, and one-to-one links to individual/shared settlements.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
