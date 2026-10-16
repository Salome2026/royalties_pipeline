# Reglas de lectura de ONErpm para futuras ingestas

Proyecto CATALOGO-LECTURA. Tarea LEC-ONERPM-C.
Version documental ONERPM-LECTURA-1. Fecha 2026-10-14. Responsable: Codex.
Estado: especificacion completa; prueba nativa aislada realizada, sin adopcion.
Resultado D actualizado: docs/catalogo_lectura_onerpm_lector_completo_20261014.md.
Defensas integradas y probadas en candidato completo. Siguen pendientes revision
E y validacion de futuros consumidores; no hay adopcion ni publicacion.

Pedido de Ruben: definir las reglas para futuras ingestas, respetando Shares In
and Out, sin modificar el sistema ni lo cargado. Este documento completa la
definicion C; no certifica un lector, no modifica las normas productivas ni
autoriza D, una reingesta historica o un despliegue.

La salida futura es un catalogo maestro comun: tema, codigo, principal propuesto
y otros artistas. La evidencia y los roles quedan por detras. BigQuery reutilizara
esa definicion junto con los hechos economicos y los contratos; cada pantalla no
volvera a extraer nombres por su cuenta. Los contratos determinan beneficiarios,
porcentajes y vigencias, nunca los creditos ni los porcentajes de ONErpm.

## Base y alcance

Marco comun: CAT-003 v1.2. Auditoria: catalogo_lectura_onerpm_20261014.md.
Se revisaron 182 Excel, 1092 hojas y las cuatro cuentas. El alcance observado
incluye 1063609 filas Masters, 128889 Youtube Channels, 623924 Shares y 6446
Summary; Publishing Rights y Commissions estan vacias. No es una lista fija de
artistas, ISRC ni meses permitidos. Un artista o lanzamiento nuevo no requiere
otra regla si sus columnas y significado siguen dentro del formato definido.

| Hoja exacta | Layout base | Variante observada | Funcion |
| --- | ---: | --- | --- |
| Masters | 22 columnas | 24, agrega Creations y Views | Generacion de pista o lanzamiento |
| Youtube Channels | 19 columnas | 21, agrega Creations y Views | Generacion de video/canal |
| Shares In & Out | 17 columnas | 19, agrega Creations y Views | Transferencias y evidencia |
| Summary | 7 columnas | 8, con ONErpm's Share u ONErpms Share | Control, no nueva economia |
| Publishing Rights | 21 columnas | 23, agrega Creations y Views | Esquema observado, sin filas certificadas |
| Commissions | 5 columnas | Sin otra variante recibida | Esquema observado, sin filas certificadas |

Son 12 combinaciones hoja/layout. Los encabezados completos, orden y tipos de
cada archivo estan en native_files.json y native_sheets.json del analisis A/B.
Reordenar columnas conocidas no cambia su significado. No certificar por
extension una nueva hoja, cuenta o formato de archivo.

La autoridad de negocio es la policy viva de Cloud SQL, no este documento ni un
JSON local. Snapshot observado el 2026-10-14: version 12, ajuste de reportes 10%
para las cuatro cuentas. Congelar esa version en cada futura ejecucion; si cambia,
revalidar equivalencia contra la nueva policy, no sobreescribirla desde el lector.

## O01 Paquetes, cuentas y reenvios

La unidad de lectura es el archivo completo de una cuenta y statement, con sus
seis hojas. Un lote puede declarar varios archivos y dependencias; ese conjunto
es la unidad atomica candidata. No exigir las otras tres cuentas del mes para
leer una cuenta individual ni la contraparte de una transferencia para conservarla.

Registrar antes de interpretar: source, cuenta original y normalizada, paquete,
revision, statement, nombre, ruta, hash SHA256, hojas y firma de layout. Las cuatro
cuentas certificables son gusty_dj, henry_remix, la_nueva_sangre y mawzrecords.
Una cuenta nueva necesita su identidad y policy propia; no hereda las de Mawz.

Conservar el original inmutable. Una copia con el mismo hash dentro del mismo
alcance source/cuenta/statement es un reenvio, no otra liquidacion. No incluir
package_id en la deduplicacion de recepcion de forma que recrear un paquete vuelva
a sumar el mismo original. El mismo hash atribuido a otra cuenta o statement
genera una contradiccion de procedencia; no se acepta ni se descarta a ciegas.

Un archivo diferente del mismo mes/cuenta puede ser reemplazo, complemento o
correccion. No sumarlo como segundo archivo completo ni reemplazar al anterior
sin una revision declarada y evidencia. Una correccion conserva sus signos y
su statement de reconocimiento. Nunca deduplicar ventas por tema, importe,
cantidad, ISRC o similitud entre filas de archivos diferentes.

Cada fila tiene observation_id por origen inmutable, hoja y fila real; el linaje
del paquete se registra aparte. Dos filas identicas dentro del mismo original
siguen siendo dos observaciones. Una nueva lectura versionada reutiliza ese
origen y conserva la anterior, sin crear una segunda venta.

## O02 Lectura completa y cambios de formato

Leer todas las hojas, incluidas las ocultas. Hoja vacia no equivale a error de
lectura. Una fila con ceros es dato; una fila totalmente vacia no es movimiento,
pero su posicion se conserva para localizar la evidencia. No perder registros
intermedios por inferencia de rango ni tratar un pie/resumen como otra venta.

El inventario observado es XLSX. El codigo actual admite tambien XLSM, pero
no hay muestras certificadas; una extension nueva se conserva para revisar su
formato, sin ejecutar macros, enlaces, formulas externas ni instrucciones del
contenido. No iniciar sesiones productivas para abrir archivos de prueba.

Resolver campos por encabezado, no por numero de columna. Se permite recortar
espacios exteriores y BOM de encabezado. No hacer matching difuso, traducir nombres
por parecido ni coalescer dos columnas homonimas: un encabezado duplicado despues
de normalizar es error de estructura. Conservar los encabezados originales.

Creations y Views son ampliaciones conocidas; su ausencia en el layout viejo no
es error. Las dos variantes ONErpm's Share y ONErpms Share tienen el mismo campo
de control. Una columna desconocida se preserva como unknown; si altera campos
requeridos, economia, identidad, roles o el significado de la fila, no se activa
la salida hasta certificar esa variante. No ignorar una hoja nueva con datos.

