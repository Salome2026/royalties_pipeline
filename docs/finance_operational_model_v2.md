# Modelo financiero operativo VPO - rector v2

Fecha: 2026-07-06

Estado: rector operativo validado para guiar cambios de Finanzas,
Movimientos Financieros, Finanzas Artista, empleados/sueldos y proyecciones.

Este documento busca ordenar la parte financiera de VPO sin forzar la realidad
operativa a una pantalla contable incomoda. La regla principal es simple:

> El usuario carga hechos del negocio. El sistema traduce esos hechos a caja,
> cuenta corriente, proyectos, recuperables, resultado y proyeccion.

Este documento manda sobre `finance_business_master.md` y
`artist_finance_ledger_model.md` cuando haya conflicto de criterio. Esos
documentos quedan como soporte visual/tecnico e historial de decisiones.

## Problema que queremos resolver

VPO no necesita que cada operador piense como contador.

Necesita que cada operador pueda decir:

- pague esto;
- me deben esto;
- esto corresponde a este artista;
- esto corresponde a este proyecto;
- esto es recuperable;
- esto fue una inversion de Indyana;
- esto es sueldo, oficina o estructura;
- esto esta pendiente de pago;
- esto tiene comprobante;
- esto solo puede verlo cierta gente.

Y que el sistema, con reglas claras, lo convierta en informacion financiera
confiable.

## Principio central

La pantalla de carga no debe abrir con contabilidad.

Debe abrir con una pregunta humana:

> Que estas cargando?

A partir de esa respuesta, la pantalla muestra solo los campos necesarios.

El sistema debe evitar dos errores:

1. Mostrar todos los campos posibles y hacer que nadie entienda la pantalla.
2. Esconder tanta logica que despues nadie pueda auditar por que dio un saldo.

## Decision clave 2026-07-06

`Recuperable` no es una respuesta principal a `Que estas cargando?`.

`Recuperable` es un tratamiento financiero que puede aplicarse a un gasto,
inversion, adelanto o proyecto.

Ejemplo:

- hecho cargado: gasto / inversion;
- concepto: DJ set Virrshi;
- pagado por: Indyana;
- tratamiento financiero: recuperable 100% contra booking;
- proyecto: Mix RKT #3;
- estado: pendiente de control o aprobado.

Esto evita que el usuario piense primero en contabilidad. El usuario carga el
hecho real; el sistema decide, segun el tratamiento, como impacta en caja,
cuenta corriente, proyecto, recuperables, resultado y BI.

Regla practica:

- `Que estas cargando?` describe el hecho.
- `Tratamiento financiero` describe como se interpreta ese hecho.
- `Aplicacion` describe como se cierra, recupera o compensa despues.

## Las cinco lecturas financieras

Cada movimiento puede tener una o varias lecturas. No hay que mezclarlas.

### 1. Caja

Pregunta:

> Entro o salio plata real?

Ejemplos:

- Indyana pago un videoclip.
- Un manager pago un gasto que correspondia a Indyana.
- Un boliche transfirio una sena.
- Se pago un sueldo.

### 1.a Gasto pagado por empleado

Cuando un empleado paga con plata propia un gasto que pertenece al negocio, no
cambia la naturaleza economica del gasto.

Ejemplo:

- Lautaro paga combustible o ensayo para un proyecto de Candu;
- el gasto sigue siendo `Label`, `Booking`, `Marketing` o el area que
  corresponda;
- el artista/proyecto conserva el costo;
- Indyana reconoce una deuda de reintegro con Lautaro.

Regla:

- el usuario carga el gasto normalmente;
- en `Quien pago` elige `Empleado`;
- el sistema pide el empleado desde ABM, no texto libre;
- el gasto queda imputado al artista/proyecto/area;
- se genera automaticamente una entrada de cuenta corriente:
  `Indyana debe a empleado`;
- el importe a reintegrar es el `pagado real` convertido a ARS. Si `pagado real`
  esta vacio, se asume el compromiso total del gasto;
- el reintegro posterior debe cerrar esa cuenta corriente sin modificar el gasto
  original.

Esto evita mezclar dos verdades:

- `que costo tuvo el artista/proyecto`;
- `a quien le debe plata Indyana por haber financiado ese costo`.

### 1.b Pago de reintegro a empleado

Cuando Indyana le devuelve plata a un empleado por gastos que el empleado pago
con fondos propios, no se carga otro gasto.

El movimiento correcto es:

