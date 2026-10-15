# FUGA YouTube Extended en el flujo habitual

`Procesar nuevos` ejecuta `ingest_standardized_fuga.py`. Antes de modificar los
ingresos, ese ingestor ejecuta `lib.fuga_extended.audit_directory`. La misma
proteccion aplica al ejecutar el ingestor directamente. No depende de una
revision manual ni de nombres de meses o cuentas programados.

## Operacion

1. Descargar el statement `*-royalty_product_and_asset.csv` en `input_raw/fuga`.
2. Si se dispone del complemento, descargar tambien el
   `*-youtube_extended.csv` con el mismo prefijo de periodo/cuenta.
3. Usar `Procesar nuevos` en Control de distribuidoras.
4. Revisar el detalle `YouTube Extended` de esa distribuidora y publicar los
   datos analiticos por el procedimiento habitual.

El Extended es opcional. Su ausencia no impide procesar el statement completo.
Si se agrega despues, aparece pendiente y el mismo boton lo procesa. Con ambos
archivos presentes, la comparacion es obligatoria antes de modificar ingresos.
Cuando solo llega un Extended pendiente, el boton ejecuta la revision y guarda
sus evidencias sin reconstruir los ingresos que ya estaban cargados.

## Controles

- Sale ID obligatorio y unico en ambos archivos.
- Cada fila del Extended debe existir en el principal; debe cubrir las filas
  de Youtube Music y Youtube Ad Supported. YouTube Shorts sigue exclusivamente
  en el principal y no exige cobertura en el Extended.
- Igualdad por Sale ID de royalty, gross, cantidad, moneda, territorio, DSP,
  contrato, tipo de claim y fechas; numeros comparados con decimales, sin
  redondeo de punto flotante.
- Si falta el principal, cambia el esquema requerido, hay duplicados o falla
  la comparacion, se detiene el proceso antes de escribir el mart economico.
  El archivo sigue pendiente y bloquea la publicacion.
- Los hashes de ambos originales y de las evidencias invalidan una revision
  anterior cuando cambia un archivo o se pierde evidencia. Reprocesar archivos
  iguales reutiliza la revision; no agrega filas de ingreso ni de metadatos.

Los ISRC diferentes o adicionales se conservan como evidencia de catalogo, con
el ISRC del principal separado. No se reemplazan automaticamente ISRC de audio
por ISRC de video, no se crean obras ni beneficiarios a partir de estos datos.
Estas diferencias informativas no bloquean ingresos que coinciden.

## Persistencia y publicacion

`warehouse/supplementary/fuga/<archivo>/` contiene `audit.json`,
`metadata.parquet` e `isrc_review.parquet`. Se conservan todas las columnas
nativas del Extended, archivo de origen, numero de fila, statement relacionado,
ISRC del principal y `economic_role=supplementary_metadata_only`.

La carga reconstruye dos artefactos separados de los marts economicos:

- `warehouse/marts/fuga_youtube_extended_audit.parquet`: resultado y evidencias
  resumidas para la pantalla de distribuidoras.
- `warehouse/marts/fuga_youtube_extended_metadata.parquet`: metadatos completos
  de complementos validados, disponibles para futuras mejoras del catalogo.

La publicacion habitual incluye ambos cuando existen. No son archivos
obligatorios para releases anteriores. La API publicada puede leer el resumen
desde GCS; la API local comprueba ademas que las revisiones correspondan a los
archivos que estan actualmente en la carpeta.

Este cambio usa el metodo de carga ya existente (carpeta local y boton de
procesamiento); no incorpora un nuevo formulario de subida de archivos a cloud.

Para repetir solo la revision sin reconstruir ingresos:
`python scripts/audit_fuga_youtube_extended.py --root C:\royalties_pipeline`.

## Verificacion 2026-10-15

37 pruebas FUGA: carga normal repetida, montos exactos, ausencia de principal,
duplicados, cobertura, cambios en cualquiera de los originales, evidencia
faltante o corrupta, nombres de otros periodos/cuentas, monitor, preservacion de
productos y ejecucion del script real desde la accion de procesamiento.

Octubre real: 461341 filas comparadas, sin diferencias economicas; 14135 filas
con ISRC para revisar. La revision complementaria no modifica los seis marts
economicos publicados.
