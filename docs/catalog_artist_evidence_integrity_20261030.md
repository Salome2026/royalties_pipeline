# Integridad de evidencia entre distribuidoras

## Defecto corregido

La lectura FUGA podia reiniciar las cuatro columnas artisticas de todas las
fichas y reemplazar la evidencia de las fichas coincidentes por la suya. Una
actualizacion parcial perdia evidencia ONErpm, ADA, Orchard o SoundOn ya
certificada. Conservar importes y nombres visibles no detectaba esa regresion.

El control comun tampoco informaba el caso donde un credito nativo valido
declara integrantes adicionales a la lista maestra. El ejemplo real es
QT8BW2649774: FUGA informa Aneley; SoundOn, Aneley y Para El Mundo. Conservar
la lista publicada no autoriza borrar ni ocultar la otra declaracion.

## Reglas obligatorias

- Cada lector actualiza solo su evidencia. Las fichas no presentes en sus
  entradas conservan la metadata anterior, incluidas listas nulas o vacias.
- Antes de continuar la reconstruccion se verifica que el lector no haya
  eliminado ni reescrito pruebas de las otras fuentes. Una violacion detiene
  el proceso antes de publicar; no se trata como un catalogo sin incidencias.
- FUGA sigue usando Asset Artist. Product Artist es contexto de lanzamiento,
  no una union automatica. Un artista de pista respaldado por otra fuente no
  se borra por aparecer tambien como artista de album en FUGA.
- Un integrante nativo ausente de la ficha genera PARTICIPANTS_DIFFERENCE,
  agrupada por fuente/cuenta en el monitor existente. Un orden diferente,
  alias aprobado o lista parcial cuyos integrantes ya estan presentes no
  genera por si solo una incidencia.
- Se conserva la proteccion de correcciones humanas confirmadas. Los roles
  desconocidos mantienen su revision independiente.
- Evidencia y participantes reportados no asignan derechos ni porcentajes.
  La propuesta existente de Contratos conserva las alternativas; los
  contratos guardados, vigencias y decisiones de asociados no se restauran
  desde una copia antigua.

## Reparacion de la version publicada

La recuperacion se prepara en copia. Solo se permite usar evidencia de una
publicacion anterior certificada cuyos archivos y huellas sigan presentes
en la procedencia del release actual. Se conserva la version actual de las
reglas y el diccionario; no se reintroducen conflictos de alias ya resueltos.
Las correcciones posteriores de FUGA y Dormun/Lit Killah no se revierten.

La migracion modifica unicamente catalog_artist_evidence y catalog_artist_rule.
Se comparan exactamente las demas columnas, todos los codigos y los contratos.
Los archivos financieros no se reprocesan ni sustituyen por copias historicas.
No restaurar SQL ni lanzar cargas de statements pendientes como parte de ella.

## Verificacion permanente

`scripts/qa/qa_catalog_artist_evidence.py` comprueba enriquecimientos en ambos
ordenes, reenvio idempotente, fuentes no presentes, otros lectores, evidencia
no reconocida, preservacion de literales, alias aprobados y diferencias reales.
La bateria incluye el consumo de la alternativa por Contratos, no solo un
conteo de nombres o una suma economica.

Cloud Build ejecuta estas regresiones sin red y con el contenedor de solo
lectura antes de publicar imagenes o actualizar servicios. Las pruebas
especificas y el guard de ejecucion cubren responsabilidades diferentes.

La evidencia del ensayo, la comparacion de las 3.125 fichas y la adopcion se
registra en `staging/catalogo_lectura/20261030_catalog_evidence_repair`.
No extender este cierre a todo CAT-003, los lectores economicos ampliados ni
a formatos nuevos que no hayan sido certificados.
