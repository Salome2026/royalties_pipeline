# ADA pipeline notes

## Alcance

ADA es una distribuidora multi-cuenta del pipeline productivo vigente. Las
cuentas productivas son:

- `source = ada`
- `account = mawz`
- raw: `input_raw/ada/mawz`
- `account = indyana_records`
- raw: `input_raw/ada/Indyana Records`

Cada cuenta conserva su carpeta, identificador interno y policy. El ingestor ADA
recorre todas las cuentas declaradas y escribe un unico mart ADA con la columna
`account` diferenciada. No se mezclan archivos ni se duplica un ingestor por
cuenta.

Identidad validada del origen:

- Mawz: `Account = 99205` -> `account = mawz`;
- Indyana Records: `Account = 99500`, `Account Name = INDYANA RECORDS LLC` ->
  `account = indyana_records`.

El ingestor rechaza un archivo ubicado en una carpeta cuyo `Account` original no
coincida con el esperado. El nombre original, `Account Name` y `Payee` permanecen
intactos en las columnas raw.

## Formato original

Se aceptan TXT tabulado `Statement_..._YYYYMMDD.txt` y Excel
`<cuenta>_<YYYYMM>_<YYYYMM>_<cuenta>_DTL.xlsx`. Por cuenta/mes se lee un solo
archivo: Excel tiene prioridad sobre TXT. Dos archivos del mismo formato para
ese mes son un error. Nunca sumar las dos representaciones.

El Excel se lee de `Distribution Statement`, localizando la cabecera por sus
nombres. Se validan `Contract` y el periodo del encabezado contra el filename.
Se excluyen los pies `Sub Totals`, `Previously Accounted Deductions` y `Totals`.
Las columnas originales del archivo elegido quedan preservadas.

Los TXT que contienen solamente:

```text
No Earning Activity for this Royalty Period
```

son statements validos sin movimientos. Cuentan para continuidad mensual, pero
no crean filas de regalias de importe cero.

## Periodos

- `statement_period`: mes del filename, tanto TXT como Excel.
- validacion: `Start Period` y `End Period` deben coincidir con ese mes.
- `transaction_month`: `Repdate Month ID`.
- `receipt_month`: `Recdate Month ID`.

En Excel, `Reported Month` es consumo; el periodo mensual es el del filename,
contrastado con el encabezado. No trasladar el ingreso al mes de consumo.

Un statement puede liquidar consumos de meses anteriores. Esto no es error y no
autoriza a trasladar el ingreso a otro `statement_period`.

## Importes

- bruto informativo: `Royalty Payable` -> `gross_royalty_usd`;
- comision/deducciones: `Deductible Fees` -> `deductible_fees_usd`;
- neto real reportable: `Net Royalty Payable` -> `amount_usd`, `net_amount` y
  `net_amount_usd`.

Debe cumplirse, admitiendo solo precision decimal de origen:

```text
Royalty Payable - Deductible Fees = Net Royalty Payable
```

ADA/Mawz y ADA/Indyana Records entran como generacion y caja propia completa.
Cada cuenta tiene su ajuste configurable independiente, gobernado por la policy
operativa de Cloud SQL; no se modifica durante la ingesta. Los flags de
statement, catalogo, caja y `revenue_basis` se leen de esa policy y la ingesta
falla si una cuenta declarada no tiene policy.

Excel auditado: bruto = `Receipts Value`; deduccion = `Distribution Fees`;
neto = bruto menos deduccion, con Decimal sin redondear filas. `Artist Royalties`,
`Mechanical Fees`, `Admin Fees`, `Upload Fees` y `Other Fees` son cero. Si en
un futuro dejan de ser cero se detiene la ingesta para revisar su significado.
Los aliases normalizados reutilizan el circuito vigente; no cambian ajustes
de distribuidora ni aplican splits.

## Identidad y dimensiones

- artista: `Artist Name`;
- tema TXT: `Product Title`, con fallback a `Project Title`;
- tema Excel: `Catalogue Title`;
- lanzamiento, separado del tema: `Project Title`;
- ISRC: `ISRC`;
- identificador ADA: `GPID`, conservado en `gpid`;
- catalog number: `Catalog Number` (TXT) / `Catalogue Number` (Excel),
  conservado en `catalog_number` y `source_asset_id`;
- UPC canonico: vacio mientras ADA no entregue una columna UPC demostrable;
- store: `Digital Service Provider(DSP)` (TXT) / `Territory` (Excel);
- territorio: `Country` (TXT) / `Country Code` (Excel);
- unidades: `Sale Units` (TXT) / `Sales` (Excel);
- modalidad: `Dist Chan Desc` y `Price Desc` (TXT) /
  `Revenue Type Desc` y `Price Name` (Excel).

Excel no informa GPID. `Parent Product ID` se conserva como contexto de release
en `parent_product_id`: puede reunir varios ISRC. No usarlo como identidad de
pista ni como UPC automatico. Solo una columna UPC explicita llena `product_upc`.

