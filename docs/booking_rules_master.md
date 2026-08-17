# Booking VPO - Reglas maestras

Fecha: 2026-08-16

Este documento es la referencia obligatoria antes de modificar booking. Si una idea nueva no entra aca, primero se actualiza este documento y recien despues se toca codigo.

## Regla madre

Booking tiene tres capas distintas:

1. Liquidacion esperada.
2. Caja real.
3. Cuenta corriente.

Nunca se debe resolver una diferencia cambiando la regla economica del show.

La liquidacion dice lo que deberia pasar. La caja dice lo que realmente paso. La cuenta corriente registra lo que queda vivo.

## Superficie unica de Booking

La operacion viva de booking se presenta en una sola tarjeta y una sola ventana:
`Booking Indyana`.

Dentro de esa ventana existen dos modos de carga:

1. `Booking individual`: conserva la carga directa de un show propio.
2. `Booking compartido`: conserva la liquidacion de un evento madre, sus gastos
   compartidos y sus lineas o shows hijos.

El selector cambia la superficie visible, no la regla economica ni el modelo de datos.
Cada modo mantiene su propio formulario, calculos, endpoints, registros y estado de
edicion. Cambiar de modo no convierte un show individual en evento madre, no mezcla
cajas y no borra una carga en curso.

Reglas obligatorias:

- la entrada predeterminada es `Booking individual`;
- no existe una segunda tarjeta operativa para booking compartido;
- `booking` y `composite_booking` siguen siendo permisos independientes;
- un usuario solo puede seleccionar los modos para los que tiene acceso;
- una cuenta sin permiso de booking compartido no obtiene acceso por compartir la
  misma ventana;
- los shows hijos generados por booking compartido siguen alimentando Booking,
  cuenta corriente, comisiones y finanzas con la trazabilidad actual;
- la unificacion visual no autoriza fallbacks, duplicacion de guardados ni rutas
  operativas paralelas.

## Agenda como cabecera operativa

La agenda no es otra copia del show ni otra fuente de datos. Es una vista de la
cabecera operativa comun `booking_events`. En el ABM existe el permiso independiente
`booking_agenda` para separar la operacion de agenda de la liquidacion economica.

Permisos obligatorios:

- `booking_agenda / Ver`: permite consultar toda la agenda; es el permiso inicial de
  todos los empleados activos y no se limita por artista;
- `booking_agenda / Cargar`: conserva la visualizacion y permite agregar shows,
  grupos, bloqueos, logistica y prospectos;
- `booking_agenda / Editar`: conserva visualizacion y carga, y permite modificar o
  eliminar entradas futuras que aun no tienen liquidacion;
- abrir una liquidacion existente exige `view_history` del permiso `booking` o
  `composite_booking`, segun corresponda, y alcance sobre todos sus artistas;
- iniciar una liquidacion exige `create` de `booking` o `composite_booking`, segun
  corresponda, y alcance sobre todos sus artistas;
- el permiso de Agenda nunca concede acceso implicito a importes, caja, cuenta
  corriente o liquidaciones de Booking.

`booking_events` representa la agenda operativa del artista. Puede contener un show,
un grupo de shows, un bloqueo de disponibilidad, una referencia logistica o un
prospecto. Solo los registros de tipo `show` abren o vinculan una liquidacion.

Tipos canonicos:

- `show`: prestacion vendida o precargada que puede liquidarse;
- `show_group`: agrupador visual de dos o mas shows relacionados; no liquida ni suma
  dinero por si mismo;
- `availability_block`: fecha en la que el artista no trabaja;
- `logistics`: vuelo, traslado u otra referencia operativa sin liquidacion;
- `prospect`: oportunidad aun no confirmada.

Las liquidaciones actuales siguen especializadas:

- un evento con un solo artista VPO abre o vincula un `booking_show` individual;
- un evento con dos o mas artistas abre o vincula un `booking_composite_event` y sus
  lineas;
