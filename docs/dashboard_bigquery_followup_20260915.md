# Seguimiento de rendimiento, dashboard y BigQuery

Fecha de linea base: 2026-09-15. Este es el tablero de tareas acordado para
retomar con `regresa ahora`. El orden inmediato es E0/E1: recuperar el dashboard
con `PERF-001`, `PERF-002` y `PERF-003`. BigQuery se prepara en paralelo, sin
cambiar la lectura productiva hasta conciliar y comparar.

## Tareas

| Codigo | Estado | Responsable | Evidencia | Metrica anterior | Metrica nueva | Commit | Despliegue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PERF-001 Linea base y casos testigo | Completo: tres casos productivos y respuestas testigo; percentiles pendientes de OPS-001 | Codex | Tabla de mediciones y hashes abajo; seis marts GCS verificados; politica v10 | Local previo: 6m 37.2 s, 1m 10.3 s, FUGA 6m 25.1 s; historico cloud hasta 147.2 s y dos 503 | Produccion: A 87.1 s, B 6.9 s, C 32.1 s; una muestra por caso | `7528dc7` | API `00162-brg`, GCS 18:33 |
| PERF-002 Dashboard con una sola lectura | En uso: agregados principales unificados; opciones/meses aun aparte | Codex | Seis respuestas JSON equivalentes, hashes A/B/C iguales en canaria y publica; 17 planes en un `pl.collect_all`; pico local 1324 MB con una CPU | Produccion A 87.1 s, B 6.9 s, C 32.1 s | Cloud Run A 11.5 s, B 1.2 s, C 4.1 s; A publico 8.7 s con release cache | `8bf54ca` | Incluido en API `00168-9mj`; Job y Vercel alineados |
| PERF-003 Cache por generacion de datos | Completo: release inmutable, manifiesto y fallback sano | Codex | Release y generaciones abajo; QA de concurrencia/corrupcion; dashboard con SHA-256 exacto; Job pinneado al release | Cache por existencia; reconstruccion >180 s y colision concurrente 500 | Dashboard publico 8.7 s; opciones de reportes 1.5-2.0 s; 0 errores en canaria final | `2e5dc14`, `6b592d0`, `8ffb969`, `224c50d` | API `00168-9mj` al 100%; release `20260916T054421Z-59591cb8592a` |
| BQ-001 Dataset, esquemas y permisos | Pendiente | Por asignar | - | - | Pendiente | - | - |
| BQ-002 Carga versionada desde GCS | Pendiente | Por asignar | - | - | Pendiente | - | - |
| BQ-003 Conciliacion por fuente, cuenta y mes | Pendiente | Por asignar | - | - | Pendiente | - | - |
| DASH-001 Consultas y agregados en BigQuery | Pendiente | Por asignar | - | - | Pendiente | - | - |
| DASH-002 Comparacion y cambio gradual | Pendiente | Por asignar | - | - | Pendiente | - | - |
| REP-001 Lectura de informes desde BigQuery | Pendiente | Por asignar | - | - | Pendiente | - | - |
| REP-002 Equivalencia Excel/PDF y limites de detalle | Pendiente | Por asignar | - | - | Pendiente | - | - |
| QUEUE-001 Heartbeat y deteccion de procesos trabados | Pendiente | Por asignar | - | - | Pendiente | - | - |
| QUEUE-002 Concurrencia global y reintentos | Pendiente | Por asignar | - | - | Pendiente | - | - |
| ING-001 Ingesta durable y publicacion atomica | En curso: publicacion atomica completa; job durable y reintentos pendientes | Codex / por asignar | Manifiesto escrito despues de los objetos inmutables; canonicales de compatibilidad; release activo abajo | Seis sobrescrituras secuenciales sin puntero comun | API y nuevos Jobs leen una sola version; persistencia del job de ingesta pendiente | `2e5dc14`, `224c50d` | Release inicial activo en GCS; API/Job alineados |
| OPS-001 Metricas, alertas y despliegue | Completo: readiness, cinco alertas y bloqueo de despliegue | Codex | `/health/ready`; uptime cada minuto; politicas 5xx, p95, memoria y Job; Cloud Build verifica imagen, trafico, release y fallback | 0 politicas, 0 canales; p95 horario maximo 231.9 s, memoria p95 maxima 42.8%, 7 respuestas 5xx en 24 h | 5 politicas con correo operativo, readiness externo y gate reproducible | Entrega OPS-001 | Cloud Monitoring + siguiente revision API/Job |

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

