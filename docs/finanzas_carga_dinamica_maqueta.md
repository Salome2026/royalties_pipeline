# Finanzas VPO - maqueta de carga dinamica

Fecha: 2026-07-11

Estado: maqueta para aprobacion. No implementada todavia.

Backup previo de referencia:

`C:\royalties_pipeline\backups\finance_redesign_checkpoint_20260711_111613.zip`

## Objetivo

Redisenar la carga de movimientos financieros sin parches, sin duplicar Booking
y sin convertir la pantalla en un formulario contable pesado.

La pantalla debe servir para que un usuario comun cargue lo que paso, y para que
administracion pueda completar el tratamiento financiero cuando haga falta.

## Regla central

La carga empieza por una pregunta simple:

> Que estas cargando?

Opciones iniciales:

- `Gasto`
- `Pago / cobro`
- `Ajuste` solo admin

La pantalla se abre de a poco. No se muestran campos de recupero, cuenta
corriente, imputacion, auditoria o ledger hasta que el caso los necesite.

## Diferencia humana entre gasto y pago

### Gasto

Un gasto crea un costo, inversion, compromiso o deuda nueva.

Ejemplos:

- se hizo un DJ set para Virrshi;
- Carolina pago un proveedor;
- se debe un videoclip;
- se registra un sueldo del mes;
- se carga una inversion de label o marketing.

El gasto puede estar:

- pagado;
- parcialmente pagado;
- pendiente de pago.

### Pago / cobro

Un pago o cobro no crea el gasto ni el show. Aplica dinero contra algo que ya
existe.

Ejemplos:

- Aneley paga una deuda de booking;
- Indyana paga un saldo pendiente a Candu;
- Gusty devuelve plata cobrada de mas;
- se cobra una deuda de boliche;
- se aplica dinero contra un recuperable abierto;
- se paga un proveedor que estaba pendiente.

Regla:

Un pago/cobro siempre debe intentar aplicarse a un saldo abierto. Si no se sabe
todavia a que aplicarlo, queda como `sin aplicar`, no se inventa un gasto.

## Flujo general de pantalla

### Paso 1 - Fecha

Campo siempre visible.

La fecha es la fecha del hecho cargado:

- fecha del gasto;
- fecha del pago;
- fecha del cobro;
- fecha del ajuste.

### Paso 2 - Que estas cargando?

Selector simple:

- Gasto
- Pago / cobro
- Ajuste admin

El resto de la pantalla depende de esta respuesta.

### Regla de alcance por artista

El artista es opcional, pero si se elige un artista la pantalla queda en modo
`artista/proyecto`.

En modo `artista/proyecto` no deben ofrecerse sectores internos como:

- estructura;
- administracion;
- sueldos;
- oficina.

Esos sectores pertenecen al modo `empresa/estructura`, que se usa cuando no hay
artista elegido.

Si el usuario elige un artista despues de haber seleccionado estructura, el
sistema debe cambiar automaticamente a un sector valido para artista y limpiar
la categoria. No debe permitir guardar combinaciones como:

- artista + estructura + sueldo;
- artista + administracion + proveedor interno;
- cuenta booking sin artista.

No deben aparecer como puertas principales:

- sueldo;
- recupero;
- adelanto;
- prestamo;
- proveedor pendiente.

Esos conceptos son categorias, tratamientos o aplicaciones posteriores dentro
del flujo elegido. Si aparecen como botones principales y tambien como
categorias, el usuario tiene dos caminos para el mismo hecho y la carga deja de
ser guiada.

## Flujo si el usuario elige Gasto

### Paso 3 - Sector

Selector:

- Booking
- Label
- Management
- Digitales
- Marketing
- Estructura
- General

El sector define que campos aparecen.

### Gasto de Booking, Label, Management, Digitales o Marketing

Campos visibles:

- artista opcional;
- proyecto;
- categoria;
- concepto o varios conceptos;
- a quien se pago o se debe pagar;
- importe;
- moneda;
- tipo de cambio si corresponde;
- quien pago;
- estado de pago: pagado, parcial, pendiente;
- vencimiento si esta pendiente;
- comprobante;
- notas.

Si `quien pago` es `Empleado`, aparece un selector de empleados del ABM.
Ese selector no abre datos salariales ni permisos de ABM: solo identifica quien
puso la plata. El movimiento sigue siendo gasto del artista/proyecto, pero el
sistema genera una cuenta corriente de reintegro:

- direccion: `Indyana debe a empleado`;
- contraparte: empleado seleccionado;
- origen: movimiento financiero;
- importe: pagado real convertido a ARS;
- estado inicial: abierto.

Si el movimiento se edita y deja de estar pagado por empleado, o se anula, el
saldo de reintegro derivado se elimina o se regenera desde el movimiento vigente.

Para pagarle al empleado lo que Indyana le debe por esos gastos, no se carga un
gasto nuevo. Se usa el mismo flujo:

- tipo: `Pago / cobro`;
- categoria: `Reintegro a empleado`;
- empleado desde ABM;
- importe real pagado;
- seleccion de saldos pendientes a cancelar.

Ese pago aplica contra las entradas abiertas de `Indyana debe a empleado`.
Puede cerrar una entrada completa o dejarla parcial. La imputacion de
artista/proyecto no se vuelve a pedir porque ya esta guardada en el gasto
original.

Bloque opcional cerrado por defecto:

`Tratamiento`

Opciones:

- asumido por Indyana;
- recuperable;
- cuenta corriente;
- pendiente de definir.

Si se elige `recuperable`, recien ahi aparecen:

- recuperar contra: Booking, Regalias, Manual, Mixto;
- porcentaje o importe recuperable;
- metodo: antes del split, contra parte artista, cuenta corriente directa,
  regalias o manual;
- costo economico artista;
- costo economico Indyana.

### Gasto de Estructura

No aparece artista por defecto.

Campos visibles:

- tipo de estructura: sueldo, comision, oficina, sistema, impuesto, alquiler,
  servicio, otro;
- empleado o proveedor;
- periodo si corresponde;
- area interna si corresponde;
- importe;
- moneda;
- tipo de cambio;
- quien pago;
- estado de pago;
- comprobante;
- notas.

Si el tipo es `sueldo`, el sistema puede sugerir el salario pactado desde ABM de
empleados, pero el movimiento real se carga aca.

Bloque opcional:

`Distribucion economica`

Ejemplo:

- Indyana paga USD 1.000;
- costo real Indyana USD 500;
- cuenta por cobrar a tercero USD 500.

Si no se carga distribucion, se asume 100% costo Indyana.

### Varios conceptos

La carga puede tener varios renglones dentro del mismo gasto/proyecto.

Esto debe ser un movimiento padre con lineas hijas, no varias filas sueltas
desconectadas.

Cada linea puede tener:

- concepto;
- categoria;
- proveedor/persona;
- importe;
- moneda;
- tipo de cambio;
- pagado real;
- estado de pago;
- vencimiento;
- nota.

El movimiento padre guarda:

- fecha;
- sector;
- artista/unidad;
- proyecto;
- comprobantes generales;
- notas;
- usuario.

## Flujo si el usuario elige Pago / cobro

### Paso 3 - Tipo de aplicacion

Selector:

- Cuenta booking;
- SeÃ±a de show / recibo;
- Recuperable / proyecto;
- Proveedor pendiente;
- Adelanto / prestamo;
- Cuenta corriente financiera;
- Dejar sin aplicar por ahora.

### Pago / cobro con documento financiero PDF

Cuando el usuario carga `Pago / cobro`, puede emitir un documento financiero
si necesita dejar una constancia formal en PDF.

La pantalla no debe tener un camino separado por area. Debe mostrar un bloque
de documento cuando el tipo elegido lo requiere.

Tipos:

- `Recibo por seña de show`: dinero recibido para reservar un show. Normalmente
  area Booking.
- `Orden de pago`: dinero pagado por una empresa del grupo a una persona,
  proveedor, artista, manager o tercero.
- `Comprobante de cobro`: dinero recibido por una empresa del grupo por un
  concepto que no es necesariamente seña de show.

Datos comunes:

- empresa emisora;
- contraparte, con etiqueta dinamica segun el tipo: de quien se recibe o a quien se paga;
- importe, moneda y tipo de cambio;
- concepto;
- artista principal o unidad, si corresponde;
- otros artistas si corresponde;
- fecha/lugar del show solo cuando el documento es de seña de show;
- notas y comprobantes;
- IVA interno, que no aparece en el PDF.

Reglas:

- el documento se guarda en `finance_documents` y queda vinculado al movimiento financiero;
- todos los documentos comparten numeracion incremental atomica de Postgres;
- emitir el PDF no crea un movimiento adicional;
- editar un documento emitido requiere permiso de editar en Movimientos Financieros;
- un usuario con permiso de crear puede emitir documentos dentro de su alcance,
  pero no modificarlos luego si no tiene editar;
- no se agregan ramas SQLite ni fallback historico.

### Gasto / inversion con orden de pago PDF

Cuando el usuario carga `Gasto / inversion`, puede activar `Generar orden de
pago PDF` para emitir una constancia formal sin duplicar la carga.

Reglas:

- el movimiento sigue siendo `Gasto / inversion`;
- el documento asociado es `Orden de pago`;
- el sistema precarga el documento con concepto, contraparte, importe, moneda,
  tipo de cambio, artista, proyecto y area del gasto;
- si la contraparte del documento queda vacia, toma "A quien se pago";
- emitir el PDF no crea un movimiento adicional ni aplica saldos;
- para multiples conceptos no se emite PDF automatico en esta etapa.

### Pago / cobro contra Cuenta booking

Esto debe usar la logica ya validada de Booking, pero dentro del mismo flujo.

No es derivacion ni pantalla separada. Es el mismo asistente mostrando el bloque
de cuenta booking.

Campos:

- artista;
- importe total;
- metodo: transferencia, efectivo, compensacion, ajuste, otro;
- contraparte;
- comprobante;
- notas.

Despues el sistema muestra los shows con saldos abiertos:

- fecha;
- venue;
- saldo a favor de Indyana;
- saldo a favor del artista;
- deuda boliche;
- estado actual.

Acciones:

- seleccionar shows manualmente;
- sugerir por fecha;
- cerrar bloque seleccionado;
- aplicar parcial;
- dejar sobrante sin aplicar.

El guardado debe escribir en:

- `booking_account_movements`;
- `booking_account_applications`.

Y debe conservar la conducta actual:

- no reescribe cachet;
- no reescribe gastos;
- no cambia split;
- no borra caja original;
- cierra shows cuando el saldo vivo queda en cero;
- deja alerta si queda saldo parcial;
- conserva trazabilidad del movimiento padre.

### Pago / cobro contra Recuperable / proyecto

Campos:

- artista;
- proyecto;
- recuperable abierto;
- importe aplicado;
- metodo;
- comprobante;
- notas.

El sistema debe mostrar recuperables abiertos y el saldo pendiente.

El guardado debe escribir una aplicacion contra el recuperable:

- `finance_recovery_applications`;
- y actualizar lectura de saldo recuperable.

No debe crear un gasto nuevo.

### Pago a proveedor pendiente

Campos:

- proveedor;
- gasto pendiente;
- importe pagado;
- metodo;
- comprobante;
- notas.

Debe bajar el pendiente de pago del gasto original.

No debe duplicar el gasto.

### Pago / cobro de adelanto o prestamo

Campos:

- artista o tercero;
- saldo abierto;
- importe aplicado;
- metodo;
- comprobante;
- notas.

Debe bajar cuenta corriente financiera.

### Dejar sin aplicar

Uso excepcional.

Ejemplo:

- entro una transferencia pero todavia no sabemos contra que saldo va.

Debe quedar visible como plata sin aplicar, no como ingreso ganado.

## Flujo si el usuario elige Ajuste

Solo admin.

Campos:

- fecha;
- motivo;
- origen afectado;
- importe;
- nota obligatoria;
- comprobante si existe.

No debe ser el camino normal para cerrar diferencias.

## Resumen lateral

La pantalla debe mostrar un resumen chico y siempre visible:

- total cargado;
- total pagado/cobrado;
- pendiente;
- sector;
- artista/proyecto/unidad;
- estado: borrador, pendiente control, listo para guardar, observado;
- impacto estimado en lenguaje humano.

Ejemplos de impacto:

- "Gasto de proyecto. No genera cuenta corriente por ahora."
- "Gasto recuperable. Queda saldo a recuperar."
- "Pago aplicado a 3 shows. 2 cerrarian y 1 queda parcial."
- "Sueldo pagado. 50% costo Indyana y 50% cuenta por cobrar a tercero."

## Estados visibles

Estados simples:

- Borrador;
- Pendiente de control;
- Observado;
- Aprobado;
- Aplicado;
- Cerrado;
- Anulado.

Regla:

Los operadores pueden cargar borrador o pendiente de control.

Administracion aprueba, aplica o cierra.

Un movimiento aprobado/aplicado no se pisa; se corrige con ajuste o movimiento
nuevo.

## Que se conserva del sistema actual

### Booking

Se conserva la logica actual de:

- `Saldar / aplicar` por show;
- movimiento padre de cuenta booking;
- cierre de bloque seleccionado;
- aplicaciones a shows;
- cierre verde cuando no hay saldo vivo;
- compensaciones entre shows;
- deuda de boliche separada.

La mejora es de presentacion e integracion: cuando el usuario carga
`Pago / cobro > Cuenta booking`, ve esa misma logica dentro del flujo financiero
unificado.

### Recuperos desde booking

Se conserva:

- recupero antes del split;
- imputacion automatica FIFO contra recuperable abierto cuando corresponda;
- validacion de que exista saldo recuperable suficiente.

### Finanzas Artista

Se conserva como pantalla de lectura:

- resumen;
- booking;
- proyectos;
- cuenta corriente;
- detalle tecnico.

No debe ser la pantalla principal de carga.

### ABM empleados

Se conserva:

- salario pactado;
- moneda;
- tipo de compensacion;
- funciones;
- permisos.

El pago real del sueldo se carga como gasto de estructura.

## Que se reemplaza o corrige

### Formulario unico pesado

El formulario actual muestra demasiadas decisiones juntas:

- hecho;
- tratamiento;
- auditoria;
- recupero;
- imputacion;
- origen tecnico.

La nueva pantalla debe mostrar solo lo necesario segun el camino elegido.

### Multiples conceptos como filas sueltas

La carga de varios conceptos no debe guardar movimientos separados sin padre.

Debe guardar:

- movimiento padre;
- lineas hijas.

### Recupero como tipo principal

`Recupero` no debe ser un tipo inicial al mismo nivel que gasto.

Debe aparecer como:

- tratamiento de un gasto; o
- aplicacion posterior contra un recuperable.

### Origen tecnico visible

Campos como `legacy`, `source_type`, `source_id` y similares deben quedar en
auditoria/admin, no en la carga diaria.

## Mapeo de datos

### Gasto simple

Usa:

- `finance_movements`
- opcionalmente `finance_movement_allocations`

### Gasto con varios conceptos

Debe usar:

- `finance_movements` como padre;
- `finance_movement_lines` como hijas.

### Gasto recuperable

Usa:

- `finance_movements` como origen;
- `finance_recoverables` como saldo recuperable canonico cuando se apruebe;
- `finance_recovery_applications` para recuperos posteriores.

### Pago / cobro de booking

Usa:

- `booking_account_movements`;
- `booking_account_applications`.

No usa `finance_movements` para duplicar shows.

### Sueldo / estructura

Usa:

- `employees` para condicion pactada;
- `finance_movements` para pago real;
- `finance_movement_allocations` si hay distribucion mixta.

## Permisos

La pantalla debe respetar:

- modulo;
- accion;
- artistas permitidos;
- proyectos permitidos cuando exista esa capa;
- ver historial;
- editar;
- aprobar;
- sensibilidad salarial.

Ejemplos:

- un PM puede cargar gastos de artistas permitidos sin ver historial;
- Carolina puede cargar pagos simples sin ver campos contables;
- Ruben/admin ve todo y puede aprobar/aplicar;
- salarios solo visibles para permisos autorizados.

## Casos obligatorios de validacion

### Virrshi - DJ set recuperable

Debe poder:

- cargar gasto de proyecto DJ set;
- marcarlo recuperable;
- definir metodo de recupero;
- aplicar recuperos desde booking;
- mantener show cerrado aunque el recuperable siga abierto.

### Aneley - manager/familia

Debe poder:

- ver saldo booking separado;
- cargar gasto de proyecto pagado por Dami/manager;
- reconocerlo como credito si corresponde;
- bajar cuenta corriente sin meter el gasto dentro del show;
- mantener inversion/proyecto visible.

### Bianca

Debe poder:

- cargar inversiones de label/marketing;
- cargar proveedores pendientes;
- conservar tipo de cambio por movimiento;
- mostrar proyectos sin cuenta corriente falsa.

