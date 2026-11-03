# Búsqueda del reporte por contrato de distribución

Debajo de Palabras clave, el reporte acepta hasta 100 números de contrato separados
por comas. Buscar contratos permite filtrar por número, sello o subsello y agregar
o quitar selecciones sin cerrar la lista. Solo los números viajan en el pedido.

`distribution_contract_numbers` selecciona la unión de los ISRC que tienen esos
números aplicados en sus acuerdos guardados. Las palabras clave, distribuidora,
cuenta y período son filtros adicionales dentro de esa unión. No se amplía la
búsqueda por coincidencia de artista. No se modifica el reparto ni el estado de
los contratos. Un contrato desconocido o una selección sin temas falla sin
generar un reporte general. Sin números, el comportamiento anterior se conserva.

La selección y las asociaciones se congelan en el manifiesto del trabajo con la
misma versión de datos del catálogo. Los resúmenes, detalle, conteo de filas,
Excel, Google Sheet y PDF de ingresos usan ese alcance. Los PDF contractuales
también intersectan su selección de artistas con los ISRC de esos contratos.
El filtro agrupa temas vinculados; las vigencias siguen siendo responsabilidad
del cálculo contractual existente y no alteran el ingreso histórico del tema.

Los ISRC nativos tienen prioridad sobre UPC o videos compartidos. Los ingresos
sin ISRC solo entran si las asociaciones publicadas resuelven un único ISRC,
respetando exclusiones y productos pendientes. La selección requiere acceso de
backoffice a reportes y contratos y no está habilitada para WML.

Verificación: `scripts.qa.qa_report_contract_filter` cubre selección múltiple,
intersección con palabras, ambos ejes temporales, detalle completo, conteo,
asociaciones ambiguas y excluidas, conservación del importe y snapshots obsoletos.
`web/scripts/qa_report_contract_filter.cjs` recorre el buscador, ingreso manual,
selección, eliminación, deduplicación, generación sin palabras y vista móvil con
respuestas de prueba aisladas.
