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
| BQ-001 Dataset, esquemas y permisos | Completo: capa analitica sombra creada en US | Codex | Dataset `royalties_analytics`; 10 tablas, 3 vistas; particiones mensuales, clustering y permisos de lectura/consulta para API y Job | No habia datasets ni tablas BigQuery | Esquema completo validado y disponible sin cambiar lectores productivos | `861714f`, `9d601d6` | BigQuery `vpo-corp-royalties.royalties_analytics` |
| BQ-002 Carga versionada desde GCS | Completo: release vigente cargado y validado | Codex | Release `20260916T065558Z-4270970b55a3`; objetos curados inmutables en GCS; carga transaccional; conteos e importes conciliados a centavos | 0 releases en BigQuery | 12,355,023 movimientos y 3,194,911 filas de dashboard disponibles | `861714f` | BigQuery release `ready`; consumido por el dashboard desde DASH-002 |
| BQ-003 Conciliacion por fuente, cuenta y mes | Completo: control automatico y persistente | Codex | Run `20260916T150010Z-ae47e0ab`; 757 grupos; 0 diferencias; informe y resultados inmutables en GCS/BigQuery | Solo validacion global de filas e importes | 306 grupos statement y 451 transaction conciliados; assets contados por ISRC | `9d601d6` | Release BigQuery `ready`; futuras cargas quedan bloqueadas hasta conciliar |
| DASH-001 Consultas y agregados en BigQuery | Completo y promovido por DASH-002 | Codex | Ocho casos A-H equivalentes campo por campo en local y Cloud Run; ruta `/royalties-dashboard/bigquery-shadow`; opciones, matriz, rankings y YouTube | Parquet: A 8.7 s caliente; historico amplio puede superar un minuto | BigQuery productivo caliente: 1.05-1.58 s; frio local 3.5-8.5 s; respuestas exactas | `6cc60e7` | Sombra en API `00176-8cm`; activado en `00197-vav` por DASH-002 |
| DASH-002 Comparacion y cambio gradual | Completo: BigQuery activo con fallback automatico | Codex | Casos A-H equivalentes; canaria 8/8 sin fallback; trafico 10/50/100; evidencia JSON; salud y modulos vecinos verificados | Parquet: 6m 8.1 s caliente; ISRC historico 89.9 s | BigQuery: 6m 1.8-1.9 s; ISRC 1.25 s canaria y 1.50-2.23 s caliente publico | `2f44372` + cierre DASH-002 | API `00197-vav` al 100%; Job alineado en `2f44372`; rollback `00178-jrz` |
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

`PERF-001`, `PERF-002`, `PERF-003`, `OPS-001`, `BQ-001`, `BQ-002`, `BQ-003` y
`DASH-001` ya tienen implementacion y evidencia. BigQuery permanece en modo
sombra: el dashboard productivo y los reportes siguen leyendo el release
Parquet/GCS. El siguiente paso recomendado es `DASH-002`, ejecutando
comparaciones productivas sostenidas, canaria y cambio gradual con rollback.
La parte restante de `ING-001` se coordina con `QUEUE-001` y `QUEUE-002` para
persistir estado, heartbeat, concurrencia global y reintentos.

## BQ-001/BQ-002: base analitica sombra

El 2026-09-16 se creo el dataset `vpo-corp-royalties.royalties_analytics` en
`US`, la misma ubicacion multirregional del bucket. Contiene diez tablas y tres
vistas. Las tablas de hechos y agregados mensuales estan particionadas por mes
y agrupadas por release, fuente, cuenta y la dimension de busqueda principal.
Las cuentas de servicio de la API/publicador y del Job de reportes tienen
permiso para ejecutar consultas y leer el dataset. Todavia no se modifico
ningun endpoint para usar BigQuery.

La primera carga usa el manifiesto GCS activo y crea Parquet curados e
inmutables bajo
`marts/analytics/releases/20260916T065558Z-4270970b55a3/`. La escritura final
en BigQuery se realiza dentro de una transaccion y solo despues marca el
release como `ready`. Resultado verificado:

| Tabla logica | Filas | Importe USD |
| --- | ---: | ---: |
| Detalle de statements | 12,355,023 | 1,241,535.146556282 |
| Rankings de dashboard | 3,194,911 | 1,175,269.4029890413 |
| Canciones | 81,325 | - |
| Catalogo | 3,031 | - |
| Ingresos digitales | 27,210 | - |
| Dashboard mensual | 2,794 | - |

BigQuery devolvio los mismos conteos. Los importes de las columnas `FLOAT64`
pueden variar en millonesimas por el orden de suma distribuida; la validacion
operativa exige igualdad a un centavo. Una consulta representativa del
dashboard para seis meses tiene un limite estimado de 44,023,631 bytes
procesados. El procedimiento reproducible y los comandos de recuperacion
quedan en `docs/bigquery_shadow.md`.