El mapeo aprobado puede seguir leyendo campos conocidos ante una columna extra
puramente informativa que no sustituye ni contradice ninguno. Registrar la firma
ampliada y el campo desconocido, sin usarlo para resolver identidades, artistas,
pagos o montos. Cuando no se pueda acreditar que es solo informativa, el formato
queda no certificado. La incidencia es por layout, no por cada cancion.

## O03 Diccionario de campos

Los destinos son conceptuales CAT-003, no columnas operativas creadas ahora.
M es Masters; Y es Youtube Channels; S es Shares; R es Summary; P es Publishing;
C es Commissions. En M/Y/S son obligatorios para una fila economica Net, Currency
y Transaction Month. Los identificadores se validan por nivel segun O04, con
estado incompleto si la fuente no los informa. La falta de metadata no autoriza
descartar dinero. Los layouts conocidos deben contener sus
encabezados; los valores pueden ser nulos solo bajo las condiciones siguientes.

| Campo original | Hojas | Destino y regla |
| --- | --- | --- |
| Album Title | M | release_title_original; titulo de producto, no participantes |
| Track Title | M | track_title_original; esperado en Track/Video Track, vacio valido en Album |
| Artists | M/S | texto de creditos; O06/O07 por nivel, nunca Payer como reemplazo |
| Label | M | sello/contexto original; no titularidad ni artista inferido |
| UPC | M | identificador de lanzamiento explicito, texto, O04 |
| ISRC | M/P | identificador de grabacion explicito; P conserva esquema sin certificar filas |
| Product Type | M/S | nivel nativo Track, Video Track, Album o YouTube Video segun hoja |
| Store | M/Y/S | dsp_original; taxonomia vigente, desconocido no altera dinero |
| Territory | M/Y/S/P | country_original; conservar literal, sin inferir desde DSP |
| Sale Type | M/Y/S | usage_original; conservar sufijos Share In/Out y correcciones |
| Transaction Month | M/Y/S/R/P/C | consumo mensual, O09; no statement ni fecha de cobro |
| Accounted Date | M/Y/S/P/C | fecha contable original, O09; no banco ni sustituto de consumo |
| Original Currency | M/Y/P | gross_currency_original; admite ausencia cuando no se informa esa etapa |
| Gross (Original Currency) | M/Y/P | gross_original; no se suma al Gross ni al Net |
| Exchange Rate | M/Y/P | distributor_fx; ya forma parte de la etapa anterior, no aplicarlo a Net otra vez |
| Currency | M/Y/S/R/P/C | reported_currency; obligatoria para monto informado, sin default USD |
| Gross | M/Y/P | bruto informado; no reconstruye ni reemplaza el Net |
| Quantity | M/Y/S/P | units_original y units; signo/cero conservados, O10 |
| Average Unit Gross | M/Y/P | promedio original; no sumar promedios ni recalcular Net con el |
| % Share | M/Y/P | termino de liquidacion ONErpm, no split interno; no reaplicarlo a Net |
| Fees | M/Y/P | deduccion informada; no restarla de Net otra vez |
| Net | M/Y/S/R/P | amount_reported en detalle; R es control, no otra venta |
| Creations | M/Y/S/P nuevos | metrica separada, nulo si no se informaba; no suplanta Quantity |
| Views | M/Y/S/P nuevos | metrica separada, nulo si no se informaba; no suplanta Quantity |
| Video Title | Y | video_title_original; no lista de artistas |
| Channel Name | Y | channel_name_original; contexto, no interpretes de cada video |
| Channel ID | Y | identificador de canal, no asset ni ISRC |
| Video ID | Y | identificador de video, sensible a mayusculas, no ISRC |
| Title | S/C | titulo de la entidad transferida o comision segun hoja; C sin filas certificadas |
| ID | S | ISRC, video o UPC segun Product Type; sin inferir por forma aislada |
| Parent ID | S | UPC del lanzamiento o Channel ID segun Product Type |
| Payer Name | S | contraparte pagadora, no artista por ese dato |
| Receiver Name | S | contraparte receptora, no artista por ese dato |
| Share Type | S | In u Out, no derivarlo del signo de Net |
| % Share In/Out | S | participacion de transferencia ONErpm, no reparto interno ni otro factor sobre Net |
| Source | R | agrupador del resumen de distribuidora, no otra distribuidora de hechos |
| Catalog Revenue | R | control de generacion nativa M mas Y antes de filtrar el negocio |
| Share In | R | control de transferencias entrantes con su signo |
| Share Out | R | control de transferencias salientes con su signo |
| ONErpm's Share | R variante | partida de control; cero observado, no nueva deduccion aprobada |
| ONErpms Share | R variante | mismo destino anterior, conservar encabezado recibido |
| Song Title | P | titulo editorial original; hoja vacia, sin nueva regla economica |
| Writers | P | credito editorial, no artista por ese solo campo |
| Performers | P | credito declarado en esquema editorial; no adoptarlo sin certificar filas P |
| Custom ID | P | identificador nativo scoped, no convertirlo en ISRC |
| ISWC | P | identificador distinto de ISRC, mantener tipo y literal |
| Revenue Source | P | contexto de origen editorial, no mapearlo a Store sin certificacion |
| Owned Share | P | participacion informada, no contrato interno ni titularidad inferida |
| Revenue | C | monto de esquema Commissions, sin filas certificadas; no tratarlo como Net |

Las 49 columnas estan cubiertas. Conservar campo original, tipo de celda,
valor recibido, valor interpretado, regla, evidencia y estado. Un nulo opcional
no se vuelve cadena de nombre ni cero. Una celda con formula sin resultado
cacheado fiable no se calcula ejecutando Excel para adivinar el monto.

## O04 Identidad segun hoja y nivel

