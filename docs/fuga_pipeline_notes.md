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

## Product vs Asset

FUGA puede informar ingresos a nivel `Asset` o a nivel `Product`.

### Asset

Fila normal de tema/asset:

- `Asset/Product`: `Asset`
- suele traer `Asset ISRC`
- suele traer `Asset Title`
- suele traer `Asset Artist`
- las unidades vienen en `Asset Quantity`

### Product

Fila a nivel producto/release:

- `Asset/Product`: `Product`
- puede traer `Product UPC`
- puede traer `Product Title`
- puede traer `Product Artist`
- las unidades vienen en `Product Quantity`
- puede no traer `Asset ISRC`

Esto no debe corregirse dentro del ingest. El standardized debe conservarlo tal
cual vino.

Regla operativa:

- `asset_isrc` solo sale de `Asset ISRC`.
- `product_upc` sale de `Product UPC`.
- `asset_product_type` conserva `Asset/Product`.
- Si `Asset ISRC` viene vacio, no se inventa ISRC en standardized.
- La resolucion por UPC, si corresponde, pertenece a catalogo/reportes.

Caso testigo validado:

- `March2026StatementRun_INDYANARECORDSLLC-royalty_product_and_asset.csv`
- `Product UPC`: `198474357444`
- `Product Title`: `Perreo TL`
- `Product Artist`: `mamiyosoyelth and Lihueeel`
- `Asset/Product`: `Product`
- `Asset ISRC`: vacio
- `DSP`: `Amazon`
- `Sale Type`: `Download`
- `Product Quantity`: `1`

La fila se puede asociar en catalogo a `QZK6L2413497` porque ese UPC aparece con
un unico ISRC y la metadata externa confirma el par UPC/ISRC. Pero la fila raw y
standardized deben seguir mostrando que FUGA la reporto como producto.

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
- Si aparecen filas `Product` sin ISRC, revisar si el catalogo las resuelve por
  UPC unico. Esa revision no debe cambiar el total de `amount_usd`.

## Nota para reporte por statement

El reporte viejo aplica un factor a FUGA:

```text
net_amount_usd * 0.977832
```

El reporte nuevo desde marts mantiene ese ajuste para replicar el reporte por statement.

## Evidencia para DSP y monetizacion

FUGA usa `DSP`, `Sale Store Name`, `Sale Type` y `Sale User Type`. Es la fuente
mas completa para separar Premium/Ads y, en YouTube, Art Track/Music, Channel
Income, UGC y Manual Claim. La clasificacion es derivada: todos esos campos
originales permanecen disponibles para auditoria.

Family, Duo, Student y Bundle se agrupan como monetizacion `Premium`; no se
presenta una columna `Plan`. En plataformas sociales, `User generated content`
se clasifica como `UGC / Content ID` y `Partner-provided` como
`Audio Library / Partner Provided`; el nombre TikTok o Meta por si solo no
autoriza a clasificar todo como UGC.

El mapa completo es `docs/store_dsp_taxonomy_policy.md`.

## Artistas comunes de catalogo: FUGA-ARTISTS-1

Decision de Ruben del 2026-10-14: aplicar a lo publicado y a futuras ingestas
la union de artistas de pista (`Asset Artist`) y lanzamiento (`Product Artist`).
El contrato define los beneficiarios y porcentajes; esta lectura no los infiere.

Implementacion unica: `scripts/lib/fuga_catalog_artists.py`, llamada por
`build_catalog_master.py` despues de las correcciones manuales confirmadas.
Para cada ISRC recibido, se consideran las observaciones de contexto musical
con Product Reference numerico, excluyendo referencias de explotacion YT-A/YT-V.
No se buscan nombres por titulos ni se propagan artistas entre pistas de un UPC.

- Conservar todos los nombres observados, tambien de statements anteriores;
  un credito parcial posterior no borra participantes.
- Ordenar primero artistas de pista y despues los adicionales del lanzamiento.
  El orden no acredita derechos ni un principal unico.
- Usar la gramatica FUGA observada: lista con coma y `and` final, opcionalmente
  `featuring`; respetar comillas de nombres compuestos. Serializacion ambigua
  conserva literal y estado en evidencia, sin inventar artistas por otra columna.
- Deduplicar espacios y mayusculas; no quitar DJ ni crear aliases por parecido.
- Las dos referencias humanas ya confirmadas se limitan a su ISRC en
  `fuga_catalog_artist_references.json`: Kita/Federikita para ARDL12400060 y
  Nueva/Nueva Adoracion para ARDL12500040. Se conservan los literales nativos;
  no son equivalencias globales ni una lista de artistas admitidos.
- Guardar literales, columna, cuenta, statement, archivo/hash, UPC y referencias.
- No eliminar nombres que el catalogo global ya mostraba de otras fuentes.
  Las correcciones manuales aprobadas prevalecen; los originales siguen intactos.

El snapshot agrega `catalog_artists`, `catalog_artist_statement`,
`catalog_artist_evidence` y `catalog_artist_rule`. No reemplaza los campos
historicos de identidad ni los hechos economicos. Catalogo y Contratos proyectan
la lista comun para visualizacion y sugerencias; un contrato guardado se devuelve
sin cambiar participantes, porcentajes, vigencias, version, estado o asociados.
BigQuery conserva la misma lista/evidencia en `royalty_catalog` por release.

Esta adopcion no cambia el lector economico, FX, fechas de consumo/statement,
factor historico del reporte ni personalizacion vigente. Tampoco habilita
formatos complementarios no certificados ni modifica las otras distribuidoras.
Antes de activar un release se comparan los campos anteriores del catalogo,
los cinco marts economicos, aliases, inferencias, ingresos asociados y contratos.
