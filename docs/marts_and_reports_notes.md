# Marts and reports notes

## Pipeline nuevo

El pipeline nuevo sigue esta forma:

```text
input_raw
  -> standardized_raw_*
  -> song_level_*
  -> consolidated marts / reports
```

## Standardized marts

Archivos actuales:

- `warehouse\marts\standardized_raw_dashgo.parquet`
- `warehouse\marts\standardized_raw_fuga.parquet`
- `warehouse\marts\standardized_raw_onerpm.parquet`
- `warehouse\marts\standardized_raw_orchard.parquet`
- `warehouse\marts\standardized_raw_soundon.parquet`

Objetivo:

- Conservar columnas originales.
- Agregar columnas normalizadas comunes.
- Evitar volver a leer CSV/Excel pesados.
- Permitir validaciones contra el pipeline viejo.

Columnas comunes esperadas:

- `source`
- `account`
- `statement_period`
- `transaction_month`
- `artist_statement_style`
- `amount_usd`
- `net_amount`
- `net_amount_usd`
- `statement_file_name`
- `statement_file_hash`
- `ingested_at`

## Song-level marts

Archivos actuales:

- `warehouse\marts\song_level_dashgo.parquet`
- `warehouse\marts\song_level_fuga.parquet`
- `warehouse\marts\song_level_onerpm.parquet`
- `warehouse\marts\song_level_orchard.parquet`
- `warehouse\marts\song_level_soundon.parquet`

Objetivo:

- Agregar por tema/ISRC/artista/mes.
- Mantener totales cerrados contra standardized.
- Servir como base para reportes por catalogo, tema, artista, splits y tendencias.

## Consolidated marts

Scripts:

- `scripts\build_consolidated_marts.py`
- `scripts\audit_consolidated_marts.py`
- `scripts\audit_marts_general.py`

Outputs:

- `warehouse\marts\standardized_raw_all_sources.parquet`
- `warehouse\marts\song_level_all_sources.parquet`

El consolidado incluye `mart_source_file` para saber de que mart individual vino cada fila.

## Reporte por statement desde marts

Script:

- `scripts\build_statement_report_from_mart.py`

Output:

- `reports\reporte_ingresos_digitales_por_mes_de_statement_marts.xlsx`

Replica el formato del reporte viejo:

- Hoja `TOTAL`
- Hojas por `source/account`
- Artistas por fila
- Statement periods por columna
- TOTAL USD por hoja

La documentacion completa de los criterios viejo/nuevo esta en:

- `docs\statement_report_notes.md`

## Diferencias conocidas contra reporte viejo

### ONErpm MAWZ

El reporte nuevo incluye `mawzrecords 2024-02 Masters`, recuperado por normalizacion `RUR -> RUB`.

### ONErpm Henry

El reporte nuevo usa conversion FX; el viejo usaba `net_amount` directo.

## SoundOn Summary

`Summary` no se carga al standardized principal. Solo se usa como control en `audit_soundon.py`.

## Auditorias recomendadas

Despues de regenerar marts, correr:

```powershell
python C:\royalties_pipeline\scripts\audit_marts_general.py
python C:\royalties_pipeline\scripts\audit_consolidated_marts.py
```

Para SoundOn:

```powershell
python C:\royalties_pipeline\scripts\audit_soundon.py
```
