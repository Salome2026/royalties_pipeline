# Contrato rector de trabajos de reportes de regalias

## Autoridad y estado

Este documento define el destino aprobado para la generacion de reportes
pesados. Manda sobre notas anteriores que describan ejecucion local, threads,
Cloud Tasks o un endpoint HTTP de worker dentro de la API.

Contrato aprobado: `2026-09-02`.

Estado de implementacion: vigente en produccion desde `2026-09-03`. El motor,
sus contratos, builders, publicacion de artefactos y ejecucion viven en
`app/royalty_reports/`. Las migraciones `011_report_runs_definitive_contract` y
`012_cloud_run_report_job_cutover` fueron aplicadas a Cloud SQL y preservaron
los cuatro trabajos anteriores. La API y la pantalla disparan exclusivamente el
Cloud Run Job `vpo-royalty-report-job`; Cloud Tasks, el endpoint HTTP de worker,
la ejecucion local y las rutas sincronas reemplazadas fueron retirados.

## Objetivo

La API operativa no genera archivos ni mantiene una peticion abierta durante el
calculo. Su responsabilidad termina al validar al usuario, congelar el pedido,
registrarlo y solicitar una ejecucion de Cloud Run Jobs.

La semantica economica, las policies de distribuidoras, la identidad de catalogo,
los filtros de periodo y las hojas de cada reporte siguen definidas por sus
documentos rectores. Este contrato define ejecucion, persistencia, seguridad y
entrega; no redefine importes.

## Una verdad por responsabilidad

- Cloud SQL PostgreSQL es la verdad operativa de pedidos, estados, permisos y
  auditoria de ejecuciones.
- GCS contiene los marts publicados que alimentan el reporte y los artefactos
  finales con retencion controlada.
- Los documentos rectores y las policies operativas vigentes determinan la
  interpretacion de los datos.
- Cloud Run Jobs aporta computo aislado. No es una base ni conserva estado entre
  ejecuciones.
- Vercel presenta la interfaz. No procesa, almacena ni retransmite archivos
  pesados.

No se crea una copia operativa en SQLite, JSON local o filesystem de Vercel.

## Componentes definitivos

### API operativa `vpo-corp-api`

Responsabilidades:

1. autenticar la sesion y validar permisos;
2. validar y normalizar el pedido;
3. resolver la version publicada de datos y policies;
4. crear una fila en `report_runs`;
5. ejecutar el recurso Cloud Run Job con solo el `report_run_id`;
6. devolver estado y metadata;
7. autorizar una descarga y emitir una URL de GCS de corta duracion.

La API no importa Polars para construir el reporte dentro de estos endpoints y
no descarga el resultado a `/tmp` para enviarlo al navegador.

### Cloud Run Job `vpo-royalty-report-job`

Responsabilidades:

1. recibir unicamente `report_run_id` como argumento o variable de ejecucion;
2. leer el pedido confiable desde Cloud SQL;
3. reclamar atomicamente el trabajo;
4. leer desde GCS las versiones congeladas de los marts;
5. ejecutar el builder registrado para `report_key`;
6. guardar el artefacto final en GCS;
7. registrar metadata, checksum y estado final en Cloud SQL;
8. terminar el contenedor.

El Job no expone una URL publica y no recibe filtros enviados directamente por
el navegador.

Despliegue validado el `2026-09-03`:

- region: `us-central1`;
- imagen inmutable compartida con la API:
  `sha256:b30b9a60a63745efca6b5f44527c18c45152511d254a72815af2c87200180d2c`;
- service account:
  `vpo-royalty-report-job@vpo-corp-royalties.iam.gserviceaccount.com`;
- recursos: `2 CPU`, `4 GiB`, timeout `3600 s`;
- una tarea, paralelismo `1`, sin reintento automatico;
- Cloud SQL por socket a `vpo-corp-postgres-ssd`;
- entrada desde `marts/` y salida en `reports/jobs/` del bucket operativo;
- secretos permitidos: password de PostgreSQL y token OAuth necesario para
  el formato Google Sheets.

Las pruebas reales cubrieron periodo por consumo y por statement, congelaron
cuatro objetos de entrada y la policy de distribuidoras, y registraron ejecucion
y version de motor. La prueba final desde la API cloud genero el artefacto en
GCS y lo descargo mediante una URL V4 de diez minutos; el archivo fue validado
por cabecera PDF, tamano y SHA-256. Las filas y artefactos de prueba se retiran
al terminar; los cuatro trabajos operativos previos quedan intactos.

