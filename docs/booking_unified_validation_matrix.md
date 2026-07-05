# Booking VPO - Matriz de validacion para carga unificada

Fecha de trabajo: 2026-05-15

Esta matriz sirve para validar el futuro flujo unificado de booking antes de modificar la pantalla actual. Cada caso debe poder cargarse en el nuevo flujo sin perder informacion, sin hacer cuentas manuales innecesarias y sin romper los reportes.

## Columnas de validacion

Para cada caso se revisa:

- Datos que carga el usuario.
- Calculos que debe hacer el sistema.
- Caja esperada.
- Saldos posibles.
- Si genera show interno/hijo.
- Si impacta en Indyana ganado.
- Si impacta en base comisionable.
- Condicion de cierre.
- Reportes afectados.

## Matriz

| Caso | Datos que carga el usuario | Calculos del sistema | Caja esperada | Saldos posibles | Hijo interno | Indyana ganado | Base comisionable | Cierre | Reportes afectados |
|---|---|---|---|---|---|---|---|---|---|
| Show simple 70/30 | Fecha, artista, venue, cachet, gastos, split 70/30, pagos/rendicion | Neto = cobrado - gastos; artista 70%; Indyana 30% | Caja artista + caja Indyana segun split | Artista, Indyana, boliche | No | Si | Si, salvo marca no comisionable | Cierra si boliche, artista e Indyana estan saldados | Shows, resumen booking, comisiones |
| Show simple 60/40 | Igual al show simple, split 60/40 | Neto y split 60/40 | Caja artista + Indyana | Artista, Indyana, boliche | No | Si | Si, salvo marca no comisionable | Igual show simple | Shows, resumen booking, comisiones |
| Show 100/0 | Artista, cachet, sin participacion Indyana | Todo al artista; Indyana 0 | Caja artista o salida completa | Artista/boliche | No | No o 0 | No | Cierra si el pago real coincide | Shows, control historico |
| Show no cobrado | Cachet pactado, cobrado 0, estado no cobrado/cancelado | Deuda boliche = pactado | No deberia generar caja cobrada | Boliche | No | No hasta cobrar | No | Queda pendiente u observado | Agenda/control, deuda boliche |
| Show historico 0/0 | Fecha, artista, venue, importes 0, estado historico/revision | No calcula ganancias | Sin caja | Revision pendiente | No | 0 | No definido | Historico, no bloquea | Control historico |
| Show con seña cobrada por Indyana | Cachet, gastos, split, movimiento caja Indyana | Calcula cuanto debia recibir Indyana y cuanto ya recibio | Seña Indyana + saldo PM/boliche | Puede deberse al artista si seña supera Indyana | No | Si | Segun regla | Cierra si caja total y saldos cierran | Shows, caja, cuenta corriente |
| Show con seña cobrada por artista | Cachet, gastos, split, movimiento caja artista | Calcula si artista debe rendir o si se compensa contra su pago | Seña artista + eventual saldo Indyana | Artista puede deber a Indyana o Indyana puede deber artista | No | Si | Segun regla | Cierra si cuenta entre artista/Indyana queda saldada o registrada | Shows, caja, cuenta artista |
| Show con deuda parcial de boliche | Cachet pactado, cobrado real menor, motivo | Base operativa puede usar cobrado real; deuda boliche se mantiene | Caja sobre cobrado real | Boliche pendiente | No | Segun cobrado o segun regla definida | Comisionable solo sobre Indyana realmente ganado/cobrado, salvo decision contraria | Cierre parcial/observado | Deuda boliche, shows |
| Virrshi con recupero DJ set | Show normal + ajuste/recupero artista | Separa show de recupero; recupero puede repartir 70/30 | Caja show + recupero aplicado | Cuenta artista/productora | No | Si + parte recupero Indyana si aplica | Depende: show puede ser comisionable, recupero no necesariamente | Cierra show aunque cuenta recupero siga abierta si se registra | Shows, cuenta artista, recuperos |
| Aneley con manager/familia | Shows, caja informada por manager, pagos a equipo/Indyana | Calcula show y cuenta corriente externa | Puede manejar caja externa | Saldo con manager/familia | No | Si | Segun regla, normalmente si es booking propio | Cierre show separado de cuenta corriente | Cuenta corriente, shows, resumen artista |
| G Sony solo | Cachet, gastos, comision Facha %, split G Sony/Indyana/Fede | Descuenta Facha; reparte base entre G Sony, Indyana y tercero externo | Caja artista, Indyana y tercero si aplica | Tercero, artista, Indyana | No | Si | Generalmente no comisionable si la comision se resolvio internamente | Cierra si G Sony, Indyana y tercero estan conciliados | Shows, terceros, comisionabilidad |
| Candu + G Sony | Evento bruto, gastos generales, comision directa 10%, lineas Candu y G Sony | Madre calcula base; comision directa se reparte; G Sony incorpora parte; genera hijos | Caja madre + cajas hijas | Madre, hijos, tercero, Indyana | Si, Candu y G Sony | Si por cada hijo | Normalmente no comisionable si ya hubo comision directa | Cierra madre y/o hijos segun caja y saldos | Liquidaciones compuestas, shows, comisiones |
| Comision directa evento | Porcentaje/importe, beneficiarios, destino directo o incorporar a linea | Calcula salida directa o ajuste de base | Si caja VPO maneja la salida, debe aparecer | Beneficiario/tercero | No necesariamente | Puede reducir o redistribuir Indyana | No vuelve a comisionar si ya es comision directa | Cierra cuando la salida esta registrada o marcada externa | Comisiones, caja |
| Tercero externo no caja VPO | Nombre, rol, porcentaje/importe, caja no VPO | Baja la parte disponible para artista/Indyana si corresponde | No ingresa ni sale caja VPO | No deberia generar saldo VPO | No | Indyana neto despues de tercero | Segun regla | Cierra si se marca externo/no caja VPO | Terceros, shows |
| Tercero externo caja VPO | Nombre, rol, importe/porcentaje, caja VPO | Calcula importe y lo espera como salida de caja | Salida a tercero | Tercero pendiente | No | Indyana segun regla | Segun regla | Cierra cuando se paga tercero | Caja, terceros |
| Caserio sin artistas VPO | Bruto, gastos, artistas externos | Calcula caja a rendir a Caserio | Caja Caserio | Caserio pendiente | No | No directo | No | Cierra cuando se rinde a Caserio | Caserio |
| Caserio con artista VPO | Bruto Caserio, artistas externos, artistas VPO, gastos | Calcula caja Caserio y show interno VPO | Caja Caserio + caja Indyana artista VPO | Caserio, artista VPO, Indyana | Si | Si por artista VPO | Segun regla artista VPO | Cierra Caserio y show interno por separado | Caserio, shows, comisiones |
| Gasto general de evento | Categoria, concepto, importe | Baja base general antes de lineas | Salida o gasto informado | Caja si VPO lo pago | No | Reduce Indyana indirectamente | Reduce base comisionable indirectamente | Cierra si caja/gasto documentado | Gastos, rentabilidad |
| Gasto propio artista | Linea artista, categoria, concepto, importe | Baja base de esa linea | Salida si VPO lo pago | Artista/Indyana segun regla | No | Reduce Indyana de esa linea | Reduce o no base comisionable segun regla | Cierra con linea | Shows, artista |
| Gasto artista recuperable | Artista, proyecto, monto, recuperable, porcentaje artista/Indyana | Genera cuenta corriente recuperable | Salida inicial VPO; recuperos posteriores | Cuenta artista | No | No es show, pero afecta cuenta | Normalmente no comisionable | Cierra cuando se recupera o se condona | Cuenta artista, recuperos |
| Recupero aplicado en show | Linea artista, gasto recuperable origen, importe, tipo de recupero | Baja saldo recuperable; segun tipo puede afectar base antes del split o solo deuda artista | Puede entrar como recupero a caja Indyana | Saldo recuperable artista/Indyana | No | No debe mezclarse con Indyana booking salvo tipo antes del split | Normalmente no comisionable | Show puede cerrar si recupero queda trazado | Cuenta artista, recuperos, caja |
| Pago posterior de deuda de boliche | Show con deuda abierta, fecha de cobro, importe, metodo, comprobante | Aplica cobro contra deuda de boliche sin recalcular show | Entra caja real posterior | Baja `venue_balance_amount` o entrada operativa equivalente | No | No cambia Indyana ganado original | No cambia base comisionable original salvo regla aprobada | Cierra deuda si queda en 0 | Cuenta booking del show, finanzas artista |
| Reintegro de artista por cobro de mas | Show con saldo a favor de Indyana, fecha, importe, metodo, comprobante | Aplica reintegro contra saldo del artista sin modificar pago original | Entra caja real posterior | Baja saldo a favor de Indyana | No | No cambia resultado del show | No cambia base comisionable | Cierra cuenta si queda en 0 | Cuenta corriente artista, cuenta booking del show |
| Pago posterior al artista | Show con saldo a favor del artista, fecha, importe, metodo, comprobante | Aplica pago contra saldo a favor del artista sin modificar liquidacion original | Sale caja real posterior | Baja deuda de Indyana al artista | No | No cambia resultado del show | No cambia base comisionable | Cierra cuenta si queda en 0 | Cuenta corriente artista, cuenta booking del show |
| Compensacion entre shows | Dos saldos abiertos del mismo artista/tercero, importe, nota | Aplica un saldo contra otro con trazabilidad doble | Sin caja nueva si es compensacion pura | Baja ambos saldos segun direccion | No | No cambia resultados originales | No cambia base comisionable | Cierra o deja parcial segun importe | Cuenta corriente, auditoria |