La seleccion compartida en Cloud SQL estaba en version 25 y limitaba la vista
a `ada / indyana_records` durante la primera alineacion; Codex no la modifico.
Durante PERF-002 cambio a version 28: incluye todas las distribuidoras y
excluye solo `ada / mawz`. Ese estado compartido se conservo sin escribirlo.
El build completo
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

La muestra historica se tomo antes de alinear el trafico. En ese momento el
100% estaba en `vpo-corp-api-00161-rkc` (imagen `d4de3cf`). Una prueba funcional de
`royalties-dashboard` para 2026-06 devolvio HTTP 200 en 24.1 s; no se usa
como percentil ni como linea base representativa. Los casos testigo se
midieron luego en `00162-brg` y cerraron PERF-001.

## PERF-001: linea base productiva alineada

Medicion secuencial en la API publica el 2026-09-15, revision
`vpo-corp-api-00162-brg`, commit `7528dc7`, politica de distribuidoras v10,
con el paquete GCS publicado a las 18:33. Cada caso tiene una sola muestra;
sirve para equivalencia y comparacion inicial, no para percentiles ni SLA.

| Caso | Filtros | HTTP | Tiempo | USD | Filas origen | Huella SHA-256 de respuesta |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A | Ultimos 6 meses, statement period | 200 | 87.1 s | 217,532.25 | 3,306,103 | `5FCFAD5823E788449A1AB0A54A9AC0D3DC3D92B2A85C067FC66BD58DBC7B3D9B` |
| B | 2026-09, statement period | 200 | 6.9 s | 16,778.37 | 504,469 | `219BC4FC3F9EB9F853213C9569DB0E1F9168C1350E65E6360EA573FE8370E31A` |
| C | FUGA, ultimos 6 meses | 200 | 32.1 s | 118,863.91 | 2,914,425 | `F45273DF240576AC7C3A18A5E8D5F4D0B049EBFD306E1204E0913796B32CEA03` |

La version candidata `8bf54ca` dio objetos JSON identicos a la version
publica para A, B, C y tambien rango vacio, transaction month 2026-07 y
ADA junio. El caso A candidato tardo 15.0 s local con varios nucleos y
46.3 s con una CPU; el pico de memoria con una CPU y politica real fue
1324 MB. No extrapolar esas cifras directamente a Cloud Run (2 GiB, 1 CPU).
El trafico publico se fijo temporalmente a `00162-brg` para evaluar la
revision nueva sin exponerla hasta completar la prueba canaria. La revision
`00163-bmw` se activo mediante tag con 0% de trafico publico; la API publica
recupero despues el 100% a `LATEST` y el tag `dashboard-fastpath` tambien
apunta a esa revision.

## PERF-002: prueba canaria y despliegue

Cloud Build `3bb1f29a-39c9-4e00-a277-4efeb4107a9c` termino SUCCESS para
`8bf54ca`. API `vpo-corp-api-00163-bmw` y Job de reportes usan la misma
imagen; Vercel termino su despliegue. La candidata dio HTTP 200 y la misma
huella SHA-256 exacta que la linea base para A/B/C. Logs de Cloud Run:
3 requests, 0 errores, latencias 11.35 / 1.14 / 3.94 s. La prueba en cliente
incluye el traslado HTTP y fue 11.5 / 1.2 / 4.1 s.

| Caso | Antes `00162-brg` | Candidata `00163-bmw` | Despues, ruta publica | Equivalencia |
| --- | ---: | ---: | ---: | --- |
| A, ultimos 6 meses | 87.1 s | 11.5 s | 8.2 s | SHA-256 exacto |
| B, 2026-09 | 6.9 s | 1.2 s | Pendiente de muestra publica | SHA-256 exacto |
| C, FUGA 6 meses | 32.1 s | 4.1 s | Pendiente de muestra publica | SHA-256 exacto |

