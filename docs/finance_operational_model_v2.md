# Modelo financiero operativo VPO - borrador rector v2

Fecha: 2026-07-05

Estado: borrador para validar con Ruben.

Este documento busca ordenar la parte financiera de VPO sin forzar la realidad
operativa a una pantalla contable incomoda. La regla principal es simple:

> El usuario carga hechos del negocio. El sistema traduce esos hechos a caja,
> cuenta corriente, proyectos, recuperables, resultado y proyeccion.

No reemplaza todavia a `finance_business_master.md` ni a
`artist_finance_ledger_model.md`. Si Ruben lo valida, debe pasar a ser el
documento rector de finanzas y esos documentos quedan como soporte tecnico.

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
2. Gasto recuperable.
3. Adelanto o prestamo.
4. Pago o cobro de cuenta corriente.
5. Recupero aplicado.
6. Gasto de oficina / estructura.
7. Salario / compensacion.
8. Ingreso o ajuste manual.

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

### 2. Gasto recuperable

Uso:

- DJ set recuperable;
- produccion recuperable;
- adelanto recuperable por contrato;
- gasto que se recuperara desde booking/regalias/manual.

Muestra:

- porcentaje recuperable;
- forma de recupero;
- costo economico artista/Indyana;
- fuente esperada de recupero;
- proyecto origen;
- saldo recuperable.

Impacto:

- crea un saldo recuperable;
- no mueve cuenta corriente automaticamente;
- cada recupero futuro debe aplicarse contra este saldo.

### 3. Adelanto o prestamo

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

### 4. Pago o cobro de cuenta corriente

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

### 5. Recupero aplicado

Uso:

- desde booking se recupera una parte de un DJ set;
- desde regalias se recupera un adelanto;
- se aplica un pago manual a un recuperable.

Muestra:

- recuperable abierto;
- origen del dinero;
- monto aplicado;
- saldo pendiente.

Impacto:

- baja el saldo recuperable;
- no cambia la historia del show ni del gasto original.

### 6. Gasto de oficina / estructura

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

### 7. Salario / compensacion

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

### 8. Ingreso o ajuste manual

Uso:

- correccion aprobada;
- ingreso no nacido de booking ni regalias;
- ajuste excepcional.

Muestra:

- motivo obligatorio;
- aprobador;
- referencia.

Impacto:

- depende del subtipo;
- debe quedar auditado.

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
- si hay señas o rendiciones.

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

### Señas y rendiciones

Las señas y rendiciones no cambian el split.

Solo reducen o aumentan lo que queda por cobrar/pagar.

Ejemplos:

- Indyana debia cobrar 300 y ya cobro seña de 200: queda por cobrar 100.
- Artista debia cobrar 300 y ya cobro seña de 500: queda saldo a favor de
  Indyana por 200.
- Indyana cobro una seña que excede su parte: puede generar deuda de Indyana
  al artista.

### Liquidaciones compuestas

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
- show con seña a Indyana;
- show con seña al artista;
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

### Etapa 1 - Validar este documento

No tocar codigo hasta validar lenguaje, tipos y reglas.

### Etapa 2 - Auditoria de pantalla actual

Revisar Movimientos Financieros actual:

- campos que ya sirven;
- campos que deben pasar a avanzado;
- campos que deben depender del tipo;
- campos que deben esconderse por permiso;
- campos que necesitan lista/selector.

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