- `Pago / cobro`;
- categoria `Reintegro a empleado`;
- empleado elegido desde el ABM;
- importe real pagado;
- aplicacion contra una o mas entradas abiertas de `Indyana debe a empleado`.

Reglas:

- el pago baja la cuenta corriente del empleado;
- el gasto original no se modifica;
- si el pago cubre todo el saldo, la entrada queda saldada;
- si el pago cubre una parte, la entrada queda parcial;
- si el pago sobra, el excedente no debe aplicarse automaticamente sin una
  decision explicita;
- el pago puede saldar gastos de distintos artistas/proyectos, porque la
  imputacion economica ya vive en cada gasto original.

### 2. Cuenta corriente

Pregunta:

> Quien le debe a quien?

Ejemplos:

- El artista cobro de mas.
- Indyana cobro una sena que correspondia al artista.
- Indyana debe reconocerle a un manager un gasto que pago.
- Un artista debe devolver un adelanto.

La cuenta corriente no es rentabilidad.

### 3. Proyecto / inversion

Pregunta:

> Cuanto invertimos o gastamos en este artista/proyecto?

Ejemplos:

- DJ set de Virrshi.
- Set Padel de Aneley.
- Videoclips de Bianca.
- Campana de marketing.
- Gira promocional.

Un proyecto puede estar a perdida aunque la cuenta corriente este en cero.

### 4. Recuperables

Pregunta:

> De lo invertido, cuanto se espera recuperar y cuanto ya se recupero?

Un recuperable no siempre es deuda directa del artista. Puede recuperarse:

- antes del split de booking;
- despues del split;
- contra cuenta corriente;
- contra regalias;
- por pago manual;
- por una combinacion.

### 5. Resultado / BI

Pregunta:

> Como viene el negocio?

Ejemplos:

- ingresos de booking para Indyana;
- ingresos digitales;
- inversion acumulada;
- recuperos;
- sueldos/estructura imputados;
- proyeccion futura.

Esta lectura no debe contaminar la carga diaria. Se calcula despues a partir de
datos bien cargados.

## Permisos como regla core

Los permisos no son un agregado visual. Son parte del negocio.

Todo modulo financiero debe validar:

- usuario;
- modulo;
- accion;
- artistas permitidos;
- proyectos permitidos cuando exista esa capa;
- permiso para ver historial;
- permiso para editar;
- permiso para aprobar/cerrar.

### Admin

Ruben / admin puede:

- ver todo;
- cargar todo;
- editar lo editable;
- aprobar;
- anular;
- corregir por flujo controlado.

### Project manager / operador

Un project manager puede tener permisos acotados por artista.

Puede existir este escenario:

- puede cargar gastos de Virrshi y Aneley;
- no puede ver el historial;
- no puede ver saldos globales;
- no puede aprobar;
- solo puede editar sus borradores o movimientos observados.

Esto evita que la pantalla muestre informacion sensible mientras permite
operacion real.

### Finanzas / administracion

Puede:

- ver historial;
- controlar movimientos;
- aprobar;
- aplicar pagos a cuenta corriente;
- cerrar recuperables;
- revisar comprobantes.

### Sueldos

La informacion salarial es sensible.

Debe ser visible solo para admin/administracion con permiso explicito. Un
empleado no deberia ver sueldos de otros empleados por tener acceso a
Movimientos Financieros.

Permiso operativo:

- `Movimientos financieros` habilita la carga general de hechos financieros;
- `Sueldos y compensaciones` habilita especificamente ver/cargar/editar pagos
  de sueldo o comision interna;
- `ABM Empleados` administra la ficha del empleado, funciones, usuario,
  permisos y salario pactado, pero no debe ser usado como permiso indirecto
  para cargar pagos salariales;
- para cargar un sueldo real se requieren ambos permisos: crear en
  `Movimientos financieros` y crear en `Sueldos y compensaciones`;
- para editar un movimiento salarial se requieren ambos permisos: editar en
  `Movimientos financieros` y editar en `Sueldos y compensaciones`;
- el selector de empleados dentro de Movimientos Financieros debe usar una
  lista minima de empleados autorizados para finanzas, no el ABM completo.

## Pantalla de Movimientos Financieros

La pantalla debe conservar lo que ya tiene de bueno:

- artista;
- fecha;
- area;
- categoria;
- proyecto;
- concepto simple o multiple;
- importe;
- moneda;
- tipo de cambio;
- quien pago;
- pagado real;
- estado de pago;
- vencimiento;
- recuperable;
- metodo de recupero;
- notas;
- comprobantes;
- estados.

Pero no debe mostrar todo junto.

