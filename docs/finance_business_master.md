# Finanzas VPO - documento rector

Fecha: 2026-05-26

Este documento manda sobre los documentos financieros mas tecnicos.

Objetivo: que Finanzas Artista sea simple para operar y suficientemente fuerte
para soportar booking, regalias, gastos, recuperables, proyectos y cuenta
corriente sin convertir la pantalla en contabilidad cruda.

## Principio central

El usuario carga hechos del negocio. El sistema calcula impactos.

El usuario no deberia elegir palabras como `ledger`, `account_effect`,
`source_type` o `recovery_method` salvo en una vista tecnica. Esas son
decisiones internas del sistema.

## Referencias externas revisadas

El patron comun en sistemas profesionales es:

- mostrar tableros claros de rentabilidad, costos e ingresos por proyecto;
- guardar movimientos detallados para auditoria;
- separar gastos recuperables, adelantos y pagos;
- no mostrar el ledger crudo como pantalla principal.

Referencias utiles:

- QuickBooks Projects / job costing: ver ingresos, costos y rentabilidad por
  proyecto.
  https://quickbooks.intuit.com/small-business/accounting/job-costing/
- Xero Projects: tablero de rentabilidad por proyecto.
  https://blog.xero.com/us/2020/09/profitability-at-a-glance-in-xero-projects/
- LabelGrid Accounting: expense ledger, recoupment y artist statements.
  https://labelgrid.com/features/accounting/
- Royalti.io: contratos, payouts, advances y recoupment.
  https://royalti.io/
- Eddy: royalty accounting con cost & advance recoupment.
  https://www.eddy.app/

## Traduccion a VPO

VPO tiene tres negocios conectados:

1. Booking.
2. Regalias digitales.
3. Inversiones/gastos de artistas y proyectos.

La pantalla de Finanzas Artista debe responder preguntas humanas:

- Como estoy con este artista?
- Nos debe plata o le debemos?
- Cuanto genero por booking?
- Cuanto invertimos?
- Cuanto falta recuperar?
- Que proyectos estan abiertos?
- Que movimientos explican el saldo?

## Que genera Booking

Booking ya esta bien encaminado. No hay que rehacerlo.

Booking debe generar solo dos impactos financieros:

### 1. Saldo de show

Cuando un show no cierra:

- el artista/manager nos debe;
- Indyana le debe al artista/manager;
- el boliche/cliente debe.

Eso alimenta cuenta corriente.

No cambia la liquidacion del show.

### 2. Recupero aplicado desde show

Cuando de un show se aparta plata para recuperar un gasto/proyecto:

- el show sigue cerrando como show;
- el recupero baja el saldo pendiente de un proyecto;
- debe quedar vinculado al gasto/proyecto que recupera;
- no se mezcla con ganancia de booking.

Ejemplo Virrshi:

- show cierra;
- se recuperan 100.000 de un DJ set;
- el proyecto DJ set baja su saldo pendiente;
- la cuenta corriente solo se mueve si ademas queda alguien debiendo plata.

Regla operativa actual:

- si el recupero se carga antes del split y a favor de Indyana, el usuario puede marcarlo como recupero imputable;
- el sistema debe aplicar ese importe contra el recuperable abierto mas viejo del artista, por orden cronologico FIFO;
- si no hay saldo recuperable abierto suficiente, el show no debe guardarse con una imputacion falsa;
- los movimientos historicos marcados como aplicados/anulados no participan del FIFO.

## Que genera Regalias

Hoy regalias alimenta reportes.

Mas adelante debera generar:

- ingresos digitales de Indyana;
- saldos a pagar a artistas;
- recuperos contra adelantos o gastos recuperables;
- estados de cuenta por periodo.

No se implementa ahora, pero la pantalla debe dejar lugar conceptual.

## Que genera Gastos

La carga de gastos debe empezar con una pregunta simple:

> Que estas cargando?

Opciones principales:

### 1. Gasto asumido por Indyana

Uso:

- marketing;
- videoclip;
- produccion;
- prensa;
- contenido;
- gasto que Indyana decide invertir.

Impacto:

- aumenta inversion de Indyana en el artista/proyecto;
- no genera deuda directa del artista;
- puede tener comprobante y proveedor;
- puede estar pendiente de pago.

