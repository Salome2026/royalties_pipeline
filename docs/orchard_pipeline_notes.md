# Orchard / Altafonte pipeline notes

## Objetivo

Unificar Orchard moderno y el historico Altafonte dentro de la fuente `orchard`, sin perder la distincion entre datos granulares modernos y legacy limitado.

## Inputs

Orchard moderno:

- Carpeta: `C:\royalties_pipeline\input_raw\orchard`
- Archivos: CSV `revenue_details`

Altafonte legacy:

- Archivo: `C:\royalties_pipeline\input_raw\altafonte\altafonte.xlsx`

## Scripts principales

- `scripts\ingest_orchard_incremental.py`: pipeline viejo de Orchard moderno
- `scripts\ingest_orchard_altafonte_legacy.py`: pipeline viejo de Altafonte legacy
- `scripts\ingest_standardized_orchard.py`: pipeline nuevo unificado
- `scripts\build_song_level_orchard.py`: mart agregado por tema/artista
- `scripts\audit_song_level_orchard.py`: auditoria del song-level

## Reglas de monto

Orchard moderno:

- Columna base: `NET SHARE ACCOUNT CURRENCY`
- `amount_usd`, `net_amount`, `net_amount_usd`: derivan de esa columna

Altafonte legacy:

- El Excel tiene formato historico por artista/mes.
- Se transforma a filas con:
  - `artist_statement_style`
  - `transaction_month`
  - `statement_period`
  - `amount_usd`
  - `net_amount`
  - `net_amount_usd`

## Reglas de fechas

Orchard moderno:

- `transaction_month`: `TRANSACTION DATE` en formato `YYYY-MM`
- `statement_period`: `STATEMENT PERIOD`, parseado desde texto tipo `November 2025`

Altafonte legacy:

- Los meses se detectan desde los encabezados de columnas del Excel.

## Reglas de artista/tema

Orchard moderno:

- `artist_statement_style`: `TRACK ARTIST` si existe; fallback a `PRODUCT ARTIST`
- `track_statement_style`: `TRACK`
- `asset_isrc`: `ISRC`
- `product_upc`: `DISPLAY UPC`

Altafonte legacy:

- Solo tiene granularidad por artista/mes.
- No inventa track ni ISRC.
- `content_type` queda como `legacy` en song-level.

## Outputs

- `warehouse\marts\standardized_raw_orchard.parquet`
- `warehouse\marts\song_level_orchard.parquet`

## Validacion esperada

El standardized de Orchard debe cerrar contra `royalties_detail.parquet` incluyendo Altafonte:

```text
Orchard moderno + Altafonte legacy = total source orchard
```

El song-level debe cerrar contra standardized.

## Evidencia para DSP y monetizacion

Orchard moderno usa `STORE`, `SERVICE DETAIL`, `TRANSACTION TYPE`,
`TRANSACTION SUBTYPE` y `ROYALTY TYPE`. Permite separar suscripcion/ads y, para
YouTube, Art Tracks & Music Videos, Content ID, partner-provided, UGC y Shorts.

Altafonte legacy no tiene esa granularidad. Sus filas deben conservar
`classification_status = unknown`; no se completa Store por inferencia.
