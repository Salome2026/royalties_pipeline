# Reglas de lectura SoundOn para futuras ingestas

Proyecto CATALOGO-LECTURA. Tarea LEC-SOUNDON-C. Fecha 2026-10-19.
Version documental: SOUNDON-LECTURA-1. Responsable: Codex.
Estado: especificacion completa y 72 casos de aceptacion definidos, NO ejecutados.
Autorizacion recibida: consolidar reglas y pruebas; sin modificar el sistema ni
lo cargado. No hay lector candidato, commit, ingesta o despliegue de esta etapa.

La economia vigente y las decisiones aprobadas se conservan. La novedad de esta
especificacion es una evidencia SoundOn comun para todos los consumidores y un
tratamiento explicito de diferencias entre fuentes que no borra participantes.
El catalogo identifica artistas; solo los contratos deciden beneficiarios,
porcentajes y vigencias. El dashboard actual sigue SIN splits.

## S01 Alcance precedencia y base

Rigen las decisiones expresas de Ruben, CAT-003 v1.2 y las reglas vigentes de
soundon_pipeline_notes.md, statement_period_policy.md, la taxonomia central,
identity_normalization_policy.md y master_contract_association_rules.md.
No se extienden separadores, reglas de producto, Shares o excepciones de otras
distribuidoras. Este texto no altera CAT-003 ni las policies publicadas.
El recorrido activo consultado es ingest_standardized_soundon.py,
lib/soundon_identity.py, build_song_level_soundon.py, audit_soundon.py,
build_catalog_master.py y su proyeccion/consumidores. No reactivar un pipeline
legacy por aparecer nombrado en notas historicas.

Base A/B: catalogo_lectura_soundon_20261019.md; evidencia en
C:/royalties_pipeline/staging/catalogo_lectura/20261019_soundon_analysis.
Codigo productivo consultado en A/B: 1510506; release economico
20261016T232317Z-b847dfda42f2. Son referencias de comparacion, no versiones a
imponer a una futura ingesta. Antes de D se congela la base vigente de su copia.

Foto existente: 47 CSV, once paquetes de 2025-10 a 2026-08, 75.439 filas
economicas, 17 ISRC, 19 Track ID, 18 UPC, USD 36.455,999280 y 1.500.379.081
unidades. Todos los hashes coinciden con la adopcion del 2026-10-07. C reutiliza
su inventario y conciliacion; no repite esa adopcion ni declara probado un
lector nuevo. Los conteos no limitan meses, artistas o grabaciones futuros.

Los destinos de S02-S14 son conceptuales de CAT-003. No crean columnas SQL,
Parquet, BigQuery, endpoints, flags de interfaz ni un esquema operativo nuevo.

## S02 Cuenta paquete procedencia e idempotencia

El alcance recibido es source=soundon, account=soundon. Los CSV no traen ID
nativo de cuenta: source_account_original queda desconocido con ese motivo;
no se inventa desde artistas, UPC o una empresa supuesta. Una segunda cuenta
requiere mapeo/configuracion explicitos y paquete separado antes de activarse.

Cada archivo conserva bytes originales, ruta, nombre, SHA-256, tamano, fuente,
cuenta, paquete, revision, tipo, firma de cabecera y mapa de columnas. Registrar
registro CSV logico y rango de lineas fisicas; no equiparar linea fisica con
observacion cuando un campo entre comillas contenga saltos de linea.
raw_values conserva literales antes de convertir numeros o nombres.

La observacion se identifica reproduciblemente por fuente/cuenta, identidad
estable del paquete, hash y registro logico. La version del lector identifica
la interpretacion, no una venta nueva. Dos filas identicas en distintas
posiciones siguen siendo dos observaciones. Dos nombres o identificadores de
una fila no duplican su monto ni sus unidades.

El manifiesto detecta un reenvio del mismo archivo dentro del mismo alcance y
lo procesa una vez, conservando las rutas recibidas. No se deduplica por
titulo, importe, artista, UPC o parecido de ventas. Un hash nuevo para igual
cuenta/statement/tipo requiere declarar reemplazo, parte o complemento: no
sumar ambos ni elegir por fecha del disco. Encabezados vacios de Shares pueden
tener igual hash en meses distintos; siguen siendo recibos de esos paquetes,
no una razon para eliminar meses o presumir transferencias.

## S03 Formatos y reconocimiento

Cada archivo del paquete se clasifica. No llamar vacio a un archivo ilegible
ni omitirlo por extension inesperada. Solo CSV SoundOn entra en este perfil;
no hay Excel, TXT, API de catalogo ni legacy SoundOn certificados aqui.
Los nombres habituales contienen SoundOn_royalty_monthly_statement_YYYY_MM y
el tipo. Un tipo/nombre desconocido requiere clasificacion, no adivinacion.

| Layout | Columnas | Archivos de A/B | Significado |
| --- | ---: | ---: | --- |
| SO-MY-20 | 20 | 8 | My Royalty, hasta mayo 2026 |
| SO-MY-21 | 21 | 3 | My Royalty, agrega Discovery Mode Commission Amount |
| SO-IN-17 | 17 | 8 | Share in, incluye Final Royalty Currency; vacio |
| SO-IN-16 | 16 | 3 | Share in, sin columna de moneda; vacio |
| SO-OUT-19 | 19 | 10 | Share out, incluye Currency y Payee; vacio |
| SO-OUT-20 | 20 | 1 | Share out, agrega Status; vacio |
| SO-SUMMARY-7 | 7 | 11 | Control mensual por tienda |
| SO-DISC-5 | 5 | 3 | Control de comision Discovery por ISRC |

La lista exacta de nombres y orden recibido de cada layout se conserva en
layouts.json de A/B. Leer por nombre, no por posicion. Una permutacion de los
mismos nombres unicos puede usar el mismo perfil semantico, registrando la
nueva firma fisica y su column_map; los casos D deben probarlo. Cabeceras
duplicadas, renombradas, suprimidas o extendidas con campos desconocidos no se
aceptan por similitud: conservar paquete y diagnostico, no activar esa lectura
hasta clasificar el cambio. No usar strict=False o utf8-lossy para ocultarlo.

