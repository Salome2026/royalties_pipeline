# Royalties pipeline docs

## Fuente por fuente

- [FUGA](fuga_pipeline_notes.md)
- [DashGo](dashgo_pipeline_notes.md)
- [Orchard / Altafonte](orchard_pipeline_notes.md)
- [ONErpm](onerpm_pipeline_notes.md)
- [SoundOn](soundon_pipeline_notes.md)

## Marts y reportes

- [Marts and reports](marts_and_reports_notes.md)
- [Statement period policy](statement_period_policy.md)
- [Web users admin](web_users_admin.md)
- [Cloud environment policy](cloud_environment_policy.md)

## Booking

- [Booking rules master](booking_rules_master.md)
- [Booking validation matrix](booking_validation_matrix.md)
- [Booking go-live workflow](booking_go_live_workflow.md)
- [Booking system design](booking_system_design.md)
- [Booking data model](booking_data_model.md)
- [Booking raw profile](booking_raw_profile.md)
- [Booking operational rules](booking_operational_rules.md)

Antes de modificar la pantalla nueva de booking, backend de booking o guardado de shows, leer primero `booking_rules_master.md` y validar el cambio contra `booking_validation_matrix.md`.

## Arquitectura general

El proyecto tiene dos capas:

1. Pipeline viejo
   - Escribe en `warehouse\detail\royalties_detail.parquet`
   - Usa `warehouse\registry\processed_files.parquet`
   - Alimenta `build_ingresos_por_statement.py`

2. Pipeline nuevo
   - Escribe en `warehouse\marts\standardized_raw_*.parquet`
   - Construye `warehouse\marts\song_level_*.parquet`
   - Construye marts consolidados para reportes nuevos

La meta es que el pipeline nuevo pueda reemplazar gradualmente al viejo, pero manteniendo el viejo como control historico hasta que todos los reportes importantes esten replicados y validados.

## Reglas importantes

- No cargar summaries como royalties si duplican detalle.
- No inventar artista/tema cuando la fuente no lo trae.
- Conservar columnas originales siempre que sea razonable.
- Usar `scripts\lib\fx.py` para conversion FX.
- Validar contra el pipeline viejo cuando exista comparable.
