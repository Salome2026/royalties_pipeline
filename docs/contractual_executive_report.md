# PDF Ejecutivo Contractual

## Alcance

En Reporte de regalias > PDF ejecutivo > Ingresos y reparto contractual.
No agrega paginas de navegacion ni modifica Excel, Google Sheets, PDF de ingresos,
dashboard, catalogo, ingestion, policies o contratos guardados. No activa la
aplicacion automatica de contratos en los reportes existentes.

Seleccion de uno o varios artistas/proyectos, periodo completo o mensual/rango,
busqueda opcional por tema/ISRC y filtros de distribuidora/cuenta.
El reporte usa exclusivamente fecha de statement y los mismos descuentos netos
del dashboard. Los filtros seleccionan ingresos completos de los temas; el PDF
muestra todos sus beneficiarios, no solo el artista usado como filtro.

## Reproducibilidad

La API congela release de GCS, catalogo y version/payload de contratos en el
input_manifest_json existente, junto con policy/version y parametros. No crea
tablas ni migra datos operativos. La copia de contratos se lee en una transaccion
Postgres REPEATABLE READ READ ONLY; futuras ediciones no alteran ese pedido.

El Cloud Run Job lee royalty_dashboard_rankings por release_id congelado en
BigQuery. No descarga los Parquet de detalle. Se exige la copia de contratos;
no hay fallback a contratos actuales ni a un release diferente.

Vigencias inclusivas, statement representado por su primer dia. Hasta vacio usa
la fecha del pedido en America/New_York. Solo se distribuyen contratos cerrados
y validos. Contratos abiertos, invalidos, ingresos fuera de vigencia y codigos
sin contrato permanecen separados, sin inferir ISRC por titulo ni perder dinero.

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
--reference-directory permite comparar con el snapshot privado del PDF aprobado,
sin incorporar datos financieros reales al repositorio.
Referencia La Juntada enero-septiembre 2026: total 102751.99, cubierto 102705.03,
sin asignar 46.96, Indyana 36440.13, Claudio/Hernan 28692.21 cada uno,
artistas 8880.48. Release 20261008T030559Z-0a3041226a8c.
