# Cambio gradual del dashboard a BigQuery

## Objetivo

Mover solamente `/royalties-dashboard` desde los Parquet publicados hacia
BigQuery, sin cambiar el contrato que consume la pantalla. La ruta sombra se
mantiene para diagnostico y el resto del sistema conserva sus lectores
actuales.

## Controles

- `VPO_ROYALTIES_DASHBOARD_BACKEND=parquet|bigquery` elige el motor.
- `VPO_ROYALTIES_DASHBOARD_BIGQUERY_FALLBACK=1` vuelve automaticamente a
  Parquet si BigQuery falla.
- `VPO_BIGQUERY_MAX_BYTES_BILLED=5000000000` bloquea consultas que excedan el
  presupuesto tecnico esperado.
- `X-VPO-Dashboard-Backend` identifica `bigquery`, `parquet` o
  `parquet-fallback` en cada respuesta.
- `/health/ready` expone la configuracion activa del dashboard.
- Los logs `royalties_dashboard_backend` registran resultado, latencia y tipo
  de error sin guardar filtros ni datos del usuario.
- Cada consulta resuelve primero la version `ready` de `current_release` y
  pasa ese identificador como parametro a `royalty_dashboard_rankings`. Las
  opciones y los importes leen la misma version. El filtro explicito permite
  omitir bloques de versiones historicas sin borrar respaldos ni aumentar el
  limite de bytes. Si no existe una version conciliada, se usa el retorno
  operativo existente; nunca se consulta una version pendiente de validacion.

## Secuencia de activacion

1. Desplegar el codigo con `parquet` y comprobar salud y alineacion.
2. Crear una revision sin trafico con `bigquery`, fallback activo y tag
   `dashboard-bigquery-canary`.
3. Comparar los casos A-H contra la revision publica y guardar la evidencia.
4. Verificar que todas las respuestas canarias indiquen `bigquery`, sin usar
   el fallback.
5. Asignar 10% del trafico a la candidata y observar errores y latencia.
6. Subir a 50% y luego a 100% si no aparecen diferencias ni fallas.
7. Fijar `bigquery` en `cloudbuild.yaml` para que el siguiente despliegue no
   cambie accidentalmente el motor.

## Retorno inmediato

El retorno operativo consiste en asignar nuevamente 100% del trafico a la
ultima revision Parquet verificada. Si BigQuery presenta una falla aislada,
el fallback ya evita que la pantalla deje de responder. Luego del retorno se
restaura `VPO_ROYALTIES_DASHBOARD_BACKEND=parquet` en la plantilla del servicio
antes del siguiente despliegue automatico.
