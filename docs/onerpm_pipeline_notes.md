# ONErpm pipeline notes

## Objetivo

Unificar las tres subcuentas de ONErpm dentro de un solo mart `onerpm`, preservando reglas distintas por cuenta y agregando flags de vista para reportes.

## Inputs

- `C:\royalties_pipeline\input_raw\onerpm\henry_remix`
- `C:\royalties_pipeline\input_raw\onerpm\gusty_dj`
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
- `scripts\audit_standardized_onerpm.py`: auditoria standardized
- `scripts\audit_song_level_onerpm.py`: auditoria song-level

## Reglas por cuenta

### Henry Remix

- Se carga `Masters`.
- `Shares In & Out` viene vacio o no relevante.
- En el pipeline viejo Henry usaba `net_amount` directo para reporte.
- En el pipeline nuevo se convierte a USD usando FX cuando corresponde.

### Gusty DJ

- Se carga `Masters`.
- `Shares In & Out` no se carga como filas de ingreso.
- `Shares In & Out` se usa para flags/alertas sobre Masters.
- Es una cuenta externa historica: sirve para vista catalogo, no para cash propio.

### MAWZ Records

- Se carga `Masters`.
- Se carga `Shares In & Out` como filas porque representa movimientos relevantes de la cuenta.
- Se marca `possible_internal_transfer = true` para Shares.

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
- `asset_isrc`: `ISRC`
- `track_statement_style`: `Track Title`

Shares:

- `artist_statement_style`: `Payer Name`
- IDs posibles desde `ID` / `Parent ID`

## Vistas de negocio

El standardized incluye flags:

- `include_in_cash_view`
- `include_in_catalog_view`
- `include_in_statement_view`
- `possible_internal_transfer`
- `revenue_basis`

Uso esperado:

- Cash/statement: Henry + MAWZ
- Catalogo: Masters de las cuentas, incluyendo Gusty
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
