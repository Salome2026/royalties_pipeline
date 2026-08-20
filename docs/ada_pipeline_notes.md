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

La fuente operativa es el TXT tabulado mensual `Statement_..._YYYYMMDD.txt`.
Se conserva el archivo original y sus 32 columnas. Si existe una representacion
Excel equivalente, queda como documento auxiliar de auditoria y no se suma como
una segunda fuente.

Los TXT que contienen solamente:

```text
No Earning Activity for this Royalty Period
```

son statements validos sin movimientos. Cuentan para continuidad mensual, pero
no crean filas de regalias de importe cero.

## Periodos

- `statement_period`: mes de la fecha `YYYYMMDD` al final del filename.
- validacion: `Start Period` y `End Period` deben coincidir con ese mes.
- `transaction_month`: `Repdate Month ID`.
- `receipt_month`: `Recdate Month ID`.

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

## Identidad y dimensiones

- artista: `Artist Name`;
- tema: `Project Title`, con fallback a `Product Title`;
- ISRC: `ISRC`;
- identificador ADA: `GPID`, conservado en `gpid`;
- catalog number: `Catalog Number`, conservado en `catalog_number`;
- UPC canonico: vacio mientras ADA no entregue una columna UPC demostrable;
- store: `Digital Service Provider(DSP)`;
- territorio: `Country`;
- unidades: `Sale Units`;
- modalidad: `Dist Chan Desc` y `Price Desc`.

`GPID` y `Catalog Number` no se reinterpretan como UPC. Los campos originales
se preservan y no se infieren ISRC, UPC, artistas ni temas en el ingest.

En el consolidado, ADA usa la taxonomia comun de Store/DSP. Caso testigo
validado para Spotify:

- `Dist Chan Desc = Subscription` -> monetizacion `Premium`;
- `Dist Chan Desc = Ad Supported` -> monetizacion `Ads`;
- `Payment Top - Up` y `Audit Recovery` permanecen `Unknown` mientras ADA no
  demuestre una modalidad mas precisa;
- el origen es `Audio / Master`;
- el plan permanece `Unknown`, porque ADA no informa Individual, Family o Duo.

Por lo tanto, ningun reporte debe agrupar ADA solamente bajo `Spotify`. Debe
mostrar al menos la separacion Premium/Ads cuando el statement la demuestra,
sin modificar `Dist Chan Desc`, `Price Desc` ni el resto de las columnas raw.

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

Se recibieron 29 statements consecutivos desde 2024-02 hasta 2026-06:

- 26 con movimientos;
- 3 sin actividad: 2024-02, 2024-03 y 2024-04;
- sin meses faltantes;
- sin meses duplicados.

### Indyana Records

La cuenta comienza en el sistema con el statement 2026-07:

- archivo: `Statement_99500_5779_99500_20260731.txt`;
- 30.505 filas;
- 0 filas sin ISRC;
- bruto USD 7.957,40619029;
- deducciones USD 795,74062007;
- neto USD 7.161,66557022;
- `Royalty Payable - Deductible Fees = Net Royalty Payable` validado;
- consumos informados: 2026-05 a 2026-06;
- no se esperan statements anteriores para esta cuenta dentro del sistema.