- una madre historica de Caserio se vincula como una unica cabecera compartida y sus
  shows hijos no se duplican en Agenda;
- la cantidad de artistas define el flujo por defecto, sin obligar al usuario a elegir
  un motor contable;
- agenda, Booking individual y Booking compartido deben compartir `event_id` y nunca
  crear versiones independientes del mismo hecho.
- los bloqueos, la logistica, los prospectos y los agrupadores nunca crean caja,
  cuenta corriente, comisiones ni ingresos de Booking;
- un grupo conserva una sola fila visible en Agenda y sus shows concretos como hijos
  liquidables, evitando sumar el cachet del grupo y de los hijos al mismo tiempo.

La carga inicial minima contiene:

- fecha;
- artista o artistas;
- venue/evento;
- ciudad;
- cachet pactado;
- moneda y tipo de cambio cuando corresponda;
- responsable comercial y/o tour manager si se conoce;
- seña opcional;
- notas.

La carga inicial no calcula ni confirma gastos, splits, pagos al artista, ingreso
ganado por Indyana ni cierre. Esos hechos se completan en la liquidacion vinculada.

### Sincronizacion de un show vinculado

Agenda y liquidacion son dos vistas del mismo show, no dos fichas independientes.
Cuando una liquidacion individual vinculada se edita, `booking_events` debe reflejar
en la misma transaccion la fecha, venue, ciudad, artista, responsables, cachet,
moneda, tipo de cambio y estados vigentes. La referencia original importada se
conserva sin cambios en `booking_event_source_links` como evidencia de conciliacion.

Una correccion como `a revisar` a `30-30` debe verse inmediatamente en Agenda. No se
crea otro evento, no se edita el texto fuente y no se espera una nueva importacion.

### Estado inicial segun el tipo de agenda

Un show vendido nace con dimensiones separadas:

- estado comercial: `confirmado`;
- estado operativo: `programado`;
- estado de seña: `sin_sena`, `sena_parcial` o `sena_recibida`;
- estado de liquidacion: `no_iniciada`.

### Edicion operativa

Toda entrada futura sin liquidacion vinculada puede editarse desde Agenda con permiso
`booking_agenda / Editar`. La edicion conserva el mismo `event_id`, registra
auditoria y nunca altera `booking_event_source_links`. Si el show ya tiene
liquidacion, Agenda abre esa liquidacion exacta: no mantiene un segundo formulario
para el mismo hecho.

La fecha y el vinculo determinan la accion del usuario:

- show futuro sin liquidacion: abre la edicion operativa de Agenda;
- show pasado sin liquidacion: abre una liquidacion nueva precargada y vinculada;
- show pasado con liquidacion: abre la liquidacion exacta existente;
- show futuro ya vinculado: abre la liquidacion exacta, porque el registro economico
  ya es la verdad editable;
- compromiso pasado no liquidable: queda en consulta y no vuelve a un formulario de
  edicion;
- grupo pasado: se despliega y cada show hijo se liquida por separado.

Toda liquidacion nueva debe terminar vinculada a una cabecera `booking_events`. Si el
usuario entra directamente por Liquidaciones, el guardado busca una coincidencia
exacta por fecha, artistas, venue y ciudad. Una unica coincidencia se reutiliza; si no
existe, la cabecera se crea dentro de la misma operacion. Varias coincidencias exactas
o una liquidacion historica exacta sin vinculo bloquean el alta para evitar duplicados.
No se crean liquidaciones nuevas independientes de Agenda.

Un usuario autorizado tambien puede crear y editar `show_group`. El grupo contiene dos
o mas shows hijos con fecha, hora, venue, ciudad y cachet propios. El total visible del
grupo se calcula como la suma de sus hijos; el grupo no genera liquidacion, caja,
comision ni ingreso. Cada hijo se liquida de forma independiente. Agregar o quitar
hijos se permite mientras ninguno tenga liquidacion vinculada.

