# Contratos: ingresos de prueba hasta julio de 2026

Contratos consulta la misma vista vigente de BigQuery que el dashboard de
regalias (`royalty_dashboard_current`) y aplica la misma politica de descuento
por fuente y cuenta. El unico limite temporal de esta prueba es el mes de
statement: se incluyen statements hasta julio de 2026 inclusive. No se fija
una publicacion anterior ni se mantiene un importe alternativo.

Si el dashboard usa su respaldo Parquet, Contratos consulta el mismo resumen
vigente y aplica `apply_report_net_personalization`. La lista y la ficha
conservan los ISRC, titulos y creditos del catalogo activo; un ISRC sin
ingresos en el periodo figura con cero. La primera venta sugerida para la
vigencia contractual sigue saliendo del crudo o del catalogo.

Esta vista es solo para validar contratos. No modifica el catalogo, los
repartos guardados, el dashboard ni los reportes actuales.