## Reglas de aceptacion por caso

### Regla 0 - La hija es fuente de verdad

Cuando un evento genera shows hijos, esos hijos son shows operativos reales.

La madre guarda contexto, reglas y sugeridos. La hija guarda gastos propios, terceros, pagos, caja y cierre real.

Por lo tanto:

- Editar una hija debe verse reflejado al abrir la madre.
- Editar una madre no debe borrar automaticamente gastos, terceros o pagos reales de la hija.
- Aplicar sugeridos de madre a hijas debe ser una accion explicita.
- Si madre e hija difieren, el sistema debe mostrar alerta y no esconder la diferencia.

### Regla 0.1 - Diferencias madre vs hija

Si hay diferencia entre madre e hija, gana la hija como realidad operativa.

Tipos de diferencia:

- Base distinta.
- Gastos distintos.
- Terceros distintos.
- Caja distinta.
- Estado distinto.
- Comisionabilidad distinta.

Acciones disponibles:

- `Aceptar hija como realidad`: recalcula la madre desde hijas.
- `Aplicar sugerido madre a hija`: requiere preview y confirmacion.
- `Mantener diferencia observada`: deja trazabilidad sin pisar datos.

### Regla A - La caja no reemplaza la liquidacion

El sistema calcula lo que deberia pasar. La caja registra lo que efectivamente paso. Si difieren, aparece saldo o alerta.

