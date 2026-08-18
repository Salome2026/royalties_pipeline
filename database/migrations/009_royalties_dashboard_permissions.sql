-- Registra Dashboard Regalias en el catalogo canonico de modulos.
-- Los permisos de empleados referencian app_modules por clave foranea, por lo que
-- toda tarjeta configurable debe existir aqui antes de poder guardarse desde el ABM.

BEGIN;

INSERT INTO app_modules (module_key, label, active, created_at)
VALUES ('royalties_dashboard', 'Dashboard Regalias', TRUE, CURRENT_TIMESTAMP)
ON CONFLICT (module_key) DO UPDATE SET
    label = EXCLUDED.label,
    active = EXCLUDED.active;

INSERT INTO schema_migrations(version, notes)
VALUES (
    '009_royalties_dashboard_permissions',
    'Registers Dashboard Regalias in the canonical permission module catalog.'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