## Flujo propuesto de carga

### Paso 1 - Que estas cargando?

Opciones iniciales:

1. Gasto / inversion en artista o proyecto.
2. Adelanto o prestamo.
3. Pago o cobro de cuenta corriente.
4. Gasto de oficina / estructura.
5. Salario / compensacion.
6. Ingreso o ajuste manual.

### Paso 2 - Datos basicos

Siempre visibles:

- fecha;
- artista o empleado/proveedor segun corresponda;
- area;
- proyecto si aplica;
- concepto;
- importe;
- moneda;
- tipo de cambio si aplica;
- quien pago;
- a quien se pago;
- estado de pago;
- comprobante/notas.

### Paso 3 - Bloque dinamico

Segun el tipo elegido, se abre solo el bloque necesario.

### Paso 4 - Tratamiento financiero

Despues de cargar el hecho, el sistema muestra solo si corresponde un bloque de
tratamiento financiero.

Opciones de tratamiento:

- pendiente de criterio;
- inversion Indyana;
- recuperable total o parcial;
- cuenta corriente directa;
- compromiso pendiente a proveedor;
- imputacion de estructura;
- ajuste aprobado.

Este bloque no debe estar siempre abierto. En carga rapida de operador puede
quedar como `pendiente de control` y ser completado por administracion.

## Tipos de movimiento

### 1. Gasto / inversion en artista o proyecto

Uso:

- videoclip;
- marketing;
- contenido;
- produccion;
- foto;
- prensa;
- gasto de booking no cargado como gasto de show.

Muestra:

- artista;
- proyecto;
- area;
- categoria;
- proveedor;
- pagado por;
- pagado real;
- pendiente a proveedor.

Impacto:

- aumenta inversion/costo del artista o proyecto;
- no genera cuenta corriente salvo que lo pague un tercero y se reconozca deuda;
- no es recuperable salvo que se marque como tal.

Tratamientos posibles:

- inversion Indyana no recuperable;
- recuperable contra booking;
- recuperable contra regalias;
- recuperable manual;
- credito a favor de quien pago si lo pago un tercero;
- pendiente de criterio.

### 2. Adelanto o prestamo

Uso:

- plata dada al artista;
- adelanto contra regalias;
- prestamo;
- pago personal que debe devolver.

Muestra:

- beneficiario;
- fuente esperada de recupero;
- fecha estimada;
- nota obligatoria.

Impacto:

- genera cuenta corriente;
- puede recuperarse por booking, regalias o pago manual.

Tratamientos posibles:

- cuenta corriente directa;
- recuperable contra booking;
- recuperable contra regalias;
- recuperable mixto.

### 3. Pago o cobro de cuenta corriente

Uso:

- el artista paga una deuda;
- Indyana paga algo que debia;
- se compensa saldo entre partes;
- un manager entrega/rinde dinero.

Muestra:

- cuenta afectada;
- saldo previo;
- monto aplicado;
- saldo posterior;
- referencia al origen si existe.

Impacto:

- baja o cierra cuenta corriente;
- no modifica el show/proyecto original.

### 3.a Documentos financieros PDF

Un documento financiero es una constancia formal en PDF emitida desde un
movimiento financiero real. No es una segunda caja, no es una segunda cuenta
corriente y no reemplaza al movimiento original: lo documenta.

Regla core:

- todo documento financiero nace de un movimiento en `Movimientos Financieros`;
- el documento guarda numero incremental, fecha, empresa emisora, contraparte,
  importe, moneda, tipo de cambio, concepto, notas y datos de negocio cuando
  correspondan;
- la numeracion incremental es unica para todos los documentos financieros y
  canonica de Postgres. No se calcula con `MAX(numero) + 1`;
- el PDF se genera desde los datos guardados;
- emitir el documento no aplica saldos automaticamente, salvo que el flujo de
  negocio elegido tenga una aplicacion explicita aparte;
- los documentos operativos viven en Cloud SQL/Postgres. No se crean tablas,
  columnas ni fallback SQLite para esta funcionalidad.
- un `Gasto / inversion` puede emitir una `Orden de pago` en PDF desde el mismo
  movimiento. El documento copia concepto, contraparte, importe, moneda, tipo de
  cambio, artista/proyecto y area del movimiento; no crea un segundo movimiento
  ni convierte el gasto en pago/cobro.

Tipos actuales:

- `show_deposit_receipt`: recibo por seña de show. Se usa cuando un cliente,
  boliche o productor entrega dinero para reservar un show.