CSV se interpreta como UTF-8, admitiendo BOM y comillas/escapes propios de CSV;
validar ancho de cada registro y errores de decodificacion. Las comas del CSV
se procesan antes del separador de Track Artists. Un paquete sin observaciones
validas nunca reemplaza el mart historico por un dataset vacio. Un recibo
expresamente sin actividad se conserva como tal, sin inventar filas economicas.

## S04 Mapa completo de campos nativos

Los 28 nombres distintos proceden de los ocho layouts. La ausencia estructural
de una columna en otro tipo de archivo no es un dato cero ni prueba su valor.
Los campos originales y los normalizados conservan enlaces de evidencia.

| Campo | Destino conceptual | Regla |
| --- | --- | --- |
| `Sales Period` | consumption_start/end, transaction_month, precision | Ventana original; S06. No statement |
| `Reporting Period` | statement_period y evidencia | Columna rectora, contrastada contra nombre; S06 |
| `Track ID` | identifiers, native_entity_key | Referencia SoundOn de pista, texto con scope de cuenta; no ISRC |
| `Track Title` | track_title_original, title_resolved | Titulo de pista completo; no dividir medleys ni quitar versiones |
| `ISRC` | identificador original/normalizado, resolved_isrc | Codigo de grabacion valido para este perfil; S05 |
| `Track Artists` | track_credit_original, credits, artistas de fuente | Acreditacion de pista, coma como separador del perfil; S07 |
| `UPC Code` | identificador de lanzamiento y relaciones | Texto con ceros iniciales; no repartir venta de album ni decidir principal |
| `Album Title` | release_title_original | Contexto de lanzamiento; no contiene por eso artistas o roles |
| `Release Date` | fecha de lanzamiento informada | Contexto; no reemplaza consumo, statement o fecha bancaria |
| `Royalty Type` | royalty_type_original, economic_kind | RECORDING/PUBLISHING literales; inclusion vigente S09 |
| `Store Name` | dsp_original, dsp_normalized | Taxonomia central; no separar etiquetas combinadas sin evidencia |
| `Sales Region` | country_original, country_normalized | Conservar codigo/region informado; no inferir desde DSP |
| `Sales Type` | usage_original, classification | Modalidad original; no define beneficiarios |
| `Sales Sub Type` | monetizacion/origen y literal | Evidencia de taxonomia; no porcentaje, artista ni Plan visible |
| `Units of Sold` | units_original, units, units_status | Conteo firmado; ausencia separada de cero; S09 |
| `Exchange rate` | distributor_fx y literal | Cambio del distribuidor, ya incorporado al neto; no multiplicar otra vez |
| `Currency` | reported_currency | USD en My Royalty y Share out actuales; no asumir otra moneda |
| `Gross revenue` | gross_original | Bruto de distribuidora; no sumarlo con Final Royalty |
| `Artist Share` | componente monetario de distribuidora | No es porcentaje ni split de contrato interno |
| `Discovery Mode Commission Amount` | distributor_fees, comision incluida | Ya deducida en Final Royalty; layout antiguo no la trae |
| `Final Royalty` | amount_literal, amount_reported, amount_usd | Unica base de generacion; S09. No aplicar contratos |
| `Final Royalty Currency` | reported_currency de control/transferencia | Summary y Share in antiguo; no una segunda moneda a sumar |
| `Gross revenue currency` | gross_currency en Summary | Moneda del bruto de control |
| `Payee` | payee_original | Contraparte de transferencia, nunca artista inferido |
| `Status` | estado original de transferencia | Solo encabezado observado; valores futuros no certificados |
| `Opening pending balance` | saldo original de control Discovery | No nueva generacion ni monto para distribuir |
| `Deduction for this period` | deduccion de control Discovery | Comparar por mes/ISRC; no otra venta ni segundo descuento |
| `Closing pending balance` | saldo original de control Discovery | No sumarlo al neto ni inventar ecuacion de movimiento |

No hay artista de album, compositor, productor, video ID, channel ID, numero
nativo de cuenta o fecha bancaria en estos formatos. Esos bloques quedan
ausentes/desconocidos, no rellenados desde Album Title, Store Name o Payee.

## S05 Identidad titulos y relaciones

Los ISRC de My Royalty identifican grabaciones y mantienen el criterio vigente
de forma valida: 12 caracteres ASCII, patron [A-Z]{2}[A-Z0-9]{3}[0-9]{7}.
La forma no demuestra titularidad ni parentesco de versiones. No quitar
guiones, completar digitos o cambiar un codigo por similitud para hacerlo pasar.
Conservar literal y validacion separadamente; no reparar un
codigo incorrecto con un UPC o un numero de Track ID. Falta/forma invalida de
ISRC en este perfil impide activar el paquete hasta definir su nivel/clave;
se conserva la observacion recibida y su dinero en evidencia, no se elimina.

ISRC distintos con el mismo titulo son assets distintos. Un ISRC puede tener
varios UPC y Track ID: conservar relaciones originales y todas sus ventas,
sin duplicar el master ni deduplicar consumos. El Track ID esta scoped por
fuente/cuenta y no prevalece sobre el ISRC explicito. Si un mismo Track ID
declara dos ISRC validos, mantener dos identidades y la incidencia de relacion;
no fusionarlos ni trasladar ingresos por esa referencia contradictoria.

El UPC 640472880757 contiene QT5M22664077 y QT5M22692699. Los UPC de referencia
046081037238 y 046081037160 conservan su cero. Este ejemplo no es un diccionario
cerrado: UPC compartido futuro produce la misma relacion de lanzamiento, no
herencia de contratos o distribucion automatica de ingreso de album.

