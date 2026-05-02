# DashGo pipeline notes

## Objetivo

Replicar el pipeline viejo de DashGo y conservar todas las columnas utiles para reportes por artista, tema, ISRC, tienda, region y tipo de uso.

## Inputs

- Carpeta: `C:\royalties_pipeline\input_raw\dashgo`
- Archivos: CSV DashGo

## Scripts principales

- `scripts\ingest_dashgo_incremental.py`: pipeline viejo hacia `warehouse\detail\royalties_detail.parquet`
- `scripts\ingest_standardized_dashgo.py`: pipeline nuevo hacia `warehouse\marts\standardized_raw_dashgo.parquet`
- `scripts\build_song_level_dashgo.py`: mart agregado por tema
- `scripts\audit_song_level_dashgo.py`: auditoria del song-level

## Reglas de monto

- Columna base: `Payable`
- `amount_usd`, `net_amount`, `net_amount_usd`: se derivan de `Payable`
- No hay conversion FX en el standardized actual de DashGo porque el monto ya esta en la moneda usada para reporting USD.

## Reglas de fechas

- `transaction_month`: se deriva de `Transaction Date`, formato `YYYY-MM`
- `statement_period`: se deriva del nombre del archivo, con la misma logica del ingest viejo

## Reglas de artista/tema

- `artist_statement_style`: principalmente `Artist Name`
- Si `Artist Name` falta y `Track Title` indica asset auto generado, se usa `No Identificado`
- Si no, fallback a `Track Title`

Campos relevantes conservados:

- `track_statement_style`
- `artist_name_statement`
- `track_artist_statement`
- `asset_isrc`
- `product_upc`
- `store_name`
- `territory`
- `product_type`
- `use_type`
- `units`

## Outputs

- `warehouse\marts\standardized_raw_dashgo.parquet`
- `warehouse\marts\song_level_dashgo.parquet`

## Validacion esperada

El total de `song_level_dashgo.amount_usd` debe cerrar contra `standardized_raw_dashgo.amount_usd`.

Tambien debe cerrar contra el pipeline viejo en el reporte por statement.