- `payment_order`: orden/comprobante de pago. Se usa cuando Indyana o una
  empresa del grupo deja constancia de dinero pagado a una persona, proveedor,
  artista, manager o tercero. Puede nacer desde `Pago / cobro` o desde un
  `Gasto / inversion` cuando el usuario activa "Generar orden de pago PDF".
- `collection_receipt`: comprobante de cobro. Se usa cuando entra dinero a una
  empresa del grupo por un concepto que no es necesariamente sena de show.

Los nombres visibles del PDF dependen del tipo:

- recibo por seña de show: "Recibo";
- orden/comprobante de pago: "Orden de pago";
- comprobante de cobro: "Comprobante de cobro".

Campos minimos comunes:

- fecha;
- empresa emisora;
- contraparte: de quien se recibe o a quien se paga, segun el tipo;
- importe, moneda y tipo de cambio;
- concepto;
- artista principal o unidad, cuando corresponda;
- area del negocio;
- notas/comprobantes;
- tratamiento IVA interno si corresponde. No aparece en el PDF.

Permisos:

- un usuario con permiso de crear en Movimientos Financieros puede emitir
  documentos financieros para los artistas/alcances que tenga habilitados;
- corregir un documento emitido requiere permiso de editar en Movimientos
  Financieros;
- un usuario sin permiso de editar no puede modificar documentos ya emitidos,
  ni siquiera los propios;
- para abrir/descargar un PDF se requiere acceso al movimiento financiero y al
  artista/unidad correspondiente.

### 3.a.1 Orden de pago desde gasto / inversion

Uso:

- se carga un gasto real o inversion del negocio;
- el usuario necesita dejar un comprobante formal en PDF;
- no quiere cargar dos veces los mismos datos.

Regla:

- el movimiento sigue siendo `Gasto / inversion`;
- el documento financiero asociado es `payment_order`;
- la contraparte visible del PDF sale de "A quien se pago". Si el usuario quiere
  otro texto para el PDF, puede completarlo en el bloque del documento;
- el importe y la moneda del PDF son los del movimiento;
- si la moneda es USD, el tipo de cambio sigue siendo obligatorio para registro
  interno;
- no se genera cuenta corriente ni aplicacion adicional por emitir el PDF.

Limitacion actual:

- para cargas con multiples conceptos no se genera orden de pago automatica. Se
  debe cargar un concepto por movimiento cuando se necesita PDF.

### 3.b Seña de show como documento financiero

Uso:

- un cliente entrega una seña para reservar un show;
- Indyana necesita emitir un recibo formal;
- todavia no se quiere modificar la liquidacion del show ni aplicar contra cuenta booking.

Regla:

- la seña se carga como `Pago / cobro` del area `booking`;
- el tipo de documento financiero es `show_deposit_receipt`;
- el movimiento financiero representa caja real recibida;
- el detalle del documento vive en `finance_documents`;
- el PDF se genera desde los datos guardados, no desde texto suelto;
- no se altera cachet, gasto, split ni estado del show hasta que exista una aplicacion explicita;
- el artista del movimiento sale del artista principal del documento.

Impacto:

- aumenta la caja recibida por Indyana;
- queda preparada para vincularse con booking, agenda y cuenta corriente;
- no cierra saldos de booking automaticamente.

Regla multiartista:

- una sena por un evento de dos o mas artistas genera un solo documento;
- el documento guarda todos los artistas asociados;
- no se duplica caja por artista;
- no se reparte la sena automaticamente en esta etapa;
- el artista principal funciona como ancla administrativa para permisos y filtros;
- la distribucion/aplicacion economica se resuelve despues desde Booking o Cuenta
  booking, cuando exista el show o la liquidacion correspondiente.

### 4. Gasto de oficina / estructura

Uso:

- alquiler;
- herramientas;
- sistemas;
- gastos administrativos;
- servicios;
- gastos generales.

Muestra:

- proveedor;
- area;
- si es recurrente;
- vencimiento;
- distribucion interna opcional.

Impacto:

- gasto de estructura;
- no pertenece a un artista salvo que se impute explicitamente.

Tratamientos posibles:

- gasto estructura Indyana;
- imputacion parcial por area/proyecto;
- compromiso mensual;
- pendiente proveedor.

### 5. Salario / compensacion

Uso:

- sueldo mensual;
- honorario fijo;
- compensacion pactada;
- pago parcial de sueldo;
- deuda salarial.

Muestra:

- empleado;
- periodo;
- monto acordado;
- pagado real;
- pendiente;
- quien financia;
- distribucion interna;
- estado.