Una precarga `show` sin liquidacion ni seña puede convertirse en `show_group` sin crear
otra cabecera: conserva su `event_id`, auditoria y fuente original, y crea los shows
hijos debajo. Si ya existe liquidacion o seña, la conversion se bloquea.

La relacion tambien funciona en sentido inverso. Si un grupo futuro queda con una sola
presentacion, se convierte en `show` sobre la misma cabecera. Toma fecha, lugar, ciudad,
cachet y nota del hijo restante; conserva las fuentes y deja auditados los hijos
anteriores. La reduccion se bloquea si algun hijo tiene seña o liquidacion.

La seña no confirma ni cancela por si sola la venta. Un show puede estar confirmado
con o sin seña. La seña es caja real y debe quedar trazada, pero no convierte el
cachet en ingreso ganado ni cierra la liquidacion.

En cabeceras reconstruidas desde historia se admite `no_informada` cuando no existe
una entrega separada y comprobable. No equivale a `sin_sena` y no crea caja.

Estados comerciales iniciales admitidos:

- `confirmado`;
- `cancelado`;
- `prospecto`, solo para oportunidades todavia no vendidas;
- `no_aplica`, para bloqueos, logistica y agrupadores.

Los registros que no son shows usan liquidacion `no_aplica`. Un prospecto no se
presenta como show confirmado. Un bloqueo usa estado operativo `bloqueado`; la
logistica usa `informativo`. Estas dimensiones permiten compartir Agenda sin inventar
hechos financieros.

El filtro `Proximos` de Agenda incluye toda entrada futura no cancelada, sin exigir
estado operativo `programado`. Por eso tambien muestra bloqueos, logistica y prospectos.
El resumen `Proximos shows` conserva alcance exclusivo de shows y grupos.

### Grupos de shows

Cuando una contratacion comprende varias presentaciones relacionadas, Agenda muestra
un `show_group` y conserva cada presentacion como un `show` hijo con su propia fecha,
venue, cachet y futura liquidacion. `group_event_id` y `group_position` mantienen la
relacion. El agrupador es visual y comercial: nunca es una madre economica de Booking
compartido y nunca se suma junto con sus hijos en reportes.

Ejemplo validado: `Teodolina las 2` se presenta como un grupo total de $19.000.000 y
contiene dos shows individuales de $9.500.000 para Candu.

### Trazabilidad de fuentes

Una importacion conciliada no guarda referencias dentro de notas libres. Cada renglon
de origen se registra en `booking_event_source_links`, que permite:

- vincular un renglon a un evento existente sin duplicarlo;
- vincular una misma referencia a varios shows, como un paquete o una celda resumida;
- repetir una importacion de forma idempotente;
- conservar el texto original sin convertirlo en regla economica.

### Prevencion de duplicados

Antes de guardar, el sistema debe buscar coincidencias en eventos y shows existentes.
La comparacion considera:

- fecha;
- conjunto normalizado de artistas;
- venue normalizado;
- ciudad normalizada;
- hora, cuando exista;
- registro individual o compartido ya vinculado.

Una coincidencia fuerte ofrece `Abrir existente` o `Continuar precarga`. No se crea un
nuevo registro silenciosamente. No se usa una restriccion rigida solamente por fecha,
artista y venue porque existen shows legitimos del mismo artista y venue nominal en
ciudades distintas. Un administrador puede confirmar `Es otro show`, dejando nota de
auditoria.

Los usuarios sin permiso para ver historial reciben solo la informacion minima para
evitar una duplicacion. No deben ver importes, caja ni liquidaciones fuera de su
alcance.

## Dashboard de Booking

La tarjeta `Booking Indyana` abre un espacio de trabajo de pantalla completa. Dentro
de esa superficie viven:

- Inicio;
- Agenda;
- Nuevo show;
- Liquidaciones;
- Resumen por artista;
- Detalle.

La navegacion no duplica calculos. Agenda usa `booking_events`; Liquidaciones abre el
motor individual o compartido que corresponda; Resumen y Detalle conservan sus fuentes
operativas actuales.

