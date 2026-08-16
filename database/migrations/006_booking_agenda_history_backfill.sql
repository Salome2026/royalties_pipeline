-- Canonical Booking agenda backfill.
-- Creates only agenda headers and links. Existing settlements and financial facts are untouched.

BEGIN;

ALTER TABLE booking_events DROP CONSTRAINT IF EXISTS booking_events_deposit_chk;
ALTER TABLE booking_events
    ADD CONSTRAINT booking_events_deposit_chk
    CHECK (deposit_status IN ('no_informada', 'sin_sena', 'sena_parcial', 'sena_recibida'));

ALTER TABLE caserio_events
    ADD COLUMN IF NOT EXISTS booking_event_id bigint REFERENCES booking_events(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_caserio_events_booking_event
    ON caserio_events(booking_event_id)
    WHERE booking_event_id IS NOT NULL;

DO $$
DECLARE
    missing_count bigint;
BEGIN
    SELECT count(*) INTO missing_count
    FROM booking_shows s
    LEFT JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(s.artist))
    WHERE s.origin_type IS NULL
      AND s.booking_event_id IS NULL
      AND (s.show_date IS NULL OR NULLIF(trim(s.venue), '') IS NULL OR a.id IS NULL);
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Agenda backfill blocked: % independent shows lack date, venue, or artist mapping', missing_count;
    END IF;

    SELECT count(*) INTO missing_count
    FROM booking_shows s
    LEFT JOIN booking_composite_event_lines l ON l.booking_show_id = s.id
    WHERE s.origin_type = 'booking_composite' AND l.id IS NULL;
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Agenda backfill blocked: % composite child shows are orphaned', missing_count;
    END IF;

    SELECT count(*) INTO missing_count
    FROM booking_shows s
    LEFT JOIN caserio_event_lines l ON l.booking_show_id = s.id
    WHERE s.origin_type = 'caserio' AND l.id IS NULL;
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Agenda backfill blocked: % Caserio child shows are orphaned', missing_count;
    END IF;

    SELECT count(*) INTO missing_count
    FROM booking_composite_events e
    WHERE e.booking_event_id IS NULL
      AND (e.event_date IS NULL OR NULLIF(trim(e.venue), '') IS NULL OR NOT EXISTS (
          SELECT 1
          FROM booking_composite_event_lines l
          JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(l.artist))
          WHERE l.event_id = e.id AND l.line_type = 'artista_vpo'
      ));
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Agenda backfill blocked: % composite mothers lack date, venue, or VPO artists', missing_count;
    END IF;

    SELECT count(*) INTO missing_count
    FROM caserio_events e
    WHERE e.booking_event_id IS NULL
      AND (e.event_date IS NULL OR NULLIF(trim(e.venue), '') IS NULL OR NOT EXISTS (
          SELECT 1
          FROM caserio_event_lines l
          JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(l.artist))
          WHERE l.event_id = e.id AND l.line_type = 'artista_vpo'
      ));
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'Agenda backfill blocked: % Caserio mothers lack date, venue, or VPO artists', missing_count;
    END IF;
END $$;

DO $$
DECLARE
    source_row record;
    agenda_id bigint;
BEGIN
    FOR source_row IN
        SELECT s.*, a.id AS artist_id, a.stage_name AS canonical_artist
        FROM booking_shows s
        JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(s.artist))
        WHERE s.origin_type IS NULL AND s.booking_event_id IS NULL
        ORDER BY s.show_date, s.id
    LOOP
        INSERT INTO booking_events (
            event_date, venue, city, booking_mode,
            commercial_status, operational_status, deposit_status, settlement_status,
            contracted_cachet_amount, currency, fx_rate, tour_manager, seller,
            notes, created_by, created_at, updated_at
        ) VALUES (
            source_row.show_date,
            source_row.venue,
            source_row.city,
            'individual',
            CASE WHEN source_row.status = 'cancelado' THEN 'cancelado' ELSE 'confirmado' END,
            CASE
                WHEN source_row.status = 'cancelado' AND source_row.show_date > current_date THEN 'programado'
                WHEN source_row.show_date <= current_date OR source_row.status IN ('realizado', 'rendido', 'aprobado', 'no_cobrado', 'promocional', 'ajuste') THEN 'realizado'
                ELSE 'programado'
            END,
            'no_informada',
            CASE
                WHEN source_row.status = 'no_cobrado' THEN 'observada'
                WHEN source_row.settlement_status IN ('cerrado', 'cerrado_compensado', 'cerrado_con_pago_posterior', 'historico')
                     OR source_row.status = 'aprobado' THEN 'cerrada'
                ELSE 'pendiente'
            END,
            COALESCE(source_row.contracted_cachet_amount, source_row.cachet_amount, 0),
            COALESCE(NULLIF(source_row.currency, ''), 'ARS'),
            source_row.fx_rate,
            source_row.tour_manager,
            source_row.seller,
            source_row.notes,
            'system_agenda_backfill',
            COALESCE(source_row.created_at, now()),
            COALESCE(source_row.updated_at, source_row.created_at, now())
        ) RETURNING id INTO agenda_id;

        INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position, created_at)
        VALUES (agenda_id, source_row.artist_id, source_row.canonical_artist, 1, COALESCE(source_row.created_at, now()));

        UPDATE booking_shows SET booking_event_id = agenda_id WHERE id = source_row.id;
    END LOOP;
END $$;

