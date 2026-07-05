# Booking Operational Rules

Este documento registra reglas operativas aprendidas durante la migracion de booking.
No reemplaza al modelo de datos; baja criterios practicos para la carga rapida, la web
y la conciliacion de cuentas corrientes.

## Principio General

Todo show propio debe existir como show economico aunque la caja no la administre VPO.

Separar siempre:

- resultado del show;
- caja real;
- responsable de administracion/rendicion;
- cuenta corriente del artista o tercero.

El resultado del show responde a la regla economica acordada. La caja responde a quien
cobro, pago o rindio dinero. Si no coinciden, no se cambia la regla del show: se deja un
balance o movimiento de cuenta corriente.

## Agenda y Precarga

La agenda debe ser la base operativa futura.

Flujo esperado:

1. La agenda precarga fecha, artista, venue, cachet pactado, moneda, responsable y estado.
2. La carga rapida completa rendicion: ingresos cobrados, gastos, pagos, comprobantes y
   observaciones.
3. El sistema calcula el resultado esperado segun la regla del artista.
4. El usuario aprueba o corrige la caja real.
5. Las diferencias quedan como balance o cuenta corriente.

La agenda no es contabilidad final. Sirve como control de shows esperados, cancelados,
sin rendir o pendientes de cobro.

## Responsable de Caja

Un show puede estar administrado por:

- VPO / Indyana;
- tour manager propio;
- tour manager externo;
- familiar o manager del artista;
- productor, venue o tercero.

El responsable de caja define quien debe rendir, no cambia la propiedad economica del
show.

Campos que la carga rapida debe contemplar:

- `cash_responsible`;
- `cash_admin_type`: internal, own_tm, external_tm, family_manager, promoter, other;
- `settlement_status`: draft, submitted, observed, approved, closed;
- comprobantes;
- notas de excepcion.

## Cuenta Corriente

La cuenta corriente consolida derechos y pagos.

Debe separar como minimo:

- deuda generada por shows;
- pagos recibidos por VPO/equipo;
- gastos generales/no show;
- adelantos;
- recuperos;
- ajustes manuales;
- saldo pendiente.

Pagos a personas internas como Salome, Carolina o Indyana se consideran pagos recibidos
por el equipo/VPO cuando correspondan a rendiciones del artista o su responsable.

La cuenta corriente no debe duplicarse por modulo. Booking, Movimientos Financieros y
Regalias deben alimentar una misma lectura financiera, siempre con origen trazable.

Para saldos nacidos en Booking:

- el origen es `booking`;
- la fuente es el show o show hijo;
- el saldo puede ser a favor de Indyana, a favor del artista o deuda del boliche;
- un pago posterior no reescribe el show;
- un reintegro posterior no reescribe el show;
- una compensacion con otro show debe quedar como aplicacion trazada.

Ejemplo:

- Candu debia cobrar 1.000.000 y cobro 1.200.000.
- El show conserva que Candu cobro 1.200.000.
- La cuenta corriente muestra 200.000 a favor de Indyana con origen booking.
- Cuando Candu reintegra 200.000, se carga una aplicacion contra ese saldo.
- El show queda historicamente correcto y la cuenta corriente queda saldada.

Movimientos Financieros se usa para hechos financieros no representados por la carga
del show: gastos de proyecto, inversiones, adelantos, prestamos, gastos de oficina,
salarios, pagos manuales o recuperos externos. No debe usarse para duplicar una
liquidacion de booking ya cargada.

### Estado verde de un show

Un show debe verse como cerrado/verde solo cuando no quedan saldos vivos.

Saldos que impiden verde:

- deuda de boliche/cliente;
- Indyana debe cobrar algo;
- Indyana cobro de mas y debe devolver o reconocer;
- artista debe cobrar algo;
- artista cobro de mas y debe reintegrar o compensar;
- tercero asociado al show tiene saldo abierto.

Si el saldo se paga o compensa despues, no se edita el show original para borrar la
diferencia. Se agrega una aplicacion posterior trazada. Cuando esa aplicacion deja el
saldo en cero, el show puede volver a verse verde con etiqueta historica:

- `cerrado_con_pago_posterior`;
- `cerrado_compensado`.

La etiqueta explica como cerro. La alerta viva desaparece porque ya no hay deuda.
En la base operacional, estas aplicaciones viven en `booking_account_applications` y
se suman al saldo original del show para calcular el saldo vivo.