| Hoja y Product Type | Identidad de entidad | Relacion/contexto |
| --- | --- | --- |
| M Track | ISRC explicito de ISRC | UPC explicito de lanzamiento |
| M Video Track | ISRC explicito de ISRC, Product Type conservado | UPC, sin convertirlo automaticamente en Video ID |
| M Album | UPC explicito; entidad lanzamiento | ISRC nulo esperado; no distribuir a pistas |
| Y | Video ID explicito, namespace youtube_video | Channel ID explicito, namespace youtube_channel |
| S Track/Video Track | ID como ISRC valido | Parent ID como UPC; economic_kind transfer |
| S YouTube Video | ID como Video ID valido | Parent ID como Channel ID; economic_kind transfer |
| S Album | ID como UPC | Parent ID como UPC, conservando ambos; economic_kind transfer |

Primero determinar el nivel desde la hoja y Product Type; luego validar forma.
Para ISRC se admite limpieza de espacios/separadores tipograficos y mayusculas,
con literal conservado; debe resultar dos letras, tres alfanumericos y siete
digitos. No limpiar basura hasta que cualquier texto parezca un ISRC. Dos ISRC
distintos siguen siendo dos assets aunque titulo o participantes sean iguales.

UPC se conserva como texto con ceros iniciales. Recortar espacios no altera su
identidad; no rellenar digitos, extraer numeros de una etiqueta ni recuperar
precision perdida de una cadena cientifica recortada. La validacion de forma y
la evidencia de columna/tipo son separadas de cualquier comprobacion adicional
de GTIN. Un codigo dudoso se conserva con estado puntual, no se transforma en
ISRC ni cambia los aliases existentes. No endurecer retroactivamente el filtro
productivo de UPC dentro de la adopcion de participantes.

Video ID y Channel ID se validan con los validadores vigentes y conservan
mayusculas/minusculas. No forzar uppercase de claves YouTube para asociar entidades.
Ningun ID se interpreta como pista solo por tener once caracteres o por estar en
una columna llamada ID. Si nivel y forma discrepan, guardar ambas evidencias y
marcar identidad incompleta/contradictoria, conservando la observacion economica.

Si Track no informa ISRC, no usar Parent ID/UPC como ISRC de reemplazo. Conservar
su identificador original y observation_id; una relacion derivada se evalua luego
con el resolver aprobado. Una fila Album con ISRC inesperado no pasa a Track a
escondidas: registrar la contradiccion de nivel.

No crear nuevas fusiones, aliases, asociados aceptados ni selecciones contractuales
por definir estas reglas. Una relacion UPC/pistas puede ser multiple. Un video
UGC puede explotar varios ISRC; no repartirlo a todos ni absorberlo en uno por
parecido. El contexto de transferencia no prueba por si solo un enlace video/ISRC.

## O05 Titulos y contexto

Conservar siempre track_title_original, release_title_original y
video_title_original por separado. Para display de Track/Video Track usar Track
Title; para Album usar Album Title; para Y usar Video Title y para S usar Title
segun su nivel. No usar el titulo del album como si fuera una pista identificada.

Una ausencia de titulo deja metadata incompleta; no elimina la fila. No inferir
participantes desde Album Title, Track Title, Video Title, Label ni nombre del
archivo. Titulo puede apoyar una relacion candidata en el resolver vigente, pero
no es por si solo prueba de identidad ni de interpretes. Live, remix, cover,
version, sesiones y otros descriptores permanecen como metadata, no artistas.

Titulos variantes del mismo ISRC se conservan con periodo y fuente. No separar
un ISRC ni fusionar otros por cambio de titulo. Cambios incompatibles de titulo
y creditos se revisan como una causa de identidad, sin trasladar su dinero a otro
codigo. Una correccion humana aprobada tiene alcance, version y evidencia propia.

## O06 Gramatica y roles de Artists

En los formatos observados, cada credito es nombre(rol), con espacio opcional
antes del parentesis y comas entre creditos. El parser debe consumir todo el
texto y conservar su orden; no aceptar solo el prefijo que pudo interpretar ni
unir un fragmento descartado a otro artista. No dividir nombres por y, and, &, x
o feat contenidos en un nombre: los limites los da la gramatica de creditos.

Usar parentesis de rol completos y validar el campo, no split ciego por cada coma.
Un nombre con coma literal o parentesis propios que no pueda delimitarse sin
ambiguedad queda con su texto intacto y estado puntual de credito. No inventar
un apellido, una segunda persona ni una lista desde el fragmento. Esto no es
motivo para perder economia ni exigir revisar todos los otros temas del archivo.

| Rol recibido | Resultado operativo |
| --- | --- |
| performer | Artista de la entidad acreditada, segun nivel de O04 |
| featuring | Otro artista de la entidad acreditada, mismo valor para pertenencia |
| writer | Credito conservado, no artista de pista por ese solo rol |
| musician | Credito conservado, no artista comercial por ese solo rol |
| producer | Credito conservado, no artista de pista por ese solo rol |
| mixing_engineer | Credito tecnico conservado |
| mastering_engineer | Credito tecnico conservado |
| executive_producer | Credito conservado; observado en Shares, sin inferir derechos |
| Otro rol | role_original intacto, role_normalized unknown; no adivinar equivalencia |

Normalizar espacios y caja del rol para comparar. Una persona con performer y
writer sigue siendo artista; guardar ambos creditos. Repeticiones del mismo
nombre/rol no duplican personas en display, pero se conservan en evidencia.
Nunca multiplican ingresos. No existe limite de diez artistas en la lectura;
un limite de pantalla no puede recortar los creditos recibidos.

Un nombre desconocido funciona igual que uno conocido. Un rol desconocido no
borra los performer/featuring que si se pueden leer ni bloquea un tema porque no
se sabe el detalle fino. Si la ambiguedad afecta la pertenencia de una persona,
marcar esa pertenencia incompleta; no asignarle automaticamente el rol performer.
No usar una lista de artistas de la empresa para reconocer o excluir personas.

## O07 Resolucion comun de artistas y principal

Cada observacion resuelve primero sus creditos por su hoja, nivel y ISRC. Los
performer/featuring de Masters Track/Video Track y Shares Track/Video Track con
el mismo ISRC pueden aportar evidencia de pista. En Shares conservar procedencia
y cuenta sin inferir que administramos el master. Album aporta artistas del
lanzamiento, no de cada pista; no importar la union FUGA pista/lanzamiento a ONErpm.

