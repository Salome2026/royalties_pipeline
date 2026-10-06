# Contratos: base temporal para contraste de ingresos

Solo la pantalla de Contratos usa temporalmente el resumen del dashboard de la
publicacion `20260922T160603Z-df288d7cce3c`. La base termina en el mes de
transaccion `2026-07`, pero el importe de prueba incluye solamente statements
con `statement_period <= 2026-07`. El objeto es
`gs://vpo-corp-royalties-marts/marts/releases/20260922T160603Z-df288d7cce3c/royalties_dashboard_summary.parquet`,
generacion `1790093189242250`.

La lista y la ficha siguen tomando ISRC, titulo, credito de origen y fuentes
del catalogo activo. El ingreso de Contratos agrupa el resumen reportable por
ISRC, fuente y cuenta, aplica `apply_report_net_personalization` con la politica
vigente (la misma funcion del dashboard) y luego suma por ISRC. Los meses de
actividad mostrados son meses de statement. La primera fecha de venta usada
para la vigencia del contrato sigue saliendo del crudo o del catalogo, no del
mes de statement. Los ISRC sin ingresos en el corte figuran con cero.

Este importe coincide con una busqueda exacta del ISRC en el dashboard con
base `statement_period` y rango hasta julio, si se compara la misma publicacion
y politica. No se modifica ningun mart, status, split guardado, dashboard ni
reporte; tampoco se aplica un filtro al catalogo general.

Es una base **fija para pruebas**: nuevos statements o correcciones no entran
automaticamente, aunque correspondan a meses anteriores. El descuento sigue la
politica vigente y puede cambiar si esa politica se edita. Al terminar la
validacion, retirar el corte temporal o disenar un mart mensual versionado y
conciliado antes de usarlo en Contratos.
