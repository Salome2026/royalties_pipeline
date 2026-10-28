# Asociar desde Sin identificar

## Operacion

Accion Asociar en cada referencia, disponible con permiso de edicion.
El dialogo busca por tema, artista o ISRC y exige elegir y confirmar el destino.
La busqueda no vuelve a calcular los ingresos de todo el catalogo.

La confirmacion guarda decisiones en `code_association_overrides`, con marca
`manual`, usando la misma infraestructura de asociados que Contratos.
No se crean ventas, se cambian importes ni se reescriben los crudos.
Los lectores generales y el dashboard sin splits no se modifican.
El contrato queda abierto y sin aplicacion futura seleccionada hasta su revision;
porcentajes, titulares, participantes, reglas y notas guardadas se conservan.
El historial registra usuario, fecha y version mediante `save_split`.

## Protecciones

- Permisos de edicion y, para reabrir un contrato cerrado, aprobacion.
- Version optimista, release de datos y firma de referencia comprobados al guardar.
- Mismo bloqueo global que las asociaciones normales; dos confirmaciones no
  pueden reclamar la misma referencia para destinos diferentes.
- Se comprueban todos los identificadores economicos de las filas afectadas:
  ningun vinculo puede quitar ingresos de otro destino o duplicarlos.
- Cualquier ISRC nativo incompatible, UPC compartido o reclamo previo bloquea.
- Los productos ADA sin ISRC conservan su identidad propia; no se asignan a una cancion.
- Las referencias sin codigo estable no se asignan por texto.
- La decision sirve en ingestas posteriores para el mismo codigo y su ambito;
  cambios en evidencia nativa invalidan la decision en vez de forzarla.
- Descartar desde Codigos asociados conserva la exclusion manual.
- Las reglas se leen usando la conexion de la transaccion, sin reservar otra
  conexion de la misma piscina; tambien funciona con un unico puesto disponible.

## Pruebas

Regresion local de 352 pruebas Python, siete grupos de controles de contratos
en la web y controles del proxy, autenticacion, origen y versiones.
Las escrituras reales de aceptacion se ejecutan exclusivamente en la copia cloud
y se restauran junto con el historial y los estados de revision.
En produccion se despliega solo codigo, sin importar contratos de la copia.

Evidencias: `C:/royalties_pipeline/staging/catalogo_lectura/20261028_unidentified_associate`.