### PostgreSQL

`report_runs` conserva el pedido y su trazabilidad. Como minimo, cada ejecucion
debe identificar:

- `id`;
- `report_key`;
- `output_format`;
- `requested_by`;
- parametros canonicos del negocio;
- hash de idempotencia;
- version o manifiesto de los datos de entrada;
- version de las policies aplicadas;
- version del motor, commit o digest de imagen;
- nombre de la ejecucion de Cloud Run Job;
- estado y etapa humana;
- cantidad de intentos;
- URI, nombre, tipo, tamano y checksum del resultado;
- error publico acotado y referencia al log tecnico;
- fechas de creacion, inicio, ultima actividad, finalizacion y expiracion.

Las migraciones de esta tabla viven exclusivamente en `database/`. Ningun
request ejecuta `CREATE TABLE` o `ALTER TABLE`.

### Google Cloud Storage

- Entrada analitica publicada: `gs://vpo-corp-royalties-marts/marts/`.
- Resultados: `gs://vpo-corp-royalties-marts/reports/jobs/<report_run_id>/`.
- Un trabajo completado tiene un solo artefacto final por formato.
- Los archivos incompletos usan un nombre temporal y solo se promueven al
  finalizar correctamente.
- Los resultados conservan la retencion operativa vigente de 30 dias.
- La metadata de `report_runs` puede permanecer para auditoria aunque el archivo
  haya expirado.

## Contrato HTTP de usuario

### Crear

`POST /reports/jobs`

Pedido conceptual:

```json
{
  "report_key": "royalty_keyword",
  "output_format": "excel",
  "filters": {
    "keywords": ["super junte"],
    "start_month": "2026-04",
    "end_month": "2026-06",
    "period_basis": "statement_period",
    "mode": "any",
    "raw_limit": 5000,
    "source": null,
    "account": null
  }
}
```

Respuesta `202`:

```json
{
  "item": {
    "id": 123,
    "status": "queued",
    "progress_stage": "queued"
  },
  "reused": false
}
```

`refresh_cache` no forma parte del contrato definitivo. El pedido referencia
una publicacion identificable de datos; no ordena mutaciones tecnicas de cache.

### Consultar

- `GET /reports/jobs?limit=<n>` lista trabajos visibles para el usuario.
- `GET /reports/jobs/<id>` devuelve estado y metadata.
- `GET /reports/jobs/<id>/download` valida permisos y responde con una
  redireccion o URL firmada de corta duracion.

El archivo no atraviesa Vercel ni se materializa dentro de la API.

### Endpoints que no pertenecen al destino

- `POST /reports/jobs/<id>/execute`.
- generacion directa sincrona como `POST /reports/keyword`.
- threads locales para construir reportes.

Se retiran en el mismo corte que activa Cloud Run Jobs. No quedan como fallback.

## Tipos iniciales registrados

| `report_key` | Formato | Reglas del pedido |
| --- | --- | --- |
| `royalty_keyword` | `excel` | Requiere keywords; admite periodo, base de periodo, modo y limite de detalle. |
| `royalty_executive` | `executive_pdf` | Keywords opcionales; admite periodo, base de periodo, distribuidora y cuenta. |
| `royalty_google_sheet` | `google_sheet` | Requiere keywords; admite periodo, base de periodo, modo y limite de detalle. |

Cada `report_key` apunta a un builder unico en el registro del motor. No se
seleccionan funciones por nombre recibido del usuario.

Para Google Sheets, PostgreSQL conserva la URL del documento externo. Si el
builder tambien produce un archivo, ese archivo sigue la misma regla de GCS. La
ausencia de archivo binario no cambia el estado operativo del trabajo.

## Parametros canonicos y reproducibilidad

Antes de crear el trabajo, la API:

1. normaliza keywords con la politica comun de busqueda;
2. aplica la politica comun de periodos;
3. valida combinaciones de distribuidora y cuenta;
4. elimina campos vacios sin significado;
5. ordena listas cuyo orden no modifica el resultado;
6. resuelve el manifiesto de marts publicado;
7. congela la version de las policies operativas;
8. calcula el hash sobre `report_key`, formato, filtros canonicos, manifiesto y
   version de policy.