Para comparar nombres se permiten Unicode normalizado, espacios, caja y acentos;
el literal de display se conserva. Esa clave de comparacion no aprueba aliases
legales o artisticos. No quitar DJ, cambiar apodos, suprimir palabras o borrar
signos significativos para hacer que dos personas coincidan.

| Diferencia entre observaciones del mismo ISRC y nivel | Resolucion propuesta |
| --- | --- |
| Solo espacios, caja, acento, duplicacion del mismo credito | Una persona en salida; preservar todos los literales y sus evidencias |
| Mismo conjunto, orden o rol performer/featuring diferente | Mismas personas; roles/orden por observacion; tratar principal por separado |
| Todas las listas compatibles forman una cadena de subconjuntos, con una lista maxima recibida y sin reemplazos, contradiccion de identidad ni correccion aprobada que retire creditos | Conservar automaticamente los nombres acreditados de esa lista completa; ausencia en una observacion no borra un credito previo |
| Listas que sustituyen nombres o no son subconjuntos entre si | Conservar alternativas y estado contradictorio; no publicar solo su interseccion como lista completa |
| Nombre variante que requiere alias, como Matias Mareco y Matias Mareco DJ | Una incidencia agrupada por causa; ambas formas conservadas, sin alta automatica de dos beneficiarios ni desaparicion por interseccion |
| Correccion humana o referencia de pista expresamente aprobada | Respetar su alcance y version, manteniendo el historial original; no crear un alias global desde un caso |

La resolucion automatica de subconjuntos es una regla especifica propuesta para
creditos de pista ONErpm con identidad compatible, no una union general de todas
las fuentes ni una afirmacion de vigencia contractual. Conserva las personas
acreditadas historicamente sin afirmar que toda ausencia sea error de la fuente.
Una retirada explicita o una sustitucion contradictoria necesita evidencia propia.

Evaluar el conjunto completo de observaciones, no pares aislados ni el resultado
parcial de un bucle. Debe existir una lista nativa maxima que contenga las demas,
y cada par de conjuntos distintos debe ser comparable por inclusion. {A}, {A,B}
y {A,C} no autorizan fabricar {A,B,C}. Agregar una cuarta lista no elimina por si
solo una sustitucion ya detectada; una referencia/correccion aprobada puede
resolverla expresamente. Un alias personal pendiente tampoco se resuelve por
parecer que una lista es mas completa. La economia no depende de esta decision.

En caso contradictorio, conservar la lista ya validada del catalogo, si existe,
y las alternativas nuevas detras; no sobrescribirla silenciosamente. Si es un
tema nuevo sin lista validada, conservar los creditos candidatos con su estado,
sin presentarlos como un reparto validado. Agrupar la revision por ISRC/causa,
no por fila de reproduccion. Un cambio de metadata no reabre contratos guardados.

No decidir prioridad por monto, texto mas largo, cuenta que pago, fecha de ingesta
ni una jerarquia global de distribuidoras. Evidencia de otra fuente mantiene su
regla certificada; una contradiccion entre fuentes se conserva para el resolver
comun, no se resuelve por aplicar la regla FUGA a ONErpm.

ONErpm no declara main_artist en estos layouts. Cuando los creditos Masters de
pista compatibles tienen el mismo primer performer, se puede proponer ese nombre
como principal por orden de fuente, con estado order_only, no principal declarado
ni titular exclusivo. Si cambia el primero, principal queda incierto y los otros
artistas no desaparecen. El orden de Shares no reemplaza un principal de pista
validado. Si solo existe Shares, conservar su orden sin inventar un principal de
Masters. Referencias o decisiones confirmadas mantienen su prioridad acotada.

Para literal y orden de display, primero respetar las referencias de nombres
expresamente aprobadas. Sin ellas, elegir una observacion de la lista maxima
compatible, con este desempate fijo: Masters antes que Shares; statement mas
reciente; cuenta normalizada en orden alfabetico; SHA256 de archivo ascendente;
hoja y fila real ascendentes. Las dos ultimas claves solo hacen determinista el
desempate, no otorgan autoridad comercial. Usar sus nombres con espacios limpios
y su orden de creditos, deduplicando por la clave de comparacion acordada.

Este desempate no resuelve discrepancias de identidad, aliases ni principal. Si
el primer performer varia, sigue incierto aunque una observacion gane el desempate
de presentacion. Otros artistas siguen el orden de esa referencia excluyendo solo
al principal propuesto cuando lo haya; si no lo hay, conservar todos. Nunca usar
orden de recorrido, read_at, fecha del archivo en disco, ruta o monto para ese
resultado. Una regla nueva de display queda versionada y no cambia los nombres
guardados de beneficiarios contractuales.

La pantalla futura seguira siendo sencilla: principal propuesto y otros artistas.
Los roles y la causa de una discrepancia se consultan solo cuando hacen falta.
No exigir al operador clasificar writer, producer o featuring para poder usar
un tema, y no crear ahora un panel nuevo para esta propuesta.

## O08 Shares In and Out y politicas por cuenta

Leer siempre la hoja completa para control y evidencia. Leerla no implica
incorporar todas sus filas al mart de ingresos. Separar economic_kind nativo,
flags de negocio vigentes y evidencia de artistas. El siguiente tratamiento se
conserva; este documento no modifica policies de Cloud SQL.

| Cuenta | Masters | Youtube Channels | Shares In & Out |
| --- | --- | --- | --- |
| henry_remix | Generacion/caja/statement segun policy propia | Vacia hoy; si llega dinero falta sheet rule, no heredar Mawz ni omitirlo | Vacio hoy; filas nuevas requieren resolver alcance, sin convertirse automaticamente en ingreso |
| gusty_dj | Generacion; elegibilidad parcial por reglas existentes | Generacion; elegibilidad parcial por reglas existentes | Auditoria y flags, cero nuevas filas de ingreso en mart operativo |
| la_nueva_sangre | Generacion; elegibilidad parcial por reglas existentes | Generacion; elegibilidad parcial por reglas existentes | Auditoria y flags, cero nuevas filas de ingreso en mart operativo |
| mawzrecords | Generacion/caja/statement segun policy propia | Vacia hoy, pero tiene sheet rule definida | Filas separadas transfer/caja/auditoria, catalog_view false y statement_view false |

