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