`Resumen booking` y `Detalle Booking` dejan de ser entradas principales separadas
cuando el dashboard queda validado, pero conservan sus calculos, endpoints y permisos.
El dashboard navega hacia esas mismas verdades; no las vuelve a calcular.

Inicio es una superficie de trabajo de ancho completo: no se presenta como una tarjeta
dentro de otra tarjeta ni vuelve a aplicar el contenedor general del menu. La navegacion
lateral, los indicadores, la agenda y sus acciones pertenecen a un mismo dashboard.

Inicio permite alternar entre `Lista` y `Calendario` sin cambiar datos ni reglas. La
vista predeterminada es el calendario mensual. Sus reglas son:

- cada celda muestra solamente el artista o conjunto de artistas del evento;
- varios shows del mismo artista en un dia se compactan como `Artista xN`;
- si hay artistas distintos el mismo dia, se muestran como entradas independientes;
- el padre `show_group` no se vuelve a mostrar junto con sus hijos concretos;
- un dia muestra hasta tres artistas y resume el resto como `+N mas`;
- seleccionar un dia abre su detalle operativo y permite entrar a la misma edicion;
- en celular se conserva el calendario de siete columnas con marcadores compactos y
  el listado legible del dia debajo, sin comprimir nombres dentro de celdas angostas;
- `Lista` conserva el acceso cronologico a proximos shows y acciones rapidas.

El calendario es una vista de `booking_events`: no crea otra agenda, no calcula
ingresos y no altera la liquidacion.

Los indicadores iniciales deben ser operativos y accionables:

- proximos shows;
- pendientes de rendicion;
- observados;
- saldos abiertos.

No se incorporan mapas hasta normalizar ubicaciones. Un elemento visual no puede
mostrar precision geografica que los datos todavia no tienen.

## Liquidacion esperada

La liquidacion esperada se calcula con:

- cachet pactado o cobrado aplicable;
- gastos del show;
- comisiones directas;
- base asignada a cada artista;
- gastos propios de la linea/artista;
- terceros externos;
- recuperos;
- split artista / Indyana / terceros.

El usuario carga datos, pero el sistema calcula. El Excel externo o la foto que mandan sirve como fuente de datos, no como fuente de verdad matematica.

## Cachet pactado vs cobrado real

Cuando el boliche/cliente paga menos que el cachet pactado, el sistema debe pedir una decision explicita. No alcanza con cargar "cobrado real", porque existen dos casos de negocio distintos:

1. `deuda_boliche`: el cachet pactado sigue siendo la base economica del show. La diferencia entre cachet pactado y cobrado real queda como deuda del boliche/cliente. Esta es la opcion por defecto porque conserva el derecho de cobro y evita perder deuda por accidente.
2. `ajustar_cachet`: el cachet pactado queda guardado solo como referencia/auditoria, pero la liquidacion se recalcula usando el cobrado real. La diferencia no queda como deuda del boliche. Se usa cuando se decide aceptar que el show valio menos, fue renegociado, cancelado parcialmente o el dato pactado anterior ya no aplica.

Reglas obligatorias:

- Si no hay problema de cobro, `cachet efectivo = cachet pactado` y `deuda boliche = 0`.
- Si hay cobro parcial y politica `deuda_boliche`, `cachet efectivo = cachet pactado` y `deuda boliche = pactado - cobrado`.
- Si hay cobro parcial y politica `ajustar_cachet`, `cachet efectivo = cobrado real` y `deuda boliche = 0`.
- La politica debe guardarse junto al show para auditoria futura.
- Esta regla aplica a booking simple, liquidaciones compuestas, laboratorio/unificado, Caserio cuando genera shows internos y cualquier carga futura de booking.

## Caja real

Caja real son movimientos de dinero:

- quien cobro;
- quien pago;
- cuanto recibio Indyana;
- cuanto recibio el artista;
- cuanto recibio un manager, PM o tercero;
- si fue transferencia, efectivo, sena u otro;
- comprobante;
- nota.