Los creditos de un ISRC observado solo en Shares pueden crear una referencia de
catalogo con procedencia y sin generacion propia. No activar negocio, contrato o
derechos ni sumar esos shares porque ahora sus artistas son legibles. Los ocho
ISRC exclusivos de Shares del inventario A/B son testigos de esa separacion.

Share Type In/Out es la direccion original. Mantener Net y Quantity con signo:
existen In negativos y Out positivos. % Share In/Out es informacion ya incluida
en la liquidacion ONErpm; no volver a multiplicar Net, calcular un split interno
con ese porcentaje ni ajustar otro Net de Masters por esos movimientos.

Payer Name y Receiver Name son contrapartes. Aunque coincidan con nombres de
artistas conocidos, no constituyen creditos de pista. Artists solo aporta
participantes mediante O06/O07 y su nivel explicito. Para S YouTube Video, Artists
esta ausente en todos los originales; no reconstruirlo desde Payer/Receiver.

Los flags sobre Masters se basan en evidencia ID/Parent ID tipada. Una coincidencia
por UPC puede afectar a varias pistas y no prueba un share especifico de cada una.
has_share_in_out es senal; sus contadores no son porcentajes ni montos. En el
candidato futuro, cada registro Masters cuenta los movimientos por observation_id
de Shares unico. Los tipos de enlace ISRC y UPC son dos evidencias del mismo
movimiento, no dos unidades de conteo. Al agregar el indicador por asset/cuenta/
statement, usar la union de esos IDs, no la suma de contadores repetidos en cada
fila economica de Masters. Un enlace UPC a varias pistas conserva su alcance
de lanzamiento. Ese diagnostico no modifica Net ni reparte un monto entre pistas.

La conciliacion entre cuentas es un multiconjunto de movimientos, nunca un join
muchos-a-muchos que multiplica observaciones. Primero comparar en moneda nativa,
identidad, periodo, contrapartes, unidades, porcentaje y monto opuesto. Conservar
el sufijo Share In/Out de Sale Type; se puede reconocer su distinta perspectiva
solo en el control de espejo, no borrarlo de los originales ni de la taxonomia.

El par historico iTunes/Apple Music registrado en A/B es evidencia puntual de una
etiqueta distinta, no autorizacion de equivalencia global. Una divergencia futura
de DSP se registra como diferencia de dimension. Una contraparte no recibida se
marca sin contraparte local, no se inventa ni se elimina el ingreso. No exigir
igualdad USD entre transferencias liquidadas en meses de FX diferentes.

## O09 Fechas de consumo, statement y contabilizacion

statement_period se obtiene del prefijo YYYY-MM valido del filename. Conservar
statement_period_source filename y su evidencia. El dia 01 del nombre observado
no es una fecha bancaria ni fecha exacta de consumo. Un archivo sin ese prefijo
o con mes invalido requiere acreditar el periodo del paquete; no usar hoy, el
mes de ingesta o Accounted Date como default silencioso. Si se acredita otra
regla para un nuevo nombre, registrar version y volver a probarla.

transaction_month sale de Transaction Month, recortando espacios exteriores y
validando el calendario completo YYYY-MM. No cortar siete caracteres de cualquier
texto. No usar Reporting Period, Month o Sales Month por parecido sin certificar
un layout que informe esos campos y su significado. No copiar statement a consumo
cuando falte. En estos layouts de detalle es un dato requerido; un valor invalido
no permite activar un paquete economicamente atribuido a un mes inventado.

Accounted Date conserva la fecha contable y su precision. Si viene como fecha
Excel, registrar sistema de fechas del libro y tipo original; si es texto, aceptar
solo representaciones no ambiguas del layout. Un formato 03/04 no se adivina.
La falta o discrepancia de una fecha contable se registra sin reemplazar statement
ni consumo; no afirmar una fecha bancaria que el archivo no proporciona.

Consumo posterior al statement o un Accounted Date de otro mes son incidencias
cronologicas con ambos valores conservados, no una correccion automatica del mes.
Una correccion financiera negativa conserva su consumo y su nuevo statement.
No repartir ventanas de varios meses en estos layouts mensuales: conservar el
original y marcar el cambio de formato para certificarlo, sin prorratear ingresos.

Tendencias filtran consumo; liquidaciones filtran statements. Rangos de meses son
inclusivos de principio a fin; no se pierden dias por horas o zonas horarias. Las
vigencias contractuales y sus filtros existentes no se redefinen en la lectura.

## O10 Montos, precision, unidades y conversion

Net es la base autoritativa de M/Y/S en Currency. Conservar valor literal/tipo
original y decimal interpretado, negativos, ceros y precision. No calcularlo
desde Gross, Fees, Quantity, Average Unit Gross, % Share o % Share In/Out para
que coincida. Net vacio, texto invalido, NaN o infinito es error economico,
no cero. Currency ausente no implica USD, aunque Net sea cero.

Gross, Fees y porcentajes son evidencias de otra etapa, no importes adicionales.
Original Currency, Gross (Original Currency) y Exchange Rate no se reaplican a
Net ya expresado en Currency. Conservar porcentajes tal como se reciben: 70 no
se almacena como 0.70 sin registrar la unidad original; no deducir otro reparto.

Convertir internamente a USD solo con la regla vigente por statement. USD usa 1;
RUR se normaliza como RUB conservando la moneda original. Registrar tasa,
periodo, origen y version de conversion. Si falta una tasa requerida, no activar
una salida que presente moneda original como USD. No usar COALESCE a Net nativo
como si fuera convertido. No cambiar el proveedor, periodo o metodologia FX
dentro de la incorporacion de participantes. La ingesta no aplica el ajuste de
reportes de 10%; ese ajuste vigente vive despues y se aplica una sola vez.

Quantity alimenta units, no Views ni Creations. Cero se conserva; ausencia es
unknown, no cero. Un valor no vacio no numerico queda como error de cantidad,
sin descartarlo ni falsear su suma; requiere resolver el dato del candidato.
Conservar cantidades negativas y precision original, sin cast a entero que las
trunque. Average Unit Gross es promedio, no se suma ni sirve de fallback de Net.
Views y Creations se guardan por separado; no se infiere una unidad universal ni
se suman a streams. Ausentes en formatos viejos quedan nulos, no cero informado.

