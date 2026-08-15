# Booking System Design

## Objetivo

Agregar a VPO Corp un modulo de booking que permita controlar shows, rendiciones,
caja, comisiones, gastos, adelantos y cuenta corriente de artistas sin mezclar esos
conceptos en una sola planilla.

El sistema de royalties sigue separado. Booking puede convivir con royalties en una
cuenta corriente consolidada por artista, pero no debe reutilizar automaticamente la
logica de FX ni los pipelines de distribuidoras.

## Principio Central

El show calcula resultado. La caja registra movimientos reales. La cuenta corriente
consolida quien le debe a quien.

Separar estas capas evita errores comunes:

- tratar un cachet esperado como dinero cobrado;
- tratar la parte del artista como pago realizado;
- pagar comisiones comerciales sobre una base incorrecta;
- descontar gastos del show cuando en realidad pertenecen a label o royalties;
- perder trazabilidad de senas, efectivo, transferencias y comprobantes.

## Capas Del Modelo

### Agenda

La agenda es el origen operativo del show. Puede venir de una planilla rudimentaria al
principio y despues transformarse en una vista propia.

Campos esperados:

- fecha;
- artista o artistas;
- venue/evento;
- ciudad;
- cachet pactado;
- moneda;
- estado del show;
- tour manager asignado;
- vendedor o responsable comercial;
- contacto;
- observaciones.

La agenda no debe ser la fuente contable final. Debe crear o prellenar fichas de show.

### Evento Madre

Un evento madre representa una unidad de negocio mas amplia que puede contener varios
shows o prestaciones.

Ejemplos:

- El Caserio;
- una fiesta en sociedad;
- un festival propio;
- un evento producido por VPO con artistas internos y externos.

Un evento madre puede tener ingresos, gastos, socios y resultado propio. Si dentro del
evento toca un artista de VPO, ese cachet tambien puede generar un show interno de
booking.

Ejemplo:

- Evento madre: El Caserio fecha X.
- Gasto del evento: cachet Virrshi.
- Show booking vinculado: Virrshi cobra cachet y se liquida segun regla VPO.

Esto no es duplicar mal: es el mismo hecho visto desde dos roles distintos.

### Show

Un show es una prestacion artistica concreta. Puede existir solo o estar vinculado a un
evento madre.

Campos esperados:

- show_id;
- event_id opcional;
- fecha;
- artista principal;
- nombre del evento;
- venue/ciudad;
- cachet bruto;
- moneda original;
- tipo de cambio booking;
- cachet en ARS;
- cachet en USD;
- estado: programado, rendido, en revision, aprobado, cerrado, observado;
- regla de liquidacion;
- tour manager;
- vendedor.

### Participantes

Un show no debe asumir un solo artista y un solo porcentaje. Debe permitir varios
participantes.

Tipos de participantes:

- artista propio;
- artista externo;
- productora;
- manager;
- vendedor;
- comisionista;
- socio;
- proveedor;
- tour manager.

Cada participante puede tener una regla:

- porcentaje sobre bruto;
- porcentaje sobre neto despues de gastos;
- porcentaje sobre share de productora;
- monto fijo;
- monto manual;
- no participa del resultado pero recibe un pago operativo.

### Ingresos

Ingresos posibles:

- cachet del show;
- sena;
- saldo cobrado en el lugar;
- sponsor;
- ingresos de puerta/barra si aplica;
- transferencia de socio;
- ajuste o recupero.

Cada ingreso debe guardar:

- monto original;
- moneda original;
- monto ARS;
- monto USD;
- tipo de cambio usado;
- fecha de tipo de cambio;
- medio de cobro;
- quien cobro;
- comprobante;
- estado de verificacion.

### Gastos

Los gastos pueden pertenecer a distintas areas y no todos se descuentan del mismo lugar.

Campos clave:

- artista;
- show_id opcional;
- event_id opcional;
- categoria: booking, label, digital, general;
- concepto;
- proveedor/beneficiario;
- monto original;
- moneda original;
- monto ARS;
- monto USD;
- comprobante;
- pagado por;
- aprobado por;
- descuento_aplica_a: show, royalties, cuenta_corriente, no_descuenta;
- metodo de recupero: inmediato, cuotas, manual, no_recuperable.

Ejemplos:

- sonido de show: booking, descuenta del show;
- videoclip: label, no descuenta del show, puede descontar de cuenta del artista;
- adelanto artista: cuenta corriente, puede recuperarse de royalties digitales;
- DJ set a descontar en partes: booking, recupero en cuotas o manual.

### Movimientos De Caja

La caja registra hechos de dinero, no calculos de resultado.

Ejemplos:

- productor pago una sena;
- tour manager cobro efectivo;
- tour manager pago sonido;
- tour manager pago al artista;
- tour manager rindio a VPO;
- VPO transfirio diferencia al artista;
- VPO recibio transferencia de socio.

Cada movimiento debe tener:

- fecha;
- tipo: ingreso, egreso, transferencia, ajuste;
- monto;
- moneda;
- medio: efectivo, transferencia, otro;
- pagador;
- receptor;
- responsable;
- comprobante;
- show/evento/artista relacionado;
- estado: borrador, enviado, aprobado, posteado.

### Rendicion Tour Manager

El tour manager no deberia resolver contabilidad compleja. Debe cargar hechos desde una
web mobile:

- cuanto cobro;
- cuanto pago;
- a quien pago;
- cuanto entrego a VPO;
- si pago al artista;
- comprobantes/fotos;
- notas;
- si considera que el caso es especial.

