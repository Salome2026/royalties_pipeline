# Finanzas de artista - modelo propuesto

## Objetivo

Crear una capa financiera comun para ver, cargar y auditar la relacion economica entre Indyana/VPO, artistas, proyectos y terceros.

Esta capa no reemplaza booking ni regalias. Los usa como origenes de informacion.

## Regla principal

No mezclar negocio, caja y cuenta corriente.

Cada movimiento debe poder responder tres preguntas distintas:

1. Que negocio lo genero?
2. Quien pago o cobro la plata real?
3. Genera saldo entre Indyana y el artista/tercero?

## Decision vigente: ledger financiero v1

El ledger financiero oficial v1 es una capa canonica de lectura, no una copia
duplicada de todas las tablas operativas.

Motivo:

- booking ya es fuente de verdad para shows, liquidacion, caja y saldos de
  shows;
- `finance_staging_movements` es fuente de verdad para gastos, inversiones,
  adelantos, pagos y movimientos cargados manualmente;
- `finance_recovery_applications` es fuente de verdad para recuperos aplicados
  contra gastos recuperables;
- duplicar todo en otra tabla antes de cerrar el modelo podria crear dos
  verdades distintas.

Por eso, el ledger v1 se construye leyendo las fuentes reales y normalizando
cada movimiento en una fila financiera comun con referencia de origen.

Cada fila del ledger debe indicar:

- fecha;
- artista;
- area de negocio;
- tipo de ledger;
- proyecto;
- concepto;
- origen (`booking`, `finance_movement`, `recovery_application`, etc.);
- id de origen;
- importe ARS;
- impacto en cuenta corriente;
- impacto en caja;
- impacto en resultado/inversion;
- impacto en recuperables;
- estado/control;
- notas.

El ledger v1 no debe esconder la fuente. Si una fila nace de un show, debe
mostrar el show. Si nace de un gasto, debe mostrar el movimiento financiero. Si
nace de un recupero, debe mostrar desde que show o fuente se aplico.

Mas adelante, cuando el flujo de aprobacion este validado, se podra agregar un
ledger posteado/inmutable. Ese ledger posteado no reemplazara las fuentes:
sera una foto contable cerrada con control de auditoria.

## Tipos de ledger v1

### `booking_account_current`

Saldos vivos que salen de booking.

Ejemplos:

- artista/manager debe a Indyana;
- Indyana debe al artista;
- saldo de show no conciliado.

Esto no es resultado del show. Es cuenta corriente.

### `booking_venue_receivable`

Deuda de boliche/cliente.

No debe mezclarse con la cuenta corriente del artista, aunque pueda aparecer en
la misma pantalla para control operativo.

### `finance_investment`

Gastos e inversiones cargados en movimientos financieros.

Ejemplos:

- DJ set;
- videoclip;
- marketing;
- estreno;
- gasto de proyecto.

Puede afectar resultado/inversion de Indyana sin generar deuda directa del
artista.

### `finance_account_current`

Movimientos financieros manuales que si generan cuenta corriente directa.

Ejemplos:

- adelanto;
- prestamo;
- pago pendiente entre Indyana y artista;
- gasto pagado por un tercero que Indyana debe reconocer.

### `recoverable_origin`

Gasto recuperable abierto.

No es automaticamente deuda directa del artista. Depende de su metodo:

- antes del split;
- despues del split;
- cuenta corriente directa;
- regalias;
- manual.

### `recoverable_application`

Aplicacion real de recupero contra un gasto recuperable.

Debe indicar fuente y destino:

- desde que show, regalia o pago se recupero;
- contra que movimiento/proyecto se aplico;
- importe;
- metodo.

### `legacy_audit`

Solo auditoria historica de tablas viejas.

No debe mostrarse como movimiento financiero vigente ni como recupero real. Si
un dato legacy se valida, debe migrarse o vincularse a una fuente canonica
actual.

## Reglas visuales de Finanzas Artista

La pantalla de Finanzas Artista debe separar vistas:

1. **Ledger financiero**: lectura canonica consolidada.
2. **Cuenta booking**: saldos vivos de shows.
3. **Proyectos / inversiones**: resultado e inversion por proyecto.
4. **Recuperables**: origen, aplicaciones y saldo.
5. **Movimientos**: staging/carga manual.
6. **Auditoria vieja**: legacy, solo para control tecnico.

La palabra `legacy` no debe usarse para gastos reales solo porque sean viejos.
Un gasto viejo validado puede ser historico, pero no legacy. Legacy significa
fuente vieja de apoyo que todavia no es canonica.

## Capas separadas

### 1. Booking

Booking sigue siendo el modulo de shows.

Maneja:

- shows simples;
- liquidaciones compuestas;
- Caserio;
- cachet pactado;
- cachet cobrado;
- gastos de show;
- splits;
- comisiones;
- senas;
- rendiciones;
- cierre operativo.

Si un show no cierra en caja o queda saldo entre artista/manager e Indyana, booking debe generar un movimiento hacia la cuenta corriente, pero no ser la cuenta corriente completa.

### 2. Regalias

Regalias sigue siendo el modulo de ingresos digitales.

