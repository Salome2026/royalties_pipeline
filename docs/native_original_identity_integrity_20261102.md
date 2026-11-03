# Conservacion de identificadores desde los archivos originales

## Causa reproducida

En FUGA, `read_csv(infer_schema_length=10000, ignore_errors=True)` inferia
Product Reference y Asset Reference como enteros por el prefijo del archivo.
Las referencias YT-V/YT-A posteriores se convertian silenciosamente en nulos.
La misma inferencia quitaba el cero inicial del UPC 046081037160.
Probar la expresion de extraccion sobre un frame ya leido como texto no
certificaba la lectura completa del CSV. El control anterior de BigQuery
comparaba dos archivos derivados y no detectaba una perdida anterior a ambos.

## Lectura y admision

- FUGA, DashGo, Orchard y SoundOn leen las celdas CSV como texto, sin omitir
  errores de parseo. Cada adaptador conserva sus conversiones de dinero,
  fechas, cantidades y reglas comerciales.
- ONErpm conserva celdas de Excel como texto. Las hojas admitidas como dinero
  siguen dependiendo de la configuracion existente. Masters y Shares conservan
  sus ISRC de identidad aun cuando Shares no se admita como generacion.
- ADA mantiene su lector XML/Excel certificado y sus controles particulares.
- Batch.stage contrasta los identificadores con los originales de los mismos
  SHA-256 antes de reemplazar una salida. Una perdida genera
  NATIVE_IDENTITY_LOSS en el monitor existente y bloquea la publicacion.

## Evidencia transportable y reconstrucciones

Cada lectura genera ingestion_control_<fuente>_native_identity.json. La
consolidacion, los dos publicadores, el cargador BigQuery y el reparador de
contexto exigen native_identity_proofs.json, con cobertura de los archivos
economicos habituales. Altafonte conserva su ambito legacy; no se declara
certificado por un lector de otra fuente y no se borra.

Las huellas comprueban cantidad de filas, celdas presentes y dos acumuladores
independientes del conjunto de tuplas de identificadores. Conservan duplicados
legitimos y detectan intercambios entre filas. No determinan derechos ni splits.
Se registra la version de Polars: un cambio de su algoritmo requiere recertificar
desde originales y nunca rehacer la huella sobre una copia normalizada perdida.

La conciliacion economica y de proyecciones de bigquery_source_integrity sigue
vigente, como control complementario. No reemplaza la evidencia desde originales.

## Metadata humana y referencias externas

La biblioteca de catalog_manual_metadata puede materializar referencias de
grabaciones externas confirmadas por el titular, sin agregar ingresos. La
referencia de Dale Turro / Session en el Barrio #12 se conserva en futuras
reconstrucciones; sus inclusiones siguen siendo decisiones del contrato.
No se crean porcentajes ni se importa el dinero de distribuidoras externas.

## Alcance de la auditoria historica

Los resultados, huellas originales, planes de recuperacion por Sale ID y
conciliaciones se guardan en
C:/royalties_pipeline/staging/catalogo_lectura/20261102_native_identity_full.
La certificacion final solo se emite despues de activar y comprobar los datos
y el codigo publicados. Un archivo preparado no equivale a una publicacion.