La caja no reemplaza la liquidacion esperada.

Si el artista debia cobrar 700.000 y cobro 600.000, no se cambia el split. Queda saldo.

Si Indyana debia recibir 300.000 y recibio 250.000, no se cambia la ganancia de Indyana. Queda saldo.

## Cuenta corriente

Toda diferencia viva debe poder expresarse como cuenta corriente.

Tipos minimos:

- saldo a favor del artista;
- saldo a favor de Indyana;
- deuda de boliche/cliente;
- deuda o sobrante del PM/tour manager;
- saldo con manager externo o familia;
- gasto recuperable abierto;
- recupero aplicado;
- adelanto/prestamo;
- ajuste manual observado.

La cuenta corriente debe ser independiente por artista o tercero. No alcanza un saldo global de booking, porque cada artista puede tener derechos, adelantos, recuperos, senas o deudas distintas.

Como minimo, todo movimiento futuro de cuenta corriente debe poder responder:

- de que artista/tercero es;
- que show, gasto o recupero lo genero;
- si es a favor de Indyana o a favor del artista/tercero;
- si ya fue saldado;
- con que movimiento se saldo.

Un show puede estar cerrado operativamente y aun tener cuenta corriente viva. En ese caso no es simplemente `cerrado`; es `cerrado con cuenta corriente`.

### Cuenta corriente unica con origen

No debe existir una cuenta corriente aislada de Booking y otra distinta de Finanzas. Debe existir una sola lectura financiera de cuenta corriente, con origen trazable.

Origenes minimos:

- `booking`: saldos nacidos por shows, senas, rendiciones, deuda de boliche, pagos de mas o pagos de menos;
- `finance`: gastos, inversiones, adelantos, prestamos, pagos manuales y ajustes financieros;
- `royalties`: futuro origen para regalias, adelantos digitales o recuperos contra ingresos digitales;
- `manual_adjustment`: correccion aprobada y observada.

Booking es fuente de verdad del show. Finanzas Artista es la vista consolidada. Movimientos Financieros carga hechos financieros que no son el show en si.

Reglas obligatorias:

- Si un show quedo con saldo, no se reescribe el show para saldarlo despues.
- El show conserva liquidacion, caja cargada y saldo original.
- Un pago posterior, reintegro o compensacion debe ser un movimiento nuevo aplicado al saldo.
- Si un pago, cobro o compensacion cubre varios shows, debe existir un movimiento
  padre con aplicaciones hijas por show. No se debe cargar como ingreso/gasto
  comun ni duplicar resultado de booking.
- El movimiento aplicado debe guardar `source_module`, `source_table`, `source_id` y nota/comprobante.
- La cuenta corriente debe poder filtrarse por artista, por show, por proyecto y por origen.

### Estado tecnico actual

Hoy Booking todavia lee la cuenta corriente derivada desde saldos del show:

- `balance_producer_amount`: saldo a favor/en contra de Indyana;
- `balance_artist_amount`: saldo a favor/en contra del artista;
- `venue_balance_amount`: deuda de boliche/cliente.

Ese modelo sirve para visualizar saldos, pero no alcanza como cuenta corriente operativa completa porque no registra pagos posteriores sin tocar el show.

El esquema Postgres ya tiene `booking_current_account_entries`. El paso correcto no es inventar otra tabla ni duplicar Movimientos Financieros, sino pasar metodicamente de saldos derivados a entradas operativas:

1. Al aprobar/cerrar un show con saldo, generar entradas de cuenta corriente con origen `booking`.
2. Registrar pagos posteriores como aplicaciones contra esas entradas.
3. Permitir compensaciones entre shows sin modificar la liquidacion original.
4. Hacer que Finanzas Artista lea la cuenta operativa cuando exista y use los saldos derivados solo como transicion/auditoria.

`booking_artist_ledger` queda solo como auditoria historica. No debe usarse para recuperos nuevos ni como ledger oficial.

## Estados por capas

No alcanza un unico estado.

