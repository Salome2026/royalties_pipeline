# Trabajos de reportes de regalias

## Objetivo

La generacion de un reporte no debe depender de que el navegador mantenga una
conexion abierta. Los reportes pueden leer marts grandes y superar el tiempo
maximo de una funcion web intermedia.

El calculo economico y las hojas del reporte no cambian. Este modelo solo
ordena la ejecucion, persistencia y entrega del resultado.

## Flujo rector

1. El usuario solicita el reporte desde `Reporte de regalias`.
2. La API valida el permiso `royalty_reports.create`.
3. Se registra un unico trabajo en `report_runs`, dentro de Cloud SQL.
4. En cloud, Cloud Tasks entrega el trabajo al mismo backend de Cloud Run.
5. El worker usa los builders vigentes y los marts publicados en GCS.
6. El resultado se guarda en GCS bajo `reports/jobs/<id>/`.
7. La pantalla consulta el estado y habilita la descarga al terminar.

Localhost y cloud comparten la misma tabla de trabajos y los mismos builders.
Localhost ejecuta el worker en segundo plano dentro de la API local; cloud usa
Cloud Tasks para no depender de la vida de una peticion del navegador.

## Estados

- `queued`: recibido y pendiente de ejecucion.
- `running`: el worker lo tomo.
- `completed`: resultado persistido y disponible.
- `failed`: finalizo con un error visible para el usuario.

`progress_stage` informa una etapa humana (`preparing`, `reading_data`,
`building`, `uploading`, `completed`) sin inventar un porcentaje cuando no se
puede medir con precision.

## Seguridad y permisos

- Crear requiere `royalty_reports.create`.
- Consultar y descargar requiere `royalty_reports.access`.
- Un usuario solo ve sus trabajos; un administrador puede auditar todos.
- El endpoint del worker no usa la sesion del usuario. Exige un secreto interno
  exclusivo de Cloud Tasks.
- Los parametros y estados viven en Cloud SQL; el archivo final vive en GCS.
- No se guardan marts ni resultados en Vercel.

## Duplicados y recuperacion

Si el mismo usuario repite exactamente el mismo pedido mientras esta en cola o
ejecutandose, se devuelve el trabajo existente. Los trabajos terminados o
fallidos no bloquean una nueva solicitud.

La pantalla muestra trabajos recientes. El usuario puede salir y volver sin
perder el resultado.

## Operacion y costo

- Cola: una ejecucion simultanea.
- Cloud Run: concurrencia 1 y maximo una instancia para este primer corte.
- Tiempo maximo del worker: 30 minutos.
- Resultados: vigencia operativa de 30 dias.

Subir CPU o memoria puede acelerar el trabajo, pero no reemplaza este modelo.
La optimizacion posterior debe enfocarse en particionar o resumir marts, sin
cambiar la semantica de los reportes.
