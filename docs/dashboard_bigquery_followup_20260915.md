# Seguimiento de rendimiento, dashboard y BigQuery

Fecha de linea base: 2026-09-15. Este es el tablero de tareas acordado para
retomar con `regresa ahora`. El orden inmediato es E0/E1: recuperar el dashboard
con `PERF-001`, `PERF-002` y `PERF-003`. BigQuery se prepara en paralelo, sin
cambiar la lectura productiva hasta conciliar y comparar.

## Tareas

| Codigo | Estado | Responsable | Evidencia | Metrica anterior | Metrica nueva | Commit | Despliegue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PERF-001 Linea base y casos testigo | En curso; datos y codigo alineados, medicion productiva pendiente | Codex | Casos locales, colision y registros Cloud Run abajo; seis marts GCS verificados; prueba funcional productiva de un mes HTTP 200 | Local: 6m 37.2 s, 1m 10.3 s, FUGA 6m 25.1 s; historico cloud hasta 147.2 s y dos 503 | Pendiente; prueba funcional 2026-06 en Cloud Run 24.1 s, no linea base | `d4de3cf`; tracker en commit posterior | GCS 18:33; API revision `00161-rkc` al 100%; Job y Vercel publicadas |
| PERF-002 Dashboard con una sola lectura | Pendiente | Por asignar | 7 llamadas `.collect()` fuera de rankings y 2 por cada uno de 13 rankings en `royalties_dashboard` | PERF-001 | Pendiente | - | - |
| PERF-003 Cache por generacion de datos | Pendiente | Por asignar | El cache GCS usa existencia local; el resumen local se regenera por mtime durante GET | Primer GET >180 s; un GET concurrente dio 500 | Pendiente | - | - |
| BQ-001 Dataset, esquemas y permisos | Pendiente | Por asignar | - | - | Pendiente | - | - |
| BQ-002 Carga versionada desde GCS | Pendiente | Por asignar | - | - | Pendiente | - | - |
| BQ-003 Conciliacion por fuente, cuenta y mes | Pendiente | Por asignar | - | - | Pendiente | - | - |
| DASH-001 Consultas y agregados en BigQuery | Pendiente | Por asignar | - | - | Pendiente | - | - |
| DASH-002 Comparacion y cambio gradual | Pendiente | Por asignar | - | - | Pendiente | - | - |
| REP-001 Lectura de informes desde BigQuery | Pendiente | Por asignar | - | - | Pendiente | - | - |
| REP-002 Equivalencia Excel/PDF y limites de detalle | Pendiente | Por asignar | - | - | Pendiente | - | - |
| QUEUE-001 Heartbeat y deteccion de procesos trabados | Pendiente | Por asignar | - | - | Pendiente | - | - |
| QUEUE-002 Concurrencia global y reintentos | Pendiente | Por asignar | - | - | Pendiente | - | - |
| ING-001 Ingesta durable y publicacion atomica | Pendiente | Por asignar | - | - | Pendiente | - | - |
| OPS-001 Metricas, alertas y despliegue | Pendiente | Por asignar | - | - | Pendiente | - | - |

No se debe completar una tarea sin actualizar las ocho columnas. Las cifras
locales son referencia para comparar una implementacion nueva, no sustituyen
mediciones en produccion.

## Alineacion previa a PERF-002

El 2026-09-15 entraron FUGA agosto y septiembre (12:14) y ADA / Indyana
Records junio (13:35). Los marts locales de fuente y consolidado se generaron
despues; el monitor local marca cero archivos sin procesar para FUGA y ADA.
`validate_analytics_package_for_publish()` dio OK para los seis marts locales.

Antes de alinear, el paquete GCS estaba publicado a las 12:59, antes del ADA
nuevo. Comparacion inicial del `statement_summary_all_sources.parquet` local y GCS,
agrupado por fuente, cuenta y mes:

| Fuente / cuenta / mes | Local | GCS | Estado |
| --- | --- | --- | --- |
| ADA / indyana_records / 2026-06 | 17 `artist_total`; suma USD 759.10 | Sin filas | Falta publicar |
| FUGA / indyana_records / 2026-08 | 549 filas; suma USD 20,435.81 | Igual | Alineado |
| FUGA / indyana_records / 2026-09 | 561 filas; suma USD 18,229.32 | Igual | Alineado |

La suma ADA es un total del statement, no un importe bancario. Solo hubo un
grupo fuente/cuenta/mes diferente en el resumen comparado: ADA junio. El
monitor productivo marca ADA como `ok` por antiguedad (julio 2026) aunque
falte junio de Indyana Records: ese estado no prueba inclusion archivo a
archivo. El
publicador actual reconstruye dashboard durante la publicacion y sube los
archivos uno por uno, sin puntero atomico de generacion. La API publicada
mantiene cache local por existencia de archivo, no por generacion GCS; subir
los objetos no garantiza por si solo que una instancia viva lea el nuevo dato.
El estado de jobs de publicacion vive en memoria de la API; tras un reinicio
no se puede reconstruir confiablemente el resultado de un job anterior.

Estado despues de publicar a las 18:33: los seis objetos GCS tienen tamanos
identicos a sus pares locales. El resumen GCS es igual al local (12,193 filas),
incluye 17 `artist_total` de ADA junio por USD 759.10 y conserva 1,110 filas
FUGA agosto/septiembre. Respaldo del paquete previo bajo
`marts/release_backups/pre_ada_jun_20260915/`.

| Mart | Generacion GCS nueva |
| --- | --- |
| `standardized_raw_all_sources.parquet` | `1789511623673697` |
| `song_level_all_sources.parquet` | `1789511625077825` |
| `catalog_master.parquet` | `1789511625657230` |
| `statement_summary_all_sources.parquet` | `1789511625946717` |
| `digital_income_statement_summary.parquet` | `1789511626377417` |
| `royalties_dashboard_summary.parquet` | `1789511637355872` |

