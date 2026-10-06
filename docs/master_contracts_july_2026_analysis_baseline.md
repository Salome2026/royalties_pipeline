# Contratos: base temporal para contraste de ingresos

Solo la pantalla de Contratos usa temporalmente los importes de
`catalog_master.parquet` de la publicacion
`20260922T160603Z-df288d7cce3c`. Esa publicacion termina en el mes de
transaccion `2026-07`; incluye toda la actividad anterior acumulada en el
catalogo con sus reglas de identidad y policies. El objeto es
`gs://vpo-corp-royalties-marts/marts/releases/20260922T160603Z-df288d7cce3c/catalog_master.parquet`,
generacion `1790093187143319`.

La lista y la ficha siguen tomando ISRC, titulo, credito de origen, fuentes y
meses del catalogo activo. Solo se reemplaza el importe de analisis por el de
la publicacion fijada, unido por ISRC. Los ISRC nuevos que no existian en la
base de julio se muestran con importe cero. La lista se ordena por ese importe
de analisis. No se modifica ningun mart, status, split guardado, dashboard ni
reporte; tampoco se aplica un filtro al catalogo general.

Es una base **fija para pruebas**, no una suma dinamica de cualquier correccion
futura imputada a meses anteriores a agosto. Al terminar la validacion con
informes existentes, retirar el join temporal en `master_contract_catalog()` y
la referencia a este objeto. Si se necesita un corte historico dinamico,
disenar un mart mensual con las mismas reglas de identidad/policy del catalogo
y conciliarlo antes de usarlo en contratos.
