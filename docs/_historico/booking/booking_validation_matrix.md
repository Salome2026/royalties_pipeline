# Booking VPO - Matriz de validacion

Fecha: 2026-05-16

Esta matriz define los casos minimos que deben probarse antes de conectar guardado nuevo o reemplazar pantallas existentes.

## Estado de la pantalla laboratorio

La pantalla `Carga de Shows laboratorio` es solo calculo/validacion.

No debe guardar en base viva hasta que esta matriz este validada.

## Caso 1 - Show simple comun

Ejemplos:

- Lazer K;
- Laalo DJ;
- Gusty DJ directo;
- Facuu DJ directo.

Entrada:

- un artista VPO;
- cachet;
- gastos generales;
- split artista/Indyana;
- pagos reales;
- rendido a Indyana.

Debe mostrar:

- modo: `Show simple`;
- base = cobrado real - gastos generales;
- artista sugerido;
- Indyana sugerido;
- pagado artista;
- rendido Indyana;
- saldo artista;
- saldo Indyana;
- cuenta corriente sugerida si hay diferencias.

No debe:

- crear madre;
- pedir campos complejos;
- mezclar gastos generales con cuenta corriente;
- cerrar si hay saldo.

## Caso 2 - Show simple con regla avanzada: G Sony solo

Entrada:

- un artista VPO: G Sony;
- gastos generales del evento;
- comision directa del evento si corresponde;
- gasto propio de linea: Gaston/Facha 15%;
- tercero externo: Fede;
- split G Sony / Indyana / Fede;
- marca exclusion de comision general si corresponde.

Debe mostrar:

- modo: `Show simple con reglas avanzadas`;
- no debe crear madre;
- Facha como gasto/comision propia de linea;
- Fede como tercero/socio externo, no como gasto;
- Indyana ganado;
- comisiones aplicables segun reglas vigentes;
- saldos reales.

No debe:

- tratar Fede como gasto comun;
- tratar G Sony solo como madre;
- esconder la parte de Indyana por estar Fede.

## Caso 3 - Evento madre: Candu + G Sony

Entrada:

- evento con dos artistas VPO;
- gastos generales compartidos;
- comision directa del evento;
- parte Marce: salida directa;
- parte Gaston/Facha: incorporada a G Sony;
- linea Candu 70/30;
- linea G Sony con Facha y Fede;
- pagos/rendiciones por linea.

Debe mostrar:

- modo: `Evento madre`;
- madre con contexto y gastos generales;
- hija Candu;
- hija G Sony;
- Candu sin regla G Sony;
- G Sony con su tercero externo y comision propia;
- base no asignada en cero o alerta;
- resumen por linea;
- saldos por linea;
- cuenta corriente sugerida por linea si corresponde.

No debe:

- duplicar Indyana esperado entre madre e hijas;
- pisar datos de hijas editadas;
- mezclar comision directa con gastos propios salvo cuando se incorpora explicitamente.

## Caso 4 - Show simple con sena

Ejemplos:

- Laalo con sena a Indyana;
- Gusty con sena cobrada por artista;
- Virrshi con sena y pago posterior.

Entrada:

- liquidacion normal;
- movimiento real de caja tipo sena;
- quien recibio la sena;
- comprobante;
- pago/rendicion posterior.

Debe mostrar:

- liquidacion esperada igual que siempre;
- caja real separada;
- saldo neto despues de sena;
- si Indyana cobro de mas, deuda a artista;
- si artista cobro de mas, deuda a Indyana;
- si PM tiene plata sin rendir, saldo PM/Indyana.

No debe:

- cambiar el split por la sena;
- tratar sena como gasto;
- cerrar si queda saldo sin cuenta corriente.

## Caso 5 - Virrshi con recupero

Entrada:

- show normal Virrshi;
- gasto recuperable abierto, por ejemplo DJ set;
- regla recuperable 70/30;
- recupero aplicado total o parcial;
- forma de recupero: contra parte artista, antes del split, contra Indyana o manual.

Debe mostrar:

- show/liquidacion normal;
- recupero separado;
- saldo recuperable artista;
- saldo recuperable Indyana;
- saldo total del gasto;
- impacto en caja;
- cuenta corriente si falta recuperar.

No debe:

- esconder recupero como gasto comun sin trazabilidad;
- asumir que todo recupero es antes del split;
- cerrar gasto recuperable si queda saldo.

## Caso 6 - Aneley / manager externo administra caja

Entrada:

- show propio de Aneley;
- caja administrada por padre/manager externo;
- pagos a Salome, Carolina o Indyana;
- saldo informado por externo;
- posible diferencia aceptada u observada.

Debe mostrar:

- show economico propio;
- derecho de Indyana;
- responsable de caja externo;
- movimientos que reducen deuda;
- cuenta corriente con manager/artista;
- estado cerrado con cuenta corriente si corresponde.

No debe:

- borrar saldo por cerrar show;
- inferir split desde lo que el manager pago;
- mezclar gastos generales no show con gastos de show.

## Caso 7 - Artista externo dentro de evento

Entrada:

- evento con artista VPO;
- artista externo que cobra cachet;
- gastos generales;
- rendicion/caja.

Debe mostrar:

- artista externo baja caja del evento;
- no genera show VPO;
- no genera Indyana ganado;
- no genera comision interna de booking;
- queda trazado para auditoria.

No debe:

- crear hijo para artista externo;
- mezclarlo con tercero externo de una linea;
- ocultar su efecto en caja.

## Caso 8 - Historico 0/0 o no cobrado

Entrada:

- show historico con cachet informado pero sin cobro;
- show cancelado o no rendido;
- datos incompletos.

Debe mostrar:

- visibilidad del show;
- no suma a ingresos reales si no cobro;
- alerta o estado historico/observado;
- no afectar comisiones;
- posibilidad de completar despues.

No debe:

- borrar por estar incompleto;
- inventar cobros;
- sumar a Indyana ganado si no corresponde.

## Caso 9 - Dolares y tipo de cambio

Entrada:

- importes en ARS y/o `u$`;
- tipo de cambio informado;
- gastos en dolares o pesos.

Debe mostrar:

- calculo interno en ARS;
- tipo de cambio guardable;
- importes sugeridos coherentes;
- alerta si falta tipo de cambio.

No debe:

- mezclar monedas sin conversion;
- usar FX de royalties digitales;
- perder el valor original si se cargo en USD.

## Criterio de aprobado

Una pantalla se considera lista para guardar solo si:

- cada caso muestra modo correcto;
- cada caso separa liquidacion, caja y cuenta corriente;
- los saldos no se esconden;
- los botones `Usar sugerido` cargan valores exactos;
- los reportes no duplican Indyana;
- Indyana ganado se distingue de comisiones aplicables y neto Indyana;
- Caserio sigue aislado;
- no se rompe Booking Indyana actual.

## Protocolo de prueba por cambio

Cada cambio relevante debe documentar:

- que caso resuelve;
- que casos se probaron;
- que no se pudo probar;
- si afecta base viva;
- si requiere migracion.