Track Title y Album Title quedan separados. Un titulo con barras puede ser un
medley de una grabacion; no se crean ISRC o participantes por sus fragmentos.
Un cambio real de titulo para el mismo ISRC conserva alternativas y evidencia,
sin elegir por mayor ingreso o fecha del archivo. Las correcciones humanas
aprobadas mantienen su alcance y procedencia; no se crean excepciones nuevas.
Este lector no crea ni quita asociaciones contractuales o enlaces UGC.

## S06 Statement consumo y precision temporal

Reporting Period gobierna liquidacion y debe ser YYYY-MM valido, un solo mes
por archivo, igual a YYYY_MM del nombre bajo la regla SoundOn vigente. Una
contradiccion se informa y no activa el paquete; nunca se corrige usando la
fecha de carga. Mantener statement_period_source=column con su evidencia.

Sales Period conserva la ventana YYYY-MM-DD~YYYY-MM-DD, sus dos extremos y el
mes de consumo. Validar calendario, comienzo no posterior al fin y ambos
extremos dentro del mismo mes. Ventana valida no significa que cada venta
tenga un dia individual informado: precision window, no asignacion diaria.
Una ventana multimes o invalida sigue detenida, sin prorrateo ni eleccion de
uno de sus meses. Consumo tardio conserva su mes aun si statement es posterior.

Release Date no cambia esos dos ejes. No rechazar una ventana mensual solo
porque empieza antes del dia de lanzamiento dentro de ese mes: no informa el
dia de cada stream. Fecha bancaria desconocida. Rangos de consulta de meses y
dias finales son inclusivos; no mover ventas por cortes horarios o UTC local.
Los contratos y sus vigencias no se reinterpretan dentro de este lector.

## S07 Creditos nativos y nombres nuevos

Track Artists es el unico campo nativo de artistas de pista del perfil. Leer
todos sus participantes, conservar cadena original, orden, campo y registro,
y producir una lista sin duplicados equivalentes dentro de esa evidencia.
La coma separa la lista SoundOn; no aplicar el parser FUGA/ADA/ONErpm. Grupos
con x, y, and o ampersand permanecen como un nombre si no hay coma divisora.

Para comparar: Unicode, espacios y casefold segun politica comun; los acentos
no producen participantes distintos por si solos. Conservar grafia original.
Una igualdad de nombre no acredita identidad legal o un alias global. No usar
un diccionario de artistas conocidos para decidir quienes existen.

Artista o ISRC nuevos con datos consistentes se interpretan automaticamente.
El rol fino no informado queda desconocido, sin exigir featuring/colaborador
para trabajar. No inferir productores, compositores, porcentajes o propietarios.
Creditos mas extensos que el limite de la interfaz se conservan completos.

La convencion de comas no permite demostrar un nombre de grupo con coma
literal sin otra evidencia. Si una referencia acreditada contradice esa
tokenizacion, mantener literal/alternativas y tokenization_unresolved; no
inventar una union o division para que coincida. No marcar a todo nombre nuevo
como dudoso por esa posibilidad teorica: la incidencia requiere evidencia real.

## S08 Participantes orden y diferencias entre fuentes

Se distinguen tres resultados: creditos originales por fuente, lista propuesta
con evidencia y estado de resolucion comun. La lista propuesta no equivale a
participantes definitivos ni a un derecho de cobro. Todas las decisiones tienen
alcance fuente/cuenta/ISRC/periodos y version; ninguna nace del ingreso mayor.

### Resolucion dentro de SoundOn

- Igual conjunto y orden estable: participantes resueltos como as_reported;
  primer artista como propuesta de orden observada, no titularidad contractual.
- Igual conjunto con distinto primer artista y sin referencia: participantes
  completos, principal_unresolved. No perder los otros artistas ni adivinar
  principal por frecuencia, UPC, archivo mas nuevo o importe.
- Conjuntos distintos del mismo credito de pista: conflicting_participants;
  conservar cada alternativa. No unir listas y llamar a eso una resolucion.
- Referencia ISRC aprobada y conjunto exactamente compatible: usar su orden y
  primer artista como principal, preservando los literales de cada observacion.
- Referencia cuyo conjunto ya no coincide: conservar nombres nuevos y
  reference_mismatch/conflicting_participants; no recortar para aplicar la vieja.

El registry aprobado de SoundOn es la autoridad de esas referencias, no una
consulta OGS en cada ingesta. Las referencias QT5M22664077 y QT5M22692699 y sus
evidencias siguen sin cambios. Una referencia nueva requiere su aprobacion
versionada por ISRC; no importar el resto de OGS ni cambiar la hoja externa.

### Compatibilidad entre fuentes del mismo ISRC

Comparar solo creditos pertinentes con identidad acreditada; no equiparar
artista de pista con canal, sello, Payee o titulo de album. Conservar las reglas
particulares de cada fuente, incluida la union FUGA ya aprobada, sin extenderla.

| Situacion | Resultado propuesto | Lo que no puede ocurrir |
| --- | --- | --- |
| Mismos miembros y principal compatible | Lista comun compatible, con todos los origenes | Exigir evidencia FUGA a un credito SoundOn valido |
| Mismos miembros, orden diferente | Miembros conservados; principal independiente y referencia aprobada si aplica | Descartar nombres o usar UPC como principal |
| Una lista incluye nombres que otra omite | cross_source_membership_difference; conservar ambas listas y nombres de la propuesta como reportados, no validados globalmente | Interseccion que oculte al adicional o lista mas larga declarada verdad automaticamente |
| Listas con integrantes incompatibles | conflicting_participants y alternativas separadas | Union, interseccion, fuente de mayor ingreso o mayoria declaradas resolucion |
| Correccion humana aprobada | Decision resuelta conservada en su alcance; nueva evidencia no compatible queda por detras con su incidencia | Sobrescribirla desde el nuevo statement o inventar una correccion global |

La diferencia de miembros y la de principal son independientes. Si ambas
fuentes mantienen Aneley primero, el nombre propuesto como principal puede
seguir siendo Aneley aunque falte resolver otro integrante. Ningun estado de
principal debe ocultar una diferencia de miembros.

