-- Booking individual y compartido comparten una unica superficie de acceso.
-- Las claves de permiso permanecen separadas para conservar el alcance existente.

BEGIN;

UPDATE app_modules
SET label = 'Booking compartido'
WHERE module_key = 'composite_booking';

INSERT INTO schema_migrations(version, notes)
VALUES (
    '003_unified_booking_workspace',
    'Renames the composite_booking module label for the unified Booking workspace; permission keys and assignments are unchanged.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