Impacto:

- gasto de estructura o de area;
- puede tener parte financiada por Indyana y parte por externo;
- puede alimentar proyeccion mensual;
- no debe mezclarse con comisiones variables de booking.

Tratamientos posibles:

- pagado completo;
- pago parcial;
- deuda pendiente;
- financiacion mixta;
- imputacion por area/proyecto;
- proyeccion mensual.

### 6. Ingreso o ajuste manual

Uso:

- correccion aprobada;
- ingreso no nacido de booking ni regalias;
- ajuste excepcional.

Impacto:

- depende del subtipo;
- debe quedar auditado.

## Recuperables como tratamiento

Un recuperable nace cuando un gasto, inversion o adelanto queda marcado como
recuperable.

No debe nacer como movimiento suelto sin gasto/proyecto origen.

Muestra:

- porcentaje recuperable;
- fuente esperada: booking, regalias, manual o mixto;
- metodo: antes del split, despues del split, cuenta corriente directa,
  royalties o manual;
- costo economico artista/Indyana;
- proyecto origen;
- saldo recuperable.

Impacto:

- crea un saldo recuperable;
- no mueve cuenta corriente automaticamente;
- cada recupero futuro debe aplicarse contra este saldo;
- no cambia la historia del gasto original.

## Aplicaciones de recupero

Una aplicacion de recupero no es el gasto original.

Es el hecho posterior que baja el saldo recuperable.

Puede venir de:

- booking;
- regalias;
- pago manual;
- compensacion aprobada.

La aplicacion debe indicar:

- recuperable abierto afectado;
- origen del dinero;
- monto aplicado;
- saldo anterior;
- saldo pendiente;
- comprobante o nota si corresponde.

Regla:

- un show puede estar cerrado aunque el recuperable siga abierto;
- un recuperable puede cerrarse por varias aplicaciones;
- no se debe ocultar un recupero como gasto comun.

## Distribucion interna

La distribucion interna no es lo mismo que quien paga.

### Quien paga / financia

Pregunta:

> De donde salio o deberia salir la plata?

Ejemplos:

- 100% Indyana;
- 50% Indyana / 50% externo;
- lo pago el artista;
- lo pago un manager;
- pendiente de pagar.

### Donde se imputa

Pregunta:

> A que parte del negocio pertenece este costo?

Ejemplos:

- Booking;
- Label;
- Marketing;
- Digitales;
- Administracion;
- Proyecto Set Padel;
- Artista Aneley;
- Oficina general.

### Como se guarda

No conviene agregar una columna nueva por cada posibilidad.

Conviene guardar lineas de distribucion:

- movimiento_id;
- tipo de destino: area, artista, proyecto, empleado, tercero;
- destino;
- porcentaje o importe;
- nota.

Asi el movimiento puede ser simple, pero tambien soportar casos mixtos.

## Salarios y ABM de empleados

El ABM de empleados debe guardar configuracion estable:

- empleado;
- funciones;
- usuario/permisos;
- salario pactado si corresponde;
- moneda;
- vigencia desde/hasta;
- financiacion esperada;
- imputacion interna esperada.

Pero eso no genera impacto financiero por si solo.

El impacto nace cuando se genera/carga el movimiento mensual:

- salario enero 2026;
- pagado;
- parcial;
- pendiente;
- financiado por Indyana/externo;
- imputado a areas/proyectos.

Esto permite:

- proyectar egresos futuros;
- registrar pagos reales;
- auditar diferencias entre pactado y pagado.

### Primer corte implementado

El empleado puede tener una condicion de compensacion:

- sin compensacion fija;
- salario mensual;
- salario mensual + comision de booking;
- solo comision de booking.

Regla:

- el salario configurado en el ABM no mueve caja;
- la comision de booking se configura en el modulo de Comisiones;
- el pago real de sueldo, anticipo o deuda salarial se carga en Movimientos
  Financieros como `Salario / compensacion`;
- los gastos de oficina o estructura se cargan como movimientos financieros de
  area `Administracion` o `Estructura`;
- mientras el modelo operativo siga usando `artist` como campo obligatorio en
  movimientos financieros, oficina y sueldos se registran bajo la unidad interna
  `VPO Corp / estructura`; esa unidad no es artista de booking;
- mas adelante, estos datos alimentan proyeccion y BI sin cambiar el hecho
  original.

Esto mantiene separados:

- condicion pactada del empleado;
- pago real;
- comision variable;
- estructura/oficina.

### Distribucion economica de un pago