Debe distinguirse:

- estado del show/evento;
- estado boliche/cliente;
- estado caja/rendicion;
- estado artistas/terceros;
- estado cuenta corriente;
- estado de revision historica.

Estados sugeridos:

- `borrador`;
- `realizado`;
- `rendido`;
- `aprobado`;
- `cerrado`;
- `cerrado_con_pago_posterior`;
- `cerrado_compensado`;
- `cerrado_con_cuenta_corriente_abierta`;
- `observado`;
- `historico`;
- `cancelado`;
- `no_cobrado`.

### Verde operativo vs historia del cierre

El color verde de un show no significa que nunca tuvo diferencias. Significa que hoy
no tiene saldos vivos.

Un show esta verde cuando:

- no hay deuda viva de boliche/cliente;
- no hay saldo vivo a favor de Indyana;
- no hay saldo vivo a favor del artista;
- no hay saldo vivo con terceros asociados al show;
- si hubo diferencia, existe movimiento posterior, pago o compensacion trazada que la salda.

Por eso:

- `cerrado`: no tuvo diferencias vivas al cierre;
- `cerrado_con_pago_posterior`: tuvo saldo, pero se saldo despues con caja real;
- `cerrado_compensado`: tuvo saldo, pero se saldo aplicando otro show/movimiento;
- `cerrado_con_cuenta_corriente_abierta`: el show esta liquidado, pero todavia hay saldo vivo y por lo tanto debe mantener alerta;
- `pendiente`: falta rendicion, pago, cobro, compensacion o criterio;
- `observado`: hay una diferencia detectada que no se debe cerrar sin revision.

No se deben dejar alertas eternas si el saldo fue saldado. Tampoco se debe borrar la
historia para apagar una alerta.

Ejemplo:

1. Show A: Candu cobro 200.000 de mas. Queda saldo a favor de Indyana.
2. Show B: Candu debia cobrar 900.000, pero se le pagan 700.000 y se aplican 200.000 contra Show A.
3. Show A queda `cerrado_compensado`.
4. Show B queda `cerrado_compensado`.
5. La cuenta corriente de Candu queda en 0.
6. La auditoria conserva que Show B compenso Show A.

## Gasto general vs gasto propio de linea

### Gasto general del evento

Es un gasto necesario para que el evento ocurra o que afecta a todas las lineas:

- sonido general;
- musicos generales;
- staff/stage general;
- tour manager general;
- movilidad/traslado/viaticos del evento;
- hotel/comida del evento;
- gastos varios del evento.

En un show simple, normalmente los gastos van aca.

### Gasto propio de la linea/artista

Es un gasto que pertenece a una liquidacion artistica particular:

- comision Facha en G Sony;
- gasto especifico de un artista dentro de un evento con varios artistas;
- recupero aplicado a un artista;
- gasto que debe viajar con el show hijo;
- ajuste propio de la regla de ese artista.

Regla practica:

- show simple comun: gastos generales;
- G Sony/Facha: gasto propio de linea;
- evento madre: gastos compartidos arriba, gastos especificos dentro de cada linea.

## Comision directa vs tercero externo

### Comision directa del evento

Es una salida o asignacion que se calcula a nivel evento antes de repartir lineas.

Puede:

- salir del calculo y no volver a ningun artista;
- incorporarse a una linea artistica;
- repartirse entre destinos.

Ejemplo Candu + G Sony:

- comision directa total 10%;
- parte Marce: sale directo;
- parte Gaston/Facha: se incorpora a linea G Sony.

### Tercero externo de una linea

Es alguien que participa de la liquidacion de una linea artistica, no un gasto generico.

Ejemplo G Sony:

- Fede participa del split.
- Si G Sony 50%, Indyana 25%, Fede 25%, Fede se carga como tercero/socio externo de la linea.

## Indyana ganado y comisiones internas

Indyana ganado es la ganancia economica de Indyana por un show o linea.

La comision interna no se define por una unica base global. Se calcula show por
show contra las reglas vigentes de cada empleado y artista.