`GPID` y `Catalog Number` no se reinterpretan como UPC. Los campos originales
se preservan y no se infieren ISRC, UPC, artistas ni temas en el ingest.

En el consolidado, ADA usa la taxonomia comun de Store/DSP. Caso testigo
validado para Spotify:

- `Dist Chan Desc = Subscription` -> monetizacion `Premium`;
- `Dist Chan Desc = Ad Supported` -> monetizacion `Ads`;
- `Ad Channel` -> monetizacion `Ads`;
- `Payment Top - Up` y `Audit Recovery` -> `Adjustment`;
- el origen es `Audio / Master` para Spotify y DSP de audio;
- `YouTube Music` -> origen `Music / Art Track`;
- `YouTube` generico queda con origen `No informado` si no existe otra evidencia;
- ADA no informa un plan comercial y ese dato no forma parte del resumen.

Por lo tanto, ningun reporte debe agrupar ADA solamente bajo `Spotify`. Debe
mostrar al menos la separacion Premium/Ads cuando el statement la demuestra,
sin modificar `Dist Chan Desc`, `Price Desc` ni el resto de las columnas raw.

El contrato completo y los valores visibles se definen en
`docs/store_dsp_taxonomy_policy.md`.

## Scripts y marts productivos

- `scripts/ingest_standardized_ada.py`
- `scripts/build_song_level_ada.py`
- `warehouse/marts/standardized_raw_ada.parquet`
- `warehouse/marts/song_level_ada.parquet`

Luego se ejecuta el circuito compartido vigente:

1. `build_consolidated_marts.py`
2. `build_statement_summary_mart.py`
3. `build_catalog_master.py`
4. summaries de ingresos digitales y dashboard
5. auditorias
6. publicacion del paquete analitico

No existe conector ADA hacia pipelines archivados ni hacia SQLite. No se agrega
compatibilidad con esquemas anteriores.

## Continuidad validada por cuenta

### Mawz

Se recibieron 30 statements consecutivos desde 2024-02 hasta 2026-07:

- 27 con movimientos;
- 3 sin actividad: 2024-02, 2024-03 y 2024-04;
- sin meses faltantes;
- sin meses duplicados.

### Indyana Records

Caso testigo historico de julio, actualmente reemplazado por su Excel equivalente:

- archivo: `Statement_99500_5779_99500_20260731.txt`;
- 30.505 filas;
- 0 filas sin ISRC;
- bruto USD 7.957,40619029;
- deducciones USD 795,74062007;
- neto USD 7.161,66557022;
- `Royalty Payable - Deductible Fees = Net Royalty Payable` validado;
- consumos informados: 2026-05 a 2026-06;
- actualmente tambien estan cargados junio y agosto 2026.

## Regla de lectura obligatoria (2026-10-06)

Antes de modificar ADA, leer este documento, la policy vigente de Cloud SQL,
`identity_normalization_policy.md` y el diccionario de statements. No extrapolar
otra distribuidora ni otro formato de ADA.

1. ISRC valido: `ISRC:<ISRC>`. Nunca unir ISRC distintos por titulo.
2. Sin ISRC: `ADA:<cuenta original>:CATALOG:<numero de catalogo>`.
3. Si falta catalog number: `ADA:<cuenta original>:GPID:<GPID>`. Sin ambos
   identificadores en una fila sin ISRC, detener la ingesta.
4. La fila sin ISRC es un producto. No inventar ISRC, video, participantes ni
   distribuir ventas de album entre pistas.
5. `Artist Name` es evidencia informada, no una lista contractual verificada.
   Julio/agosto Excel traen nombres mas completos; junio aun tiene truncamientos.
   Revisar las ambiguedades, no completar a ojo.
6. Antes de reemplazar: comparar todas las filas economicas y duplicados por
   cuenta, ISRC, catalog number, DSP, pais, modalidad, precio y meses; comprobar
   bruto, fees, neto y unidades. Respaldar, verificar otras fuentes y conciliar BQ.

Implementacion: `scripts/lib/ada_identity.py`.
Prueba: `scripts/qa/qa_ada_excel_replacement.py`.

Statements activos Indyana: junio, julio y agosto 2026 (Excel).

| Statement | Filas | Unidades | Neto USD |
| --- | ---: | ---: | ---: |
| 2026-06 | 3.936 | 758.912 | 759,09047926 |
| 2026-07 | 30.505 | 11.263.163 | 7.161,66557022 |
| 2026-08 | 69.924 | 49.158.662 | 20.218,40138180 |
| Total | 104.365 | 61.180.737 | 28.139,15743128 |

Comparacion TXT/Excel completa: mismas transacciones economicas, sin duplicar.
Fila sin ISRC de agosto: `A10302B0013835580K`, neto USD 1,89, unidades 1;
queda como `ADA:99500:CATALOG:A10302B0013835580K`. GPID historico
`8718521191726` se conserva en TXT y releases respaldados, no se fabrica para
un Excel que no lo informa. Los tres TXT sustituidos se archivan fuera de ingesta.