### Regla B - Cierre por capas

Un caso puede estar:

- Abierto.
- Observado.
- Cerrado.
- Cerrado con cuenta corriente.
- Historico pendiente.
- Historico revisado.

El cierre se evalua por capas:

1. Boliche / cliente.
2. Caja del show.
3. Liquidacion de artistas y terceros.
4. Cuenta corriente.

Un evento o show no debe mostrarse simplemente como cerrado si tiene cuenta corriente viva. En ese caso debe mostrarse como `cerrado con cuenta corriente`.

No usar un unico "cerrado" para todo si hay varias capas.

### Regla B.1 - Pagos posteriores no reescriben shows

Si un saldo se salda despues del show, el sistema debe registrar una aplicacion o
movimiento de cuenta corriente. No debe editar silenciosamente la caja original del
show porque se perderia la historia de lo que paso en el evento.

Ejemplos:

- boliche pago la deuda dias despues;
- artista reintegro plata cobrada de mas;
- Indyana pago una diferencia pendiente al artista;
- un show compenso el saldo de otro show.

El show puede pasar a `cerrado` o `cerrado con cuenta corriente saldada`, pero la
liquidacion original debe seguir auditable.

### Regla B.2 - Verde significa sin saldo vivo

Un show con saldo abierto no debe verse verde aunque su liquidacion este clara.

Un show puede verse verde despues de haber tenido saldo si existe una aplicacion
posterior que lo salda:

- pago posterior;
- reintegro;
- compensacion con otro show;
- ajuste aprobado.

La historia del cierre debe quedar visible como etiqueta o detalle, pero no debe
mantener alerta si la cuenta corriente quedo en cero.

### Regla C - Indyana ganado vs base comisionable

Toda linea que genere Indyana debe responder:

- Cuanto gano Indyana.
- Cuanto de eso es comisionable.
- Por que es comisionable o no.

### Regla D - Historico no define futuro

Splits raros y 0/0 del historico se conservan, pero no se usan para disenar reglas operativas futuras salvo que Ruben los valide.

## Casos prioritarios para probar primero

1. G Sony solo con Facha y Fede.
2. Candu + G Sony Berlin/Ramon Castillo.
3. Virrshi con recupero/set y caja.
4. Aneley con cuenta manager/familia.
5. Laalo/Gusty show simple con seña.
6. Caserio con Facu/Lazer.
7. Historico 0/0.

## Pendientes de definicion

- Si una madre cerrada debe poder cerrar hijos automaticamente o solo sugerirlo.
- Si los hijos reciben caja automaticamente desde la madre o si siempre se carga por linea.
- Exactitud de cierre: la caja debe cerrar exacta; redondeo solo visual, no operativo.
- Como visualizar cuenta corriente abierta aunque el show este cerrado.
- Como marcar "historico revisado" vs "historico pendiente".
- Implementar la tabla operativa `booking_current_account_entries` como destino de
  saldos nuevos al aprobar/cerrar shows, manteniendo saldos derivados solo como
  transicion/auditoria.

## Regla E - Sin tolerancia automatica por redondeo

Internamente la caja debe cerrar con diferencia exacta 0.

- Los totales visuales pueden redondearse.
- Los sugeridos y botones deben mostrar centavos si existen.
- Usar sugerido carga el valor exacto.
- Si se carga un entero y el sugerido era con centavos, queda diferencia.
- Una diferencia chica puede marcarse observada con nota, pero no cerrar automaticamente.