Tres repeticiones adicionales de A en la candidata: 9.4, 8.4 y 8.4 s,
HTTP 200 y USD 217,532.25. `/health`, Ingresos digitales, opciones de
reportes y web publica respondieron despues del cambio de trafico. Se
consultaron opciones de reportes, no se genero un reporte pesado. El pico
local de 1324 MB con una CPU exige vigilar memoria y 5xx productivos en
OPS-001; Cloud Monitoring a resolucion de un minuto no certifica el pico
de cada request. PERF-002 reduce la lectura costosa de los agregados, pero
todavia obtiene opciones y meses en pasos anteriores. PERF-003 cerro la cache
por generacion; los agregados materializados de BigQuery siguen pendientes.

## PERF-003: release atomico y cache por generacion

El 2026-09-16 se publico la primera version inmutable de los seis marts:

- release: `20260916T054421Z-59591cb8592a`;
- manifiesto: `marts/release_manifest.json`;
- generacion del manifiesto: `1789537689957898`;
- API final probada: `vpo-corp-api-00168-9mj`;
- commit funcional final: `224c50d`.

Los seis archivos locales fueron comparados por tamano y MD5 con los objetos
canonicos antes de crear el release; todos coincidieron. La validacion del
paquete dio OK. El publicador sube primero objetos bajo
`marts/releases/<release_id>/`, conserva nombres canonicos para consumidores
anteriores y activa el manifiesto solo cuando el paquete inmutable existe.
Desde el segundo release, el manifiesto anterior permanece activo hasta que
terminan todas las copias de compatibilidad y el manifiesto nuevo se escribe
al final.

La API consulta la generacion del manifiesto cada 15 segundos, descarga en un
staging unico, valida tamano y metadata Parquet, y mueve el archivo a una
carpeta identificada por release/generacion antes de cambiar el puntero local.
Solicitudes concurrentes de una instancia comparten un lock. La QA simulo
ocho solicitudes simultaneas y realizo una sola descarga; tambien publico un
archivo corrupto y comprobo que se mantuviera la version sana anterior.
`/health` expone release, generacion, fallback y ultimo error. Los marts
auxiliares de informes especiales se cachean individualmente por generacion.

Dashboard e Ingresos digitales ya no reconstruyen resumenes dentro del GET
productivo. En la candidata y despues en la ruta publica, el dashboard de seis
meses conservo la huella SHA-256 exacta de PERF-001. Resultado publico final:
HTTP 200 en 8.7 s, release correcto, sin fallback ni error. Source Monitor,
Ingresos digitales, web y opciones de reportes respondieron.

Durante la canaria, `/reports/custom/options` mostro un 503 por memoria al leer
783 MB solo para obtener distribuidoras/cuentas. El trafico seguia en la
revision anterior. Se comprobo que `song_level` contiene exactamente las 10
combinaciones de `standardized`; la ruta paso a ese mart compacto y bajo a
1.5-2.0 s. La revision final tuvo 0 errores 5xx en la canaria. No se genero un
reporte pesado. Los nuevos Jobs congelan `song`, `standardized` y
`catalog_master` desde el release inmutable, y `catalog_status` por su propia
generacion canonica.

PERF-003 queda completo. ING-001 queda parcial: la publicacion del paquete ya
es atomica, pero el estado del proceso de ingesta/publicacion todavia vive en
memoria y faltan persistencia, heartbeat y reintentos. Tambien falta definir
retencion/limpieza de releases antiguos para controlar almacenamiento.

## Proxima decision E1/E2

`PERF-001`, `PERF-002`, `PERF-003` y `OPS-001` ya tienen implementacion y
evidencia productiva. El siguiente paso recomendado es iniciar `BQ-001` y
`BQ-002` en paralelo, manteniendo A/B/C y los bordes como casos de equivalencia.
La parte restante de `ING-001` se coordina con `QUEUE-001` y `QUEUE-002` para
persistir estado, heartbeat, concurrencia global y reintentos.
