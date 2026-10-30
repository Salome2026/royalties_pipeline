# Cierre de controles de ingesta del catalogo

## Alcance

Se conservan los lectores aprobados de ADA Excel, FUGA, ONErpm, Orchard,
SoundOn y DashGo. Altafonte sigue como historico. Estos controles no cambian
formulas economicas, fechas, asociados, porcentajes, contratos ni reportes.
Son controles de admision y trazabilidad para las proximas ingestas, no una
reconstruccion de los ingresos ya publicados.

## Archivos repetidos y reemplazos

`scripts/lib/ingestion_controls.py` reconoce cada archivo por SHA-256 y por
fuente, cuenta, mes de statement y tipo de archivo. Un mismo contenido con
otro nombre dentro del mismo contexto se procesa una sola vez. No se
eliminan filas economicas repetidas dentro de un statement: pueden ser ventas
legitimas. ADA conserva su validacion estricta de nombres de Excel.

Dos archivos distintos para el mismo contexto detienen el lote, sin escoger
por fecha de modificacion ni sumar ambos. Hay que conservar la version
correcta; los suplementos requieren una regla explicita por fuente. Un
reemplazo con el mismo nombre se reconoce por contenido, no por nombre.
Se verifica que los archivos no cambien durante la lectura y que no falten
meses/cuentas anteriormente procesados. Una salida antigua no puede ser
declarada como reemplazada si conserva huellas que ya no fueron seleccionadas.

## Importes y publicacion

Cada lector valida su importe USD despues de su conversion original. Los
valores nulos, no numericos, NaN e infinitos detienen el lote; cero y negativos
validos siguen permitidos. No se cambia el parser propio, FX, bruto/neto,
configurador ni Shares In & Out.

La evidencia y los controles se preparan antes de promover las salidas.
`warehouse/registry/ingestion_failure_<fuente>.json` se crea al iniciar;
si hay error o interrupcion queda pendiente y bloquea publicar. Solo un
reprocesamiento exitoso lo retira. Esto protege la publicacion; no es una
transaccion de sistema operativo entre todos los archivos locales.

## Lecturas que requieren revision

`scripts/lib/catalog_ingestion_review.py` agrupa roles desconocidos,
serializaciones ambiguas, conflictos de participantes y contradicciones de
titulos nativos por fuente, cuenta y causa. Conserva identidades, archivos y
hasta cinco ejemplos por grupo. No crea tareas por venta ni infiere artistas
o porcentajes. Los titulos derivados de videos asociados no se comparan como
si fueran titulos nativos de pista. Los acentos, orden, Cover y evidencia de
album complementaria no originan por si solos una incidencia.

Los grupos aparecen dentro del monitor de fuentes existente. Los cambios
reales de integrantes siguen el circuito aprobado de reapertura de contratos,
con integrantes nuevos sin porcentaje y decisiones humanas conservadas.
Un rol desconocido no se oculta por existir otra evidencia de interprete.

## Evidencia versionada

Cada fuente guarda recibo de archivos y revision, incluyendo la huella del
lector. `catalog_ingestion_controls.parquet` los reune y se publica como
artefacto auxiliar dentro de las siguientes versiones atomicas de marts.
Para adoptar el control sobre la version actual, el auxiliar inicial contiene
solo la procedencia ya publicada y debe coincidir con su `base_release_id`.
No se modifica el manifest economico ni se recargan tablas de BigQuery.

## Pruebas y recuperacion

- Pruebas unitarias de admision, roles, importes y bloqueo de publicacion.
- Los seis entrypoints reales con reenvios, reemplazos, importes invalidos,
  archivos contradictorios y falla al escribir el control; se preservan las
  salidas anteriores y el reintento se valida con el mismo archivo original.
- Dos meses sinteticos por las seis fuentes, sus constructores song-level,
  consolidacion y catalogo maestro reales. El consumidor de Contratos recibe
  el integrante nuevo sin inventar porcentaje ni cambiar asignaciones previas.
- La misma bateria en el runtime cloud de produccion, sin red, credenciales
  ni montajes de datos productivos.
- Publicacion privada real en GCS, carga en tablas BigQuery de prueba,
  conciliacion por fuente/cuenta/mes, interrupcion antes de activar,
  retroceso y reintento. No se usa ni reemplaza el puntero productivo.

La evidencia ejecutable y certificacion quedan en
`C:/royalties_pipeline/staging/catalogo_lectura/20261030_catalog_closure`.
