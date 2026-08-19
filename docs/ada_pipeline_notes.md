# ADA pipeline notes

## Alcance

ADA es una distribuidora del pipeline productivo vigente. La primera cuenta es:

- `source = ada`
- `account = mawz`
- raw: `input_raw/ada/mawz`

Las cuentas futuras deben vivir debajo de `input_raw/ada/<account>` y declarar
su propia policy. No deben mezclarse dentro de `mawz`.

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

ADA/Mawz entra como generacion y caja propia completa. El ajuste configurable
de reportes comienza en 0% y se gobierna por
la policy operativa de Cloud SQL; no se modifica durante la ingesta.

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
3. summaries de ingresos digitales y dashboard
4. `build_catalog_master.py`
5. auditorias
6. publicacion del paquete analitico

No existe conector ADA hacia pipelines archivados ni hacia SQLite. No se agrega
compatibilidad con esquemas anteriores.

## Continuidad inicial validada

Se recibieron 29 statements consecutivos desde 2024-02 hasta 2026-06:

- 26 con movimientos;
- 3 sin actividad: 2024-02, 2024-03 y 2024-04;
- sin meses faltantes;
- sin meses duplicados.