Para QT8BW2649774, el candidato SoundOn debe conservar [Aneley, Para El Mundo];
FUGA conserva su [Aneley]. La propuesta de integrantes reportados no puede
ocultar Para El Mundo, y el resultado comun debe indicar que difieren las
fuentes. No se publica [Aneley] como lista completa resuelta ni se reemplaza
automaticamente por [Aneley, Para El Mundo] como verdad definitiva. El principal
observado en ambas es Aneley. No se decide aqui quien fue cargado mal ni pagos.

La propuesta y sus evidencias son una salida comun del catalogo, no un arreglo
privado de Contratos. Una integracion futura debe poder mostrar el nombre
reportado y la incidencia sin afirmar que esta globalmente confirmado. Solo
casos realmente discrepantes necesitan una resolucion agrupada por ISRC/causa,
no cada stream ni cada nombre nuevo. La presentacion se decide en FUT/USO;
esta etapa no crea pantalla, badge obligatorio o bloqueo de guardado nuevo.

## S09 Economia moneda cantidades y precision

Final Royalty es amount_reported y base de amount_usd del perfil USD. Conservar
signo y literal, interpretar con Decimal para controles nativos y no redondear
por fila a centavos. En A/B hay hasta seis decimales; no es licencia para
truncar una precision futura mayor. La conversion de salida se valida aparte.

Moneda requerida, monto numerico y finito. No convertir vacios, NaN, infinito,
texto invalido o moneda ausente en USD/cero. Moneda distinta de USD detiene
activacion hasta aprobar su conversion; no aplicar un tipo de cambio supuesto.
Exchange rate de la distribuidora no se vuelve a aplicar sobre Final Royalty.
La tolerancia historica a coma decimal nunca significa separador de miles:
mezclas ambiguas o no soportadas no se reparan quitando signos.

Artist Share es un importe, no el porcentaje del artista de un contrato. No
sumar Gross revenue con el neto ni distribuir segun nombres. Mantener los
componentes originales; en la base actual Artist Share menos la comision
Discovery coincide con Final Royalty en todas las filas. Final Royalty sigue
siendo el recibido, no un numero recalculado para forzar una conciliacion.

Units of Sold conserva signo, valor y units_status: cero, conocido o ausente.
Una unidad ausente no se convierte en cero. El lector vigente rechaza ese caso;
el candidato puede conservarlo como desconocido, pero no activar una proyeccion
que lo pierda. Es condicion de compatibilidad, no permiso para cambiar ahora
los reportes ni obligacion de rechazar todo ingreso valido con dato ausente.
Cantidades fraccionarias no observadas se conservan con incidencia, sin truncar;
su activacion requiere semantica certificada del uso y compatibilidad.

PUBLISHING sigue incluido economicamente en recordings, conservando su literal
en Royalty Type. RECORDING y PUBLISHING se cuentan una vez. Otro tipo no hereda
ese tratamiento por parecido: preservar evidencia y clasificar antes de activar.
No se importan las decisiones de Publishing Rights de ONErpm u otras fuentes.

## S10 Summary Discovery y transferencias

Summary es control, no generacion. Deben coincidir filas/grupos esperados y
totales de My Royalty por cuenta, Reporting Period, tienda y moneda: Final
Royalty, Gross revenue y unidades. Una diferencia no se compensa con otra
tienda o mes. Falta de Summary requerido o moneda incompatible no se resuelve
publicando solo lo legible. No crear artistas/ISRC desde ese resumen agregado.

Discovery Mode es complemento opcional: si no se entrego, registrar
not_provided, no inventar comision cero ni exigir ese archivo para cada mes.
La comision ya incorporada en My Royalty se conserva aun sin complemento. Si
se entrega, conciliar mes y mes/ISRC contra la comision incorporada: 38 grupos
en la base A/B. Dos filas del mismo ISRC pueden corresponder a dos UPC, pero
Discovery no informa ese UPC: agrupar para controlar, sin multiplicar costos
por un join ni asignarlos dos veces. Falta de contrapartida o diferencia del
complemento entregado detiene activacion del paquete candidato.

Opening/Closing pending balance son saldos de control; no ventas ni deudas
contractuales nuevas. No asumir opening menos deduction igual closing: la
informacion disponible no acredita esa ecuacion. Conservar saldos futuros
distintos de cero sin agregarlos al neto.

Share in/out: solo estan observados sus encabezados y cero filas. No certifica
transferencias reales la frase antigua de que el script esta preparado. Los
22 vacios se reconocen y no generan ingresos ni error por moneda ausente de
SO-IN-16. Un Share con filas requiere especificacion economica, moneda,
Status/Payee, signos y policy propios antes de activar el paquete; no omitirlo
silenciosamente, sumarlo como master o reutilizar Shares In & Out de ONErpm.
Guardar la evidencia recibida y conservar el release vigente hasta resolver el
alcance. No hay muestras reales para afirmar probado ese tratamiento.

## S11 Dimensiones y taxonomia

Store Name, Sales Type, Sales Sub Type y Royalty Type alimentan exclusivamente
la taxonomia central versionada. Country conserva Sales Region, sin inferir
pais de DSP o artista. DSP nuevo o subtipo sin clasificar conserva su literal
y No informado donde corresponda; no requiere backoffice por cada tema ni
autoriza clasificacion especulativa. Un enum nuevo que cambie el nivel economico
se trata aparte, no como simple DSP desconocido.

INDIVIDUAL/FAMILY/DUO/STUDENT/BUNDLE mantienen Premium; AD_SUPPORTED mantiene
Ads; TRIAL mantiene Trial / Promo. DEFAULT/OTHER no revelan un plan oculto.
YouTube Music / Content ID no separa Music y UGC por si solo. UGC/PGC explicitos
en TikTok/Meta mantienen las reglas de origen existentes. No se crea Plan visible
ni una clave de agrupacion adicional en reportes o dashboard.

## S12 Catalogo comun consumidores y contratos