## Shows Administrados Por Terceros

Caso tipo Aneley:

- El show se carga como show propio.
- El padre/manager puede administrar caja y rendir por Drive.
- La parte de Indyana se registra como derecho de cobro.
- Los pagos que el padre hace a Salome, Carolina o Indyana reducen la deuda.
- Si hay gastos generales fuera del show, van a cuenta corriente, no al resultado del
  show salvo que esten expresamente imputados a un show.

## Reglas de Liquidacion

No inferir porcentajes desde la caja real.

Ejemplo:

- Regla del show: 70% artista / 30% Indyana.
- Neto: 500.000.
- Objetivo artista: 350.000.
- Objetivo Indyana: 150.000.
- Si la caja real pago otro importe, registrar balance.

La caja real no redefine el contrato.

## Gastos de Show vs Gastos Generales

Gastos de show:

- musicos;
- staff;
- tour manager;
- sonido;
- traslado del show;
- viaticos del show;
- gastos directamente imputables a una fecha/show.

Gastos generales/no show:

- ropa;
- videoclips;
- grabaciones;
- contenido;
- produccion artistica;
- adelantos;
- gastos promocionales no asociados a una fecha concreta.

Los gastos generales deben entrar a la cuenta corriente del artista con marca:

- recuperable;
- no recuperable;
- recuperable por booking;
- recuperable por royalties;
- pendiente de criterio.

## Migracion Historica

Cuando el origen historico esta incompleto:

- No inventar fechas si no hay forma razonable de inferirlas.
- Si la fecha se infiere del nombre de hoja o archivo, guardar esa inferencia en notas.
- Si una hoja agrupa varios shows y no conviene prorratear, cargarla como rendicion
  historica agrupada.
- Si luego se necesita granularidad por venue, se puede refinar con una correccion o
  apertura posterior.

Para Aneley:

- PM Salome contiene la primera carga operativa desde 2026.
- Shows Aneley.xlsx contiene historico anterior y rendiciones del responsable externo.
- Los meses 2026 ya cargados no deben duplicarse.
- Las hojas anteriores a 2026 deben conciliarse como shows historicos o rendiciones
  agrupadas, segun la claridad de cada hoja.
- La hoja `GASTOS` de Shows Aneley.xlsx parece contener gastos generales/no show y no
  debe mezclarse automaticamente con gastos de show.

## Carga Rapida Web

La carga rapida debe permitir casos simples y especiales sin romper contabilidad.

Debe permitir:

- seleccionar artista desde lista cerrada;
- seleccionar show precargado desde agenda;
- cargar cachet cobrado;
- cargar varios gastos individuales con categoria y concepto;
- cargar pago al artista;
- cargar monto rendido a Indyana;
- indicar responsable de caja;
- cargar comprobantes;
- marcar caso especial;
- registrar ajustes antes del split;
- registrar ajustes de cuenta corriente;
- guardar borrador sin impactar;
- aprobar y cerrar.

El sistema debe sugerir importes segun regla, pero el usuario debe poder ingresar caja
real. Si hay diferencia, queda balance.

### Cuenta booking del show

La pantalla de Booking debe permitir abrir una vista de cuenta del show desde el
buscador, las ultimas cargas o una alerta. Esa vista sirve para cerrar saldos nacidos
en booking sin editar la liquidacion original.

Debe mostrar:

- liquidacion esperada;
- caja real;
- saldos vivos;
- movimientos posteriores aplicados;
- recuperos aplicados;
- comprobantes y notas.

Debe permitir, cuando el flujo este implementado:

- cobrar deuda de boliche;
- pagar saldo al artista;
- registrar reintegro del artista;
- compensar contra otro show;
- aplicar recupero contra un proyecto.

Cada accion genera un movimiento nuevo. Ninguna accion debe cambiar de forma silenciosa
cachet, gastos, split, pago original o rendicion original.

## Reportes De Control

El reporte global de shows debe mantenerse como control permanente.

Debe permitir:

- filtrar por artista;
- filtrar por fecha;
- ver cachet, gastos, neto, objetivo artista, objetivo Indyana, pagos reales y balances;
- ver resumen mensual de Indyana por artista;
- distinguir shows reales de alertas/pendientes;
- listar movimientos de caja y ajustes.

Los pendientes sin fecha o no cobrados deben ir a una hoja de alertas o pendientes, no
sumar a ingresos reales.