### Sueldos y estructura

Debe poder:

- guardar salario pactado en ABM empleado;
- cargar pago real en estructura;
- soportar pago parcial;
- soportar financiacion mixta;
- no exponer sueldos sin permiso.

### Candu / Gusty / G Sony

Debe poder:

- no duplicar booking;
- aplicar pagos posteriores a shows;
- compensar shows entre si;
- cerrar shows cuando no queda saldo vivo;
- no alterar liquidacion original.

### Recuperable desde booking

Debe poder:

- cargar recupero en show;
- aplicar contra saldo recuperable abierto;
- no contarlo como ingreso de booking para comisiones internas salvo regla explicita.

### Caserio

Queda fuera de esta pantalla por ahora.

Debe seguir en su modulo hasta que la logica de booking/finanzas quede estable.

## Maqueta visual en texto

```text
Movimientos financieros

[Fecha]
[Area]
[ Marketing | Label | Digitales | Booking | Oficina ]

Si Area = Marketing / Label / Digitales / Booking:
  Artista
    - selector cerrado segun permisos del usuario
  Proyecto asociado
    - sin proyecto
    - proyecto existente del artista/area
    - nuevo proyecto

Si Area = Oficina:
  No pide artista
  Solo visible para admin o usuarios con permiso financiero sensible

Luego:
  Que queres cargar?
  [ Gasto / inversion ] [ Pago / cobro ] [ Ajuste admin ]

Si Gasto / inversion:
  Categoria segun area
  Conceptos
    + concepto / proveedor / importe / pagado / estado / vencimiento
    + multiples conceptos si es un proyecto con varias partidas
  Comprobante
  Notas
  Tratamiento / recuperable solo si corresponde

Si Pago / cobro:
  Aplicar a
  [ Cuenta booking | Recuperable | Proveedor pendiente | Adelanto/prestamo |
    Cuenta corriente | Sin aplicar ]

  Si Cuenta booking:
    Artista ya seleccionado
    Importe total
    Metodo
    Comprobante
    Shows abiertos
      seleccionar / aplicar / resultado
    Guardar movimiento

Si Oficina + sueldo/comision interna:
  Empleado desde ABM, no texto libre
  Importe, moneda, tipo de cambio y estado de pago
  Distribucion economica opcional
  No muestra recuperables/tratamiento financiero por defecto

Resumen:
  Total
  Pagado
  Pendiente
  Impacto humano
  Alertas
```

## Orden de implementacion propuesto

### Fase 0 - Aprobacion

Validar esta maqueta con Ruben.

No tocar codigo vivo antes de aprobar.

### Fase 1 - Maqueta UI sin guardado

Crear una version visual segura de la nueva pantalla.

Objetivo:

- probar flujo;
- probar textos;
- probar campos dinamicos;
- validar casos reales.

### Fase 2 - Reusar logica de booking dentro del flujo

Integrar visualmente:

- movimientos padre de booking;
- aplicaciones a shows;
- cierre de bloque.

Sin cambiar la logica backend que ya funciona.

### Fase 3 - Rehacer carga de gastos

Cambiar la carga de gastos para que:

- un movimiento pueda tener lineas hijas reales;
- no guarde multiples conceptos como filas sueltas;
- el tratamiento aparezca solo cuando corresponde.

### Fase 4 - Control y aprobacion

Separar:

- carga operador;
- control admin;
- aprobacion;
- aplicacion.

### Fase 5 - Limpieza

Revisar y retirar:

- campos tecnicos visibles en la carga diaria;
- opciones confusas como recupero principal;
- codigo duplicado o muerto;
- nombres historicos que no correspondan.

## Criterio de aprobacion

La maqueta queda aprobada solo si permite cargar, sin explicar contabilidad:

1. gasto simple de artista;
2. gasto con varios conceptos;
3. gasto de estructura/sueldo;
4. gasto recuperable;
5. pago de deuda booking que cierra shows;
6. cobro/pago parcial que deja saldo abierto;
7. pago a proveedor pendiente;
8. gasto pagado por manager/tercero;
9. compensacion entre shows;
10. caso dudoso pendiente de control.

Si alguno de estos casos obliga a meter campos contables visibles desde el
inicio, la maqueta no esta lista.
