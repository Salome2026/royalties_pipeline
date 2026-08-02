# Booking VPO - Flujo para empezar a cargar shows

Fecha: 2026-05-16

Este documento baja a operativo el estado actual del modulo booking. La prioridad es empezar a cargar shows sin romper la base viva ni perder la logica de negocio que ya validamos.

## Regla de avance

La pantalla nueva `Carga de Shows laboratorio` todavia no guarda. Sirve para validar calculos, reglas, saldos y cuenta corriente sugerida.

La pantalla `Booking Indyana` sigue siendo la carga viva para shows simples y controlados.

La pantalla `Liquidaciones compuestas` solo se usa cuando el caso ya fue probado y entendido, por ejemplo Candu + G Sony, pero no debe convertirse en el flujo definitivo sin revisar.

## Capas obligatorias

Todo show debe leerse en tres capas:

1. Liquidacion esperada.
2. Caja real.
3. Cuenta corriente.

No se cambia la liquidacion para hacer cerrar la caja. Si hay diferencia, queda como saldo o cuenta corriente.

## Que se puede cargar ya

### Shows simples comunes

Usar `Booking Indyana`.

Ejemplos:

- Lazer K;
- Laalo DJ;
- Gusty DJ directo;
- Facuu DJ directo;
- Toti, Dj Plaga, Dormun, Candu sola, si no tienen regla especial.

Condiciones:

- un solo artista VPO;
- gastos simples del show;
- split normal;
- se puede cargar seña si queda claro quien la recibio;
- si queda saldo, documentarlo en notas y estado.

### Shows con pago parcial del boliche

Usar `Booking Indyana`.

Campos clave:

- cachet pactado;
- marcar que el boliche no pago completo;
- cobrado real;
- nota de deuda.

El show no debe sumar como cobrado total si el boliche pago menos.

### Shows G Sony solo

Primero simular en `Carga de Shows laboratorio`.

Si el resultado coincide, cargar en `Booking Indyana` solo si se puede expresar sin perder informacion:

- gastos generales;
- comision Facha como gasto/comision propia;
- Fede como tercero externo;
- marcar exclusion de comision general si corresponde;
- notas claras.

Si no se puede expresar bien, no cargar en vivo todavia.

### Candu + G Sony

Usar `Liquidaciones compuestas` solo cuando:

- la madre y las hijas se entienden;
- no se duplican shows historicos;
- la parte de Candu y la de G Sony quedan separadas;
- G Sony conserva su tercero externo;
- la comision directa queda documentada;
- las hijas quedan revisables como shows propios.

## Que no conviene cargar todavia en vivo

### Virrshi con recuperos complejos

No cargar recuperos definitivos hasta tener claro:

- gasto recuperable original;
- parte artista;
- parte Indyana;
- recupero aplicado;
- saldo abierto.

Se puede cargar el show si el recupero queda documentado en notas, pero no dar por cerrada la cuenta corriente.

### Aneley con cuenta corriente externa

Los shows historicos ya se fueron trabajando, pero para cargas nuevas hay que mantener separado:

- liquidacion del show;
- caja administrada por manager/familia;
- pagos a Salome, Carolina o Indyana;
- saldo con Aneley/manager.

Si queda saldo entendido, el show puede ser `cerrado con cuenta corriente`, no pendiente eterno.

### Caserio

Seguir usando el modulo `El Caserio`.

No mezclarlo con Booking Indyana ni con el laboratorio general hasta que el flujo comun este cerrado.

## Maqueta objetivo de carga unica

La pantalla final debe empezar simple y abrir secciones solo si hacen falta.

### Datos base

- fecha;
- venue/evento;
- ciudad;
- responsable;
- cachet pactado;
- cobrado real;
- moneda;
- tipo de cambio;
- notas/comprobantes.

### Gastos generales

Gastos que afectan al evento completo:

- sonido;
- musicos;
- staff/stage;
- tour manager;
- movilidad/viaticos;
- hotel/comida;
- varios.

### Señas

Boton opcional `Agregar seña`.

Campos minimos:

- importe;
- metodo: transferencia, efectivo u otro;
- quien recibe: Indyana, artista, PM/manager o tercero;
- aplicar a artista si hay mas de una linea;
- nota/comprobante.

La seña no cambia el split. Solo impacta contra lo que esa parte ya cobro.

### Lineas artisticas

Una linea por artista VPO o externo relevante.

Cada linea debe tener:

- artista;
- base asignada;
- gastos propios;
- terceros/socios;
- split;
- pagado artista;
- rendido Indyana;
- exclusion de comision general y motivo, si aplica;
- saldo.

### Cierre

Antes de guardar debe mostrar:

- se guarda como show simple o evento madre;
- que hijas se crean;
- Indyana ganado;
- Indyana cobrado;
- saldo Indyana;
- artista ganado;
- artista cobrado;
- saldo artista;
- terceros esperados;
- cuenta corriente sugerida;
- deuda de boliche;
- alertas.

## Estados de carga recomendados

- `borrador`: falta revisar.
- `realizado`: show hecho, aun puede faltar rendicion.
- `rendido`: alguien rindio caja.
- `aprobado`: Ruben reviso.
- `cerrado`: sin saldos vivos.
- `cerrado_con_cuenta_corriente`: el show esta claro, pero queda saldo vivo.
- `observado`: hay diferencia o caso raro pendiente.
- `historico`: importado o aceptado por control.
- `cancelado`: no se hizo.
- `no_cobrado`: se hizo o estaba previsto, pero no genero cobro.

## Procedimiento diario para ponerse al dia

1. Separar shows del dia por tipo:
   - simple;
   - simple con regla avanzada;
   - varios artistas;
   - Caserio;
   - historico/dudoso.
2. Cargar primero los simples en `Booking Indyana`.
3. Probar los avanzados en `Carga de Shows laboratorio`.
4. Si el avanzado esta validado, cargarlo en la pantalla viva correspondiente.
5. Si queda saldo, no forzar cierre: marcarlo y documentarlo.
6. Adjuntar o pegar links de comprobantes.
7. Al final del dia, generar reporte de control de shows.

## Criterio para habilitar guardado del laboratorio

No habilitar hasta que pasen estos casos:

- show simple sin seña;
- show simple con seña a Indyana;
- show simple con seña al artista;
- G Sony solo;
- Candu + G Sony;
- Virrshi con recupero;
- Aneley con cuenta corriente;
- historico 0/0;
- dolares con tipo de cambio.

Cuando pase, el guardado nuevo debe escribir en la misma estructura viva sin romper `Booking Indyana`.