El candidato de metadata aporta todos los creditos SoundOn pertinentes,
su version, evidencia, estado nativo y estado entre fuentes. Debe poder completar
las 14 listas hoy no estructuradas sin necesitar un diccionario de artistas y
conservar las tres fichas que ya tienen evidencia de otras fuentes.

Respetar grafias/manuales aprobados y no anidar evidencia de la ejecucion previa
como si fuera un statement nuevo. Mismos archivos/regla dan el mismo resultado
semantico. La resolucion SoundOn de principal no depende de tener un Asset Artist
FUGA; el consumidor futuro reconoce orden/reference/status de SoundOn sin borrar
dudas reales de otras fuentes. No crear una interpretacion distinta por pantalla.

No reescribir artist_statement_original ni artist_statement_style, sus variantes,
agrupaciones, filtros, importe, redondeo o formatos de reportes existentes. La
metadata nueva se adopta solo despues de probar el consumidor en copia y obtener
autorizacion; no se cambian los otros lectores para hacer pasar una prueba.

Ningun contrato, historial, porcentaje, vigencia, cierre, seleccion de reportes,
artista eliminado manualmente o decision de asociados se guarda por leer un
statement. En fichas nuevas/abiertas las sugerencias son propuestas, respetando
la logica vigente de ediciones previas; un integrante con atribucion pendiente
no se presenta como confirmado. Los cerrados permanecen identicos. No se
autocompleta un porcentaje para cerrar la suma ni se reabre un contrato.

Buscar un artista en el dashboard actual sigue devolviendo generacion de los
temas donde participa, SIN splits y con las policies actuales. Otro dashboard
podra mostrar el reparto en el futuro. Este lector no lo implementa.

## S13 Estados controles y proyecciones

Mantener independientes economic_validation_status, identity_resolution_status,
participant_resolution_status, principal_resolution_status y credit_resolution_status.
Rol fino desconocido no equivale a participante dudoso; principal dudoso no
significa dinero perdido. Incidencias de artistas validamente identificados
no borran observaciones economicas ni generan una segunda fila.

| Situacion | Tratamiento de candidato |
| --- | --- |
| Lectura valida, nombre nuevo | Automatico, sin revision por desconocimiento |
| Dato no informado o rol fino ausente | Conservar ausencia y estado; no inventar valor |
| Diferencia de miembros/principal | Alternativas y causa por ISRC; economia valida conservada una vez |
| Forma/layout/economia no soportados | Archivo y diagnostico preservados; no activar un paquete parcial |
| Unidades desconocidas que una proyeccion vuelve cero | Conservar candidato y bloquear esa adopcion incompatible, sin borrar dinero |
| Contrato o correccion manual existente | No sobrescribir; presentar evidencia sin guardar decision nueva |

Controles nativos Decimal: igualdad exacta por observacion y grupos. No usar
tolerancia para esconder filas faltantes, participantes perdidos, conversiones
de signo, unidades, moneda o joins multiplicados. Identificadores, cardinalidad
y textos/literales deben conservarse; solo normalizaciones declaradas se comparan
contra su forma derivada.

Controles Float64 de formatos actuales: regla historica de suma absoluta hasta
USD 0,000001 por grupo, sobre observaciones ya equivalentes, con diferencias
registradas y verificadas por separado. En A/B el maximo observado fue
USD 0,0000000000154614. No es una tolerancia Decimal ni universal para otras
fuentes. Precision/rango nuevos requieren controlar conversion por etapa y
certificar compatibilidad antes de activar; no redondear para hacerla pasar.

Proyecciones Parquet y BigQuery se contrastan con la base vigente: monto,
unidades y estados por statement, consumo, ISRC/Track ID/UPC, DSP, territorio,
tipo de royalty, cuenta y clase. Preservar ceros, nulos y negativos en las
agregaciones; una suma de solo desconocidos no es cero conocido. Exportar
listas/relaciones no autoriza UNNEST que multiplique los hechos economicos.

El contexto futuro fija release economico, revision de metadata, reader/rule
version, policy/taxonomia, estado de catalogo y decisiones de asociados. Los
contratos y descuentos se aplican fuera del lector, una sola vez. El 10% y la
policy v12 son la foto protegida de A/B, no un hardcode para statements futuros.

## S14 Plan de pruebas y puertas de adopcion

C define los casos siguientes; comprobar que la tabla tiene 72 casos NO los
ejecuta. El QA existente de SoundOn y la adopcion anterior se reutilizan como
regresion, sin afirmar que ya cubren las nuevas diferencias entre fuentes.
Los casos sinteticos deben ser copias aisladas, nunca editar input_raw o marts.

D, si se autoriza, debe usar los 47 originales congelados y casos sinteticos
rotulados, ejecutar lector candidato sin side effects y entregar esperado,
observado, diferencias y estado por cada ID. Comprobar los 17 ISRC, ambas
referencias, la diferencia de Imaginando La Gloria y las 14 listas comunes,
sin guardar contratos. Un caso sin aplicacion real se declara sintetico o no
certificado; no se presenta como probado con transferencias reales.

E revisa hallazgos, precision, unidades desconocidas y compatibilidad. FUT/USO
prueba consumidores reales en copia, incluida ausencia de avisos artificiales
de principal. Una publicacion requiere despues autorizacion separada y foto
viva nueva. Ni C ni aprobar D autoriza cambiar produccion.

