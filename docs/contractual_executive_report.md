# PDF Ejecutivo Contractual

## Alcance

En Reporte de regalias > PDF ejecutivo > Ingresos y reparto contractual.
No agrega paginas de navegacion ni modifica Excel, Google Sheets, PDF de ingresos,
dashboard, catalogo, ingestion, policies o contratos guardados. No activa la
aplicacion automatica de contratos en los reportes existentes.

Seleccion de uno o varios artistas/proyectos, periodo completo o mensual/rango,
busqueda opcional por tema/ISRC y filtros de distribuidora/cuenta.
La seleccion comienza vacia. Los nombres completos se reconocen sin distinguir
mayusculas, acentos o espacios repetidos; + o Enter los agregan y Generar tambien
incluye un nombre valido pendiente. No se aceptan coincidencias parciales ni se
ignora un nombre pendiente invalido al generar con otros artistas seleccionados.
El reporte usa exclusivamente fecha de statement y los mismos descuentos netos
del dashboard. Los filtros seleccionan ingresos completos de los temas; el PDF
muestra todos sus beneficiarios, no solo el artista usado como filtro.

## Reproducibilidad

La API congela release de GCS, catalogo y version/payload de contratos en el
input_manifest_json existente, junto con policy/version y parametros. No crea
tablas ni migra datos operativos. La copia de contratos se lee en una transaccion
Postgres REPEATABLE READ READ ONLY; futuras ediciones no alteran ese pedido.

Los nuevos pedidos congelan tambien el indice de asociados (snapshot v2): mismas
reglas de Contratos, catalogo completo, decisiones y reclamos de todos los contratos,
con el mismo release. No se aplica el corte de junio de la pantalla de validacion.
El Cloud Run Job conserva exclusivamente la base elegible publicada de
royalty_dashboard_rankings: importes, unidades, descuentos y search_text originales.
Recupera solo el slot de ID del formato serializado publicado, verificando su
prefijo literal y un registro de IDs sin colisiones. No busca IDs en los titulos.
La asociacion exige que todos los bundles originales de identificadores del
mismo ID/fuente/cuenta/hoja/mes resuelvan al mismo contrato, sin vetos ni productos
ADA nativos. Antes de repartir concilia importe bruto y cantidad de filas contra
esos bundles congelados; diferencias conservan la fila original como pendiente,
sin bloquear el informe ni agregar ingresos ajenos a su filtro original.
Un control privado proyecta exclusivamente las columnas de identidad del Parquet
crudo fijado por generacion: veta slots cuya precedencia difiera entre productores.
Usa lectura en dos pasos, poda por estadisticas y cache por generacion; no relee
los importes del crudo ni altera catalogo, tablas BigQuery o la ingesta.
Cada fila economica se cuenta una vez. Los asociados incluidos entran tambien
al buscar el ISRC o titulo canonico. Mes/rango, fuente/cuenta y vigencias se aplican
a ambos tipos de ingreso. Snapshots v1 ya pedidos conservan su lectura anterior.
Se exige la copia de contratos y, en v2, de asociados;
no hay fallback a contratos actuales ni a un release diferente.
Usa el report_key existente royalty_executive con params.executive_mode=contractual,
compatible con las restricciones vigentes de report_runs; no cambia su esquema.

Vigencias inclusivas, statement representado por su primer dia. Hasta vacio usa
la fecha del pedido en America/New_York. Solo se distribuyen contratos cerrados
y validos. Contratos abiertos, invalidos, ingresos fuera de vigencia y codigos
sin contrato permanecen separados, sin inferir ISRC por titulo en el PDF ni perder
dinero. Las asociaciones fuertes o confirmadas se resuelven en el pedido con las
reglas compartidas de Contratos.

El calculo replica contractLogic.ts (bolsas, socios, contrato interno y legado)
con prueba cruzada obligatoria. Se consolidan beneficiarios ANTES del redondeo
por mayor resto. Los centavos, incluidos ajustes negativos, conservan el neto.

## Presentacion Y Acceso

Plantilla contractual-v1 basada en el PDF aprobado el 08/10/2026: logo VPO,
A4 horizontal, resumen, evolucion, socios/componentes, principales temas,
artistas y conciliacion. Paginacion automatica: hasta 44 beneficiarios por pagina
y 12 ingresos pendientes por pagina. Mas de tres socios agrega su detalle.
Los importes son devengados, no saldos de pago; no descuenta pagos anteriores.

Requiere acceso no acotado a royalty_reports y master_contracts; crear exige
royalty_reports.create. Portales de artistas no reciben nuevos permisos.
La autorizacion se vuelve a verificar en historial, estado y descarga.
Resultados: GCS reports/jobs/<id>, descarga firmada, retencion de 30 dias.
La plantilla permanece en codigo; un resultado expirado debe generarse de nuevo.

## Validacion

scripts/qa/qa_contractual_executive.py cubre permisos, snapshot, negativos,
vigencias contiguas, solapamientos, pendientes y paridad con TypeScript.
scripts/qa/qa_contractual_associations.py cubre asociados, descartes, conflictos,
fuentes/cuentas, filtros, vigencias, conservacion, snapshot y compatibilidad v1.
scripts/qa/qa_contract_identity.py cubre precedencia de IDs/UPC, generaciones
fijadas, lectura proyectada, poda segura y colisiones con identificadores legacy.
--reference-directory permite comparar con el snapshot privado del PDF aprobado,
sin incorporar datos financieros reales al repositorio.
Referencia La Juntada enero-septiembre 2026: total 102751.99, cubierto 102705.03,
sin asignar 46.96, Indyana 36440.13, Claudio/Hernan 28692.21 cada uno,
artistas 8880.48. Release 20261008T030559Z-0a3041226a8c.

Validacion de asociados del 10/10/2026 sobre ese mismo release y 244 contratos:
Movimento QZW9L2430233, enero 2025-junio 2026, suma 14983.858361940473 USD,
igual a Contratos e incluyendo uqY-3RS-V0Y. Enero 2025-septiembre 2026 suma
16087.557298323998 USD; no se aplica al PDF el corte interno de junio.
MC Tota conserva total 35596.56 USD y 400181848 unidades con y sin asociaciones.
Los ingresos cubiertos pasan de 20687.75 a 26396.55; pendientes de 14908.81
a 9200.01. Con indice vacio, v2 conserva total, unidades, cubierto y pendientes
de v1. Excel, Google Sheets, PDF de ingresos y dashboard no cambian su lectura.
