# Aneley - seguimiento de caja

## Marca temporal 2026-05-08

Para poder avanzar hoja por hoja contra el Drive de Aneley, se toma una
marca temporal sobre las hojas ya cargadas desde `CATAMARCA 117` hasta
`BYSIDE 109`.

Como esas hojas no traian aclaraciones especificas de caja/cobro directo,
se asume provisoriamente que esos saldos estan saldados o rendidos fuera de
la informacion visible. Esta marca es solo operativa y debe verificarse contra
el Drive antes de cerrar la cuenta corriente.

Hojas incluidas en esta marca:

- `CATAMARCA 117`
- `AEROPUERTO 28`
- `ZARATE Y HEMISFERIO 98`
- `NEUQUEN 1 SHOW`
- `CORDOBA 69`
- `BYSIDE 109`

Pendiente:

- Confirmar contra Drive si efectivamente estan saldadas.
- Si estan saldadas, registrar los movimientos de caja correspondientes.
- Si no estan saldadas, dejar balance abierto en cuenta corriente.
- Retirar esta marca temporal cuando quede conciliado.

Desde `BUENOS AIRES 269` en adelante se empieza a seguir la caja de forma
explicita con movimientos reales recibidos por Indyana u otros responsables.

## Validacion cuenta corriente - tramo inicial

Validado con Ruben el 2026-05-19.

| Bloque | Saldo del bloque | Cuenta corriente acumulada |
| --- | ---: | ---: |
| Byside / Apolo 10/9 | 0 | 0 |
| Buenos Aires 26/9 | -125.600 | -125.600 |
| Mouche 11/10 | -66.000 | -191.600 |
| Pentos 24/10 | +171.000 aplicado contra saldo previo | -20.600 |

Lectura al cierre de `Pentos 24/10`:

- Aneley / manager tiene 20.600 a favor.
- Pentos no fue pago nuevo de dinero.
- Pentos fue una compensacion contra saldo previo.

Por este motivo, cualquier vista financiera debe distinguir entre:

- efectivo realmente recibido por Indyana;
- compensaciones contra cuenta corriente previa;
- saldo vivo de la cuenta corriente.

## Criterio mayo 2026 - cuenta corriente e inversion

El saldo vivo validado de Aneley/manager contra Indyana, luego de cargar los
shows y antes de aplicar gastos pagados por el manager, es:

- saldo booking a favor de Indyana: `1.532.770`

Este saldo corresponde a la cuenta corriente de booking: shows liquidados,
senas, pagos recibidos y diferencias de caja. No debe mezclarse con la
rentabilidad del artista ni con inversiones de la compania.

En mayo aparece un proyecto nuevo:

- proyecto: `Set Padel`
- destino/contenido: streaming `Para el Mundo`
- criterio de negocio: inversion de Indyana 100%

Algunos gastos de ese proyecto fueron pagados por el padre/manager de Aneley.
Como son inversion de Indyana, no son gastos recuperables del artista. Si el
manager los pago, se registran como credito a su favor y reducen lo que debe
rendir de la cuenta corriente de booking.

Detalle inicial informado:

- `PARA FEDE UBER DE FOTOGRAFO`: 47.000
- `BASKSTAGE`: 40.000
- `FOTOGRAFA`: 100.000
- `5 MUSICOS PROGRAMA`: 200.000
- `UBER EQUIPO`: 80.000
- `COMIDA`: 95.000

Total pagado por manager para proyecto `Set Padel`: `562.000`.

Lectura de cuenta:

- saldo booking a favor de Indyana: `1.532.770`
- credito por inversion Indyana pagada por manager: `562.000`
- saldo neto estimado a rendir por manager: `970.770`

Importante: estos gastos no deben entrar como gastos de show. Deben quedar en
cuenta corriente/proyecto con trazabilidad, porque explican por que el manager
descuenta importes del saldo que debe rendir.