### Casos de paquete formato y procedencia

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T01 | S01 S02 S14 | Base real | Inventario A/B con los 47 hashes vigentes | Misma cobertura y base, sin reactivar la adopcion anterior ni crear ventas por version del lector |
| SO-T02 | S02 | Sintetico | Misma fuente/mes con cuenta nueva sin mapeo | Cuenta original desconocida preservada; no heredar soundon por artista o filename; sin activacion |
| SO-T03 | S02 | Sintetico | Dos filas identicas en registros 2 y 3 | Dos observation_id y dos importes; no deduplicar por contenido economico |
| SO-T04 | S02 | Sintetico | Reenvio de mismo hash y paquete en otra ruta | Una sola contribucion; ambas rutas de evidencia, IDs estables |
| SO-T05 | S02 | Sintetico | Hash nuevo para igual cuenta/mes/tipo sin declaracion | No sumar ni reemplazar por mtime; preservar versiones y pedir clasificacion de paquete |
| SO-T06 | S03 | Sintetico | Las mismas columnas certificadas en otro orden | Mapeo por nombre correcto; nueva firma fisica, mismo resultado semantico |
| SO-T07 | S03 | Sintetico | Columna desconocida, renombrada o requerida ausente | Conservar original y diagnostico por archivo/campo; no activar layout parecido |
| SO-T08 | S03 | Sintetico | UTF-8 invalido o registro con ancho incorrecto | Error explicito sin utf8-lossy, filas vacias inventadas ni salida parcial |
| SO-T09 | S02 S03 | Sintetico | CSV con comillas, coma y salto de linea en un titulo | Un registro logico, lineas fisicas correctas, titulo y monto conservados |
| SO-T10 | S02 S03 | Base real | SO-MY-20 frente a SO-MY-21 | Ambos reconocidos por cabecera; comision ausente antes de junio, no otra venta |
| SO-T11 | S02 S03 | Sintetico | Archivo con tipo desconocido o My Royalty legible junto a otro roto | Paquete no activado parcialmente; todos los archivos clasificados o con error trazable |
| SO-T12 | S03 S13 | Sintetico | Candidato sin observaciones o recibo expresamente sin actividad | No reemplazar historia por dataset vacio ni generar filas de dinero; conservar recibo/causa |

### Casos de identidad y titulo

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T13 | S04 S05 | Base real | 17 ISRC, 19 Track ID y 18 UPC de A/B | Identificadores completos como texto, con namespace y relaciones sin fusionar ventas |
| SO-T14 | S05 | Sintetico | Dos ISRC validos con titulo identico | Dos grabaciones y montos independientes |
| SO-T15 | S05 | Base real | Un ISRC con dos Track ID y dos UPC | Un master, varias referencias, todas las observaciones y unidades una vez |
| SO-T16 | S05 | Base real | UPC 640472880757 con los dos ISRC de La Juntada/Candu | Relacion de lanzamiento multiple, nunca identidad exclusiva ni reparto de album |
| SO-T17 | S04 S05 | Base real | UPC 046081037238 y 046081037160 | Texto exacto con cero inicial en cada proyeccion |
| SO-T18 | S05 | Sintetico | Track ID largo o con cero inicial | Texto sin Float64, notacion cientifica ni perdida de digitos |
| SO-T19 | S04 S05 | Sintetico | My Royalty sin ISRC valido y con UPC/Track ID presentes | Observacion recibida preservada; no inventar ISRC ni activar nivel no certificado |
| SO-T20 | S04 S05 | Base real | Titulo medley con barras y Album Title diferente | Una pista, ambos titulos separados, sin crear artistas o tres assets por fragmentos |
| SO-T21 | S05 | Sintetico | Igual Track ID declara dos ISRC validos | Dos identidades por ISRC y relacion contradictoria, sin fusion ni traslado de ingresos |
| SO-T22 | S05 S12 | Sintetico | Un ISRC con dos titulos incompatibles o correccion manual aprobada | Conservar variantes; correccion en su alcance intacta, sin decidir por dinero o filename |

### Casos de credito nativo y principal

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T23 | S04 S07 | Base real | Los 17 creditos de Track Artists disponibles | Todos los nombres y literales conservados, con campo/registro y sin contrato inferido |
| SO-T24 | S07 | Sintetico | Artista e ISRC nuevos, no presentes en diccionario | Interpretacion automatica por campos/regla; no exigir backoffice por desconocimiento |
| SO-T25 | S07 | Sintetico | Cambios de mayusculas, espacios o acentos del mismo nombre | Comparacion normalizada, grafia original preservada, sin alias legal global |
| SO-T26 | S07 | Base real | ACIT x o Los Nocheros en un elemento | Un nombre por elemento, sin cortar por espacios o x |
| SO-T27 | S07 | Sintetico | Un grupo con and, y o ampersand y otro artista tras coma | Grupo intacto y segundo nombre separado solo por coma |
| SO-T28 | S07 S08 | Sintetico | Iguales miembros y mismo primer artista en todos los registros | Lista SoundOn consistente y orden observado; rol fino desconocido no provoca revision |
| SO-T29 | S07 S08 | Sintetico | Iguales miembros con primer artista distinto, sin referencia | Miembros completos; principal_unresolved, sin orden por frecuencia o importe |
| SO-T30 | S07 S12 | Sintetico | Mas de diez invitados o un nombre repetido equivalente | No truncar evidencia; deduplicar solo el nombre dentro de la lista, no ventas |
| SO-T31 | S07 S08 | Sintetico | Referencia acreditada indica un grupo con coma literal incompatible con el parseo | Literal y alternativas conservados, tokenization_unresolved, sin agrupacion inventada |
| SO-T32 | S08 | Base real | QT5M22664077 en sus dos UPC con referencia aprobada | La Juntada primero, Candu conservada, credito economico y todas las ventas intactos |
| SO-T33 | S08 | Base real | QT5M22692699 en sus dos UPC con referencia aprobada | Mismo criterio de referencia por ISRC, sin sustituir principal por UPC |
| SO-T34 | S08 | Sintetico | Un invitado nuevo hace incompatible una referencia previa | No recortar invitado ni aplicar referencia fuera de conjunto; reference_mismatch con evidencia |
| SO-T35 | S07 S08 | Sintetico | Dos listas SoundOn del mismo ISRC difieren en integrantes | conflicting_participants y alternativas; no union/interseccion declaradas verdad |
| SO-T36 | S04 S07 | Sintetico | Album Title o Payee contiene nombre de persona | No alta automatica como interprete, compositor, principal o beneficiario |