La lectura futura debe conservar precision decimal del valor nativo y el original
completo, no redondear cada fila a centavos ni fijar una escala que recorte nuevos
decimales. Decimal para controles nativos; un tipo destino insuficiente detiene
la activacion, no reduce precision silenciosamente. Si la libreria entrego Float64,
no presentar Decimal(str(float)) como copia lexical exacta de la celda XML.

Los controles de conversion/almacenamiento Float64 se separan de la lectura
Decimal. Antes de D, fijar para cada operacion un presupuesto de error numerico
por representacion y suma, usando precision de la maquina, cantidad de terminos
y suma de valores absolutos. Probar cancelaciones y valores pequenos; exigir
identidad exacta en conteos, claves, fechas y unidades exactas. No usar un umbral
general de centavos o tolerancia proporcional al total neto para ocultar perdidas.
Una diferencia de datos nativos no se justifica como tolerancia de Float64.

## O11 DSP, territorio, modalidad y UGC

Conservar Store, Territory, Sale Type y Product Type y reutilizar la taxonomia
central vigente. Un Store nuevo puede quedar No informado en monetizacion/origen
sin perder su ingreso. No inventar el pais desde idioma, DSP o cuenta. No cambiar
la granularidad economica por traducir una etiqueta.

Mantener las reglas ONErpm ya aprobadas: Spotify simple se clasifica como Premium
en su contexto de fuente; Spotify Ad Supported y Discovery Mode siguen distintos.
YouTube simple y Youtube Premium no se confunden, y Youtube Channels conserva
origen Video / Channel. YouTube en Masters no demuestra UGC, canal o video oficial.
YouTube Audio Tier conserva Music / Art Track y Shorts Flat Fee conserva Shorts
segun la taxonomia vigente. Una clasificacion conocida no convierte Shares en
generacion. No extrapolar estas inferencias a otras distribuidoras.

Identificar un video como UGC no elimina sus ingresos identificados por ISRC ni
exige volver a marcarlos en contratos. Asociados aceptados, excluidos, relaciones
fuertes e inciertas conservan sus decisiones. La lectura nueva solo agrega
evidencia trazable; adoptar cambios del resolver requiere una fase distinta.

## O12 Summary, Publishing y Commissions

Summary se usa como control antes de filtros de negocio/contrato y conversion
interna USD. Comparar por cuenta, archivo, moneda y los niveles de consumo/DSP
que sean realmente equivalentes. Catalog Revenue se contrasta con Net de M mas
Y; Share In/Out con S por direccion y signo; Net con la suma de esos conceptos
si no existen otras partidas. No sumarlo a los detalles ni confundirlo con banco.

ONErpm's Share y ONErpms Share fueron siempre cero. Si llegan valores no cero,
conservarlos y exigir definir su signo, base y ecuacion antes de activar una
conciliacion economica nueva. No restarlos por segunda vez ni asumir que son
el 10% interno. Una diferencia nativa de Summary no se arregla modificando ventas.

El BRL 0.01888476175 que cambia de Summary entre junio/julio 2023 y los residuos
USD del inventario A/B son testigos historicos, no una tolerancia ilimitada para
futuros archivos. No mover meses ni insertar ajustes para cerrar. Separar estado
de igualdad detalle interpretado/original, que debe conservarse, de estado de
conciliacion Summary. Una discrepancia nueva no explicada debe resolverse antes
de activar el paquete, sin publicar solo las hojas que si cerraron.

Publishing Rights y Commissions estan vacias en los originales recibidos. Su
estado es vacio comprobado, no lector certificado de todos los valores futuros.
Si aparecen filas, preservar archivo y datos y detener su adopcion economica
hasta definir la regla por fuente. No copiar la decision PUBLISHING de SoundOn
ni descartarlas por considerar que siempre son insignificantes. No repartir
Owned Share en nuestros contratos ni convertir un ISWC en ISRC.

## O13 Salida, estados y controles de aceptacion

La futura observacion conserva los diez bloques CAT-003: procedencia, version,
nivel, identificadores, titulos, creditos, fechas, economia, conversion y dimensiones.
El manifiesto registra todas las hojas y exclusiones con motivo. economic_kind
generation/transfer/control y elegibilidad de negocio son campos independientes.

La metadata comun tiene catalog_artists, principal propuesto y otros artistas,
estado de principal, literales, roles/niveles, alternativas, regla y evidencia
por archivo/cuenta/hoja/fila. El hecho economico existe una sola vez. Al unir
listas de artistas o codigos asociados no multiplicar Net ni Quantity. Los
datos granulares de statement y consumo deben llegar juntos a la futura capa
BigQuery; song-level agregado solo por consumo no sustituye al detalle de pago.

Estados independientes: economic_validation_status, identity_resolution_status,
participant_resolution_status, credit_resolution_status y principal_resolution_status.
Un rol fino o principal incierto no implica que se haya perdido dinero. Un total
que cierra no valida identidades ni participantes. Un ingreso puede conservarse
con metadata incompleta y no se le asigna un artista inventado para completar la ficha.

| Resultado | Accion del futuro candidato |
| --- | --- |
| Resuelto dentro de formato/policy | Lectura automatica, tambien para nombres y codigos nuevos |
| Metadata incompleta o rol desconocido aislado | Conservar economia, evidencia y datos acreditados; no bloquear todo por detalle fino |
| Participantes/identidad contradictorios | Conservar alternativas y catalogo validado; no modificar contratos ni hacer pasar atribucion dudosa por confirmada |
| Hoja/policy nueva con economia o formato critico no certificado | Preservar original, diagnosticar y no activar paquete parcial |
| Error de monto, moneda, periodo requerido, estructura o integridad | No activar candidato; mantener vigente el release anterior |
| Error FX o tipo destino insuficiente | Conservar candidato nativo, sin activar conversion falsa o truncada |

