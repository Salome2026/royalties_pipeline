# Royalties pipeline docs

## Fuente por fuente

- [FUGA](fuga_pipeline_notes.md)
- [DashGo](dashgo_pipeline_notes.md)
- [Orchard / Altafonte](orchard_pipeline_notes.md)
- [ONErpm](onerpm_pipeline_notes.md)
- [SoundOn](soundon_pipeline_notes.md)

## Marts y reportes

- [Marts and reports](marts_and_reports_notes.md)
- [Reporte por statement](statement_report_notes.md)
- [Catalogo general core](catalog_core_notes.md)
- [Normalizacion de identidad](identity_normalization_policy.md)
- [Configurador distribuidoras fase 1](distributor_catalog_configurator_phase1.md)
- [Configurador distribuidoras fase 2](distributor_catalog_configurator_phase2_design.md)
- [Configurador distribuidoras fase 3](distributor_configurator_phase3_validation.md)
- [Configurador distribuidoras fase 4](distributor_configurator_phase4_policy_integration.md)
- [Statement period policy](statement_period_policy.md)
- [Web users admin](web_users_admin.md)
- [Cloud environment policy](cloud_environment_policy.md)
- [Cloud operational schema v1](cloud_operational_schema_v1.md)
- [Cloud migration progress 2026-06-25](cloud_migration_progress_20260625.md)
- [Secure operational DB connection](secure_operational_db_connection.md)
- [Control de distribuidoras](source_monitor_notes.md)
- [UI period control policy](ui_period_control_policy.md)

## Booking

- [Modelo financiero operativo VPO v2 - rector vigente](finance_operational_model_v2.md)
- [Finanzas VPO - maqueta de carga dinamica](finanzas_carga_dinamica_maqueta.md)
- [Finanzas VPO - soporte visual/tecnico](finance_business_master.md)
- [Booking rules master](booking_rules_master.md)
- [Booking validation matrix](booking_validation_matrix.md)
- [Booking unified validation matrix](booking_unified_validation_matrix.md)
- [Booking go-live workflow](booking_go_live_workflow.md)
- [Gastos historicos de artistas y proyectos](artist_expense_staging_plan.md)
- [Finanzas de artista y ledger](artist_finance_ledger_model.md)
- [Booking system design](booking_system_design.md)
- [Booking data model](booking_data_model.md)
- [Booking raw profile](booking_raw_profile.md)
- [Booking operational rules](booking_operational_rules.md)

Antes de modificar Booking, Finanzas Artista, Movimientos Financieros o cualquier
flujo que afecte caja/cuenta corriente de shows, leer primero
`finance_operational_model_v2.md`, `booking_rules_master.md` y validar el cambio
contra `booking_unified_validation_matrix.md`.

## Arquitectura general

El proyecto operativo de regalias trabaja sobre el pipeline nuevo:

- Escribe en `warehouse\marts\standardized_raw_*.parquet`
- Construye `warehouse\marts\song_level_*.parquet`
- Construye marts consolidados para reportes nuevos
- Publica a cloud solo los marts validados

El pipeline viejo quedo archivado como referencia historica en `_cleanup_archive\20260517_pipeline_viejo\scripts`. No debe usarse para decidir pendientes, publicar datos ni alimentar la web.

## Reglas importantes

- No cargar summaries como royalties si duplican detalle.
- No inventar artista/tema cuando la fuente no lo trae.
- Conservar columnas originales siempre que sea razonable.
- Usar `scripts\lib\fx.py` para conversion FX.
- Validar contra marts nuevos y contra reportes exportados cuando exista comparable.
- No pisar identificadores originales: si una fila nueva viene sin ISRC pero con
  UPC, la resolucion a ISRC pertenece al catalogo/reportes y debe seguir
  `identity_normalization_policy.md`.
