# Orchard / Altafonte pipeline notes

## Lectura comun de participantes: 2026-10-19

La construccion del catalogo incorpora `scripts/lib/orchard_catalog_artists.py`
despues de FUGA, ONErpm y ADA. Su alcance se limita a `catalog_artists`,
`catalog_artist_statement`, `catalog_artist_rule` y `catalog_artist_evidence`.
No reescribe importes, unidades, ISRC/UPC, asociados ni contratos guardados.

`TRACK ARTIST`, separado exclusivamente por barra vertical, acredita la pista.
`PRODUCT ARTIST` se conserva como contexto y no agrega participantes. Los nombres
nuevos no requieren diccionario ni porcentajes; listas contradictorias conservan
su evidencia y las decisiones previas. El orden estable es una propuesta, no
un rol contractual. La evidencia `ORCHARD-CAT003-adapter-1` permite a Contratos
reconocer artista unico u orden estable sin exigir evidencia propia de FUGA,
sin borrar dudas reales de otras fuentes o correcciones manuales.

Se usa el raw estandarizado inmutable como evidencia; `standardized_row` es un
localizador en su vista Orchard moderna, no una linea del CSV original.
Altafonte legacy queda excluido de este adaptador. La ingesta economica sigue
vigente: no se reemplaza su lector ni se cambia el tratamiento actual de unidades.
Antes de sustituirla, debe certificarse la conservacion de unidades desconocidas.
El dashboard actual sigue mostrando generacion completa, sin splits.

Validacion previa: 16 CSV, 419 ISRC, 127 pruebas de regresion, 419 registros HTTP,
nueve fichas y paneles asociados, cinco casos visuales desktop/mobile en cloud.
Las 247 listas estructuradas nuevas complementan las 172 ya conservadas;
las 102 dudas reales de orden principal no se resuelven artificialmente.
La adopcion productiva tiene sus comprobantes en
`staging/catalogo_lectura/20261019_orchard_production` y conserva el release
economico y las cinco generaciones de marts financieros existentes.
La auditoria de dependencias del frontend queda separada de esta adopcion.

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

Subscription se clasifica como `Premium`, Ad Supported como `Ads` y las
deducciones, fraude, streams no calificados y promociones negativas como
`Adjustment`. En YouTube manda la evidencia mas precisa de Transaction Type:
Art Track, Partnered Channel, UGC o Shorts; el nombre `Content ID` por si solo
no debe pisar un Art Track explicitamente informado.

Altafonte legacy no tiene esa granularidad. Sus filas deben conservar
`classification_status = unknown`; no se completa Store por inferencia.

No se presenta una columna `Plan`. El contrato completo esta en
`docs/store_dsp_taxonomy_policy.md`.
