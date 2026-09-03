-- Evidence-based indexes for the operational PostgreSQL access layer.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_booking_event_source_event
    ON booking_event_source_links(event_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_booking_show_expenses_show
    ON booking_show_expenses(show_id, id);

CREATE INDEX IF NOT EXISTS idx_booking_movements_show
    ON booking_movements(show_id, id);

INSERT INTO schema_migrations(version, notes)
VALUES (
    '013_postgres_access_indexes',
    'Adds measured lookup indexes for Agenda source links and Booking show details.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
