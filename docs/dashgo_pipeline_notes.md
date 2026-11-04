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

## Evidencia para DSP y monetizacion

La clasificacion usa `Store`, `Product Type` y `Use Type`. Para Spotify estan
validados por negocio:

- `P`: Premium, plan individual.
- `FAM6`: Premium, plan familiar.
- `DUO`: Premium, plan duo.
- `A`: Ads.
- `PDS`: significado pendiente; debe permanecer `Unknown`.

Individual, familiar y duo son evidencia raw, pero el resumen visible los
agrupa bajo monetizacion `Premium`; no existe una columna `Plan`. Los codigos
promocionales explicitamente identificables se clasifican como `Trial / Promo`.

YouTube distingue Store Premium, Ads, Shorts, Audio Tier y ajustes. `Use Type`
permite separar UGC de partner-provided cuando viene informado. No se debe
inventar Art Track o video oficial si la fila no lo demuestra.

UGC se presenta como `UGC / Content ID`; partner-provided como
`Audio Library / Partner Provided`. El contrato completo esta en
`docs/store_dsp_taxonomy_policy.md`.

## Correccion de admision de pies, 2026-11-04

`scripts/lib/dashgo_row_classes.py` reconoce ventas, controles y separadores
antes de validar Payable. Verifica la correspondencia de cada registro CSV con
la lectura y la estructura fisica del pie: cinco controles de trece campos,
sus etiquetas y secuencia, y tres registros separadores. Un pie incompleto o
alterado se rechaza; una venta sin importe sigue siendo una venta invalida.

La validacion monetaria se aplica solo a ventas. La salida standardized conserva
todas las filas y celdas originales, incluidos controles y separadores. No se
cambian formulas, identidades, contratos, asociados, clasificacion ni reportes.
Esta entrega publica codigo; no reconstruye ni reemplaza datos historicos.

La guarda comun agregada el 2026-10-30 validaba tambien los pies como ventas y
rechazaba los 35 originales. La prueba aislada de la correccion conserva
499.977 ventas, USD 28.212,27238360, 50.739.925 unidades, 175 controles y 105
separadores. Los nueve auxiliares Mechanical Royalty historicos incompletos
siguen fuera del alcance; su recuperacion al releer ya existe en el lector
publicado desde la preservacion lexical de noviembre, no en esta correccion.

Regresion permanente: `scripts/qa/qa_dashgo_row_classes.py`, incluida en
`cloudbuild.yaml`. Evidencia aislada inmutable:
`C:/royalties_pipeline/tmp/dashgo_footer_trial_20261104/evidence`.
Evidencia de publicacion y comprobaciones antes/despues:
`C:/royalties_pipeline/staging/catalogo_lectura/20261104_dashgo_footer_release`.