En D conciliar conteos y dinero por cuenta, hoja, tipo, statement, consumo,
moneda, entidad nativa, DSP y territorio; negativos y desconocidos separados.
Comparar economia nativa y USD en etapas distintas. Verificar aliases, asociados,
contratos guardados y su historial con snapshots separados. Las exclusiones
de Shares son intencionales y deben figurar en el control, no como datos perdidos.

## O14 Compatibilidad y autorizacion de adopcion

No cambiar cortes contractuales, cash_view, statement_view, descuentos ni fechas
de vigencia como parte de la normalizacion de artistas. Gusty y La Nueva Sangre
conservan sus reglas existentes de catalogo viejo/nuevo y sus anclas historicas;
el lector no decide que una obra antigua se vuelve nueva por cobrar este mes.
Las diferencias entre consumidores registradas en A/B necesitan su revision
separada, no se corrigen implicitamente aplicando esta especificacion.

No tocar el parser ni campos productivos para hacer que estas reglas parezcan
ya vigentes. El primer candidato debe escribir exclusivamente salidas aisladas
y demostrar igualdad economica contra el lector actual con el mismo snapshot.
Cambios de participantes se detallan por ISRC, regla y evidencia, sin reabrir
contratos ni cambiar sus nombres guardados, porcentajes, cierres o asociados.

La primera adopcion propuesta es metadata comun de participantes e identidad
tipada, compatible con campos antiguos. Fortalecer idempotencia, manejo de errores
y conversion requiere pruebas propias antes de activar el lector completo. No
publicar una migracion total por aprobar solo el tratamiento de artistas.

La fecha inicial de uso, version de lector, alcance historico o solo nuevos,
consumidores habilitados, rollback y publicacion requieren autorizacion expresa.
Esta especificacion no modifica Postgres, Parquet, BigQuery, GCS ni reportes.

## Casos de aceptacion para LEC ONERPM D

Son resultados exigidos al futuro candidato, NO pruebas ejecutadas en C.

| Caso | Entrada o condicion | Resultado esperado |
| --- | --- | --- |
| ON-T01 | 182 originales, cuatro cuentas, 1092 hojas | Todas clasificadas; perfiles/cuentas sin omisiones ni errores tratados como vacios |
| ON-T02 | Layout antiguo y nuevo con Creations/Views | Misma economia e identidad; metricas nuevas separadas, faltantes antiguos nulos |
| ON-T03 | Summary con cualquiera de sus tres encabezados | Una sola capa de control, ninguna venta adicional |
| ON-T04 | Publishing/Commissions vacios y luego fila sintetica nueva | Vacio comprobado en originales; futuro valor no se descarta ni incorpora automaticamente |
| ON-T05 | Nueva cuenta, hoja con datos o columna critica renombrada | Preservar recibido y diagnostico; ninguna herencia ciega ni publicacion parcial |
| ON-T06 | Encabezados conocidos reordenados, con espacios exteriores | Mismo resultado por nombre; encabezado duplicado despues de limpiar es error |
| ON-T07 | Reenvio igual con otro filename/paquete | No segunda contabilizacion dentro del mismo alcance; mismo hash en otra cuenta se revisa |
| ON-T08 | Reexport distinto del mismo mes/cuenta | No sumar dos completos ni reemplazar sin revision declarada |
| ON-T09 | Dos filas economicas identicas dentro de un archivo | Dos observation_id, ambos montos/unidades conservados |
| ON-T10 | QZHZ42271732 con performer y tres featuring | Gusty, PAPU DJ, ciro deejay y DJ BRAIAN STYLE; ningun writer agregado |
| ON-T11 | US7VG2308889 con SALASTKBRON featuring | Se conserva el invitado sin cambiar el ingreso ni el contrato |
| ON-T12 | Persona performer y writer, y otra solo producer | Primera una vez en display con dos roles; segunda como credito sin convertirla en interprete |
| ON-T13 | Artista e ISRC nuevos con gramatica conocida | Lectura automatica sin diccionario de artistas ni revision por desconocimiento |
| ON-T14 | Grupo con y/and/&, nombre con coma o parentesis ambiguos | No cortar grupo; ambiguedad conserva literal y estado, sin fragmentos inventados |
| ON-T15 | Rol nuevo junto a performers validos | Rol unknown preservado; no borrar personas acreditadas ni fabricar performer |
| ON-T16 | Subconjunto compatible y luego lista completa por mismo ISRC | Conservar nombres acreditados completos sin interseccion que borre invitados |
| ON-T17 | Listas que sustituyen participantes o misma persona con alias no aprobado | Alternativas y causa agrupada; ninguna fusion legal ni lista comun presentada como completa |
| ON-T18 | Mismo conjunto con primer performer diferente | Personas conservadas, principal incierto; no modificar principal guardado |
| ON-T19 | Mas de once artistas | Ningun nombre perdido por limites de interfaz ni economia multiplicada |
| ON-T20 | Mismo ISRC en dos cuentas y UPC distintos | Un asset identificable con origenes/relaciones separados; no descartar observaciones por duplicar codigo |
| ON-T21 | ISRC distintos, mismo titulo y artistas | Assets distintos; sin fusion por parecido |
| ON-T22 | 24 filas Masters Album y cinco Shares Album | Entidades de lanzamiento, titulos correctos, ningun ISRC inventado ni reparto a pistas |
| ON-T23 | UPC con varias pistas o con notacion cientifica recortada | Relacion multiple o codigo incompleto; no reconstruir digitos ni adjudicar todo a una pista |
| ON-T24 | Video ID/Channel ID y sus mayusculas | Identidades distintas, sensibles a caja, sin guardarlas como ISRC |
| ON-T25 | Y sin Channel Name pero con Channel ID | Reconocer contexto del canal, no usar Video Title como interprete ni perder dinero |
| ON-T26 | Video asociado a ISRC unico, relacion ambigua o UGC multiple | Aplicar resolver aprobado; conservar desconocidos/multiples y las decisiones de asociados |
| ON-T27 | Shares con credito de pista o uno de los ocho ISRC solo Shares | Evidencia de artistas conservada sin generacion ni administracion propia inventadas |
| ON-T28 | Payer/Receiver conocidos y Artists nulo en Shares YouTube | Ningun pagador/receptor transformado automaticamente en interprete |
| ON-T29 | Gusty/La Nueva Sangre Shares y Mawz Shares | Primeros auditoria/flags; Mawz transfer separado; ningun ingreso de generacion duplicado |
| ON-T30 | Espejo Gusty/Mawz y par iTunes/Apple Music registrado | Control por multiconjunto y moneda; excepcion de etiqueta documentada, sin alias DSP global |
| ON-T31 | Contraparte no recibida o FX de meses diferentes | Conservar movimiento; no inventar espejo ni exigir falsa igualdad USD |
| ON-T32 | In negativo y Out positivo | Direccion original y monto firmado conservados; no abs financiero |
| ON-T33 | Share enlaza por ISRC y UPC, o UPC corresponde a varias pistas | Flags trazables sin doble conteo del movimiento ni descuentos o porcentajes inferidos |
| ON-T34 | Consumo anterior, statement posterior y Accounted Date informado | Tres campos separados; filtro de pago usa statement, no consumo ni banco supuesto |
| ON-T35 | Mes invalido, nombre sin periodo o ventana de varios meses | No truncar, prorratear ni usar fecha de ingesta; candidato no activo con periodo inventado |
| ON-T36 | Monto nulo/invalido, Net cero, cantidad negativa o desconocida | Monto invalido no cero; ceros y signos validos; cantidad ausente no cero informado |
| ON-T37 | Currency no USD, RUR y FX faltante | Conversion por statement vigente; RUR/RUB trazable; ningun Net nativo etiquetado USD sin tasa |
| ON-T38 | Net con Fees y porcentajes, mas ajuste de reporte | Net no recalculado, porcentajes no reaplicados y ajuste interno fuera del lector |
| ON-T39 | Summary con residuo nativo, diferencia nueva o ONErpm Share no cero | Sin ajustes artificiales; distinguir discrepancia explicada de regla nueva sin certificar |
| ON-T40 | Nueva fila en Henry Y o Shares | No heredar policy ni saltar hoja fallida; resolver alcance y no activar carga parcial |
| ON-T41 | Join de artistas/asociados, agregacion por ambos ejes y tipos destino | Mismos hechos, montos/unidades; no explotar arrays multiplicando dinero ni perder statement |
| ON-T42 | Contrato cerrado y nueva evidencia de participantes | No reabrir, editar beneficiarios, porcentajes, vigencias, historiales o asociados guardados |
| ON-T43 | Mismo original/regla/policy ejecutados dos veces | Mismo resultado semantico, diferencias solo de timestamp; sin segunda venta |
| ON-T44 | Precision mayor, suma con cancelaciones o un archivo fallido del lote | Sin redondeo silencioso; presupuesto numerico comprobado y sin publicacion parcial |
| ON-T45 | Tres listas {A}, {A,B}, {A,C} para el mismo ISRC | Contradiccion global conservada; no fabricar union por comparar pares en distinto orden |
| ON-T46 | Observaciones equivalentes leidas en orden inverso, con caja/acentos/orden de nombres distintos | Mismos nombres de display y orden por desempate fijo; principal sigue incierto si corresponde |
| ON-T47 | Un Share coincide por ISRC y UPC con multiples filas Masters | Una unidad por Share observation_id en cada contexto y agregado por union; dos evidencias, no doble movimiento |

