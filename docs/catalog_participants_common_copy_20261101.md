# AUTO-002 y USO-001: resolucion comun de participantes

Estado: integracion de la regla certificada; publicacion autorizada el 2026-11-02.
Base de la primera prueba: f0e9b716b6997e825e46d50b23fbcc9fc2d5a60f.
Version de regla: AUTO-002-COMMON-1.
Directorio: C:/royalties_pipeline/staging/catalogo_lectura/20261101_auto002_uso001.

## Alcance autorizado

Completar listas compatibles de participantes en el catalogo maestro y hacer que
Contratos use exactamente esa resolucion. Se reutilizan los lectores y reglas
aprobados. No se vuelven a auditar crudos ni se sustituyen lectores economicos.
La adopcion autorizada publica solo metadata artistica y el lector comun. No
recalcula importes ni cambia asociados, contratos guardados o reportes actuales.
No se ejecutan planes de reapertura. Salome y los datos WML quedan fuera.

## Regla comun

1. La identidad debe ser un ISRC valido de la misma pista. UPC, titulo y parecido
   de nombre no autorizan fusionar grabaciones ni heredar participantes.
2. Cada fuente aporta solo sus creditos de pista certificados, con su version,
   campos, procedencia y gramatica. El resolutor no impone un separador universal.
3. Una lista completa realmente informada debe contener a todos los integrantes
   de las listas parciales compatibles y a los que ya conserva el maestro.
   Se pueden completar los nombres que faltan, no eliminar nombres anteriores.
4. No se inventa una union que ninguna observacion completa declare. Dos listas
   incomparables sin ese respaldo, una identidad incompatible o una interpretacion
   nativa contradictoria se conservan para revision, sin ampliacion automatica.
5. No gana una distribuidora universal, el archivo mas reciente ni la lista mas
   repetida. Los reenvios y meses repetidos no son votos. Se conserva el orden
   vigente; los nombres nuevos se agregan con orden estable, sin deducir principal.
6. Las equivalencias aprobadas se comparan como una persona. No quitar DJ/MC ni
   otras palabras por parecido. Las referencias FUGA Kita/Federikita y
   Nueva/Nueva Adoracion conservan su alcance por ISRC.
7. Las correcciones manuales y descartes explicitos del catalogo prevalecen.
   La aprobacion operativa de artistas en la revision externa prevalece en su
   overlay existente, sin reinsertar un integrante descartado por esa decision.
8. Un credito no define beneficiarios ni porcentajes. Las decisiones de un contrato
   no se usan para borrar artistas del catalogo ni para admitir otra venta.

## Limites que siguen vigentes por fuente

- FUGA-ARTISTS-2: Asset Artist, nunca Product Artist como participante de pista.
  Album, canal y etiquetas son contexto; no se reactiva la union antigua.
- ONErpm: performer y featuring, sin incorporar writers/producers como artistas.
  Shares puede aportar identidad y creditos aun cuando no se admita su dinero.
  Un recibo financiero no es una barrera para esa metadata certificada.
- ADA: solo Excel de Indyana/Mawz. Se conservan prefijos confirmados y la regla
  aprobada de feat. explicito en titulo, ligada al credito nativo y su localizador.
  Treinta caracteres no prueban truncamiento; una posible abreviatura no sirve
  como autoridad para inventar integrantes adicionales.
- Orchard y SoundOn: creditos nativos de pista y referencias ya aprobadas.
  Las diferencias de orden no son por si solas participantes nuevos.
- DashGo: Track Artist mantiene nombres atomicos; no se inventa una gramatica
  multiartista. Se reutiliza su normalizacion certificada de ISRC.

## Una autoridad para los consumidores

El constructor agrega la resolucion comun DESPUES de los adaptadores
actuales. Solo cambian las cuatro columnas artisticas; las evidencias nativas
permanecen literalmente conservadas dentro de su estructura original.

Una entrada derivada versionada en catalog_artist_evidence guarda el resultado,
su relacion con la evidencia nativa, los nombres agregados y el motivo. Su huella
detecta desalineacion entre el resultado y los datos que lo respaldan. La misma
entrada se transporta por el conversor real royalty_catalog de BigQuery.

Contratos toma la lista exacta de ese resultado: no vuelve a decidir integrantes
mediante otra union o interseccion. Los evaluadores existentes se conservan solo
para fechas y confianza del principal. No se asume que el orden confirme un
principal ni que un credito determine derechos. Sin resultado comun, se conserva
la compatibilidad anterior para fichas fuera del alcance certificado.

Una resolucion derivada inconsistente no se oculta mediante fallback. La
reconstruccion puede recalcular ante evidencia nueva; el consumidor exige que
la lista y la huella correspondan a la misma version.

## Datos y comprobaciones de la copia

Foto validada el 2026-11-01: 3.125 fichas, 1.552 ISRC y 345 contratos guardados.
Solo QT8BW2649774, Imaginando La Gloria, agrega Para El Mundo a Aneley en el
maestro. SoundOn ya informa la lista completa; FUGA informa una lista parcial.
Contratos ya ofrecia ambos nombres; ahora el maestro y ese consumidor coinciden.
No existe contrato guardado para ese ISRC en la foto. El plan prospectivo no se
aplica y no alcanza a ningun contrato guardado.

Se comparan todas las columnas no artisticas, la evidencia nativa completa,
los aliases/identificadores, las propuestas de contratos guardados, la confianza
del principal y las fechas. Se usa el conversor real de BigQuery. La promocion
comprueba sus columnas no artisticas contra la version activa antes de actualizar
metadata.

Las pruebas positivas y negativas incluyen las seis fuentes, artistas nuevos,
contradicciones, grupos, royalties negativos, aprobaciones humanas, creditos de
Shares sin dinero, reenvios, cambios de evidencia y una matriz de 64 pares de
listas parciales. Tambien se reutilizan la regresion existente y los dos ciclos
sinteticos de los seis entrypoints reales hasta Contratos. No se conectan a
produccion mientras se ejecutan.

## Limites del cierre

Esta regla no cierra QA-005, no certifica formatos desconocidos ni una nueva
fuente externa, no modifica el PDF contractual y no cambia los reportes actuales.
El objeto maestro y sus huellas viajan juntos. La prueba obligatoria del lector
comun se ejecuta tambien en el control de despliegue, sin acceso a la red.

## Promocion controlada

La publicacion usa una revision de metadata sobre el mismo release economico,
no una nueva ingesta ni copias de movimientos. Solo actualiza las cuatro columnas
artisticas de royalty_catalog y los objetos de metadata del manifiesto.
Se conservan las reglas actuales de ingresos de productos y los cambios recientes
de reportes. No se cambian limites de memoria, permisos ni configuraciones de
usuarios como parte de esta adopcion.

Antes de activar se verifica el manifiesto por generacion y se conservan una
instantanea de BigQuery, los objetos previos y el estado de los contratos.
El acta de ejecucion, las metricas, el commit y el despliegue quedan en
C:/royalties_pipeline/staging/catalogo_lectura/20261102_auto002_uso001_release/.
No confundir la integracion de la regla con una certificacion de rendimiento.
