# Ingresos de producto a grabaciones

Regla de sistema `product-income-equal-tracks-v1`, aplicada en vistas derivadas. No modifica TXT, Excel originales, archivos estandarizados, contratos ni identidades nativas del catálogo.

Un UPC se valida con una composición completa, con todas sus posiciones y todos sus ISRC. La evidencia debe corresponder al UPC exacto; admite equivalencias de ceros a la izquierda de GTIN. Los ISRC observados en todas las distribuidoras deben ser compatibles con esa composición. Las respuestas parciales, UPC diferentes y composiciones contradictorias permanecen pendientes. No se infiere una lista completa por contar los temas que tuvieron ventas.

El ingreso de un producto validado se reparte por posición: un tema recibe el 100%; N posiciones reciben 1/N cada una. Si se repite un ISRC en dos posiciones, recibe ambas partes. Se conservan importes negativos, monedas, unidades agregadas, períodos, cuentas, tiendas y territorios. Los movimientos que ya tienen ISRC, videos, UGC, transferencias y fracciones ya prorrateadas por origen no se vuelven a repartir. Un producto multipista exige evidencia de que el movimiento corresponde al producto completo; un UPC de un movimiento de tema desconocido no alcanza.

En ADA, un UPC ausente también puede recuperarse para la asignación si el mismo número de catálogo, en la misma cuenta, tiene un único UPC observado en el histórico admitido y ese UPC tiene composición completa validada. La referencia queda en la evidencia; el UPC vacío del archivo original no se modifica. Si el código nativo reaparece con varios UPC, deja de resolverse por esa equivalencia.

`product_income_allocations.json` contiene la composición verificada, las referencias de evidencia, los contextos nativos de producto y una huella. Se reconstruye sobre todo el histórico admitido al cerrar cada ingesta/publicación. Reutiliza composiciones verificadas de la versión anterior; los nuevos UPC se consultan con las credenciales de metadata existentes. La falta de servicio deja el ingreso original visible, sin adivinar relaciones. Una contradicción nueva invalida la asignación anterior. No se consulta Spotify al abrir un informe.

## Lecturas del sistema

- Excel por keyword, Google Sheets, PDF de ingresos y reportes por títulos utilizan la misma vista. La búsqueda contempla el texto original del producto y el ISRC/tema de destino. Los ingresos del producto resuelto se suman al ISRC; el producto sin resolver conserva su fila.
- Aplicar contratos conserva la selección y los importes base. Solo agrega las columnas de reparto existentes, cuando corresponden a un contrato vigente.
- Dashboard y detalle de ingresos digitales utilizan la misma asignación, antes de sus filtros y políticas habituales. La cifra de control de la distribuidora y la trazabilidad siguen reflejando el archivo original.
- Contratos → Sin identificar retira los movimientos ya distribuidos, sin exigir contratos cerrados. El camino de ingresos asociados adicionales no vuelve a sumarlos.
- Un producto pendiente no puede saltarse la regla por un alias antiguo UPC → ISRC ni recibir columnas de contrato por ese camino. Los hechos analíticos conservan el tipo de producto, su lanzamiento y su origen; al agrupar los pendientes se separan los movimientos de álbum de los de tema, aunque tengan el mismo título.
- El catálogo conserva sus productos, UPC y códigos nativos. Se actualizan sus importes por la diferencia de la distribución; las referencias de ISRC faltantes proceden de la composición verificada. La metadata observada del producto sigue disponible. No se crea un alias UPC → un único ISRC para un álbum multipista, ni se deducen propietarios a partir de los créditos.
- WML mantiene su propio documento y su propio catálogo. Las bases 100%, las regalías informadas y las fracciones 1/7, 1/8, etc. conservan su interpretación original; estas fracciones no se redistribuyen como otra venta completa.

## Histórico y futuras ingestas

La preparación de una publicación reconstruye primero los resúmenes de canciones preservando el UPC/tipo de producto, compila la evidencia, reconstruye el catálogo nativo y aplica la distribución, y genera los resúmenes analíticos. La reconstrucción de canciones concilia por distribuidora/cuenta y no reingiere ni sobrescribe el crudo admitido. Los constructores trabajan por lectura progresiva para evitar cargar todo el FUGA histórico en memoria.

La evidencia se publica en el mismo manifiesto inmutable que sus datos. Caché, trabajos de reportes y actualizaciones del dashboard fijan esa versión exacta. Un informe histórico de una versión anterior que no contenía la regla mantiene su comportamiento anterior. Nunca toma una asignación del objeto canónico de otra versión. Las cachés analíticas cambian al cambiar la evidencia.

Las consultas de contratos conservan la versión de sus rutas inmutables aunque otra petición active una publicación nueva. Al construir el dashboard se fijan tanto la evidencia como el catálogo de su crudo; los filtros no toman los alias que haya dejado otra petición. WML recupera la evidencia de su publicación anterior para nuevas ingestas y conserva esa copia también al reutilizar un paquete local.

El Job WML recibe las credenciales de metadata existentes desde Secret Manager. Su identidad tiene lectura únicamente sobre esos dos secretos para validar UPC nuevos; las credenciales no se guardan en el manifiesto ni en los archivos de ingreso.

El Job de reportes fija `POLARS_MAX_THREADS=2`, acorde con sus dos CPU. Esto acota los buffers de lectura del histórico completo; sin ese límite el contenedor puede dimensionarlos según el host y exceder su memoria al abrir el crudo ancho.

La actualización de importes del catálogo se aplica a un catálogo recién reconstruido desde el resumen nativo; su marca de revisión evita aplicarla dos veces. No se aplica una versión diferente sobre un catálogo ya distribuido.

La inferencia antigua por un único ISRC observado no absorbe los productos nativos. En la versión con esta regla, esos productos conservan su referencia propia y los UPC pendientes o multipista no generan una equivalencia a una sola grabación. Un sencillo con composición completa validada sí conserva su equivalencia exacta al ISRC.

## Verificación local

`scripts/qa/qa_product_income.py` cubre conservación, negativos, posiciones repetidas, contratos independientes, búsqueda original/destino, evidencia incompleta/contradictoria, reutilización ante nuevas ingestas, aislamiento WML, documentos fijados por versión, caché, catálogo, dashboard, ingresos digitales y formato del Excel con/sin contratos.

La comparación histórica y los archivos de revisión se generan sobre copias locales de los objetos publicados. No implican publicar código, subir marts o modificar la base operativa.

Validación del 1 de noviembre de 2026, sobre la publicación `20261101T163543Z-2f313121b4e1`:

- Se conciliaron 13.075.096 movimientos por distribuidora, cuenta, período de liquidación y mes de consumo, conservando dinero y unidades.
- La Juntada conserva USD 117.712,22 en los cuatro Excel: antes/propuesta, con/sin contratos. El resumen por tema pasa de 300 a 291 filas. Las columnas base son idénticas al activar contratos, incluido el detalle limitado. La búsqueda por mes de consumo conserva también el total y 668.713.063 unidades.
- Dashboard e ingresos digitales conservan sus respectivos totales y los cortes por origen y período. El catálogo mantiene todas las referencias publicadas y concilia su redistribución.
- WML conserva USD 3.846.332,769569616 de base al 100%, USD 977.028,663560130 de regalía informada y 6.404.610.360 unidades; catálogo, dashboard e ingresos digitales concilian con esa base.
- La batería conjunta ejecuta 159 pruebas: 158 aprobadas y una dependiente de datos WML locales omitida. La comprobación WML anterior se realizó por separado con el histórico real. También se verificaron motor, presentación, modos de detalle, las 19 reglas de tienda y la compilación de la aplicación web.
