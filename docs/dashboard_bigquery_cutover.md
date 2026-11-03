# Cambio gradual del dashboard a BigQuery

## Objetivo

Mover solamente `/royalties-dashboard` desde los Parquet publicados hacia
BigQuery, sin cambiar el contrato que consume la pantalla. La ruta sombra se
mantiene para diagnostico y el resto del sistema conserva sus lectores
actuales.

## Controles

Desde la conservacion de contexto de video de noviembre de 2026, los rankings
base y la tabla actualizada por catalogo incluyen `video_id`, `channel_id` y
`video_id_source`. Son identificadores nativos validados. Las claves anteriores
de admision y las dimensiones que muestra la pantalla permanecen iguales.
Los agregados por tema conservan ademas `statement_month`, DSP, monetizacion,
origen y estado de clasificacion, separados del mes de consumo.
La ampliacion del schema es aditiva; los historiales se preparan desde los
objetos publicados e inmutables y solo se activan despues de conciliar dinero,
unidades y filas economicas por fuente, cuenta, fecha y origen. El catalogo y las
asociaciones humanas se mantienen. Las clasificaciones existentes no se vuelven
a inferir como parte de esta reparacion de columnas.

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

## Rankings completos del dashboard

El resumen de ingresos por tema y por artista permite recorrer todos los
resultados del filtro en listas independientes de hasta 360 px, con encabezado
visible y scroll por rueda, tacto o teclado. La web solicita
`full_catalog_rankings=true` tanto en el resumen normal como en la exploracion
contractual. BigQuery y el retorno Parquet aplican esta opcion solo a los
rankings generales de temas y artistas; mantienen filtros, permisos, totales y
el limite existente para las otras categorias y YouTube. Sin la opcion se
conserva el limite anterior.

Las listas generales de temas y artistas dibujan solamente las filas visibles
y cuatro filas adicionales a cada lado de la ventana. El espacio restante
conserva la altura del listado completo y permite llegar al ultimo resultado
con la rueda, el pulgar del scroll, tacto o teclado. El desplazamiento se
actualiza dentro de cada lista, sin reconstruir el dashboard. Los formatos
numericos se reutilizan y la ventana vuelve al inicio al cambiar los datos.
Las pruebas de fluidez cubren tambien el scroll de la pagina completa con
miles de resultados, ademas de los clics, filtros y listas pequenas o vacias.

## Retorno inmediato

El retorno operativo consiste en asignar nuevamente 100% del trafico a la
ultima revision Parquet verificada. Si BigQuery presenta una falla aislada,
el fallback ya evita que la pantalla deje de responder. Luego del retorno se
restaura `VPO_ROYALTIES_DASHBOARD_BACKEND=parquet` en la plantilla del servicio
antes del siguiente despliegue automatico.
