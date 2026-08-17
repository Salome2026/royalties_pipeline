BEGIN;

INSERT INTO app_modules (module_key, label, active, created_at)
VALUES ('booking_agenda', 'Agenda Booking', TRUE, CURRENT_TIMESTAMP)
ON CONFLICT (module_key) DO UPDATE SET
    label = EXCLUDED.label,
    active = EXCLUDED.active;

INSERT INTO module_permissions (
    employee_id,
    module_key,
    can_access,
    can_create,
    can_view_history,
    can_edit,
    can_approve,
    scope_json,
    notes,
    created_at,
    updated_at
)
SELECT
    employee.id,
    'booking_agenda',
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    FALSE,
    '[{"scope_type":"all","scope_ref":"*"}]'::jsonb,
    'Acceso inicial de lectura a la Agenda Booking.',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM employees employee
WHERE employee.active = TRUE
ON CONFLICT (employee_id, module_key) DO NOTHING;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '008_booking_agenda_permissions',
    'Adds Agenda Booking as an independent permission module and grants view-only access to active employees.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
