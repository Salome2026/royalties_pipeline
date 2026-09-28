# Checklist unificado: rendimiento, BigQuery, reportes e ingesta

Estado al 2026-09-28. Este documento une el plan E0-E7 con el trabajo reciente
de reportes. El detalle de mediciones, responsables, commits y despliegues
permanece en `docs/dashboard_bigquery_followup_20260915.md`. Un check de tarea
completa exige evidencia y prueba, no solo codigo escrito.

## Estado de los 14 codigos originales

### Cerrados (8)

- [x] `PERF-001` Linea base y casos testigo del dashboard.
- [x] `PERF-003` Cache por release/generacion y publicacion versionada.
- [x] `BQ-001` Dataset, tablas, vistas y permisos analiticos.
- [x] `BQ-002` Carga versionada GCS a BigQuery.
- [x] `BQ-003` Conciliacion automatica por fuente, cuenta y mes.
- [x] `DASH-001` Consultas del dashboard en BigQuery.
- [x] `DASH-002` Comparacion, canaria y cambio productivo con fallback.
- [x] `OPS-001` Readiness, alertas y control del despliegue.

### Parciales (4)

- [ ] `PERF-002` Agregados centrales unificados; opciones y meses siguen por
  consultas separadas. Medir antes de optimizar el resto.
- [ ] `REP-001` Seis Excel testigo congelados y respaldados; el generador
  productivo aun lee Parquet/GCS, no BigQuery.
- [ ] `QUEUE-001` Heartbeat y conciliacion terminal publicados; falta observar
  un informe productivo que permanezca en construccion mas de un minuto.
- [ ] `ING-001` Publicacion atomica/versionada lista; falta ingesta durable,
  reiniciable y con reintentos.

### Sin iniciar (2)

- [ ] `REP-002` Equivalencia completa Excel/PDF, limites y orden del detalle.
- [ ] `QUEUE-002` Concurrencia global y reintentos seguros.

## Orden de trabajo propuesto

### 1. Cerrar la observacion de la cola

- [x] `QUEUE-001` Evitar el falso fallo por 35 minutos sin cambio de etapa;
  consultar Cloud Run antes de declarar interrumpida una ejecucion. API y Job
  publicados juntos en imagen `7651cb3`; revision API `00199-vpl`.
- [x] `QUEUE-001` Probar una ejecucion nueva de punta a punta: job 76, 5m31s
  en espera y 28s de ejecucion, archivo de 6048 bytes con SHA-256 verificado.
- [ ] `QUEUE-001` Observar `updated_at` durante un informe real que tarde mas
  de un minuto en una misma etapa; confirmar que siga `running` y termine en
  `completed` o en un error autentico de Cloud Run. Registrar job y tiempos.
- [ ] `QUEUE-002` Investigar los 5m31s de espera del job 76 por separado del
  tiempo de calculo. Medir varias ejecuciones y distinguir frio/provisionamiento,
  capacidad, concurrencia y errores antes de cambiar limites.

### 2. Preparar el lector BigQuery de informes, sin cambiar produccion

- [x] `REP-001` Conservar seis informes originales con release, policy, filas,
  importes, unidades y SHA-256; copias privadas verificadas en GCS. Ver
  `docs/royalty_report_baseline_20260928.md`.
- [ ] `REP-001` Fijar el contrato exacto de columnas y filtros del reporte:
  periodo, fuente/cuenta, artista, titulo e ISRC. El ISRC identifica el asset;
  dos ISRC con el mismo titulo no se fusionan.
- [ ] `REP-001` Consultar BigQuery con el `release_id` y la policy congelados en
  el pedido, sin leer el release vigente por accidente ni descargar todos los
  Parquet. Revisar bytes facturados y costo por caso.
- [ ] `REP-001` Habilitar un lector sombra o flag interno: mismo pedido, salida
  antigua y nueva separadas, sin cambiar el motor publico.

### 3. Demostrar equivalencia antes de activar reportes nuevos

- [ ] `REP-002` Comparar los seis testigos Excel hoja por hoja: totales USD,
  unidades, filas, meses, territorios, fuentes/cuentas y claves ISRC. Resolver
  explicitamente diferencias de redondeo y orden estable del detalle.
- [ ] `REP-002` Probar los tres modos de detalle: limitado 0-50000 filas, cinco
  paises elegidos por dinero y completo. Contar antes de exportar y avisar si
  excede las 1048575 filas de datos de una hoja Excel; no generar un archivo
  truncado en silencio.
- [ ] `REP-002` Agregar testigos actuales de PDF ejecutivo y Google Sheets si
  ambos formatos entran en el primer cambio. Verificar formato, importes y
  enlaces/descarga, no solo el total general.
- [ ] `REP-001/002` Medir tiempos de un trimestre y de un historico amplio.
  Metas originales: menos de 90s y 3 min respectivamente, separando espera de
  cola y calculo. No prometer estas metas hasta medirlas.
- [ ] `REP-001/002` Activar por etapas, con comparacion automatica, fallback y
  vuelta inmediata al lector anterior. Registrar revision y resultados.

### 4. Robustecer la operacion

- [ ] `QUEUE-002` Definir limite global de trabajos simultaneos y una cola que
  no dependa de la memoria de una instancia API.
- [ ] `QUEUE-002` Reintentar solo fallas transitorias, con backoff y un maximo
  definido. Errores de datos o limite Excel no se reintentan automaticamente.
- [ ] `QUEUE-002` Probar idempotencia: mismo pedido no duplica jobs, archivos
  ni estados terminales. Simular cierre abrupto del contenedor.
- [ ] `ING-001` Guardar estado y progreso de ingesta en almacenamiento durable;
  poder reiniciar despues de una caida y reconocer archivos ya procesados.
- [ ] `ING-001` Conservar la publicacion atomica, conciliar antes de activar el
  release, probar rollback y definir retencion/limpieza de releases antiguos.
- [ ] `ING-001` Mostrar fin, error y version publicada de cada carga sin tener
  que adivinar cuando termina.

### 5. Cerrar deuda tecnica sin frenar las mejoras anteriores

- [ ] `PERF-002` Medir p95 de opciones/meses y eliminar lecturas redundantes
  solo si siguen afectando la experiencia.
- [ ] `E7` Auditar DDL y cambios de esquema todavia presentes en rutas de la
  API; mover lo productivo a migraciones formales y retirar compatibilidad
  obsoleta con pruebas de Booking, finanzas y reportes.
- [ ] `E7` Revisar permisos minimos, retencion de artefactos y costos BigQuery/
  Cloud Run; mantener los controles de salud y despliegue ya activos.

## Regla de cierre

Para marcar una tarea como completa, registrar: `estado`, `responsable`,
`evidencia`, `metrica anterior`, `metrica nueva`, `commit` y `despliegue` en el
tablero original. Ningun cambio de motor debe modificar importes, unidades o
identidad de assets sin una diferencia explicada y aprobada.

Los cambios visuales ya aprobados de Ingresos Digitales y Booking no son
pendientes de esta migracion. Permanecen en uso y deben incluirse en las
pruebas de regresion cuando se publique una nueva version de la API.
