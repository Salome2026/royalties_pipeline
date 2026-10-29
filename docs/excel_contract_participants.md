# Participantes contractuales opcionales en Excel

En Reporte de regalias, Incluir contratos comienza en No. Esa opcion conserva
los parametros canonicos anteriores, el generador y los permisos existentes.
No hace consultas de contratos, no fija snapshots nuevos y no agrega columnas.

Con Si, Mostrar reparto permite todos los involucrados o los nombres coincidentes
con las palabras de busqueda. No requiere seleccionar un artista exacto. La
busqueda original sigue seleccionando los ingresos; los contratos no filtran,
agregan, fusionan ni eliminan resultados. El limite del detalle no limita el reparto.

Solo resumen por tema agrega dos columnas por participante: su nombre, con el
porcentaje efectivo sobre el ingreso de esa fila, y `Importe <nombre>`, en USD.
No agrega hojas, controles, observaciones ni columnas de vigencia o conciliacion.
Las hojas restantes conservan sus datos y estilo. No son dinamicas al borrar temas.

El pedido congela contratos, catalogo, fecha y asociados aceptados del mismo
release. La captura usa PostgreSQL REPEATABLE READ READ ONLY y los lectores
compartidos de asociados, sin la decodificacion de slots de rankings del PDF:
el Excel trabaja con identificadores nativos del Parquet ya fijado por generacion.
El trabajador no consulta contratos vivos ni infiere derechos desde los nombres.

El reparto usa validate_split y allocation_rows existentes. Conserva precision
numerica en las celdas y muestra dos decimales, como el Excel de referencia;
no redondea cada tema antes de sumar los importes del participante.
Respeta cierres, contratos internos, socios, destinatarios de distribucion y
vigencias por statement, incluso cuando el informe selecciona por consumo.
Los fragmentos se agrupan antes de calcular, no se recorre cada venta en Python.
Una diferencia entre el ingreso original y sus fragmentos deja el reparto de la
fila en blanco: nunca modifica el ingreso para hacerlo coincidir.

Sin contrato cerrado valido o sin vigencia aplicable: vacio, no cero. Con reparto
valido, un participante informado sin participacion economica recibe cero.
Los porcentajes reflejan el periodo completo; si hay cobertura parcial incluyen
solo el ingreso efectivamente cubierto. Ante neto cero y reparto efectivo no
representable como porcentaje, se conserva el importe y el porcentaje queda vacio.

Crear, consultar o descargar un Excel con contratos requiere los mismos permisos
de contratos que el PDF contractual. Los archivos antiguos no se reescriben.
El selector se habilita solo cuando la API anuncia soporte; el frontend elimina
estos parametros al generar PDF o Google Sheets. WML conserva su lectura al 100%.

Pruebas: scripts/qa/qa_excel_contracts.py y web/scripts/qa_excel_contracts.mjs.