### Casos de diferencias entre fuentes y catalogo comun

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T37 | S08 S12 | Base real | 14 fichas con lista comun hoy nula y credito SoundOn consistente | Propuesta de metadata comun completa con evidencia SoundOn; sin perder acceso previo ni inventar derechos |
| SO-T38 | S08 S12 | Base real | Tres fichas ya estructuradas por otras fuentes | Evidencia y decisiones previas conservadas, sin sustituirlas ciegamente por la lista SoundOn |
| SO-T39 | S08 | Base real | QT8BW2649774: SoundOn declara Aneley y Para El Mundo | Lista nativa de dos y sus 1466 evidencias conservadas, monto nativo intacto |
| SO-T40 | S08 S12 | Base real | Ese ISRC junto a FUGA que solo declara Aneley | Propuesta reportada no oculta Para El Mundo; cross_source_membership_difference; ni Aneley sola completa ni lista ampliada resuelta por defecto |
| SO-T41 | S08 | Sintetico | Misma diferencia de subconjunto para ISRC/artista nuevos | Regla generica identica a SO-T40, sin if por codigo, nombre o distribuidora de mayor ingreso |
| SO-T42 | S08 | Sintetico | Una fuente da A,B y otra A,C del mismo credito | Alternativas separadas y conflictivas; no fabricar A,B,C ni reducir a A como lista completa |
| SO-T43 | S08 | Sintetico | Fuentes con mismos miembros pero distinto primer nombre | Pertenencia y principal con estados independientes; resolver orden solo con evidencia aprobada |
| SO-T44 | S08 | Sintetico | Fuente A,B frente a A; ambas mantienen A primero | Diferencia de miembros conservada aunque principal observado coincida; no ocultarla con principal_uncertain=false |
| SO-T45 | S08 S12 | Sintetico | Correccion humana ya aprobada frente a nueva acreditacion incompatible | Decision previa intacta; nueva evidencia visible con su causa, no sobrescritura automatica |
| SO-T46 | S08 S12 | Sintetico | Lista SoundOn valida sin ningun Asset Artist FUGA | Consumidor reconoce evidencia SoundOn; no aviso artificial por carecer de campo FUGA |
| SO-T47 | S08 S12 | Sintetico | Fuente solo informa sello, canal o contexto de producto | No convertirlo en artista SoundOn ni extender la union FUGA fuera de su alcance |
| SO-T48 | S12 S13 | Sintetico | Ejecutar dos veces misma metadata o reordenar lectura de archivos | Salida semantica idempotente, sin anidar evidencia previa, alterar decisiones o multiplicar importes |

### Casos de economia fechas y ausencias

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T49 | S06 | Base real | 56756 filas con consumo diferente a statement | Ambos ejes conservados, sin repetir la correccion historica ni mover liquidacion |
| SO-T50 | S06 | Sintetico | Reporting Period contradice filename o hay dos meses en el archivo | Error trazable de paquete; no usar fecha de carga ni activar lectura parcial |
| SO-T51 | S06 | Sintetico | Fecha imposible, inicio posterior a fin o ventana multimes | No prorrateo ni mes supuesto; no activacion del paquete, originales preservados |
| SO-T52 | S06 | Sintetico | Venta en ultimo dia, ventana mensual con lanzamiento intermedio o consumo tardio | Fecha de consumo y statement exactos e inclusivos; no cortar el dia ni inventar dia del stream |
| SO-T53 | S09 | Base real | 43 filas PUBLISHING por USD 0,183938 y resto RECORDING | Todas incluidas una vez, Royalty Type literal, sin contratos ni doble generacion |
| SO-T54 | S09 | Sintetico | Moneda ausente/no USD, NaN/infinito/monto invalido o notacion ambigua | No USD/cero/FX supuestos; preservar diagnostico y bloquear activacion no soportada |
| SO-T55 | S09 | Sintetico | Montos/unidades negativos y ceros reales | Signos y ceros preservados en detalle, agregacion y comparacion; no descartar correcciones |
| SO-T56 | S09 S13 | Sintetico | Unidades ausentes o fraccionarias no observadas | No cero ni entero truncado; estado original, activacion condicionada a semantica/proyeccion compatible |
| SO-T57 | S09 S13 | Sintetico | Precision mayor a seis decimales o rango que excede conversion validada | Decimal/literal conservados; no truncar ni redondear; validar conversion antes de activar |
| SO-T58 | S09 S10 | Base real | Artist Share menos Discovery igual Final Royalty en las 75439 filas | Recibido preservado; no recalcular para forzar cierre ni descontar comision otra vez |
| SO-T59 | S09 S12 S13 | Sintetico | Exchange rate, 10% interno y contrato presentes en contexto | Final Royalty una vez; FX/ajuste/contrato no aplicados dentro del lector |
| SO-T60 | S09 S11 | Sintetico | Royalty Type nuevo frente a un subtipo/DSP nuevo | Tipo economico requiere clasificacion; DSP/subtipo conserva literal y taxonomia sin inventar origen |

### Casos de controles consumidores y preservacion

