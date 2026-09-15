# Orden de analitica y reportes - seguimiento

Inicio: 2026-09-15. Punto de partida Git: `3dd62a4f489e71bd83e726de7e8ed8c12bd38c05`.

## Objetivo

Dashboard estable y reportes rapidos sin cambiar importes, filtros, politicas
ni estructura de los archivos entregados. Cloud SQL sigue siendo la fuente
operativa; GCS conserva originales y Parquet; BigQuery sera la capa de consulta
analitica, primero en modo sombra.

## Baseline anterior al cambio

Mediciones de la auditoria del 2026-09-14, no una prueba nueva de produccion:

| Indicador | Valor anterior |
| --- | ---: |
| Dashboard directo en produccion | 80.8 s |
| Dashboard local perfilado | 30.97 s; 36 `collect()` |
| Dashboard local, lectura unica prototipo | 0.275 s; 796,312 filas |
| Resumen dashboard | 2,926,602 filas; 43.61 MB Parquet |
| Raw de reportes | 11,248,318 filas; 709.24 MB Parquet |
| Reporte trimestral reciente | aprox. 6 min total |
| Reporte historico reciente | aprox. 9-22 min total |
| API ordinaria caliente | aprox. 0.5-0.7 s |
| API health fria | 16.6 s |

Caso testigo local sin conexion a Cloud SQL: marzo-agosto 2026 por statement,
`amount_usd=231926.02`, `rows=2625891`, meses 2026-03 a 2026-08. Se
desactiva la personalizacion en esta prueba para aislar el calculo analitico;
el control con politica productiva y la medicion cloud pertenecen al gate E1.

Medicion directa de produccion el 2026-09-15, antes del cambio: respuesta 200
en 99.64 s, `amount_usd=208952.32`, `rows=2625891`, mismos seis meses.
La diferencia de importe con el caso local refleja la personalizacion vigente;
este es el testigo cloud para el canary.

## Gates

- E1: dashboard caliente p95 menor a 3 s, sin rechazo de rutas ordinarias
  durante dos consultas simultaneas; cifras iguales a casos testigo.
- E2: BigQuery shadow concilia filas, unidades e importes por fuente, cuenta
  y mes, con publicacion idempotente y sin cambio de UI.
- E3: dashboard BigQuery caliente p95 menor a 2 s, frio p95 menor a 10 s;
  ninguna diferencia de importes, rankings o filtros en canary.
- E4: reporte de hasta tres meses menor a 90 s y reporte historico menor a
  3 min, preservando contenido y politicas.
- E5: cero falsos fallidos, recuperacion de proceso y cola visible.
- E6: ingesta durable, versionada y reversible, independiente de `/tmp`.

E1 quedo mitigada, no cerrada por SLO: las vistas repetidas son rapidas y el
canary concurrido ya no cae, pero filtros amplios no cacheados aun superan 3 s.
El p95 requiere una muestra real de uso y no se infiere de estos probes.

## Entrega 2026-09-15

Revision API productiva: `vpo-corp-api-00160-fen`, 100% de trafico. Rollback:
`vpo-corp-api-00155-zf8`. Imagen ensayada:
`sha256:13c1eb51ec5d9cd692d2b38d6730bdf6fe307b38915987be57dd424f1290c85a`.
Configuracion nueva: concurrencia 1, maximo 3 instancias, minimo 0; no hay
capacidad encendida permanentemente por este cambio.
Codigo guardado en rama `codex/dashboard-fastpath-20260915`. El trigger de
Cloud Build despliega automaticamente todo `main` y aun no corre QA; antes de
integrar esta rama hay que agregar gates de prueba o confirmar un despliegue
supervisado para que otra publicacion no reponga la revision antigua.

| Prueba | Resultado |
| --- | ---: |
| Vista general anterior, directo | 99.64 s |
| Vista general nueva, primera desde URL normal | 10.74 s |
| Vista general nueva, repetida | 0.23 s |
| Flor Alvarez, primera nueva | 1.56 s |
| Flor Alvarez, repetida | 0.26 s en canary |
| Fuente fuga, nueva sin cache | 4.28 s |
| Base de transaccion, nueva sin cache | 6.66 s |
| Historico total de transacciones, nuevo | 34.36 s individual; 44.06 s en paralelo |
| Dos historicos + health en canary | 200/200/200; health 0.27 s |

La prueba previa con concurrencia 4 en una sola instancia produjo dos 503:
Cloud Run registro 2076 MiB sobre el limite de 2048 MiB y termino el proceso.
La revision `00160` aisla los calculos; la prueba equivalente no produjo 503.
No se han modificado reglas de regalias ni artefactos de reportes.

## Tareas

Estados: `pendiente`, `en curso`, `bloqueada`, `lista`. Cada cierre debe
guardar prueba, tiempo antes/despues, commit y revision publicada.

| ID | Tarea | Estado | Evidencia / siguiente paso |
| --- | --- | --- | --- |
| PERF-001 | Baseline y casos testigo | lista | Documento, fixture QA y prueba productiva con politica vigente |
| PERF-002 | Dashboard con una materializacion | lista | QA y revision `00160`; totales productivos iguales |
| PERF-003 | Cache por generacion GCS | en curso | QA de cambio pasa; falta observar una publicacion GCS real |
| PERF-004 | Aislar consultas y escalar bajo demanda | lista | Concurrencia 1, max 3; prueba simultanea 200/200/200 |
| PERF-005 | SLO para filtros amplios | pendiente | Historico completo aun 34-44 s; resolver con BQ |
| BQ-001 | Dataset, schemas y IAM | pendiente | Validar ubicacion GCS/BigQuery antes de crear |
| BQ-002 | Carga versionada GCS a tablas nativas | pendiente | Modo sombra; sin cambio de API |
| BQ-003 | Conciliacion automatica | pendiente | Fuente, cuenta, mes, filas, unidades, importes |
| DASH-001 | Agregados y consultas BigQuery | pendiente | Parametrizar filtros, release y policy version |
| DASH-002 | Canary y cambio gradual | pendiente | Comparar JSON en casos testigo |
| REP-001 | Reportes leen filtros en BigQuery | pendiente | Evitar descarga completa de 711 MB |
| REP-002 | Equivalencia de Excel/PDF | pendiente | Comparar importes, detalle y politicas |
| QUEUE-001 | Heartbeat durable | pendiente | Reemplazar umbral fijo de 35 min |
| QUEUE-002 | Concurrencia global y reintentos | pendiente | Gate de fallas forzadas |
| ING-001 | Ingesta cloud y publicacion atomica | pendiente | Versiones y rollback |
| OPS-001 | Migraciones, QA en build, alertas | pendiente | Evitar DDL runtime y regresiones |

## Orden de trabajo

1. Cerrar PERF-001 a PERF-003 y medir E1 en produccion.
2. Construir BQ-001 a BQ-003 en sombra, sin tocar la pantalla.
3. Cambiar dashboard con DASH-001 y DASH-002.
4. Migrar lectura de reportes con REP-001 y REP-002.
5. Cerrar cola, ingesta y deuda operativa.

Rollback E1: revision anterior de Cloud Run. Rollback E3: apuntar la lectura
a la ultima release aprobada o restaurar la revision anterior mientras dure
el canary. Nunca borrar los Parquet canonicamente publicados.
