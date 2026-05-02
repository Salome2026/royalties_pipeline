# FUGA pipeline notes

## Objetivo

Replicar exactamente la logica del pipeline viejo de FUGA, pero guardando el detalle completo para analisis futuro por tema, ISRC, DSP, territorio, tipo de venta y UGC/catalogo.

## Inputs

- Carpeta: `C:\royalties_pipeline\input_raw\fuga`
- Archivos regulares: CSV FUGA `royalty_product_and_asset`
- Correcciones: archivos con `CorrectionStatementRun`

## Scripts principales

- `scripts\ingest_fuga_incremental.py`: pipeline viejo hacia `warehouse\detail\royalties_detail.parquet`
- `scripts\ingest_fuga_corrections.py`: agrega correcciones al pipeline viejo
- `scripts\ingest_standardized_fuga.py`: pipeline nuevo hacia `warehouse\marts\standardized_raw_fuga.parquet`
- `scripts\build_song_level_fuga.py`: mart agregado por tema
- `scripts\audit_song_level_fuga.py`: auditoria del song-level
- `scripts\validate_standardized_fuga.py`: validacion contra detail viejo

## Reglas de monto

- Columna base: `Reported Royalty`
- Moneda real: EUR
- `net_amount` y `net_amount_eur`: `Reported Royalty`
- `amount_usd` y `net_amount_usd`: `Reported Royalty * FX EUR/USD`
- FX: se usa `scripts\lib\fx.py`, cacheado en `warehouse\registry\exchange_rates.parquet`

## Reglas de fechas

- `transaction_month`: sale de `Sale Start date`, formato `YYYY-MM`
- `statement_period`: se deriva del archivo/corrida segun la logica del ingest

## Reglas de artista/tema

- `artist_statement_style`: replica la logica del pipeline viejo.
- Principal: `Product Artist`
- Fallback: `Product Title`
- Para song-level se guardan tambien:
  - `asset_artist_statement`
  - `asset_title_statement`
  - `asset_isrc`
  - `product_artist_statement`
  - `product_title_statement`

## Correcciones

FUGA puede traer archivos de correccion. Esos archivos no deben ignorarse. En el pipeline nuevo se incorporan respetando la misma base de monto y metadata que los regulares.

## Outputs

- `warehouse\marts\standardized_raw_fuga.parquet`
- `warehouse\marts\song_level_fuga.parquet`

## Validacion esperada

Comparar contra `royalties_detail.parquet` por:

- `source`
- `account`
- `artist_statement_style`
- `transaction_month`

Resultado esperado:

- `standardized_raw_fuga.amount_usd` debe cerrar contra `royalties_detail.net_amount_usd`
- El song-level debe cerrar contra standardized

## Nota para reporte por statement

El reporte viejo aplica un factor a FUGA:

```text
net_amount_usd * 0.977832
```

El reporte nuevo desde marts mantiene ese ajuste para replicar el reporte por statement.