### 2. Gasto recuperable

Uso:

- DJ set recuperable;
- produccion recuperable;
- adelanto recuperable;
- gasto que por contrato se recupera despues.

Impacto:

- crea saldo recuperable del proyecto;
- no es automaticamente cuenta corriente;
- debe definir como se recupera:
  - desde booking;
  - desde regalias;
  - manual;
  - mixto.

El recupero se registra despues como aplicacion.

### 3. Adelanto / prestamo

Uso:

- dinero dado al artista;
- prestamo;
- adelanto contra futuros ingresos.

Impacto:

- genera cuenta corriente;
- puede recuperarse desde booking, regalias o pago manual.

### 4. Pago o cobro de cuenta corriente

Uso:

- el artista/manager paga deuda;
- Indyana paga algo que debia;
- se compensa un saldo.

Impacto:

- baja o cierra cuenta corriente;
- no cambia el resultado economico del show o proyecto original.

### 5. Gasto pagado por artista/manager/tercero

Uso:

- Dami paga un gasto que correspondia a Indyana;
- artista paga algo de un proyecto;
- manager paga un costo y lo informa.

Impacto posible:

- puede bajar cuenta corriente si Indyana lo reconoce;
- puede entrar como aporte del artista al proyecto;
- puede quedar pendiente de control si no sabemos a quien corresponde.

El sistema debe preguntar de forma humana:

- Lo reconocemos como credito a favor de quien lo pago?
- Es inversion de Indyana?
- Es parte recuperable del artista?
- Queda pendiente de revisar?

## Pantalla principal: Finanzas Artista

La pantalla no debe abrir con ledger.

Debe abrir con una ficha simple.

### Cabecera

Selector de artista.

Tarjetas:

- Estado: `Nos debe`, `Le debemos`, `Al dia`, `Pendiente de control`.
- Saldo cuenta corriente.
- Booking pendiente.
- Inversion Indyana.
- Recuperable pendiente.
- Pendiente proveedores.

No mostrar sumas brutas tipo "deben 8M / debemos 6M" en la cabecera si el
saldo util es 1.6M. Esos brutos pueden quedar en detalle tecnico.

### Seccion 1 - Resumen

Debe decir en texto simple:

- "Aneley debe a Indyana $1.628.370 por booking."
- "Hay $12.308.730 marcados como recuperables pendientes de criterio."
- "Hay $1.050.000 pendiente de pago a proveedores."

Si algo no esta controlado, debe decirlo.

### Seccion 2 - Booking

Debe mostrar:

- shows;
- Indyana ganado;
- Indyana cobrado;
- pendiente;
- deuda boliche;
- boton "ver shows que explican el saldo".

Si no hay saldos, decir:

> Sin saldos de booking abiertos.

No mostrar una tabla vacia.

### Seccion 3 - Proyectos

Orden por fecha, no alfabetico.

Columnas humanas:

- Proyecto.
- Area.
- Primera fecha.
- Ultima fecha.
- Total invertido.
- Pagado.
- Pendiente proveedor.
- Recuperable.
- Recuperado.
- Falta recuperar.
- Estado.

### Seccion 4 - Cuenta corriente

Solo movimientos donde alguien debe algo.

No mostrar inversiones ni gastos comunes.

Columnas:

- Fecha.
- Origen.
- Concepto.
- Nos debe.
- Le debemos.
- Saldo.
- Estado.

### Seccion 5 - Recuperables

Puede estar dentro de Proyectos si hay pocos.

Debe mostrar:

- Proyecto.
- Total recuperable.
- Recuperado.
- Falta recuperar.
- Como se recupera.
- Aplicaciones.

No debe llamarse legacy.

### Seccion 6 - Detalle tecnico

Incluye:

- ledger;
- auditoria vieja;
- ids de origen;
- tablas tecnicas;
- diagnostico de inconsistencias.

Esta seccion es para Ruben/Codex, no para operadores.

## Pantalla de carga: Gastos y movimientos

No debe empezar con campos contables.

Debe empezar con:

1. Artista.
2. Fecha.
3. Que estas cargando?
4. Proyecto.
5. Concepto.
6. Importe.
7. Quien pago?
8. Comprobante/notas.

Despues se abren campos segun el tipo.

### Si es gasto asumido por Indyana

Preguntar:

- Area: booking, label, marketing, digitales, general.
- Categoria.
- Esta pagado?
- Hay deuda a proveedor?

No preguntar recupero.

### Si es gasto recuperable

Preguntar:

- Recuperable contra: booking, regalias, manual, mixto.
- Porcentaje recuperable.
- Quien soporta economicamente el costo.
- Proyecto origen.

No mover cuenta corriente hasta que haya una aplicacion concreta.

### Si es adelanto/prestamo

Preguntar:

- Se recupera contra que fuente?
- Fecha estimada.
- Nota obligatoria.

Genera cuenta corriente.

### Si es pago/cobro de cuenta corriente

Preguntar:

- A que saldo se aplica?
- Quien pago?
- Metodo.
- Comprobante.

Baja cuenta corriente.

### Si lo pago artista/manager/tercero

Preguntar:

- Quien lo pago?
- Indyana lo reconoce?
- Baja una deuda existente?
- Es aporte del artista al proyecto?
- Queda pendiente de revisar?

## Estados simples

Usar pocos estados visibles:

- Borrador.
- Pendiente de control.
- Controlado.
- Cerrado.
- Observado.
- Anulado.

Estados tecnicos internos pueden existir, pero no deben dominar la pantalla.

## Reglas de oro

1. La pantalla principal debe explicar, no exigir interpretacion.
2. Booking no se mezcla con gastos de proyecto.
3. Un recupero aplicado baja un proyecto, no cambia la historia del show.
4. Una inversion puede afectar rentabilidad sin generar deuda.
5. Una cuenta corriente responde solo "quien debe a quien".
6. Un proyecto responde "cuanto invertimos, recuperamos y falta".
7. El ledger es motor y auditoria, no pantalla principal.
8. Si algo esta pendiente de criterio, no se muestra como verdad final.
9. No usar "legacy" para gastos reales viejos.
10. Toda fila debe conservar fuente y permitir auditoria.

## Casos testigo obligatorios

Antes de dar por buena la nueva pantalla:

### Virrshi

Debe mostrar:

- proyectos DJ set;
- recuperos aplicados desde shows;
- saldo recuperable abierto;
- cuenta booking sin ensuciarse si los shows estan cerrados.

### Aneley

Debe mostrar:

- saldo booking con manager/familia;
- gastos pagados por Indyana;
- gastos pagados por artista/manager;
- que movimientos bajan cuenta corriente y cuales son solo inversion;
- recuperables pendientes de criterio si no tienen metodo definido.

### G Sony

Debe mostrar:

- terceros/socios externos;
- Indyana ganado;
- no comisionable cuando corresponda;
- cuenta corriente solo si hay saldo real.

### Show simple

Debe mostrar:

- cachet;
- gastos;
- split;
- caja;
- saldo o cerrado.

## Roadmap sencillo

### Paso 1 - Solo visual

Rearmar Finanzas Artista con lenguaje humano, usando los datos existentes.
No cambiar datos.

Implementado inicial:

- vista `Resumen` como primera pantalla;
- `Booking`, `Proyectos`, `Cuenta corriente` y `Detalle tecnico` como vistas separadas;
- el ledger queda oculto en `Detalle tecnico`;
- los proyectos se ordenan por fecha;
- se separa `por recuperar definido` de `pendiente de criterio`;
- no se mutan datos desde esta pantalla.

### Paso 2 - Ordenar proyectos

Ordenar por fecha y mostrar resumen claro.

### Paso 3 - Separar cuenta corriente real

Mostrar solo saldos reales, no inversiones ni brutos tecnicos.

### Paso 4 - Redisenar carga de gastos

Crear flujo guiado por tipo de gasto.

### Paso 5 - Controlar Aneley y Virrshi

Usarlos como casos testigo.

### Paso 6 - Recién despues, ledger posteado

Si el flujo queda claro, crear ledger inmutable/aprobado.

Mientras tanto el ledger v1 queda como lectura canonica/auditoria, no como
pantalla principal.