DO $$
DECLARE
    source_row record;
    artist_row record;
    agenda_id bigint;
BEGIN
    FOR source_row IN
        SELECT *
        FROM booking_composite_events
        WHERE booking_event_id IS NULL
        ORDER BY event_date, id
    LOOP
        INSERT INTO booking_events (
            event_date, venue, city, booking_mode,
            commercial_status, operational_status, deposit_status, settlement_status,
            contracted_cachet_amount, currency, fx_rate, tour_manager,
            notes, created_by, created_at, updated_at
        ) VALUES (
            source_row.event_date,
            source_row.venue,
            source_row.city,
            'shared',
            'confirmado',
            CASE WHEN source_row.event_date <= current_date OR source_row.status IN ('rendido', 'observado', 'cerrado') THEN 'realizado' ELSE 'programado' END,
            'no_informada',
            CASE source_row.status
                WHEN 'cerrado' THEN 'cerrada'
                WHEN 'rendido' THEN 'rendida'
                WHEN 'observado' THEN 'observada'
                ELSE 'pendiente'
            END,
            COALESCE(source_row.gross_amount, 0),
            COALESCE(NULLIF(source_row.currency, ''), 'ARS'),
            source_row.fx_rate,
            source_row.responsible,
            source_row.notes,
            'system_agenda_backfill',
            COALESCE(source_row.created_at, now()),
            COALESCE(source_row.updated_at, source_row.created_at, now())
        ) RETURNING id INTO agenda_id;

        FOR artist_row IN
            SELECT a.id AS artist_id, a.stage_name,
                   row_number() OVER (ORDER BY min(l.id))::integer AS position
            FROM booking_composite_event_lines l
            JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(l.artist))
            WHERE l.event_id = source_row.id AND l.line_type = 'artista_vpo'
            GROUP BY a.id, a.stage_name
            ORDER BY min(l.id)
        LOOP
            INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position, created_at)
            VALUES (agenda_id, artist_row.artist_id, artist_row.stage_name, artist_row.position, COALESCE(source_row.created_at, now()));
        END LOOP;

        UPDATE booking_composite_events SET booking_event_id = agenda_id WHERE id = source_row.id;
    END LOOP;
END $$;

DO $$
DECLARE
    source_row record;
    artist_row record;
    agenda_id bigint;
BEGIN
    FOR source_row IN
        SELECT *
        FROM caserio_events
        WHERE booking_event_id IS NULL
        ORDER BY event_date, id
    LOOP
        INSERT INTO booking_events (
            event_date, venue, city, booking_mode,
            commercial_status, operational_status, deposit_status, settlement_status,
            contracted_cachet_amount, currency, fx_rate, tour_manager,
            notes, created_by, created_at, updated_at
        ) VALUES (
            source_row.event_date,
            source_row.venue,
            source_row.city,
            'shared',
            'confirmado',
            CASE WHEN source_row.event_date <= current_date OR source_row.status IN ('rendido', 'observado', 'cerrado') THEN 'realizado' ELSE 'programado' END,
            'no_informada',
            CASE source_row.status
                WHEN 'cerrado' THEN 'cerrada'
                WHEN 'rendido' THEN 'rendida'
                WHEN 'observado' THEN 'observada'
                ELSE 'pendiente'
            END,
            COALESCE(source_row.gross_amount, 0),
            COALESCE(NULLIF(source_row.currency, ''), 'ARS'),
            source_row.fx_rate,
            source_row.responsible,
            source_row.notes,
            'system_agenda_backfill',
            COALESCE(source_row.created_at, now()),
            COALESCE(source_row.updated_at, source_row.created_at, now())
        ) RETURNING id INTO agenda_id;

        FOR artist_row IN
            SELECT a.id AS artist_id, a.stage_name,
                   row_number() OVER (ORDER BY min(l.id))::integer AS position
            FROM caserio_event_lines l
            JOIN artists a ON lower(trim(a.stage_name)) = lower(trim(l.artist))
            WHERE l.event_id = source_row.id AND l.line_type = 'artista_vpo'
            GROUP BY a.id, a.stage_name
            ORDER BY min(l.id)
        LOOP
            INSERT INTO booking_event_artists (event_id, artist_id, artist_name, position, created_at)
            VALUES (agenda_id, artist_row.artist_id, artist_row.stage_name, artist_row.position, COALESCE(source_row.created_at, now()));
        END LOOP;

        UPDATE caserio_events SET booking_event_id = agenda_id WHERE id = source_row.id;
    END LOOP;
END $$;

INSERT INTO app_audit_log (
    actor_username, module_key, action, entity_table, entity_id, after_json, source, notes
)
VALUES (
    'system_agenda_backfill',
    'booking',
    'backfill',
    'booking_events',
    'historical_reconciliation',
    jsonb_build_object(
        'agenda_events', (SELECT count(*) FROM booking_events),
        'individual_links', (SELECT count(*) FROM booking_shows WHERE booking_event_id IS NOT NULL),
        'composite_links', (SELECT count(*) FROM booking_composite_events WHERE booking_event_id IS NOT NULL),
        'caserio_links', (SELECT count(*) FROM caserio_events WHERE booking_event_id IS NOT NULL)
    ),
    'migration',
    'Canonical agenda headers created without recalculating or rewriting settlements.'
);

INSERT INTO schema_migrations(version, notes)
VALUES (
    '006_booking_agenda_history_backfill',
    'Backfills canonical agenda headers for independent, composite, and Caserio Booking history.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