Maneja:

- statements;
- distribuidoras;
- transaction month;
- statement period;
- reportes de royalties;
- pagos futuros a artistas.

Mas adelante, si hay adelantos o recuperables contra digitales, regalias puede generar o aplicar movimientos contra la cuenta corriente.

### 3. Finanzas de artista

Es la capa nueva.

Maneja:

- cuenta corriente por artista;
- inversiones de Indyana;
- gastos recuperables;
- recuperos parciales;
- adelantos/prestamos;
- gastos pagados por terceros;
- proyectos;
- comprobantes;
- estado de control.

## Conceptos que no deben mezclarse

### Cuenta corriente

Responde:

> Quien le debe a quien?

Ejemplos:

- Indyana cobro una sena que correspondia al artista.
- El artista cobro mas de lo que le correspondia.
- El manager pago un gasto que correspondia a Indyana.
- Indyana dio un adelanto.
- Quedo un saldo de show sin rendir.

### Resultado del artista

Responde:

> Cuanto genero y cuanto invertimos en este artista?

Ejemplos:

- ingresos de booking para Indyana;
- ingresos digitales;
- videoclips;
- marketing;
- DJ sets;
- produccion;
- viajes;
- gastos asumidos por la productora.

Un artista puede tener cuenta corriente en cero y resultado negativo para Indyana.

### Recuperables

Responden:

> De un gasto que Indyana pago, cuanto se espera recuperar, por que via y cuanto falta?

Ejemplo:

- Indyana paga un DJ set de 500.000;
- se decide que es recuperable 70/30;
- cada show puede recuperar una parte;
- el saldo pendiente queda vivo hasta cerrarse.

## Entidades propuestas

### `finance_projects`

Proyectos o centros de costo.

Ejemplos:

- Set Padel;
- Para el Mundo;
- DJ Set Virrshi;
- Partido de la Costa;
- Campana El Motorcito;
- Video Super Junte.

Campos principales:

- proyecto;
- artista principal;
- artistas relacionados;
- area de negocio;
- presupuesto;
- estado;
- notas.

### `finance_staging_movements`

Entrada cruda o pendiente de control.

Sirve para cargar informacion vieja de Excel, WhatsApp, comprobantes o carga manual sin impactar saldos oficiales.

Estados:

- pendiente_control;
- controlado_inversion_indyana;
- controlado_recuperable;
- controlado_adelanto;
- controlado_cuenta_corriente;
- descartado;
- dudoso.

Regla de inviolabilidad operativa:

- mientras el movimiento esta en `borrador` o `pendiente_control`, se puede editar desde la web;
- cuando pasa a `aprobado`, `aplicado` o `anulado`, queda bloqueado;
- si despues aparece un error, no se pisa el movimiento original: se carga un nuevo movimiento de correccion, ajuste, recupero o anulacion;
- la base de datos puede corregirse manualmente solo como operacion excepcional de mantenimiento.

### `finance_ledger_entries`

Ledger oficial.

Solo recibe movimientos controlados/aprobados o movimientos generados automaticamente por modulos confiables como booking cerrado.

Cada entrada debe guardar:

- fecha;
- artista;
- proyecto;
- area;
- categoria;
- concepto;
- origen;
- importe original;
- moneda;
- tipo de cambio;
- importe ARS;
- importe USD;
- impacto cuenta corriente;
- impacto resultado;
- impacto caja;
- estado;
- referencia a comprobante;
- notas.

### `finance_recoverables`

Gastos recuperables abiertos.

Campos:

- artista;
- proyecto;
- gasto origen;
- importe original;
- parte recuperable;
- porcentaje artista;
- porcentaje Indyana;
- metodo de recupero;
- fuente permitida;
- recuperado acumulado;
- saldo pendiente;
- estado.

### `finance_recovery_applications`

Aplicaciones de recupero.

Cada vez que un show, regalia o pago manual recupera algo, se registra aca.

Campos:

- recoverable_id;
- origen de recupero;
- show_id o statement/report;
- importe aplicado;
- fecha;
- notas.

## Origenes de movimientos

Los movimientos pueden venir de:

- booking;
- regalias;
- carga manual;
- importacion historica;
- ajuste aprobado;
- pago/cobro de caja;
- recupero.

## Recuperables: metodo y costo economico

Un gasto recuperable no siempre es una deuda directa del artista.

Cada movimiento recuperable debe guardar dos lecturas separadas:

1. **Recupero de caja**: cuanto dinero vuelve o se aplica a favor de Indyana.
2. **Costo economico**: que parte del gasto soporta el artista y que parte soporta Indyana segun el contrato o la regla del proyecto.

Metodos esperados:

- `before_split`: se descuenta antes del split del show. Indyana puede recuperar el 100% de caja aplicada, pero el costo economico se reparte segun el split del show. Ejemplo Virrshi: si se recuperan 100 antes de un split 70/30, economicamente el artista soporta 70 e Indyana 30.
- `after_split`: se descuenta despues del split, normalmente desde el pago del artista.
- `direct_account`: genera o reduce una cuenta corriente directa entre artista e Indyana.
- `royalties`: se recupera contra regalias digitales futuras.
- `manual`: caso especial que necesita aplicacion o ajuste controlado.

