# Ingresos de producto a grabaciones

Regla de sistema `product-income-equal-tracks-v1`, aplicada en vistas derivadas. No modifica TXT, Excel originales, archivos estandarizados, contratos ni identidades nativas del catálogo.

Un UPC se valida con una composición completa, con todas sus posiciones y todos sus ISRC. La evidencia debe corresponder al UPC exacto; admite equivalencias de ceros a la izquierda de GTIN. Los ISRC observados en todas las distribuidoras deben ser compatibles con esa composición. Las respuestas parciales, UPC diferentes y composiciones contradictorias permanecen pendientes. No se infiere una lista completa por contar los temas que tuvieron ventas.

El ingreso de un producto validado se reparte por posición: un tema recibe el 100%; N posiciones reciben 1/N cada una. Si se repite un ISRC en dos posiciones, recibe ambas partes. Se conservan importes negativos, monedas, unidades agregadas, períodos, cuentas, tiendas y territorios. Los movimientos que ya tienen ISRC, videos, UGC, transferencias y fracciones ya prorrateadas por origen no se vuelven a repartir. Un producto multipista exige evidencia de que el movimiento corresponde al producto completo; un UPC de un movimiento de tema desconocido no alcanza.

`product_income_allocations.json` contiene la composición verificada, las referencias de evidencia, los contextos nativos de producto y una huella. Se reconstruye sobre todo el histórico admitido al cerrar cada ingesta/publicación. Reutiliza composiciones verificadas de la versión anterior; los nuevos UPC se consultan con las credenciales de metadata existentes. La falta de servicio deja el ingreso original visible, sin adivinar relaciones. Una contradicción nueva invalida la asignación anterior. No se consulta Spotify al abrir un informe.

## Lecturas del sistema

- Excel por keyword, Google Sheets, PDF de ingresos y reportes por títulos utilizan la misma vista. La búsqueda contempla el texto original del producto y el ISRC/tema de destino. Los ingresos del producto resuelto se suman al ISRC; el producto sin resolver conserva su fila.
- Aplicar contratos conserva la selección y los importes base. Solo agrega las columnas de reparto existentes, cuando corresponden a un contrato vigente.
- Dashboard y detalle de ingresos digitales utilizan la misma asignación, antes de sus filtros y políticas habituales. La cifra de control de la distribuidora y la trazabilidad siguen reflejando el archivo original.
- Contratos → Sin identificar retira los movimientos ya distribuidos, sin exigir contratos cerrados. El camino de ingresos asociados adicionales no vuelve a sumarlos.
- El catálogo conserva sus productos, UPC y códigos nativos. Se actualizan sus importes por la diferencia de la distribución; las referencias de ISRC faltantes proceden de la composición verificada. La metadata observada del producto sigue disponible. No se crea un alias UPC → un único ISRC para un álbum multipista, ni se deducen propietarios a partir de los créditos.
- WML mantiene su propio documento y su propio catálogo. Las bases 100%, las regalías informadas y las fracciones 1/7, 1/8, etc. conservan su interpretación original; estas fracciones no se redistribuyen como otra venta completa.

## Histórico y futuras ingestas

La preparación de una publicación reconstruye primero los resúmenes de canciones preservando el UPC/tipo de producto, compila la evidencia, reconstruye el catálogo nativo y aplica la distribución, y genera los resúmenes analíticos. La reconstrucción de canciones concilia por distribuidora/cuenta y no reingiere ni sobrescribe el crudo admitido. Los constructores trabajan por lectura progresiva para evitar cargar todo el FUGA histórico en memoria.

La evidencia se publica en el mismo manifiesto inmutable que sus datos. Caché, trabajos de reportes y actualizaciones del dashboard fijan esa versión exacta. Un informe histórico de una versión anterior que no contenía la regla mantiene su comportamiento anterior. Nunca toma una asignación del objeto canónico de otra versión. Las cachés analíticas cambian al cambiar la evidencia.

La actualización de importes del catálogo se aplica a un catálogo recién reconstruido desde el resumen nativo; su marca de revisión evita aplicarla dos veces. No se aplica una versión diferente sobre un catálogo ya distribuido.

## Verificación local

`scripts/qa/qa_product_income.py` cubre conservación, negativos, posiciones repetidas, contratos independientes, búsqueda original/destino, evidencia incompleta/contradictoria, reutilización ante nuevas ingestas, aislamiento WML, documentos fijados por versión, caché, catálogo, dashboard, ingresos digitales y formato del Excel con/sin contratos.

La comparación histórica y los archivos de revisión se generan sobre copias locales de los objetos publicados. No implican publicar código, subir marts o modificar la base operativa.
