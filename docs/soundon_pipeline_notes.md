# SoundOn pipeline notes

## Objetivo

Incorporar SoundOn al pipeline viejo y al pipeline nuevo, usando `My Royalty` como fuente granular principal.

## Inputs

- Carpeta: `C:\royalties_pipeline\input_raw\soundon`

Cada mes trae cuatro archivos:

- `My Royalty`
- `Share in`
- `Share out`
- `Summary`

## Decision importante sobre Summary

`Summary` es un resumen agregado por tienda. No se carga al standardized principal porque duplica el total de `My Royalty` y no trae granularidad de artista/tema/ISRC.

Se usa solo en `audit_soundon.py`, leyendo los CSV originales desde `input_raw`, para validar que `My Royalty` cierre contra el resumen mensual.

## Scripts principales

- `scripts\ingest_soundon_incremental.py`: pipeline viejo hacia `royalties_detail.parquet`
- `scripts\ingest_standardized_soundon.py`: pipeline nuevo hacia marts
- `scripts\build_song_level_soundon.py`: mart agregado por tema
- `scripts\audit_soundon.py`: auditoria contra Summary y song-level

## Reglas de monto

- Columna base: `Final Royalty`
- `amount_usd`, `net_amount`, `net_amount_usd`: derivan de `Final Royalty`
- Moneda actual: USD
- `fx_to_usd_rate`: 1.0

## Reglas de fechas

- `statement_period`: `Reporting Period`
- `transaction_month`: `Reporting Period`
- `sales_period`: `Sales Period`

## Reglas de artista/tema

- `artist_statement_style`: `Track Artists`
- `track_statement_style`: `Track Title`
- `asset_isrc`: `ISRC`
- `track_id`: `Track ID`
- `product_upc`: `UPC Code`
- `store_name`: `Store Name`
- `territory`: `Sales Region`

## Share in / Share out

Actualmente vienen vacios. El script esta preparado para leerlos si en el futuro traen filas, pero no hay impacto hoy.

## Outputs

- `warehouse\marts\standardized_raw_soundon.parquet`
- `warehouse\marts\song_level_soundon.parquet`

## Validacion esperada

- `My Royalty` debe cerrar contra `Summary` por `Reporting Period`.
- `song_level_soundon.amount_usd` debe cerrar contra `standardized_raw_soundon.amount_usd`.

## Evidencia para DSP y monetizacion

La clasificacion usa `Store Name`, `Sales Type`, `Sales Sub Type` y
`Royalty Type`. Spotify permite separar Premium, Ads y Trial. Individual,
Family, Duo, Student y Bundle se agrupan como `Premium` y no se muestran como
una columna `Plan`. `AD_SUPPORTED` se clasifica como `Ads`. SoundOn informa
YouTube como `YouTube Music / Content ID`: la monetizacion puede ser
explicita, pero Music y UGC no siempre se pueden separar. En esos casos el
origen queda `No informado`, sin inferencias. En TikTok/Meta, `UGC` se presenta
como `UGC / Content ID`; `PGC` o contenido provisto se presenta como
`Audio Library / Partner Provided`.

El contrato completo esta en `docs/store_dsp_taxonomy_policy.md`.