| Caso | Reglas | Clase | Entrada | Resultado esperado |
| --- | --- | --- | --- | --- |
| SO-T61 | S10 S13 | Base real | 133 grupos My Royalty/Summary | Neto, bruto, unidades, cuenta/mes/tienda/moneda exactos; Summary no suma ventas |
| SO-T62 | S10 | Sintetico | Falta Summary, falta un grupo o dos diferencias se compensan en total | No ocultar por total global ni publicar paquete parcial; error de control pertinente |
| SO-T63 | S10 | Base real | Tres Discovery y 38 grupos mes/ISRC, algunos ISRC con dos UPC | Controles exactos agregados por ISRC; sin join multiplicador ni segundo descuento |
| SO-T64 | S10 | Sintetico | Discovery total cierra pero dos ISRC se compensan, o hay monto sin contraparte | Control por ISRC detecta diferencia; no activacion del paquete candidato |
| SO-T65 | S10 | Sintetico | Discovery no entregado o saldos de control distintos de cero | Ausencia not_provided; comision nativa conservada; saldos no son generacion nueva ni ecuacion supuesta |
| SO-T66 | S03 S10 | Base real | Los 22 Share vacios en cuatro layouts | Reconocidos, cero transferencias; SO-IN-16 vacio no inventa moneda ni bloquea My Royalty |
| SO-T67 | S03 S10 S13 | Sintetico | Share con filas, con/sin moneda o Status no certificado | Conservar evidencia y release; no omitir ni activar tratamiento no aprobado o reglas ONErpm |
| SO-T68 | S11 S12 | Base y sintetico | YouTube combinado, UGC/PGC explicitos o subtipo OTHER | Taxonomia vigente, No informado donde falta evidencia, sin columna Plan ni clasificacion privada |
| SO-T69 | S12 S13 | Base real | 244 contratos, historiales, asociados, policies y reportes actuales | Hashes/selecciones/importes/formatos intactos; ningun guardado o reapertura por metadata |
| SO-T70 | S12 S13 | Sintetico | Ficha nueva/abierta, participante borrado manualmente y otra cerrada | Sugerencias con estado y ediciones respetadas; sin porcentajes inferidos ni cambios al contrato guardado |
| SO-T71 | S12 S13 | Base y sintetico | Parquet/BigQuery y consumidores usan listas, agregados y unidades desconocidas | Datos por observacion conservados una vez, nulos no cero, misma interpretacion sin splits nuevos |
| SO-T72 | S01 S02 S14 | Limite de etapa | Finalizar C o aprobar resultados de D | Ningun cambio/publicacion implicito; D/E/FUT/produccion requieren sus controles y autorizacion separada |

### Correspondencia con los 24 criterios CAT-003

Los casos de otras distribuidoras son controles de limite, no recertificaciones
de FUGA, ADA, ONErpm u Orchard desde SoundOn.

| Criterio | Casos | Cobertura propuesta |
| --- | --- | --- |
| C03-T01 | SO-T14 SO-T21 | Identidad de dos ISRC y referencias contradictorias |
| C03-T02 | SO-T16 SO-T19 | UPC compartido, ningun reparto de album inventado |
| C03-T03 | SO-T19 SO-T47 | No importar clave ADA a SoundOn sin ISRC |
| C03-T04 | SO-T38 SO-T47 | Conservar fuente FUGA sin extender su union al parser SoundOn |
| C03-T05 | SO-T36 SO-T47 SO-T67 | No importar roles o Shares ONErpm |
| C03-T06 | SO-T26 SO-T27 SO-T31 | Grupos, conectores y limite de coma literal |
| C03-T07 | SO-T29 SO-T32 SO-T33 SO-T34 | Referencias SoundOn y cambios de orden/conjunto |
| C03-T08 | SO-T24 SO-T41 | Artistas/ISRC nuevos sin diccionario o parche |
| C03-T09 | SO-T15 SO-T16 SO-T69 SO-T71 | No multiplicar economia ni cambiar asociados UGC existentes |
| C03-T10 | SO-T08 SO-T11 SO-T54 SO-T62 | Paquete no activado parcialmente ante error |
| C03-T11 | SO-T55 SO-T56 SO-T71 | Negativos, cero y desconocidos separados |
| C03-T12 | SO-T49 SO-T50 SO-T51 SO-T52 | Consumo y statement independientes |
| C03-T13 | SO-T53 SO-T58 SO-T59 | Neto sin dobles conversiones, descuentos o splits |
| C03-T14 | SO-T22 SO-T45 SO-T69 | Correcciones manuales y excepciones de otra fuente intactas |
| C03-T15 | SO-T06 SO-T07 SO-T60 | Cambio de formato, semantica y enum con alcance |
| C03-T16 | SO-T03 SO-T04 SO-T05 | Observaciones repetidas, reenvios y reemplazos distintos |
| C03-T17 | SO-T61 SO-T63 SO-T65 SO-T66 | Controles y complementos sin segunda generacion |
| C03-T18 | SO-T11 SO-T12 SO-T19 | No inventar granularidad o nivel no recibido |
| C03-T19 | SO-T23 SO-T28 SO-T30 | Otros artistas completos sin exigir rol fino |
| C03-T20 | SO-T36 SO-T59 SO-T70 | Beneficiarios/pagos solo por contrato, no por credito |
| C03-T21 | SO-T37 SO-T40 SO-T46 SO-T48 SO-T71 | Catalogo comun con estados para todos los consumidores |
| C03-T22 | SO-T38 SO-T47 | Respetar union FUGA ya aprobada sin extenderla automaticamente |
| C03-T23 | SO-T15 SO-T16 SO-T69 SO-T70 | Varios UPC no heredan ni alteran contratos |
| C03-T24 | SO-T36 SO-T47 SO-T67 | Separacion de fuentes, canal, producto y contraparte |

### Entrega minima de D y seguimiento

- Resultado por SO-T01 a SO-T72: esperado, observado, diferencias y evidencia;
  ninguna fila marcada ejecutada por haber validado esta tabla.
- Comparacion nativa Decimal por observacion y dimensiones, sin omitir archivos
  vacios, ceros, negativos sinteticos o casos expresamente no soportados.
- Propuesta para las 17 fichas y las 14 listas faltantes, con estados de
  miembros/principal y las tres fichas previas protegidas.
- Ejemplo QT8BW2649774 y al menos un caso nuevo generico del mismo problema,
  sin decisiones financieras, parche por ISRC ni union definitiva indiscriminada.
- Comparacion separada de los consumidores que entren en el alcance autorizado;
  no extrapolar un test de helper a todas las pantallas, HTTP o PDF.
- Snapshots/hashes de importes, asociados, contratos, policies, reportes y
  estado de publicacion antes/despues; ninguna autorizacion cloud implicita.

Pendiente de comprobar en D: ejecucion real de los casos, compatibilidad de
unidades desconocidas, consumidor de principal/evidencias SoundOn y tratamiento
de propuestas discrepantes sin perder nombres. Transfers reales siguen fuera
de certificacion hasta recibir ejemplos y definir su alcance aprobado.