Un movimiento financiero tiene dos lecturas:

- caja real: cuanto entro o salio de Indyana;
- imputacion economica: que parte es costo real de Indyana y que parte queda a
  cobrar o imputar a otra parte.

Ejemplo:

- salario Pablo pactado: USD 1.000;
- Indyana paga: USD 1.000;
- Indyana asume economicamente: USD 500;
- productora externa asume: USD 500.

La carga correcta es:

- movimiento principal: `Salario / compensacion`, pagado real USD 1.000 por
  Indyana;
- distribucion economica:
  - `Costo Indyana`: USD 500;
  - `Cuenta por cobrar a tercero`: USD 500.

Regla:

- si no se carga distribucion, el sistema asume 100% costo Indyana;
- si se carga distribucion, la suma debe cerrar contra el compromiso total del
  movimiento;
- la cuenta por cobrar a tercero no aumenta el costo de oficina, aunque haya
  salido de caja;
- cuando el tercero pague, se carga otro movimiento de cobro y se aplica contra
  esa cuenta por cobrar.

## Proyeccion y BI

La proyeccion no debe mezclarse con caja real.

Debe tener tres capas:

1. Real: ya paso y esta cargado.
2. Comprometido: esta pactado o pendiente, pero no pagado.
3. Proyectado: estimacion futura.

Ejemplos:

- sueldo mensual activo;
- gasto recurrente de oficina;
- cachets agendados;
- regalias proyectadas;
- recuperos esperados.

La carga diaria solo registra hechos y compromisos. El BI calcula escenarios.

## Estados

Estados visibles recomendados:

- Borrador.
- Enviado.
- Pendiente de control.
- Observado.
- Aprobado.
- Aplicado.
- Cerrado.
- Anulado.

Regla:

- borrador/enviado puede corregirse segun permiso;
- aprobado no se pisa;
- si hay error, se anula o se corrige con otro movimiento;
- cerrado significa que ya no tiene saldo pendiente.

## Relacion con Booking

Booking sigue siendo fuente de verdad de shows.

Booking genera:

1. Resultado del show.
2. Caja del show.
3. Saldo de cuenta corriente si no cerro.
4. Aplicaciones de recupero si se aparto plata para un proyecto recuperable.

Movimientos Financieros no debe duplicar un show.

Si hay un saldo de booking, debe verse en Finanzas Artista como cuenta corriente,
pero con origen booking.

## Ciclo booking -> cuenta corriente -> finanzas

Este punto es critico porque Booking ya esta generando informacion financiera.

Hoy la carga de booking calcula:

- cuanto deberia cobrar Indyana;
- cuanto deberia cobrar/pagar el artista;
- cuanto recibio efectivamente Indyana;
- cuanto recibio efectivamente el artista;
- si quedo deuda del boliche;
- si hay recuperos antes del split;
- si hay seÃ±as o rendiciones.

La cuenta corriente de booking debe nacer de la diferencia entre:

- objetivo de caja correcto;
- caja real cargada;
- deuda del boliche si corresponde.

### Lectura actual

En el modelo actual, la cuenta corriente de booking se lee desde los saldos
guardados en el show:

- `balance_producer_amount`: saldo a favor/en contra de Indyana;
- `balance_artist_amount`: saldo a favor/en contra del artista;
- `venue_balance_amount`: deuda del boliche/cliente.

Eso permite ver saldos en Finanzas Artista, pero todavia no es una cuenta
corriente operativa completa para pagar, compensar o cerrar saldos sin tocar el
show.

### Regla de negocio

El show no debe reescribirse para saldar una deuda posterior.

Si un show quedo con saldo:

- el show conserva su liquidacion original;
- la cuenta corriente registra el saldo;
- un pago posterior debe aplicarse contra esa cuenta corriente;
- una compensacion con otro show debe quedar trazada;
- un ajuste debe ser otro movimiento, no una edicion silenciosa del show.

### SeÃ±as y rendiciones

Las seÃ±as y rendiciones no cambian el split.

Solo reducen o aumentan lo que queda por cobrar/pagar.

Ejemplos:

- Indyana debia cobrar 300 y ya cobro seÃ±a de 200: queda por cobrar 100.
- Artista debia cobrar 300 y ya cobro seÃ±a de 500: queda saldo a favor de
  Indyana por 200.
- Indyana cobro una seÃ±a que excede su parte: puede generar deuda de Indyana
  al artista.

### Booking compartido

Las liquidaciones compuestas generan shows hijos. La cuenta corriente fina debe
vivir en los hijos, porque los hijos son los shows reales de cada artista.

