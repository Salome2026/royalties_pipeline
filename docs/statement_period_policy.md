# Statement period policy

## Objetivo

Separar claramente dos fechas distintas del sistema:

- `transaction_month`: mes real de consumo, venta o uso. Sirve para performance, tendencias y analisis musical.
- `statement_period`: mes en que la distribuidora informa o liquida el ingreso. Sirve para liquidaciones y pagos a artistas.

Para pagar regalias, la base correcta es `statement_period`.

## Metadata obligatoria

Los ingests standardized deben guardar:

- `statement_period`
- `statement_period_source`
- `statement_period_note`

Esto permite auditar por que un archivo o fila quedo asignado a un periodo de liquidacion.

## Reglas por fuente

| Fuente | Regla | `statement_period_source` |
| --- | --- | --- |
| DashGo | Sufijo del filename `MM-YY` | `filename` |
| FUGA regular | Mes y anio del filename `April2026StatementRun...` | `filename` |
| FUGA correction | Periodo de liquidacion definido por politica operativa | `correction_policy` |
| ONErpm | Prefijo del filename `YYYY-MM-01...` | `filename` |
| Orchard moderno | Columna `STATEMENT PERIOD` | `column` |
| Altafonte legacy | Encabezados mensuales del Excel historico | `legacy_manual` |
| SoundOn | Columna `Reporting Period` | `column` |

## FUGA correction

Los archivos FUGA correction pueden no traer mes de statement en el filename.

Politica elegida:

```text
Las correcciones se liquidan en el periodo en que aparecen/se informan.
No se redistribuyen hacia meses viejos para pagos.
```

En el standardized actual:

```text
statement_period = 2025-12
statement_period_source = correction_policy
```

`transaction_month` sigue disponible para analizar a que meses reales corresponden los movimientos corregidos.

## Reingesta

Agregar estas columnas no cambia importes ni FX. Para que aparezcan en los marts publicados hay que:

1. Ejecutar los standardized ingests.
2. Rebuild de song-level/consolidated/summary marts.
3. Publicar marts a GCS.

Antes de usar liquidaciones definitivas, validar que no existan `statement_period` nulos o `unknown`.
