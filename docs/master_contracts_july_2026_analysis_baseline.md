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
- Los registros anteriores con reparto plano mantienen su significado original:
  titulares + principal + invitados suman un unico 100%. No se convierten al
  nuevo modelo al leerlos ni al desplegar. "Editar con bolsas" convierte la
  estructura solo en el borrador del operador, conservando el resultado economico;
  la escritura requiere Guardar y mantiene el historial anterior.
- Total master, Total participaciones y Total general son valores del contrato
  seleccionado. El total general nunca puede superar 100%, aun en borrador;
  para cerrar deben estar completos y sumar exactamente 100% (tolerancia 0.0001).
- Los contratos de invitados internos se aplican sobre su participacion, sin
  incrementar el total base. La retencion pasa a Indyana en la simulacion.
- Versiones, historial, permisos y bloqueo ante ediciones simultaneas se
  conservan. `reports_effective` sigue siendo falso.

## Dos bolsas y proyectos (2026-10-08)

- Nuevas fichas: `allocation_model=pools`. La bolsa master/comercializacion y
  las participaciones del ingreso suman 100%. Los porcentajes de participantes
  son puntos del ingreso total: tres participaciones de 10 completan una bolsa
  de 30, no son tres veces el 10% de esa bolsa.
- Los titulares distribuyen exclusivamente la bolsa master. Su propia suma es
  100%, independiente del 70/30 inicial. `owner_split_mode=equal` guarda la regla
  de partes iguales y calcula 1/N, sin cargar tres porcentajes truncados a 33.33.
- Contrato simple y Proyecto con socios son configuraciones por acuerdo/ISRC.
  No se fijan socios ni porcentajes finales en el codigo. Se admiten doce
  titulares y diez participantes adicionales al principal.
- Cada fila, incluso el principal, elige un tratamiento explicito: `direct`,
  `artist_contract` o `project_owners`. Ser artista interno no aplica por si solo
  una segunda retencion. En proyectos, el reparto entre socios utiliza los
  mismos titulares del master, sin volver a aplicar el 70/30 ni recursividad.
- La retencion de un contrato interno tiene destinatario editable. Una propuesta
  de la biblioteca guarda porcentaje, artista y version como foto en la ficha;
  editar la biblioteca no cambia contratos de ISRC existentes. Los contratos
  generales pueden editarse desde la ficha sin perder su borrador.
- Gusty: bolsa master 70%, titulares Indyana/Gusty 50/50, participacion Gusty
  30% directa. El resultado consolidado es Indyana 35%, Gusty 65%.
- Ejemplo La Juntada: 70% master con tres socios iguales; participaciones de
  10% para La Juntada (socios), Sasha (directo en este ejemplo) y Sofi B
  (70% de retencion para Indyana). Sobre USD 100, se distribuyen 33.67, 26.67,
  26.66, 10 y 3. Este ejemplo de prueba no crea ni modifica acuerdos reales.
- La simulacion consolida destinatarios por nombre normalizado y muestra los
  origenes. Redondea solo despues de consolidar; los centavos restantes se
  asignan por mayor resto, con desempate estable por orden de destinatarios.
  Ajustes negativos usan la misma distribucion con signo invertido.
- La persistencia del modelo nuevo es exclusivamente Cloud SQL Postgres,
  usando el JSON e historial ya existentes, sin nuevas tablas ni columnas.
  Un intento de guardarlo en SQLite falla explicitamente.
- Se conservan fecha de statement, limite de julio para la prueba, descuentos,
  vigencias inclusivas y bloqueo de solapamientos. No se modifican catalogo,
  marts, BigQuery, dashboard ni lectores de reportes. Ningun contrato entra
  automaticamente en una liquidacion actual.

Validacion: `python -m unittest scripts.qa.qa_master_contracts_pilot` y
`node web/scripts/qa_contract_logic.mjs`, incluyendo limites de mes, ano
bisiesto, distintas zonas horarias, superposiciones y conservacion de importes.

## Codigos asociados en Contratos (2026-10-09)

- La ficha incorpora "Ver codigos asociados", cerrado por defecto. Consulta
  exclusivamente la version publicada de BigQuery al abrirlo, sin sumar
  lecturas al listado ni modificar el catalogo, ingestas o importes.
- UPC y video/UGC se incluyen automaticamente solo si el resolvedor vigente
  del catalogo los relaciona de forma exacta y unica con el ISRC, y ningun
  statement publicado los vincula a otro ISRC. No se comparan nombres.
- Los IDs de plataforma requieren una coincidencia exacta y unica dentro
  de su distribuidora/cuenta; no se asume que sean globales.
- Una referencia exacta sin alias unico queda pendiente, desmarcada. El
  operador debe confirmar su inclusion. UPC compartidos por varios ISRC,
  referencias a otro asset y productos ADA sin ISRC no son asignables a
  un contrato de tema. No se atribuye a un tema el ingreso de un album.
- Las inclusiones y exclusiones explicitas se guardan en
  `split.code_association_overrides`, dentro de la ficha e historial de Cloud
  SQL existentes. Hay un solo contrato, no copias por codigo. Un cliente
  anterior que omita el campo conserva las decisiones ya guardadas.
- La confirmacion manual guarda una huella de los identificadores y su
  relacion, no de importes, meses ni nombres. Una nueva contradiccion invalida
  esa confirmacion y vuelve a requerir revision; la exclusion se conserva.
- Se mantienen permisos y versionado. Un bloqueo transaccional en PostgreSQL
  impide que dos guardados simultaneos reclamen el mismo codigo. El backend
  vuelve a comprobar cualquier nueva inclusion y rechaza evidencia desactualizada.
- Esta etapa registra y muestra las asociaciones solo en Contratos. No agrega
  ingresos a la simulacion ni cambia los lectores de dashboard o reportes,
  incluido el ejecutivo contractual. Su aplicacion economica sera otra etapa
  con conciliacion y autorizacion explicita.

Validacion adicional: `python -m unittest scripts.qa.qa_master_contract_associations`.
