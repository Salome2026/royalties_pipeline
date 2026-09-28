# Linea base de informes de regalias - 2026-09-28

## Alcance y seguridad

Primera etapa de REP-001. Se leyeron trabajos completados, sus snapshots de
Cloud SQL y sus artefactos de GCS. No se recalculo ningun informe ni se cambio
una policy, un mart, un trabajo o un dato publicado.

Las copias locales verificadas estan en
`reports/qa/royalty_baseline_20260928/`, una carpeta ignorada por Git. Las
mismas seis copias tambien se archivaron en
`gs://vpo-corp-royalties-marts/qa/royalty-report-baseline/20260928/` sin
mover ni sustituir los originales. El bucket tiene acceso publico bloqueado y
control de acceso uniforme. La regla de borrado a los 30 dias aplica a
`reports/jobs/`, no al prefijo `qa/` al momento de este respaldo. El bucket
tiene borrado recuperable por siete dias; este archivo **no es inmutable** y
sus reglas de retencion deben revisarse si cambian las politicas del bucket.

## Datos congelados

Todos los trabajos nuevos elegidos usan policy de distribuidoras v10. El
manifiesto de cada trabajo identifica las generaciones exactas de los cuatro
objetos, no solo el nombre del release. `catalog_status.parquet` usa la
generacion `1785684174304652` en ambos releases.

| Alias | Release | Manifiesto | Standardized raw | Song level | Catalog master |
| --- | --- | ---: | ---: | ---: | ---: |
| R22 | `20260922T160603Z-df288d7cce3c` | 1790093191091197 | 1790093186462656 | 1790093186863010 | 1790093187143319 |
| R16 | `20260916T065558Z-4270970b55a3` | 1789541953525022 | 1789541935149067 | 1789541935832277 | 1789541936179832 |

## Testigos verificados

`Espera` mide creacion a inicio; `Job` mide inicio a finalizacion. `Filas
resultado` y `USD` salen de la hoja `resumen general`; `Detalle` excluye el
encabezado. Las sumas de `resumen mensual` y `resumen por tema` coinciden con
el USD general dentro de 0.000001 por redondeo de lectura.

| Job | Caso | Release | Filas resultado | USD exacto | Unidades | Detalle | Espera / Job | Hojas | Bytes |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 75 | La Juntada, statement 2025-01 a 2026-07, limitado 5000 | R22 | 647109 | 67006.95121179015 | 508377352 | 5000 | 2.7 / 8.5 min | 6 | 597381 |
| 74 | Busqueda mixta por ISRC y titulos, statement 2025-11 a 2026-06, limitado 15000 | R22 | 64340 | 14892.181090479 | 24876675 | 15000 | 2.1 / 44.4 min | 6 | 1685218 |
| 71 | La Juntada, mismo alcance que 75, cinco paises | R16 | 647109 | 67006.95121179015 | 508377352 | 258419 | 1.4 / 14.3 min | 6 | 34690748 |
| 64 | `Protagonista Lit Killah`, modo all, sin coincidencias | R16 | 0 | 0 | 0 | 0 | 1.4 / 1.3 min | 2 | 6041 |
| 62 | Facuu, transaction, limitado 5000 | R16 | 6405 | 32632.22667884017 | 1341989061 | 5000 | 3.2 / 4.3 min | 6 | 561378 |
| 55 | mamiyosoyelth, transaction, limitado 50000 | R16 | 3322 | 31767.34956758867 | 558497105 | 50000 | 3.3 / 4.9 min | 6 | 5647702 |

Los SHA-256 de las copias locales coinciden con `report_runs.result_sha256`:

| Job | SHA-256 |
| ---: | --- |
| 75 | `1279d5f5f893ca62a20cdac772c8e1501f36562cc81353e0d17bd806eb61a73b` |
| 74 | `8bbef371432d23c0a5292a4524bc2e2ae6b318711c7a44b8a5ca9e671afd2ce6` |
| 71 | `c2d2136780a1c70400a8389e3ed4b1c0316322dc745bb1109b67c07e66153e4d` |
| 64 | `d1552e7a126e8d0dd6e61e7758aa493bdde5f085bc8bc0c3d70a093caa0c73e3` |
| 62 | `ad02c5316d9540ca12734a40ad0237b1c9366415482b44d2dab74de19c8915df` |
| 55 | `6df3f52f5267fdcba0e9299da6ebc6123c7ab527c1e18486646a6c64cae6e65b` |

Cada copia se llama `<job_id>_<result_filename>`. Los seis objetos remotos
fueron creados solo si no existian y descargados de nuevo para comprobar
tamanos y SHA-256 contra los valores de la tabla. Sus generaciones son:

| Job | Generacion del respaldo QA |
| ---: | ---: |
| 75 | 1790605196763945 |
| 74 | 1790605197734499 |
| 71 | 1790605211745051 |
| 64 | 1790605213142570 |
| 62 | 1790605213805181 |
| 55 | 1790605218055772 |

Los originales permanecen en
`gs://vpo-corp-royalties-marts/reports/jobs/<job_id>/`.

## Caso fallido y limites del testigo

- Job 63, Facuu por statement 2023-03 a 2026-06, modo cinco paises: fallo
  despues de 15.6 minutos de Job porque el detalle resulto en 1333886 filas,
  por encima de las 1048575 filas de datos permitidas por Excel. No existe
  artefacto final que copiar.
- El job 64 demuestra el comportamiento actual de esa busqueda literal; no
  demuestra que cero resultados sea el resultado de negocio correcto.
- Los jobs 71 y 75 tienen los mismos totales generales, pero usan releases
  distintos. No asumir igualdad fila por fila.
- No hay un PDF ejecutivo ni un Google Sheet reciente, con release y policy
  congelados, entre estos testigos. No generar uno solo para completar la
  matriz sin decidir primero alcance, costo y datos.
- Esta linea base no valida los cortes contractuales ni que una policy faltante
  sea manejada correctamente. Es una referencia de comportamiento actual, no
  una aprobacion economica.

## Proxima puerta de control

Antes de probar el lector BigQuery: definir comparacion por hoja, cuenta, mes e
identidad; resolver el orden de las primeras N filas del detalle; y agregar
testigos actuales para PDF y Google Sheets si esos formatos entran en el primer
corte. No cambiar el motor publico ni los importes hasta superar esa
comparacion.
