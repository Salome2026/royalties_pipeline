# DashGo: referencias sin codigo en Contratos

Estado: implementado y probado en copia Cloud SQL. No publicado ni aplicado a
contratos de produccion. Alcance: toda DashGo, los 35 archivos de MAWZ.

## Origen del problema

El catalogo ya conservaba estas observaciones y sus dimensiones de monetizacion.
El circuito contractual admitia VIDEO/TRACK/UPC, pero rechazaba TEXT. Los lectores
de reparto tampoco tenian una referencia contractual para ese contexto sin codigo.
Ademas, el PDF individual rechazaba cualquier ingreso pendiente, incluso cero.
Por eso normalizar el catalogo o arreglar su resumen no resolvia esta conexion.

## Correccion

- Se propone el contrato de un video nativo observado con titulo completo,
  distribuidora, cuenta y canal compatibles. Se respeta el destino ya confirmado
  y los descartes existentes; por ejemplo, los dos destinos de Lucete no vuelven
  a tratarse como decisiones pendientes equivalentes.
- Los tokens de `Auto generated asset` solo proponen cuando existe un video
  nativo independiente en el mismo contexto. No se convierten en VideoId.
- Sin identificar permite elegir otro contrato manualmente. La decision queda
  auditada en los asociados existentes, con version, permisos y firma de evidencia.
  No cambia el asset, sus identificadores, sus dimensiones ni el detalle.
- Las propuestas sin confirmar no obligan a cubrir el catalogo. Compartir contrato
  no fusiona items ni define como se agrupa un reporte.
- Excel y PDFs aplican las decisiones confirmadas. El PDF individual conserva
  los ingresos pendientes con sus columnas de reparto vacias y totaliza solo
  participaciones cubiertas. Sus campos de cobro siguen vacios y editables.

## Resultado de la copia

24 referencias textuales con importe: 23 reciben propuestas concretas, por
USD 396,98860277. Son 12 titulos completos y 11 referencias genericas con evidencia
nativa independiente. Se simularon las 23 confirmaciones mediante los endpoints
reales conectados exclusivamente a `vpo_dashgo_contract_text_copy_20261105`.
Se revisaron y cerraron los contratos de la copia conservando sus condiciones.

El making-of (USD 0,08009401) queda para eleccion manual; la pantalla ya permite
asignarlo. Tambien siguen separados los ocho videos pendientes con importe
(USD 0,07904193). No se deduce su contrato solamente por compartir canal/artista.
Los demas pendientes de importe cero no bloquean el PDF.

La comparacion completa, por fecha de statement y por fecha de consumo, conserva:

- USD 28.212,27238360 y 50.739.925 unidades.
- Las 500.350 filas seleccionadas del detalle, con igualdad de contenido mediante
  dos firmas independientes. Ese detalle incluye las expansiones de producto ya
  aprobadas; no debe confundirse con las 499.977 ventas nativas.
- El resumen por tema y las demas tablas, salvo las columnas contractuales que
  reciben la cobertura confirmada de la copia.
- Los importes de contratos anteriores cuando no se agregan decisiones nuevas.
- Las 61 decisiones previas y las condiciones economicas de los contratos.

263 controles del circuito contractual y DashGo; 256 controles de la suite exacta
de Cloud Build; controles de interfaz/proxy, compilacion web y prueba de pantalla.
El lector PDF consulto BigQuery real con el snapshot de contratos de la copia:
las 23 referencias se aplican sin llenar su ISRC nativo. Se revisaron las seis
paginas del PDF y sus tres campos editables.

## Pendiente

Publicar el codigo verificado, sin copiar decisiones ni contratos de la prueba.
Despues confirmar en produccion las referencias que correspondan y elegir
manualmente los destinos pendientes. La prueba no acredita derechos contractuales
ni reemplaza esa confirmacion. Las otras distribuidoras siguen en su orden de
revision; este resultado no afirma que presenten el mismo caso que DashGo.

Evidencias: `C:/royalties_pipeline/staging/catalogo_lectura/20261105_dashgo_contract_text_copy`.