El Job usa ese snapshot. Un cambio posterior de porcentaje, catalogo, policy o
publicacion no altera un trabajo ya creado. Un nuevo pedido usa la nueva version.

## Estados y etapas

Estados operativos permitidos:

- `queued`: registrado y pendiente de ejecucion;
- `running`: reclamado por una ejecucion;
- `completed`: resultado final persistido o URL externa confirmada;
- `failed`: termino sin resultado valido.

Etapas humanas:

- `queued`;
- `preparing`;
- `reading_data`;
- `building`;
- `uploading`;
- `completed`;
- `failed`.

No se muestra un porcentaje ficticio. `updated_at` funciona como heartbeat. Una
ejecucion que pierde su lease queda fallida de manera explicita; nunca vuelve
silenciosamente a `queued`.

Transiciones validas:

```text
queued -> running -> completed
queued -> failed
running -> failed
```

## Idempotencia, concurrencia y reintentos

- El mismo usuario no puede crear dos trabajos activos con el mismo hash.
- Repetir el pedido mientras esta `queued` o `running` devuelve el trabajo
  existente.
- Un trabajo terminado o fallido no bloquea uno nuevo.
- Reclamar un trabajo es una actualizacion atomica de PostgreSQL.
- El artefacto final se publica atomicamente y su checksum queda registrado.
- Un reintento automatico pertenece a la misma ejecucion y aumenta
  `attempt_count`; no crea otra fila ni otro archivo final.
- Agotados los reintentos, el estado es `failed` y el usuario puede solicitar un
  trabajo nuevo.

La concurrencia inicial de trabajos de regalias es `1`. Se aumenta solo con
metricas y sin cambiar el contrato.

## Permisos y seguridad

- Crear requiere `royalty_reports.create`.
- Consultar y descargar requiere `royalty_reports.access`.
- Un usuario comun ve solamente sus trabajos.
- Un administrador puede auditar todos.
- El permiso del usuario se valida en la API, no dentro del Job.
- La API necesita permiso minimo para ejecutar el Cloud Run Job.
- El service account del Job necesita lectura de marts, escritura limitada al
  prefijo de resultados, conexion a Cloud SQL y acceso a los secretos necesarios.
- No existe token compartido de worker ni endpoint publico de ejecucion.
- Los errores visibles no incluyen rutas internas, secretos ni trazas completas.
  El detalle tecnico vive en Cloud Logging y se relaciona por ejecucion.

## Experiencia de usuario

La pantalla confirma el pedido de inmediato y permite cerrarla. Consulta el
estado con polling moderado y conserva los trabajos recientes. Al finalizar,
habilita descarga o enlace. Un error muestra una explicacion breve y una accion
para volver a solicitar el reporte.

Localhost y cloud usan exactamente el mismo endpoint y disparan el mismo Cloud
Run Job. No existe un modo local de produccion para estos reportes.

## Corte sin caminos paralelos

La implementacion se valida con los artefactos testigo documentados en
`cloud_optimization_baseline_20260902.md`.

El corte requiere, en este orden:

1. motor modular validado contra los reportes testigo;
2. schema definitivo de `report_runs` aplicado por migracion;
3. Cloud Run Job desplegado con identidad propia;
4. API y pantalla conectadas al contrato nuevo;
5. prueba local y cloud contra el mismo trabajo;
6. retiro de Cloud Tasks, thread local, endpoint `/execute`, descarga por `/tmp`
   y rutas sincronas reemplazadas;
7. verificacion de que no existe fallback.

No se declara terminado mientras ambos circuitos convivan.

## Criterios de aceptacion

- Un reporte pesado no reduce la capacidad de login, booking o finanzas.
- El navegador puede cerrarse y el trabajo continua.
- Dos pedidos activos identicos no duplican computo.
- Cada resultado identifica datos, policies y version de motor utilizados.
- Excel/PDF coincide en contenido con su artefacto testigo para el mismo alcance.
- El usuario solo accede a trabajos autorizados.
- La descarga no atraviesa Vercel ni carga el archivo completo en la API.
- Un fallo queda trazable y no deja un archivo final parcial.
- Localhost y cloud producen el mismo resultado porque usan el mismo Job.
- Cloud Tasks y ejecucion local dejan de ser dependencias del sistema.