El show madre sirve para explicar el evento completo y controlar la caja global,
pero no debe duplicar la cuenta corriente del artista.

Riesgo a validar:

- si se carga caja en el madre pero no se sincroniza bien con las hijas, puede
  quedar el madre cerrado y las hijas con saldo abierto, o al reves.

Por eso, antes de considerar confiable la cuenta corriente, hay que validar
casos testigo de:

- show simple con saldo a favor de Indyana;
- show simple con saldo a favor del artista;
- show con seÃ±a a Indyana;
- show con seÃ±a al artista;
- show con deuda de boliche;
- show con recupero antes del split;
- liquidacion compuesta con madre e hijas;
- edicion posterior de una hija;
- pago posterior que salda cuenta corriente.

### Tabla operativa futura

El esquema cloud ya contempla una tabla de cuenta corriente de booking:

`booking_current_account_entries`

La decision a validar es cuando pasar de lectura derivada a cuenta corriente
operativa.

Propuesta:

1. Mantener por ahora la lectura derivada para no romper booking.
2. Auditar que los saldos derivados sean correctos.
3. Crear entradas explicitas de cuenta corriente al cerrar/aprobar shows.
4. Permitir pagos/compensaciones contra esas entradas.
5. Finanzas Artista debe leer la cuenta operativa cuando exista, no recalcular
   todo desde cero.

### Movimiento padre de cuenta corriente booking

Para pagos, cobros o compensaciones que resuelven mas de un show, no alcanza con
aplicar saldo show por show como accion aislada.

Debe existir un movimiento padre de cuenta corriente booking.

Ese movimiento padre representa el hecho financiero real o la decision operativa:

- Aneley transfiere 2.800.000 para saldar shows pendientes;
- Indyana transfiere 900.000 al artista por saldos acumulados;
- un artista no cobra un show nuevo porque ese saldo se aplica contra deuda vieja;
- se aprueba un ajuste administrativo por una diferencia incobrable o perdonada.

El movimiento padre debe guardar:

- fecha;
- artista o tercero;
- tipo de movimiento;
- si hubo caja real o si fue compensacion sin caja nueva;
- importe total;
- metodo de pago si corresponde;
- comprobante o referencia;
- notas;
- usuario que lo cargo;
- aplicaciones hijas contra shows concretos.

Las aplicaciones hijas indican como se distribuye el importe:

- show destino;
- saldo afectado: artista, Indyana/productora o boliche;
- importe aplicado;
- saldo anterior;
- saldo posterior;
- si el show queda cerrado o sigue abierto.

El usuario debe poder elegir aplicacion manual. El sistema puede ofrecer un helper
para sugerir aplicacion por antiguedad, pero la sugerencia no debe guardar nada sin
confirmacion.

Reglas:

- no aplicar mas que el importe disponible del movimiento padre;
- no aplicar mas que el saldo abierto de cada show;
- si el importe no alcanza, el ultimo show queda parcialmente abierto;
- si sobra importe, el sobrante queda como saldo no aplicado o cuenta corriente a
  favor, pero no se inventa un ingreso de show;
- la aplicacion no cambia cachet, split, gastos ni caja original del show;
- si un saldo queda en cero, el show puede pasar a verde con etiqueta historica;
- si queda saldo vivo, el show mantiene alerta.

Tipos minimos de movimiento padre:

- `cobro_deuda_booking`: entra plata real a Indyana para saldar saldos a favor de
  Indyana.
- `pago_saldo_artista`: sale plata real de Indyana para saldar saldos a favor del
  artista.
- `compensacion_booking`: no entra ni sale plata nueva; se cruza una deuda contra
  otro saldo.
- `pago_deuda_boliche`: entra plata real de cliente/boliche contra deuda de cachet.
- `ajuste_booking`: decision administrativa aprobada, con nota obligatoria.

Ubicacion de pantalla recomendada:

`Finanzas Artista > Cuenta Booking > Registrar movimiento`

Esta pantalla debe convivir con `Saldar / aplicar` desde un show. La accion desde
el show sirve para casos puntuales. El movimiento padre sirve para pagos grandes,
pagos acumulados o compensaciones contra varios shows.

## Relacion con Regalias

Regalias sigue siendo fuente de verdad de ingresos digitales.

En esta etapa:

- alimenta reportes;
- puede alimentar BI;
- puede, mas adelante, aplicar recuperos o adelantos.

No se debe cargar a mano una regalia como movimiento financiero salvo ajuste
aprobado.

