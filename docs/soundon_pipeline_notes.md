# SoundOn pipeline notes

## Objetivo

Incorporar SoundOn al pipeline viejo y al pipeline nuevo, usando `My Royalty` como fuente granular principal.

## Inputs

- Carpeta: `C:\royalties_pipeline\input_raw\soundon`

Cada mes trae los archivos principales:

- `My Royalty`
- `Share in`
- `Share out`
- `Summary`

El paquete tambien puede traer `Discovery Mode`. Es el detalle por tema de la
deduccion que ya aparece en la columna `Discovery Mode Commission Amount` de
`My Royalty`; no representa un segundo movimiento economico.

## Decision importante sobre Summary

`Summary` es un resumen agregado por tienda. No se carga al standardized principal porque duplica el total de `My Royalty` y no trae granularidad de artista/tema/ISRC.

Se usa solo en `audit_soundon.py`, leyendo los CSV originales desde `input_raw`, para validar que `My Royalty` cierre contra el resumen mensual.

## Decision sobre Discovery Mode

`Discovery Mode` no se carga al standardized ni se suma a ingresos. La auditoria
compara `Deduction for this period` contra `Discovery Mode Commission Amount` de
`My Royalty` para el mismo mes y falla si existe una diferencia. El monitor lo
clasifica como `ignored_audit_detail`: queda visible y trazable, pero no bloquea
la publicacion cuando la auditoria cierra.

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
- `transaction_month`: mes de consumo obtenido de `Sales Period`, nunca de `Reporting Period`.
- `sales_period`: `Sales Period`
- `sale_start_date` / `sale_end_date`: extremos originales de `Sales Period`.
- Los periodos invalidos o que abarcan varios meses detienen la ingesta: no se reparte consumo sin evidencia.
- `Reporting Period` debe coincidir con YYYY_MM del archivo. Las liquidaciones siguen usando statement; las tendencias usan consumo.

## Reglas de artista/tema

- `artist_statement_original`: `Track Artists`, sin reemplazar el credito original.
- `artist_statement_style`: credito original de `Track Artists` para conservar agrupaciones y redondeos de los informes actuales.
- `artist_catalog_style`: referencia verificada del ISRC cuando el conjunto de participantes coincide; usada por Catalogo y Contratos, sin reescribir el credito economico.
- `track_statement_style`: `Track Title`
- `asset_isrc`: `ISRC`
- `track_id`: `Track ID`
- `product_upc`: `UPC Code`
- `store_name`: `Store Name`
- `territory`: `Sales Region`

## Regla obligatoria de lectura y referencias

El primer artista de la referencia de pista del ISRC es el principal. El UPC
identifica un lanzamiento y nunca sustituye ese principal. Dos UPC asociados al
mismo ISRC conservan todas sus ventas; no se deduplican filas economicas.

Las referencias aprobadas viven en `warehouse/registry/soundon_isrc_references.json`,
versionadas con codigo y evidencia de OGS. La foto inicial resuelve Tu Falta De
Querer y Devuelvete contra las filas de pista SoundOn 621 y 620 de OGS. No se
importa automaticamente el resto de la hoja ni se modifica la hoja de Pablo.
Una nueva referencia se incorpora por ISRC y evidencia, no mediante excepciones
en reportes. Ediciones futuras de OGS deben contrastarse antes de aprobarlas.

Sin referencia, un cambio no resuelto del primer artista mantiene la duda de
principal. Los integrantes y el orden se evaluan por separado: una diferencia
de integrantes entre distribuidoras no vuelve incierto un principal observado
de forma consistente. Se conservan las listas y su procedencia, sin borrar
nombres por interseccion ni declarar que una union prueba derechos.
Contratos ofrece los participantes reportados en la propuesta y muestra la
diferencia entre fuentes, sin asignar porcentajes ni modificar contratos
guardados. Si el principal es incierto, no se precarga como confirmado.

`PUBLISHING` se incluye en el circuito economico actual de recordings. Se
conserva `Royalty Type` para auditoria; no se excluye ni se suma dos veces.

UPC e identificadores se leen como texto para conservar ceros iniciales.
Monedas distintas de USD, importes invalidos o archivos desconocidos detienen
la ingesta. Un fallo de cualquier archivo no reemplaza el mart vigente.
Antes de reemplazarlo se concilian filas, dinero y unidades por statement y
tienda contra los CSV; Summary y Discovery Mode siguen siendo controles.

QA obligatorio: `scripts/qa/qa_soundon_reading.py`, `audit_soundon.py`,
equivalencia economica por statement/ISRC y conciliacion de BigQuery. El cambio
de mes de consumo no habilita splits nuevos ni cambia formatos o descuentos.

## Share in / Share out

Los 22 archivos revisados estan vacios, con cuatro layouts. Eso no certifica
transferencias futuras. El adaptador de metadata rechaza entradas con
movimientos no certificados; el camino financiero real requiere una muestra
y conciliacion antes de reemplazarlo. No se modifican Shares In & Out de ONErpm.

## Catalogo comun y Contratos 2026-10-20

La adopcion de SOUNDON-LECTURA-1 es de metadata, no un reemplazo del lector
economico. El contrato completo y los 72 casos del lector estan en
`catalogo_lectura_soundon_reglas_v1_20261019.md`.

`scripts/lib/soundon_catalog_artists.py` interpreta las columnas SoundOn ya
preservadas en standardized, conserva las observaciones y produce evidencia
comun versionada. `build_catalog_master.py` aplica ese adaptador tambien en
futuras construcciones. No depende de abrir CSV locales desde la API ni de
consultar OGS durante la lectura de una ficha.

Solo se estructuran `catalog_artists`, `catalog_artist_statement`,
`catalog_artist_rule` y `catalog_artist_evidence`. Las listas previas y las
referencias aprobadas se conservan. `app/master_contract_participants.py`
reconoce su evidencia y Contratos utiliza esa lectura en sus propuestas;
participantes nuevos no reciben porcentajes del statement. `Artist Share`
es dinero, nunca el porcentaje de un contrato.

La prueba cloud cubre las 17 fichas SoundOn, dos testigos de otras fuentes,
los asociados reales, escritorio/movil y 159 regresiones del contexto de codigo
adoptado. Se conservan importes, ambas fechas, unidades, aliases/UGC, decisiones
de asociados, contratos e historiales, policies y entradas de reportes. El
dashboard actual continua sin splits.

QA de metadata: `scripts/qa/qa_soundon_catalog_artists.py`. El soporte financiero
de unidades desconocidas (SO-D-02 / ORCH-INT-02) y SoundOn Shares con movimientos
(SO-D-03) siguen separados de esta adopcion. La carrera de recarga/busqueda
rapida del frontal (SO-CLOUD-UI-01), reproducida en el preview con la web previa,
tampoco se modifica en esta etapa.

## Outputs

- `warehouse\marts\standardized_raw_soundon.parquet`
- `warehouse\marts\song_level_soundon.parquet`

## Validacion esperada

- `My Royalty` debe cerrar contra `Summary` por `Reporting Period`.
- `Discovery Mode` debe cerrar contra la deduccion incluida en `My Royalty`.
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
