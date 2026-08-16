-- Tipos operativos y trazabilidad de fuentes para la Agenda canonica.
-- No crea una agenda paralela ni genera hechos financieros.

BEGIN;

ALTER TABLE booking_events
    ADD COLUMN IF NOT EXISTS event_type text NOT NULL DEFAULT 'show',
    ADD COLUMN IF NOT EXISTS group_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS group_position integer;

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_event_type_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_event_type_chk
    CHECK (event_type IN ('show', 'show_group', 'availability_block', 'logistics', 'prospect'));

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_commercial_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_commercial_chk
    CHECK (commercial_status IN ('confirmado', 'cancelado', 'prospecto', 'no_aplica'));

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_operational_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_operational_chk
    CHECK (operational_status IN ('programado', 'realizado', 'bloqueado', 'informativo'));

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_settlement_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_settlement_chk
    CHECK (settlement_status IN ('no_iniciada', 'pendiente', 'rendida', 'observada', 'cerrada', 'no_aplica'));

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_group_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_group_chk
    CHECK (
        (group_event_id IS NULL AND group_position IS NULL)
        OR (event_type = 'show' AND group_event_id IS NOT NULL AND group_position > 0)
    );

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_non_show_settlement_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_non_show_settlement_chk
    CHECK (event_type = 'show' OR settlement_status = 'no_aplica');

CREATE INDEX IF NOT EXISTS idx_booking_events_type_date
    ON booking_events(event_type, event_date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_booking_events_group
    ON booking_events(group_event_id, group_position)
    WHERE group_event_id IS NOT NULL;

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

INSERT INTO schema_migrations(version, notes)
VALUES (
    '007_booking_agenda_event_types',
    'Extends canonical Booking events with non-financial agenda types, show groups, and idempotent source links.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
