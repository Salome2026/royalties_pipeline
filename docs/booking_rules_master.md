# Booking VPO - Reglas maestras

Fecha: 2026-05-16

Este documento es la referencia obligatoria antes de modificar booking. Si una idea nueva no entra aca, primero se actualiza este documento y recien despues se toca codigo.

## Regla madre

Booking tiene tres capas distintas:

1. Liquidacion esperada.
2. Caja real.
3. Cuenta corriente.

Nunca se debe resolver una diferencia cambiando la regla economica del show.

La liquidacion dice lo que deberia pasar. La caja dice lo que realmente paso. La cuenta corriente registra lo que queda vivo.

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
- `cerrado_con_cuenta_corriente`;
- `observado`;
- `historico`;
- `cancelado`;
- `no_cobrado`.

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

## Indyana ganado vs base comisionable

No son lo mismo.

Indyana ganado es la ganancia economica de Indyana por un show o linea.

Base comisionable es la parte de Indyana ganado que corresponde usar para pagar comisiones internas de booking.

Ejemplos:

- show comun: puede ser igual;
- G Sony con regla especial: Indyana gana, pero puede no ser comisionable porque la comision ya se resolvio por otra regla;
- historico importado: puede quedar marcado como historico/no definido.

Nunca usar automaticamente Indyana ganado como base comisionable sin mirar la regla.

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
- base comisionable;
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
