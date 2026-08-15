# ONErpm pipeline notes

## Objetivo

Unificar las subcuentas de ONErpm dentro de un solo mart `onerpm`, preservando reglas distintas por cuenta y agregando flags de vista para reportes.

## Inputs

- `C:\royalties_pipeline\input_raw\onerpm\henry_remix`
- `C:\royalties_pipeline\input_raw\onerpm\gusty_dj`
- `C:\royalties_pipeline\input_raw\onerpm\la_nueva_sangre`
- `C:\royalties_pipeline\input_raw\onerpm\mawzrecords`

Cada archivo suele tener hojas:

- `Masters`
- `Shares In & Out`

## Scripts principales

- `scripts\ingest_onerpm_henry_remix_incremental.py`: pipeline viejo Henry
- `scripts\ingest_onerpm_gusty_dj.py`: pipeline viejo Gusty
- `scripts\ingest_onerpm_mawzrecords_incremental.py`: pipeline viejo MAWZ
- `scripts\ingest_standardized_onerpm.py`: pipeline nuevo unificado
- `scripts\build_song_level_onerpm.py`: mart agregado por tema
- `scripts\audit_consolidated_marts.py`: cierre standardized vs song-level por fuente
- `scripts\qa\qa_statement_policy_vs_current.py`: cierre de salida reportable contra policies

## Reglas por cuenta

### Henry Remix

- Se carga `Masters`.
- `Shares In & Out` viene vacio o no relevante.
- En el pipeline viejo Henry usaba `net_amount` directo para reporte.
- En el pipeline nuevo se convierte a USD usando FX cuando corresponde.

### Gusty DJ

- Se carga `Masters`.
- Se carga `Youtube Channels`.
- `Shares In & Out` no se carga como filas de ingreso.
- `Shares In & Out` se usa para flags/alertas sobre Masters.
- Es una cuenta externa historica: sirve para vista catalogo, no para cash propio.

### La Nueva Sangre

- Se carga `Masters`.
- Se carga `Youtube Channels`.
- `Shares In & Out` no se carga como filas de ingreso.
- `Shares In & Out` se usa para flags/alertas sobre Masters.
- Es una cuenta externa tipo Gusty: principalmente catalogo de DJ Plaga.
- Los `Shares In` pueden corresponder a colaboraciones donde la cuenta recibio participacion, pero no representan administracion/porcentaje de VPO.
- Diferencia esperada: el `Summary` de ONErpm puede incluir `Share In/Out`; el mart operativo de La Nueva Sangre solo incluye ingresos de catalogo/Youtube y deja los shares como senales de auditoria.

### MAWZ Records

- Se carga `Masters`.
- Se carga `Youtube Channels`.
- Se carga `Shares In & Out` como filas porque representa movimientos relevantes de la cuenta.
- Se marca `possible_internal_transfer = true` para Shares.
- En los archivos actuales de MAWZ, la hoja `Youtube Channels` existe pero viene sin filas de datos.
- En el reporte por statement nuevo, MAWZ se informa solo con `Masters`; los shares permanecen en el mart para auditoria/caja pero no se suman a generacion de catalogo.

## Reglas de monto

- Columna base: `Net`
- `net_amount`: `Net`
- `net_amount_usd`: `Net * FX`
- `amount_usd`: `COALESCE(net_amount_usd, net_amount)`

FX:

- Se usa `scripts\lib\fx.py`
- Cache en `warehouse\registry\exchange_rates.parquet`
- Se normaliza `RUR -> RUB`

## Reglas de artista/tema

Masters:

- `artist_statement_style`: se parsea desde `Artists`, tomando performers.
- `asset_isrc`: primer ISRC valido de `ISRC`, `ID`, `Parent ID`.
- `product_upc`: primer UPC valido de `UPC`, `Parent ID`.
- `track_statement_style`: `Track Title` (o `Title` si el layout futuro no trae
  `Track Title`).
- `content_type`: `audio`.

Youtube Channels:

- `video_id`: `Video ID` valido de 11 caracteres.
- `channel_id`: `Channel ID` valido.
- `track_statement_style`: `Video Title`.
- `artist_statement_style`: `Channel Name`.
- `content_type`: `video`.
- Nunca se guarda un Video ID como `asset_isrc`.

Shares:

- `artist_statement_style`: `Payer Name`
- `ID` se clasifica por forma: ISRC valido a `asset_isrc`, video id valido a
  `video_id`.
- `Parent ID` se clasifica por forma: UPC valido a `product_upc`, channel id
  valido a `channel_id`.
- `track_statement_style`: `Title`.
- Estas columnas sirven para trazabilidad; la policy sigue decidiendo que
  Shares es transferencia/caja/auditoria y no nueva generacion.

## Vistas de negocio

El standardized incluye flags:

- `include_in_cash_view`
- `include_in_catalog_view`
- `include_in_statement_view`
- `possible_internal_transfer`
- `revenue_basis`

Uso esperado:

- Cash/statement: Henry + MAWZ
- Catalogo: Masters/Youtube de las cuentas, incluyendo Gusty y La Nueva Sangre
- Auditoria/raw: todo

## Diferencias conocidas contra pipeline viejo

### MAWZ 2024-02

El pipeline nuevo recupera `mawzrecords 2024-02 Masters`, que antes fallaba por moneda `RUR`.

Impacto aproximado:

```text
+6219 filas
+1484.495475 USD
```

### Henry Remix

El pipeline nuevo convierte a USD; el viejo usaba `net_amount` directo.

Impacto aproximado:

```text
-7.275663 USD
```

## Outputs

- `warehouse\marts\standardized_raw_onerpm.parquet`
- `warehouse\marts\song_level_onerpm.parquet`

## Validacion esperada

- Gusty Masters cierra contra viejo.
- MAWZ Shares cierra contra viejo.
- MAWZ Masters cierra contra viejo si se excluye la mejora 2024-02.
- Henry cierra contra viejo si se compara `net_amount`.
- `standardized_raw_all_sources` y `song_level_all_sources` cierran por fuente
  dentro de tolerancia de coma flotante.
- La salida de policies y la salida reportable actual cierran con diferencia
  total USD 0,00.

## Evidencia para DSP y monetizacion

La clasificacion usa `source_sheet`, `Store`, `Product Type` y `Sale Type`.
Spotify Ad Supported y YouTube Premium son explicitos. `Youtube Channels`
identifica ingreso de canal/video; `Masters` identifica la base master, pero no
autoriza a inferir UGC o video oficial si la fila no lo informa.

En `Youtube Channels`, la hoja es evidencia explicita de origen
`Video / Channel`. `YouTube Premium` sigue siendo la monetizacion y no debe
reclasificar esa fila como `Music / Art Track`.

Esta clasificacion no altera las vistas de negocio: `Shares In & Out` conserva
su caracter de transferencia/caja/auditoria y nunca se suma como nueva
generacion por tener un Store reconocible.