## Seguimiento y punto de reanudacion

- [x] LEC-ONERPM-A: inventario y lectura de todos los originales.
- [x] LEC-ONERPM-B: columnas, significados y contraste con codigo/policies.
- [x] LEC-ONERPM-C: especificacion documental ONERPM-LECTURA-1 definida, con
  14 reglas, 49 columnas cubiertas y 47 casos de aceptacion.
- [x] Ruben autoriza la prueba D aislada, sin aplicar ni publicar resultados.
- [x] LEC-ONERPM-D nativo/conservacion: 182 archivos y 1092 hojas en copias,
  recuperacion en 37 ISRC, 21 con nombres adicionales al display publicado;
  47 controles ejecutados con metodos y limites registrados. Importes,
  asociados, contratos y reparto actual sin cambios.
- [x] D-ROBUSTEZ-ENSAYO: dos defensas con nueve pruebas y replay de los 400 ISRC,
  sin diferencias; ver catalogo_lectura_onerpm_revision_previa_20261014.md.
- [x] D-ROBUSTEZ-INGESTA: defensas integradas y probadas en 182 XLSX, con base
  nueva, codigo 6bcbe77, 47 casos y 15 pruebas defensivas. Ver resultado completo.
  La prueba
  nativa no certifica adopcion de metadata nueva por todos los consumidores.
- [x] E-PREVIA: revision de los 21 cambios contra contratos congelados.
- [x] FUT-USO-CATALOGO-AISLADO: listas comunes v4, 23 fichas amplian artistas;
  importes, asociados y contratos conservados, 13 tests de merge y 23 helpers
  con raw real. Resultado: catalogo_lectura_onerpm_catalogo_maestro_aislado_20261014.md.
- [ ] FUT-USO-PRINCIPAL: adaptar la lectura de evidencia ONErpm del helper
  contractual para evitar 21 avisos adicionales FUGA-only. No cambiar guardados.
- [ ] LEC-ONERPM-E: revisar evidencia, limites y aprobar alcance de adopcion.
- [ ] FUT/USO: implementacion y publicacion autorizadas por separado.

Responsable: Codex; validacion de negocio: Ruben. Evidencia A/B:
C:/royalties_pipeline/staging/catalogo_lectura/20261014_onerpm_analisis/.
Evidencia de integridad de esta tarea:
C:/royalties_pipeline/staging/catalogo_lectura/20261014_onerpm_reglas_v1/.
Metricas de la etapa C original: 47 casos definidos, sin ejecucion en esa etapa.
D y v4 ya fueron probados por separado; ver sus resultados anteriores. Produccion
permanece sin cambios por estas pruebas. Commit y despliegue: no aplica.

Punto exacto para retomar: FUT-USO-PRINCIPAL en copia, preservando O07 y las reglas
FUGA/otras fuentes. No volver a preparar D ni empezar reingestas/publicaciones
por haber completado la prueba aislada del catalogo comun.