## BQ-003: conciliacion por fuente, cuenta y mes

La ejecucion valida `20260916T150010Z-ae47e0ab` comparo el release vigente en
Parquet contra BigQuery en 757 grupos: 306 por mes de statement y 451 por mes
de transaccion. No hubo diferencias de filas, unidades, cantidad de ISRC,
filas sin ISRC ni grupos de titulos con multiples ISRC. La diferencia monetaria
maxima fue menor a USD 0.000000002, ampliamente dentro de la tolerancia de un
centavo.

La identidad de asset es el ISRC. Un mismo titulo asociado a dos ISRC se trata
como dos assets distintos; el titulo es descriptivo y nunca se utiliza para
fusionar o deduplicar grabaciones. El control registro 4,376 apariciones
mensuales de titulos con multiples ISRC entre ambas bases temporales y las
concilio sin marcarlas como error.

La carga BigQuery ahora deja cada release en estado `loaded`, ejecuta
automaticamente la conciliacion y solo lo cambia a `ready` cuando el resultado
no tiene diferencias. Un resultado fallido queda en
`reconciliation_failed`, conserva su evidencia y hace fallar el proceso de
carga. Los resultados se guardan en las tablas
`analytics_reconciliation_runs` y `analytics_reconciliation_results`, ademas
de objetos inmutables en GCS.

## DASH-001: dashboard BigQuery en sombra

El contrato completo de `/royalties-dashboard` se implemento con una sola
consulta BigQuery. Incluye opciones de fuente/cuenta, seleccion temporal,
totales, meses, matriz, nueve rankings, YouTube, busqueda normalizada y los
ajustes porcentuales vigentes por distribuidora/cuenta. La ruta separada
`/royalties-dashboard/bigquery-shadow` usa el mismo API key y no esta conectada
al frontend.

Los casos A-F originales, la busqueda historica por ISRC y el filtro combinado
ADA/Indyana junio produjeron respuestas equivalentes campo por campo contra el
endpoint Parquet. En una segunda corrida, los seis casos base tardaron entre
1.19 y 2.00 segundos con cache BigQuery; la busqueda historica por ISRC tardo
8.49 segundos en frio. Las consultas sin cache procesaron hasta 1,572.94 MB;
las repeticiones servidas por cache procesaron 0 bytes.

`DASH-001` no cambia produccion. `DASH-002` debe probar la ruta sombra ya
desplegada, registrar diferencias y latencias durante una ventana suficiente,
habilitar una canaria y conservar rollback inmediato a Parquet.

La verificacion posterior al despliegue en API `vpo-corp-api-00176-8cm`
repitio los ocho casos contra ambas rutas. Todos fueron equivalentes. La ruta
BigQuery respondio entre 1.05 y 1.58 segundos, incluida la busqueda historica
por ISRC en 1.54 segundos. La espera prolongada observada durante esa prueba
correspondio a la ruta Parquet usada como referencia, no a BigQuery.

## DASH-002: comparacion y cambio gradual

La revision `vpo-corp-api-00197-vav` se creo sin trafico con BigQuery como
motor, fallback automatico a Parquet y un limite de 2.5 GB procesados por
consulta. Los ocho casos A-H coincidieron campo por campo con la revision
Parquet `00178-jrz`. La canaria registro ocho resultados `ok`, ningun fallback
y ningun error. La evidencia reproducible esta en
`docs/dashboard_bigquery_cutover_evidence_20260916.json`.

El trafico se traslado de 0% a 10%, 50% y 100%. En 10% hubo 20/20 respuestas
HTTP 200, cuatro atendidas por BigQuery y el mismo total en todas. En 50% hubo
16/16 respuestas HTTP 200, diez BigQuery y seis Parquet, tambien con importes
identicos. La ruta publica quedo finalmente al 100% en BigQuery.

En la comparacion A-H, BigQuery tardo entre 1.25 y 2.60 segundos. El caso de
seis meses bajo de 8.12 a 1.80 segundos y la busqueda historica por ISRC bajo
de 89.90 a 1.25 segundos. Despues del cambio, tres repeticiones publicas del
ISRC tardaron 1.50, 2.23 y 2.08 segundos. El primer acceso publico en una
instancia fria tardo 15.98 segundos; las siguientes respuestas confirmaron el
comportamiento caliente esperado.

`/health/ready` informa `backend=bigquery`, release
`20260916T065558Z-4270970b55a3`, base operativa sana y cache sin fallback.
Ingresos Digitales respondio en 1.49 segundos y las opciones de reportes en
2.82 segundos. El rollback inmediato conserva la revision Parquet
`vpo-corp-api-00178-jrz`; ademas, una falla aislada de BigQuery usa Parquet
automaticamente sin exponer un error al usuario.