La rendicion entra como borrador o enviada. Recien impacta contablemente cuando se
aprueba.

Estados:

- draft;
- submitted;
- under_review;
- approved;
- posted;
- closed;
- rejected.

### Liquidacion

La liquidacion convierte ingresos, gastos, comisiones y reglas en importes asignados.

Debe guardar tanto el resultado como la explicacion:

- base usada;
- porcentaje aplicado;
- orden de aplicacion;
- participante beneficiario;
- monto resultante;
- notas.

Esto permite auditar por que un vendedor cobro sobre bruto, neto o share de productora.

## Reglas De Comision

Las comisiones comerciales no deben tener una unica base implicita.

Bases posibles:

- gross_revenue: cachet bruto;
- net_after_show_expenses: neto despues de gastos operativos;
- producer_share: parte de la productora;
- event_profit: resultado del evento madre;
- manual_amount: monto cargado manualmente.

Campos esperados:

- vendedor;
- porcentaje;
- base;
- antes_o_despues_de_gastos;
- aplica_a_artista;
- aplica_a_show;
- notas.

Esto corrige el problema actual donde a veces se paga comision sobre ingresos sin conocer
todavia los gastos reales del artista o del show.

## FX Booking

Booking necesita una logica FX separada de royalties.

Royalties usa tasas de cambio financieras/oficiales para normalizar statements.
Booking debe usar dolar blue Argentina, idealmente promedio entre compra y venta, o una
tasa manual acordada para el show.

Tabla sugerida:

- date;
- currency_from;
- currency_to;
- rate_type: blue_avg, manual, other;
- buy_rate;
- sell_rate;
- avg_rate;
- source;
- notes;
- created_at.

Cada movimiento debe guardar su tipo de cambio congelado:

- currency_original;
- amount_original;
- amount_ars;
- amount_usd;
- fx_rate;
- fx_rate_type;
- fx_rate_date;
- fx_source.

Regla: no recalcular historico automaticamente. Si se corrige una tasa, debe quedar
auditado.

## Casos Reales Detectados

### Show Simple 70/30

Ejemplo:

- cachet: 1.000.000 ARS;
- gastos: 300.000 ARS;
- neto: 700.000 ARS;
- artista: 70%;
- productora: 30%.

Resultado:

- artista: 490.000 ARS;
- productora: 210.000 ARS.

La caja puede diferir del resultado si hubo senas, pagos en destino o rendiciones
parciales.

### Dos Artistas Propios Con Reglas Distintas

Caso Sheet18:

- Candu se liquida con logica 70/30 sobre su resultado.
- G Sony se liquida 50/50.
- La mitad no artista de G Sony se divide entre productora y manager.
- Facha cobra una comision del 15% sobre una base especifica antes de repartir.

Conclusion: se necesita una liquidacion por bloques/pools, no una formula unica.

### Evento Madre Con Shows Internos

Caso El Caserio:

- El Caserio es un evento/sociedad.
- Tiene ingresos y gastos propios.
- Si toca un artista VPO, el cachet del artista es gasto para el evento madre.
- Ese mismo cachet es ingreso de booking para el artista VPO y debe liquidarse como show.

Se requiere event_id y shows vinculados.

### Vendedores

Caso EL COLO y otros:

- algunos vendedores cobran comision por venta del show;
- hoy a veces se descuenta antes de mostrar el neto al owner;
- la base de comision no siempre esta clara;
- puede estar mal pagar comision antes de conocer gastos reales.

Se requiere guardar base de comision y orden de aplicacion.

### Socios O Producciones Especiales

Caso Booking Mauro:

- ingresos;
- comision;
- sponsors;
- gastos USD;
- balance;
- reparto Mauro/Juanma con porcentajes variables.

Esto se parece a un evento/proyecto con profit split, no solo a booking artistico.

## Entidades Iniciales

Propuesta de tablas o datasets:

- booking_artists;
- booking_events;
- booking_shows;
- booking_show_participants;
- booking_income_items;
- booking_expense_items;
- booking_cash_movements;
- booking_commission_rules;
- booking_settlement_runs;
- booking_settlement_lines;
- booking_attachments;
- booking_fx_rates;
- artist_ledger_entries.

## MVP Propuesto

Primera etapa:

1. Ingestar planillas actuales como raw booking.
2. Modelar shows simples desde Ingresos/Egresos.
3. Crear reporte comparable al owner, pero separando bruto, gastos, comisiones y neto.
4. Documentar casos especiales sin automatizarlos todos.

Segunda etapa:

1. Web mobile de rendicion tour manager.
2. Bandeja de revision/aprobacion.
3. Adjuntos de comprobantes.
4. Generacion de movimientos aprobados.

Tercera etapa:

1. Motor de liquidacion flexible por bloques.
2. Cuenta corriente consolidada artista.
3. Integracion con royalties digitales para recupero de adelantos.
4. Agenda/calendario mejorado.

## Preguntas Abiertas

- Quienes pueden crear shows: agenda, admin, owner?
- Quienes pueden rendir: tour manager, admin, socio?
- Quien aprueba gastos y comprobantes?
- Las comisiones de vendedores deben calcularse sobre bruto, neto o share de productora?
- En que casos un gasto booking se recupera desde royalties digitales?
- Como se define si una tasa blue es automatica o manual?
- Que reportes mensuales necesita el owner en version minima?