Regla core:

- No inferir deuda del artista solo porque `recoverable = true`.
- Si el recupero es `before_split`, el movimiento queda como recuperable de proyecto y su aplicacion futura debe indicar desde que show, regalia o pago se recupero.
- La cuenta corriente solo debe moverse cuando haya un saldo real entre partes o una aplicacion aprobada.

## Maquetado de pantalla

Nombre sugerido:

`Finanzas Artista`

### Vista 1 - Resumen

Selector de artista.

Tarjetas:

- saldo cuenta corriente;
- saldo booking;
- adelantos/prestamos;
- recuperables abiertos;
- inversion Indyana;
- ingresos Indyana por booking;
- ingresos digitales estimados;
- resultado neto Indyana.

### Vista 2 - Cuenta corriente

Tabla de movimientos que explican quien debe a quien.

Columnas:

- fecha;
- origen;
- concepto;
- proyecto;
- debe artista;
- debe Indyana;
- saldo;
- estado;
- comprobante;
- notas.

### Vista 3 - Inversiones y gastos

Tabla economica, no necesariamente deuda.

Columnas:

- fecha;
- area;
- proyecto;
- categoria;
- concepto;
- pagado por;
- importe;
- recuperable;
- estado control;
- impacto resultado;
- notas.

### Vista 4 - Recuperables

Lista de recuperables abiertos y cerrados.

Columnas:

- proyecto;
- gasto origen;
- total;
- recuperable artista;
- asumido Indyana;
- recuperado;
- pendiente;
- fuente de recupero;
- estado.

### Vista 5 - Proyectos

Resumen por proyecto.

Columnas:

- proyecto;
- artista;
- area;
- presupuesto;
- gasto real;
- recuperado;
- saldo;
- estado.

### Vista 6 - Carga

La carga debe empezar simple y abrir campos segun el tipo.

Campos iniciales:

- artista;
- fecha;
- tipo de movimiento;
- proyecto;
- area;
- categoria;
- concepto;
- importe;
- moneda;
- tipo de cambio;
- quien pago;
- comprobante/notas.

Tipos de movimiento:

- inversion Indyana;
- gasto recuperable;
- adelanto/prestamo;
- ajuste cuenta corriente;
- pago/cobro;
- recupero;
- dato historico pendiente.

## Reglas de impacto

### Inversion Indyana

- afecta resultado del artista;
- puede afectar caja Indyana;
- no genera deuda del artista salvo que se marque recuperable;
- si lo pago un tercero, genera credito contra Indyana.

### Gasto recuperable

- afecta resultado;
- crea recuperable abierto;
- no se descuenta hasta que haya aplicacion de recupero;
- puede recuperarse por booking, digitales o manual.

### Adelanto o prestamo

- afecta cuenta corriente;
- puede recuperarse contra booking, digitales o pago manual;
- no es gasto de show.

### Saldo de booking

- nace desde un show cerrado o cerrado con cuenta corriente;
- no redefine el resultado del show;
- vive en cuenta corriente hasta que se pague, compense o ajuste.

## Casos guia

### Virrshi

DJ sets pagados por Indyana.

Pueden ser:

- inversion asumida;
- recuperable 70/30;
- recupero antes del split;
- recupero contra parte artista.

Cada recupero debe bajar un saldo abierto y quedar vinculado al show.

### Aneley

Manager externo maneja caja y paga gastos de Indyana.

Un gasto pagado por Dami puede:

- bajar lo que Dami debe por booking;
- aumentar la inversion de Indyana en el proyecto;
- no ser gasto del show.

### G Sony

Puede tener terceros/socios externos.

Eso no es excepcion contable; es una liquidacion de participantes, pero los saldos finales deben alimentar cuenta corriente solo cuando correspondan a Indyana/artista.

## Reglas de seguridad

- No crear movimientos oficiales sin estado controlado.
- No duplicar movimientos de booking como si fueran manuales.
- No mezclar gasto de show con gasto de proyecto.
- No borrar historico: corregir con ajuste o anular con traza.
- No usar texto libre para artistas, proyectos, areas o categorias en la version final.
- No cerrar un recuperable sin registrar como se recupero.

## Fases de implementacion

### Fase 1 - Maqueta y lectura

- Crear pantalla de solo lectura por artista.
- Mostrar saldos derivados de booking.
- Mostrar inversiones/gastos staging si existen.
- No impactar ledger.

### Fase 2 - Staging manual

- Permitir cargar gastos y movimientos pendientes.
- Todo entra como pendiente de control.
- Sin impacto oficial automatico.

### Fase 3 - Control y aprobacion

- Aprobar movimientos.
- Generar ledger oficial.
- Crear recuperables abiertos cuando corresponda.

### Fase 4 - Aplicacion de recuperos

- Desde booking, elegir recuperable abierto.
- Aplicar recupero parcial o total.
- Actualizar saldo pendiente.

### Fase 5 - Reportes

- Cuenta corriente por artista.
- Resultado por artista.
- Proyectos.
- Recuperables.
- Saldos contra booking y digitales.
