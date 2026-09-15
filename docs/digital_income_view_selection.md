# Seleccion compartida de Ingresos digitales

La pantalla consulta importes declarados en statements. La seleccion de distribuidoras y cuentas es un filtro de visualizacion; no representa cobros bancarios ni modifica politicas contractuales de reportabilidad.

La seleccion global se guarda en Cloud SQL Postgres, tabla `digital_income_view_selection`. `null` con exclusiones vacias significa Todas; una lista de inclusion vacia significa Ninguna. Desmarcar opciones desde Todas guarda las exclusiones, de modo que futuras cuentas nuevas sigan incluidas. Elegir una opcion por nombre guarda una lista de inclusion exclusiva. Distribuidoras y cuentas se filtran antes de agregar los importes, por lo que metricas, matriz, detalle y PDF muestran el mismo alcance. Cada cuenta se identifica por el par distribuidora/cuenta.

El nombre de una opcion selecciona solo esa opcion. El check la agrega o la quita. Cualquier usuario con acceso a `digital_income` puede modificar la seleccion compartida. Las escrituras usan `version` para rechazar cambios simultaneos sobre una version anterior. Al entrar o actualizar la pantalla se recupera la seleccion vigente.

Las opciones siguen viniendo exclusivamente del mart `digital_income_statement_summary.parquet`. Cuentas fuera de la vista de statements, como las exclusiones contractuales ya existentes, no se reincorporan mediante este filtro.