La API `vpo-corp-api-00161-rkc` lee el nuevo paquete GCS: Ingresos digitales
para ADA / Indyana Records junio devuelve USD 759.09 en 54 filas de detalle;
la diferencia de USD 0.01 respecto de la suma `artist_total` del resumen de
statement proviene de las distintas agregaciones. La web Vercel, la API y el
Job de reportes usan el commit `d4de3cf`. La API tenia el trafico fijado a
`vpo-corp-api-cache15` pese a que Cloud Build habia terminado. Se probo la
revision nueva con un tag aislado y despues se cambio el trafico principal y
el tag `dashboard-fastpath` a `LATEST` al 100%. El endpoint de `/health`,
`/digital-income`, `/source-monitor` y `/reports/jobs` responden; el monitor
muestra 0 alertas y los ultimos ocho jobs consultados no tienen activos. El
monitor productivo no ve archivos crudos locales (raw_files=0), por lo que su
estado verde no reemplaza la conciliacion del paquete GCS. No se genero un
reporte pesado nuevo durante esta verificacion.

## Ingresos digitales: entrega aprobada

Ruben confirmo que la pantalla local quedo bien. El cambio publicado
incluye seleccion global persistente de distribuidoras/cuentas y el menu
ajustado; no modifica statements ni politicas de reportabilidad. Paso la QA
enfocada `qa_digital_income_selection`, el chequeo TypeScript `--noEmit` y
`npm run build` el
2026-09-15. Esta en el commit `d4de3cf`, publicado en Vercel, Cloud Run API
y Cloud Run Job. La prueba productiva de Ingresos digitales devolvio HTTP 200.

La seleccion compartida en Cloud SQL sigue en version 25 y limita la vista a
`ada / indyana_records`; no se modifico durante la alineacion. Todos los
usuarios con acceso ven ese filtro hasta que alguno elija `Todas` u otra
seleccion. La respuesta productiva confirma la version 25. El build completo
de Next y el estado de despliegue Vercel del commit terminaron con exito. No
se hizo una prueba visual autenticada del PDF ejecutivo en produccion; su
generacion sigue siendo del frontend y no se altero en este commit.

## PERF-001: casos testigo locales

Entorno: API `127.0.0.1:8011`, Cloud SQL via proxy, HEAD `211a643`, sin nuevo
despliegue. Consolidado local `standardized_raw_all_sources.parquet`: 783 MB,
mtime 2026-09-15 13:45:46. Antes de medir, el resumen
`royalties_dashboard_summary.parquet` tenia 47 MB y mtime 12:56:47, por lo que
la primera lectura intento regenerarlo. El resumen nuevo tiene 3,153,971 filas.

| Caso | Filtros | Resultado | Tiempo | Meses | USD | Filas origen | Respuesta |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Testigo A | Ultimos 6 meses, statement period | HTTP 200 | 37.2 s | 6 | 217,532.25 | 3,306,103 | 15,105 B |
| Testigo B | 2026-09, statement period | HTTP 200 | 10.3 s | 1 | 16,778.37 | 504,469 | 11,059 B |
| Testigo C | FUGA, ultimos 6 meses, statement period | HTTP 200 | 25.1 s | 6 | 118,863.91 | 2,914,425 | 12,155 B |
| Reconstruccion | Ultimos 6 meses con resumen atrasado | Cliente agoto timeout; servidor continuo | >180 s | - | - | - | - |
| Concurrencia | Segundo GET durante reconstruccion | HTTP 500; `WinError 32` al borrar una particion usada | - | - | - | - | - |

El resumen quedo vigente a las 18:04:53. Despues de eso se midieron A, B y C.
La API siguio respondiendo `/health` con HTTP 200. No se borraron manualmente
particiones ni se forzo `refresh_cache`.

## PERF-001: registros Cloud Run

Consulta de solo lectura a Cloud Logging el 2026-09-15, filtrada por requests
`royalties-dashboard` de las ultimas 24 horas. Muestra pequena y por revision,
no un percentil estable de todo el trafico:

| Revision | Requests | HTTP 5xx | Minimo | Mediana observada | Maximo |
| --- | ---: | ---: | ---: | ---: | ---: |
| `00155-zf8` | 1 | 0 | 98.95 s | 98.95 s | 98.95 s |
| `00158-gul` | 6 | 0 | 1.08 s | 8.11 s | 147.15 s |
| `00159-zec` | 10 | 2 | 0.12 s | 6.49 s | 34.24 s |
| `00160-fen` | 6 | 0 | 0.10 s | 1.48 s | 43.59 s |

La muestra historica se tomo antes de alinear el trafico. Ahora el 100% esta
en `vpo-corp-api-00161-rkc` (imagen `d4de3cf`). Una prueba funcional de
`royalties-dashboard` para 2026-06 devolvio HTTP 200 en 24.1 s; no se usa
como percentil ni como linea base representativa. Se necesitan casos testigo
y telemetria de esta revision antes de marcar PERF-001 como completo.

## Proxima decision E1

`PERF-002` debe reducir lecturas sin materializar las 3.15 millones de filas
completas en la API. La configuracion publicada, verificada con Cloud Run el
2026-09-15, es 2 GiB, 1 CPU y concurrencia 1; el documento de despliegue de
septiembre ya no refleja esa concurrencia. `PERF-003` debe separar
preparacion/publicacion del
GET y enlazar el cache a la generacion publicada, evitando que dos requests
escriban las mismas carpetas. Antes de cambiar el dashboard, conservar totales,
meses, rankings y opciones de A/B/C como casos de equivalencia.