La marca `Excluye comision general` significa solamente que el show no entra en
la comision general automatica. No significa que el ingreso desaparezca, ni que
exista una deuda de comision. La comision solo existe si una regla aplicable la
genera.

Regla operativa:

- si el show no excluye comision general, aplican las reglas activas del artista;
- si el show excluye comision general, no aplica ninguna regla salvo que esa
  regla particular tenga habilitado cobrar shows con booking ya pagado;
- una regla bloqueada por la exclusion suma cero y no genera deuda pendiente;
- las reglas aplicables se calculan en cascada por `orden` del 1 al 5;
- cada comision calculada reduce la base disponible para la siguiente regla;
- el orden se debe elegir cuando la regla esta activa y tiene porcentaje mayor
  a cero; una regla sin porcentaje puede quedar sin orden;
- no puede haber dos reglas activas con porcentaje mayor a cero usando el mismo
  orden para el mismo artista;
- Resumen Booking muestra Indyana bruto, comisiones aplicables e Indyana neto;
- Comisiones explica empleado por empleado que regla genero cada importe.

Ejemplos:

- Gusty DJ sin exclusion: si Marce tiene 20% y David 10%, el resumen resta 30%
  solo si ambos cobran sobre el bruto. Con cascada, Marce orden 1 cobra sobre el
  bruto y David orden 2 cobra sobre lo que queda.
- Virrshi con exclusion general: Marce no cobra si respeta la exclusion; David
  cobra solo si su regla particular lo habilita.

Nunca usar automaticamente Indyana ganado como base de pago sin mirar la regla
del show y la regla particular del empleado.

## Show simple

Un show simple tiene una sola linea de artista VPO.

Puede tener:

- gastos generales;
- gastos propios de linea;
- terceros externos;
- comisiones directas;
- recuperos;
- senas;
- cuenta corriente.

Tener reglas avanzadas no lo convierte en evento madre.

Ejemplo: G Sony solo es show simple con regla avanzada, no madre.

## Evento madre con hijas

Un evento pasa a ser madre cuando hay mas de una linea artistica relevante, especialmente mas de un artista VPO.

La madre guarda:

- contexto;
- bruto/cobrado general;
- gastos generales;
- comisiones directas;
- reglas de asignacion;
- resumen;
- links a hijas.

La hija/show operativo guarda:

- liquidacion real de ese artista;
- gastos propios;
- terceros externos;
- pagos al artista;
- recibido por Indyana;
- caja propia;
- estado;
- saldos.

La hija manda como realidad operativa. La madre organiza y controla.

Si una hija se edita despues, la madre no debe pisarla sin accion explicita.

## Artista externo

Un artista externo puede aparecer en una liquidacion para bajar la caja o explicar el evento.

Por defecto:

- no genera show VPO;
- no genera ingreso Indyana;
- debe quedar trazado como egreso/linea externa;
- puede afectar el neto a rendir o la caja del evento.

## Senas previas y movimientos de caja

Una sena es caja real, no liquidacion.

Puede recibirla:

- Indyana;
- artista;
- PM/tour manager;
- manager externo;
- tercero.

La sena puede hacer que:

- el artista haya cobrado de mas;
- Indyana tenga que transferir diferencia;
- el PM deba rendir menos o mas;
- quede cuenta corriente.

El sistema debe mostrar el efecto antes de cerrar.

La sena debe cargarse simple:

- importe;
- metodo;
- quien recibio: artista o productora;
- notas/comprobante.

La sena impacta contra la parte economica de quien la recibio:

- si Indyana debia recibir 300 y recibio sena de 200, todavia debe recibir 100;
- si el artista debia recibir 300 y recibio sena de 500, el artista cobro 200 de mas y se sugiere cuenta corriente a favor de Indyana;
- si Indyana recibio de mas respecto de su parte, se sugiere cuenta corriente a favor del artista o ajuste de caja del show.

