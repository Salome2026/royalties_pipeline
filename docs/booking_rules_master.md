# Booking VPO - Reglas maestras

Fecha: 2026-08-15

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
