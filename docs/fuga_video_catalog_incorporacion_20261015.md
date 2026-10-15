# Incorporacion de ISRC de video al catalogo — 2026-10-15

Decisiones autorizadas: incorporar los 28 identificadores de video ya revisados,
aplicar 8 relaciones con audio respaldadas por el statement y 2 alias, mantener
18 relaciones de audio como propuestas pendientes y 2 videos sin audio asignado.

## Persistencia

Las decisiones y su evidencia estan en
`warehouse/registry/fuga_video_catalog_decisions.json`. El constructor habitual
de catalogo aplica `lib.catalog_video_metadata` despues de las correcciones
manuales y del enriquecimiento de artistas. No requiere repetir una revision
manual para conservar estas decisiones en futuras cargas.

El catalogo incorpora tres campos:

- `video_isrcs`: identificadores de video, separados de `asset_isrc` e `isrcs`.
- `catalog_aliases`: claves anteriores que redirigen a una ficha existente.
- `video_relationships_json`: estado de relacion, audio confirmado o propuesto,
  identificadores de video y asset, titulos, creditos originales, fuente y notas.

El endpoint y la pantalla de catalogo muestran los identificadores y relaciones.
Se puede buscar cualquiera de los 28 ISRC, o filtrar las relaciones confirmadas,
pendientes y los videos sin relacion de audio. Los candidatos pendientes no se
usan como alias de audio, ni para contratos, reparto o imputacion de ingresos.

## Alias y controles financieros

- `VIDEO:8CUvkg_Y4XM` pasa a alias de `ISRC:ARDL12500089` (Que Ironia).
- `VIDEO:LZJSvkx13LI` pasa a alias de `ISRC:QZTB62504366`
  (Perreo mamiyosoyelth; titulo alternativo Perreo Ticket).

Ambas fichas anteriores tienen 0 filas economicas propias. Se conservan sus
titulos, identificadores y evidencia de identidad en las fichas de destino. No se
suma esa evidencia otra vez a los importes economicos. Si una futura carga
asignara a esos alias filas o valores economicos propios, el constructor se
detiene para revision en lugar de borrar esa informacion.

El cambio conserva exactamente los ingresos, unidades y filas economicas de
cada ficha que permanece. El catalogo pasa de 3057 a 3055 fichas, sin crear claves
nuevas. Reaplicar las decisiones produce el mismo resultado.

## Que falta confirmar en las 18 propuestas

Hay que confirmar que el video y el audio propuesto representan la misma
grabacion o version, mediante la ficha del lanzamiento, una referencia del
distribuidor o una comparacion de audio/duracion. Una coincidencia de titulo y
artistas no permite distinguir por si sola versiones en vivo, remixes o medleys.

Precauciones especificas:

- Por Ese Hombre: Valen aparece en el titulo y en el audio, pero falta en la
  lista de artistas del Extended. Se conservan los creditos existentes.
- Kandela RKT: sheafiel / sheafiell requiere comprobar la variante del nombre.
- Imaginando La Gloria: Para El Mundo figura en el video, no en el credito de
  audio disponible. No se cambian artistas ni titulares por inferencia.
- Fui Nada: revisar Ke Locura / Q' Lokura y el credito adicional de Kekelandia.

Todo Ke Ver de LAALODJ y Los Anormales no se une a los audios homonimos de La
Juntada y Cumbia Rocha. Set Live RKT #4 conserva su ficha de video. El video
Diabla + Session #15 mantiene su condicion de video compuesto: su relacion
registrada con Session #15 no asigna toda la pieza ni sus ingresos a un audio.

## Validacion y publicacion

50 pruebas de catalogo, artistas, filtros, correcciones manuales e ingesta FUGA.
Compilacion de produccion de la web. Validacion sobre las 3057 fichas originales:
28 codigos buscables, filtros 8/18/2, alias resueltos, 0 altas y preservacion de
ISRC principales, artistas e importes por ficha. Las fichas ajenas a los dos
alias conservan todos sus datos originales, ademas de los tres campos nuevos.

La publicacion es una revision de metadatos del catalogo del mismo release
economico. Conserva el catalogo anterior y las decisiones en objetos inmutables,
actualiza el catalogo de BigQuery sin modificar filas financieras y cambia la
referencia al archivo del catalogo mediante una actualizacion condicional del
manifiesto. Los otros cinco objetos analiticos permanecen intactos.