El responsable del show/tour manager solo deberia rendir lo que efectivamente paso por el evento luego de senas previas. Por eso el sistema debe distinguir:

- cachet cobrado total;
- senas previas;
- monto que queda por cerrar en el evento;
- pagos/rendiciones del evento;
- cuenta corriente generada.

## Cuenta booking del show

La cuenta booking del show no es un modulo separado ni una segunda contabilidad. Es una vista operativa dentro de Booking Indyana, filtrada por show.

Debe poder abrirse desde:

- el buscador de shows;
- las ultimas cargas;
- las alertas de cierre o deuda.

Debe mostrar, sin permitir confusiones:

- liquidacion esperada original;
- caja real cargada;
- deuda de boliche;
- saldo a favor de Indyana;
- saldo a favor del artista;
- recuperos aplicados;
- movimientos posteriores que saldan o compensan;
- estado actual del saldo.

Acciones futuras de esa vista:

- registrar cobro de deuda de boliche;
- registrar pago al artista;
- registrar reintegro del artista;
- aplicar compensacion con otro show;
- aplicar recupero contra proyecto;
- marcar observado con nota.

Estas acciones crean movimientos trazables. No deben modificar silenciosamente cachet, gastos, split, pagos originales ni rendiciones originales del show.

## Recuperos

Un recupero no debe esconderse como gasto comun si tiene impacto de cuenta corriente.

Ejemplo DJ set Virrshi:

- costo total;
- parte artista;
- parte Indyana;
- recuperado;
- saldo.

Modo recomendado por defecto:

- contra parte artista.

Otros modos:

- antes del split;
- contra parte Indyana;
- manual.

Si se recupera antes del split, economicamente Indyana no esta asumiendo su parte como inversion. Ese modo debe usarse conscientemente.

## Exactitud de caja

La caja debe cerrar exacta internamente.

Los totales visuales pueden redondearse, pero:

- los sugeridos deben mostrar centavos cuando existan;
- `Usar sugerido` debe cargar el valor exacto;
- una diferencia de 0,50 sigue siendo diferencia;
- se puede marcar observado, pero no cerrar automatico.

## Regla de interfaz

La pantalla debe empezar simple.

Secciones visibles de entrada:

- datos del show;
- gastos generales;
- una linea artistica;
- resumen.

Secciones opcionales por botones:

- comision directa;
- otro artista;
- artista externo;
- gasto propio de linea;
- manager/socio externo;
- caja/sena;
- recupero;
- cuenta corriente/observacion.

No agregar botones sin decidir antes en que capa viven:

- liquidacion;
- caja;
- cuenta corriente;
- reporte/control.

## Regla de guardado

Antes de guardar, el sistema debe mostrar:

- si se guardara como show simple o evento madre;
- que shows hijos se crearian;
- liquidacion esperada por linea;
- caja real por linea;
- saldos;
- cuenta corriente sugerida;
- comisiones aplicables;
- neto Indyana despues de comisiones;
- alertas.

No se conecta guardado de la pantalla nueva hasta que los casos de validacion pasen.

## Caserio

Caserio queda fuera de esta pantalla por ahora.

Tiene su propio modulo porque mezcla sociedad/evento externo y caja a rendir a terceros.

No mezclar Caserio con la pantalla general hasta tener la logica de booking estable.

## Protocolo obligatorio para cambios futuros

Antes de tocar codigo:

1. Identificar el caso real.
2. Decir que capa afecta: liquidacion, caja, cuenta corriente o reporte.
3. Verificar si ya existe campo/seccion para eso.
4. Si no existe, actualizar este documento.
5. Definir impacto en show simple, evento madre e historico.
6. Recien despues modificar pantalla o backend.
7. Compilar.
8. Probar contra la matriz de casos.

Si una modificacion arregla G Sony pero rompe Laalo, esta mal.

Si una modificacion arregla caja pero cambia liquidacion, esta mal salvo que sea intencional y documentado.

Si una modificacion cierra un saldo escondiendolo, esta mal.
