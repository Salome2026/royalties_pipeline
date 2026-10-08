# Contratos: ingresos de prueba hasta julio de 2026

Contratos consulta la misma vista vigente de BigQuery que el dashboard de
regalias (`royalty_dashboard_current`) y aplica la misma politica de descuento
por fuente y cuenta. El unico limite temporal de esta prueba es el mes de
statement: se incluyen statements hasta julio de 2026 inclusive. No se fija
una publicacion anterior ni se mantiene un importe alternativo.

Si el dashboard usa su respaldo Parquet, Contratos consulta el mismo resumen
vigente y aplica `apply_report_net_personalization`. La lista y la ficha
conservan los ISRC, titulos y creditos del catalogo activo; un ISRC sin
ingresos en el periodo figura con cero. La vigencia sugerida comienza en el
primer statement del ISRC, nunca en su primera fecha de consumo. Esta fecha
se busca en toda la publicacion vigente, incluso si es posterior a julio;
el limite de julio sigue aplicandose a los importes de las simulaciones.

Esta vista es solo para validar contratos. No modifica el catalogo, los
repartos guardados, el dashboard ni los reportes actuales.

## Vigencias y porcentajes (2026-10-08)

- Desde y Hasta son fechas civiles inclusivas, sin conversion a horas.
  Un contrato que termina el 31/10 puede ser seguido por otro desde el 01/11.
  Hasta vacio mantiene el contrato abierto; la simulacion toma la fecha actual.
- Los statements publicados tienen precision mensual. Su fecha canonica es
  el primer dia del mes. Se asigna el statement completo al contrato que
  contiene esa fecha; no se inventan fechas diarias ni se prorratean consumos.
  Un corte dentro del mes no divide el statement entre dos contratos.
- Las vigencias no pueden superponerse, tampoco al guardar borradores. Se
  admiten intervalos separados si el operador los define explicitamente;
  no se rellenan huecos ni se cambian fechas guardadas automaticamente.
- La simulacion utiliza los ingresos de statements dentro de la vigencia
  seleccionada, con la misma politica de descuentos que el dashboard.
- Cada contrato puede guardar su propio reparto. Los registros antiguos sin
  reparto por contrato conservan el reparto global como respaldo de lectura.
  No se hace ninguna migracion automatica de acuerdos o porcentajes guardados.
- En Master, titulares + principal + invitados suman un unico 100%. La parte
  empresarial se carga en titulares y no vuelve a sumarse como Indyana en el
  reparto. En Distribucion, la comision de Indyana integra el reparto economico.
- Total master, Total participaciones y Total general son valores del contrato
  seleccionado. El total general nunca puede superar 100%, aun en borrador;
  para cerrar deben estar completos y sumar exactamente 100% (tolerancia 0.0001).
- Los contratos de invitados internos se aplican sobre su participacion, sin
  incrementar el total base. La retencion pasa a Indyana en la simulacion.
- Versiones, historial, permisos y bloqueo ante ediciones simultaneas se
  conservan. `reports_effective` sigue siendo falso.

Validacion: `python -m unittest scripts.qa.qa_master_contracts_pilot` y
`node web/scripts/qa_contract_logic.mjs`, incluyendo limites de mes, ano
bisiesto, distintas zonas horarias, superposiciones y conservacion de importes.