## Pantalla Finanzas Artista

Debe ser una pantalla de lectura humana, no de carga principal.

Debe abrir con:

- selector de artista;
- resumen claro;
- estado de cuenta corriente;
- proyectos/inversiones;
- recuperables;
- booking;
- detalle tecnico opcional.

No debe mostrar primero el ledger crudo.

El ledger queda como auditoria.

## Pantalla Movimientos Financieros

Debe ser la pantalla de carga.

Modo operador:

- muestra solo lo que puede cargar;
- respeta artistas permitidos;
- puede ocultar historial si no tiene permiso;
- envia a control.

Modo admin/administracion:

- ve historial;
- filtra;
- aprueba;
- observa;
- anula;
- aplica a cuenta corriente o recuperables.

## Casos testigo

### Virrshi

Debe poder representar:

- DJ sets pagados por Indyana;
- recuperables;
- recupero desde booking antes del split;
- FIFO al recuperable mas viejo si se configura asi;
- show cerrado aunque el recuperable siga abierto;
- cuenta corriente separada del proyecto.

### Aneley

Debe poder representar:

- deuda de booking con manager/familia;
- gastos de proyectos pagados por Dami/manager;
- inversion de Indyana;
- gastos recuperables o no recuperables;
- pagos que bajan cuenta corriente;
- proyectos como Set Padel / Por El Mundo.

### Bianca

Debe poder representar:

- inversiones no recuperables;
- gastos pendientes de pago;
- proyectos de label/marketing/management;
- tipo de cambio por movimiento.

### Sueldos

Debe poder representar:

- salario pactado en ABM empleado;
- movimiento mensual real;
- parcial o pendiente;
- financiacion Indyana/externo;
- imputacion a areas;
- visibilidad restringida.

### Project manager

Debe poder:

- cargar gastos de sus artistas;
- adjuntar notas/comprobantes;
- indicar que pago el gasto con plata propia y generar reintegro pendiente;
- no ver saldos generales si no corresponde;
- no aprobar sus propios movimientos salvo permiso especial.

## Lo que no queremos

- No queremos una pantalla con todos los campos siempre visibles.
- No queremos duplicar datos de booking como movimientos manuales.
- No queremos llamar legacy a gastos reales viejos.
- No queremos que un operador vea sueldos o saldos sensibles por accidente.
- No queremos parches por artista.
- No queremos que la cuenta corriente sea lo mismo que rentabilidad.
- No queremos que un recupero cierre sin trazabilidad.

## Implementacion propuesta

### Etapa 1 - Rector validado

Este documento queda como guia para los cambios siguientes. Cualquier cambio de
Finanzas, Movimientos Financieros o Finanzas Artista debe respetar:

- hecho primero;
- tratamiento despues;
- aplicacion/cierre por separado;
- permisos por modulo, artista/proyecto y sensibilidad.

### Etapa 2 - Auditoria de pantalla actual

Revisar Movimientos Financieros actual:

- campos que ya sirven;
- campos que deben pasar a avanzado;
- campos que deben depender del tipo;
- campos que deben esconderse por permiso;
- campos que necesitan lista/selector.
- campos tecnicos que no deben mostrarse al operador.

### Etapa 3 - Reordenar UI sin cambiar datos

Usar los mismos endpoints/tablas actuales, pero mostrar el formulario por
intencion.

Objetivo: que la pantalla sea mas clara sin migracion de datos.

### Etapa 4 - Permisos finos por intencion

Aplicar:

- puede cargar;
- puede ver historial;
- puede editar;
- puede aprobar;
- alcance por artista;
- ocultar salarios salvo permiso explicito.

### Etapa 5 - Lineas de distribucion

Agregar soporte formal para:

- multiples conceptos;
- imputacion interna;
- financiacion mixta;
- sueldos;
- estructura.

### Etapa 6 - Recuperos y cuenta corriente

Formalizar:

- recuperables abiertos;
- aplicaciones;
- cuenta corriente por origen;
- compensaciones.

### Etapa 7 - Proyecciones

Con datos reales y compromisos:

- flujo mensual;
- ingresos vs egresos;
- artistas rentables/no rentables;
- recuperables futuros;
- salarios y estructura.

## Decision de producto

La pantalla no debe intentar parecer un sistema contable tradicional.

Debe parecer una herramienta operativa de VPO:

- simple para cargar;
- fuerte para auditar;
- clara para permisos;
- preparada para BI;
- trazable hasta el origen.

La contabilidad vive debajo. El usuario ve negocio.
