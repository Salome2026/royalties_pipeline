# Plan: gastos historicos de artistas y proyectos

## Objetivo

Crear una capa de carga y control para gastos historicos de artistas, proyectos y recuperos, sin ensuciar la cuenta corriente oficial hasta que cada movimiento sea revisado.

La idea es poder cargar toda la informacion vieja que hoy vive en planillas, WhatsApp, comprobantes y notas, conservarla completa, y despues decidir con criterio si cada gasto es inversion de Indyana, recuperable, adelanto, ajuste o descarte.

## Principio base

Primero se guarda todo. Despues se controla. Recien cuando esta controlado impacta en el ledger oficial.

Esto sigue la misma logica que usamos en regalias:

1. conservar el dato crudo o historico;
2. normalizarlo;
3. validarlo;
4. recien despues usarlo para reportes, saldos o pagos.

## Capas del sistema

### 1. Staging de gastos

Es la primera entrada de informacion.

Un gasto cargado aca:

- pertenece a un artista o a un proyecto;
- puede venir de una planilla vieja, comprobante, WhatsApp o carga manual;
- queda pendiente de control;
- no modifica automaticamente la cuenta corriente oficial;
- conserva la fuente de origen para poder auditarlo.

### 2. Control

Cada fila pendiente debe poder revisarse y clasificarse.

Estados esperados:

- `pendiente_control`
- `controlado_inversion_indyana`
- `controlado_recuperable`
- `controlado_adelanto`
- `descartado`
- `dudoso`

### 3. Ledger oficial

Cuando una fila se aprueba, el sistema genera el movimiento real que corresponda:

- gasto asumido por Indyana;
- gasto recuperable contra booking;
- gasto recuperable contra digitales;
- adelanto al artista;
- ajuste de cuenta corriente;
- recupero parcial o total de un gasto anterior.

## Listas maestras

Para evitar errores de tipeo, estos campos no deberian ser texto libre en la carga final. Deben salir de listas.

Listas principales:

- artistas;
- proyectos;
- areas de negocio;
- categorias;
- subcategorias;
- proveedores;
- responsables;
- tipos de movimiento;
- estados de control.

## Proyecto

El proyecto tiene que existir como entidad propia.

Ejemplos:

- `DJ Set Virrshi Mayo 2026`
- `Campaña El Motorcito`
- `Gira Aneley Catamarca / San Juan`
- `Video Super Junte`
- `Lanzamiento Laalo Abril 2026`
- `Booking Candu + G Sony`

Un proyecto puede tener:

- artista principal;
- artistas relacionados;
- area de negocio;
- presupuesto estimado;
- gastos reales;
- recuperos;
- ingresos asociados;
- estado;
- notas.

## Campos propuestos para staging

Campos minimos:

- `id`
- `artist_id`
- `artist_name`
- `expense_date`
- `business_area`
- `project_id`
- `project_name`
- `category`
- `subcategory`
- `concept`
- `amount_ars`
- `amount_usd`
- `fx_rate`
- `currency_original`
- `amount_original`
- `recoverable`
- `recovery_method`
- `artist_percent`
- `producer_percent`

`recovery_method` evita ambiguedad. Un gasto recuperable puede recuperarse antes del split, despues del split, contra cuenta corriente directa, contra regalias o por aplicacion manual. Esto permite distinguir caja recuperada de costo economico real.
- `recoupment_basis`
- `control_status`
- `controlled`
- `impact_ledger`
- `source_file`
- `source_sheet`
- `source_row`
- `evidence_url`
- `notes`
- `created_at`
- `updated_at`
- `controlled_at`

## Areas de negocio iniciales

Propuesta inicial:

- `booking`
- `digitales`
- `marketing`
- `label`
- `produccion`
- `general`

Estas areas pueden ajustarse cuando empecemos a cargar datos reales.

## Categorias iniciales

Propuesta inicial:

- `musicos`
- `tour_manager`
- `viaticos`
- `movilidad`
- `produccion`
- `dj_set`
- `video`
- `marketing`
- `publicidad`
- `adelanto`
- `comision`
- `alquiler`
- `equipamiento`
- `otros`

Regla operativa: no crear demasiadas categorias al principio. Si algo no encaja, entra como `otros` con buen concepto y nota, y despues se normaliza.

## Recuperables

Un gasto recuperable debe poder indicar:

- si se recupera contra booking, digitales o ambos;
- si se recupera antes del split o despues del split;
- porcentaje del artista;
- porcentaje de Indyana;
- proyecto relacionado;
- saldo original;
- recuperado acumulado;
- saldo pendiente.

Ejemplo:

Indyana paga un DJ set de Virrshi por 300.000.

Si el acuerdo es 70/30:

- Virrshi debe recuperar/asumir 70%;
- Indyana asume 30%;
- cada recupero futuro debe quedar trazado contra ese gasto.

## Cuenta corriente vs resultado del artista

Hay una separacion conceptual importante:

La cuenta corriente del artista no es lo mismo que la rentabilidad del artista para Indyana.

### Cuenta corriente del artista

Responde la pregunta:

> Quien le debe a quien?

Ejemplos:

- Indyana cobro una seña que correspondia al artista;
- el artista cobro mas de lo que le correspondia;
- se le dio un adelanto;
- se le desconto un recupero;
- quedo saldo pendiente de un show;
- el artista pago algo que Indyana le debe reconocer.

Estos movimientos generan saldo financiero directo entre Indyana y el artista.

Un artista puede tener cuenta corriente en cero y, al mismo tiempo, Indyana puede haber invertido mucho dinero en ese artista.

### Resultado / inversion por artista

Responde la pregunta:

> Cuanto genero este artista y cuanto invertimos en el?

Acá entran:

- ingresos de booking para Indyana;
- ingresos digitales para Indyana;
- gastos de marketing;
- videoclips;
- DJ sets;
- campamentos;
- viajes promocionales;
- produccion musical;
- gastos asumidos por la productora;
- gastos dudosos o todavia sin asignar.

Estos movimientos pueden afectar el resultado economico del artista sin generar deuda del artista.

Ejemplo:

Indyana puede haber ganado 2.000.000 por shows de un artista, pero haber invertido 6.000.000 en marketing, videoclips y produccion. En ese caso, la cuenta corriente artista puede estar en cero, pero el resultado economico del artista para Indyana sigue negativo.

## Impactos por movimiento

Cada gasto o movimiento deberia poder indicar varias dimensiones de impacto:

- `impacta_cuenta_corriente_artista`;
- `impacta_resultado_artista`;
- `impacta_caja_indyana`;
- `es_recuperable`;
- `estado_control`.

Esto evita mezclar conceptos.

Un gasto puede:

- afectar la caja de Indyana;
- afectar la rentabilidad del artista;
- no generar deuda del artista;
- quedar pendiente de decidir si es recuperable.

## Ejemplo: Partido de la Costa

Puede haber gastos como `Partido de la Costa`, donde un project manager acompaño artistas durante una temporada de shows.

Ese gasto puede tener varias interpretaciones:

- gasto de booking asociado a shows;
- gasto promocional asumido por Indyana;
- gasto parcialmente recuperable;
- gasto general de proyecto;
- gasto dudoso hasta revisar.

No debe forzarse automaticamente como deuda del artista.

Carga inicial sugerida:

- `proyecto`: Partido de la Costa Verano;
- `area_negocio`: booking;
- `categoria`: viaticos / movilidad / produccion;
- `impacta_cuenta_corriente_artista`: no;
- `impacta_resultado_artista`: si;
- `impacta_caja_indyana`: si;
- `es_recuperable`: pendiente_definir;
- `estado_control`: dudoso o pendiente_control.

Esto conserva la verdad economica: Indyana gasto dinero, pero todavia no se decidio si corresponde asignarlo al artista, al proyecto, a una gira o asumirlo como inversion.

## Relacion con booking

Cuando en un show se descuenta un recupero:

- el show puede cerrar normalmente;
- el movimiento debe quedar asociado al gasto recuperable original;
- la caja del show debe explicar cuanto fue para artista, cuanto para Indyana y cuanto se uso para recuperar;
- el saldo pendiente del gasto recuperable debe bajar.

Importante: un show puede estar cerrado aunque exista cuenta corriente abierta. Son cosas distintas.

## Relacion con digitales

Mas adelante, un gasto recuperable tambien podria descontarse de regalias digitales.

Por eso el staging no debe asumir que todo se recupera por booking. Debe dejar abierta la dimension:

- `booking`
- `digitales`
- `manual`
- `mixto`

## Reglas de seguridad

- No cargar gastos historicos directamente al ledger oficial.
- No borrar informacion vieja sin conservar fuente y motivo.
- No permitir proyectos, artistas o categorias escritos libremente en la version final.
- No considerar un gasto como recuperable si no fue revisado.
- No mezclar caja real con liquidacion teorica.
- No modificar saldos oficiales hasta que haya aprobacion/control.

## Jerarquia de fuentes historicas

La fuente original de gastos Indyana es el Google Sheet de gastos Indyana.

Las planillas de project managers (`PM Salome`, `PM Santiago`, `PM Lautaro`, `PM David`, etc.) pueden contener copias de esa informacion con cierto intento de normalizacion, pero no deben considerarse automaticamente como fuente primaria para esos mismos gastos.

Regla:

1. Si un gasto aparece en Google Indyana y tambien en una PM, la fila canonica es Google Indyana.
2. La fila PM se conserva como referencia o contexto, pero no se importa como movimiento nuevo.
3. Si una PM trae un dato que no aparece en Google Indyana, ese dato no se descarta: queda como candidato real pendiente de control.
4. Si un gasto aparece duplicado dentro de la misma PM, no se elimina automaticamente: se marca como `posible_duplicado_interno`.
5. Las PM siguen siendo utiles para shows, caja, vistas de control, datos faltantes y contexto operativo.

Esto evita duplicar gastos al reconstruir informacion historica.

## Flujo operativo inicial

1. Importar o cargar gastos historicos en staging.
2. Dejar todo como `pendiente_control`.
3. Revisar por artista.
4. Asignar proyecto, area, categoria y subcategoria.
5. Marcar si es inversion, recuperable, adelanto, ajuste o descarte.
6. Si es recuperable, definir regla de recupero.
7. Aprobar.
8. Generar movimiento oficial en ledger.
9. Usar el ledger para reportes de cuenta corriente.

## Pantalla futura

Nombre sugerido: `Gastos y cuenta corriente`

Secciones:

- pendientes de control;
- gastos controlados;
- recuperables abiertos;
- cuenta corriente por artista;
- proyectos;
- comprobantes;
- resumen por area de negocio.

Filtros:

- artista;
- proyecto;
- area;
- categoria;
- estado;
- fecha;
- recuperable si/no.

## Decision actual

Por ahora no se implementa toda la logica contable completa.

El siguiente paso tecnico recomendado es crear la estructura de staging y permitir cargar gastos pendientes sin impacto oficial. Luego, con casos reales, se define la pantalla de control y la promocion al ledger.

## Casos patron ya aprendidos

Estos casos no son excepciones aisladas. Son patrones de negocio que deben
guiar la pantalla futura.

### Caso Virrshi - gasto recuperable

Virrshi tiene gastos de produccion, principalmente DJ sets, que Indyana puede
pagar inicialmente.

Regla aprendida:

- el gasto original se carga como salida de Indyana;
- puede ser recuperable total o parcialmente;
- puede recuperarse desde booking;
- debe quedar asociado a un proyecto concreto;
- cada recupero debe bajar el saldo pendiente del gasto original;
- el show puede estar cerrado aunque el recuperable siga vivo.

Ejemplo:

- proyecto: `DJ Set Virrshi`
- gasto: 500.000
- recuperable: si
- criterio posible: 70% artista / 30% Indyana
- recupero desde show: 100.000
- saldo pendiente: se recalcula contra el gasto original.

Hay dos formas de recuperar, y deben cargarse explicitamente:

- `antes_del_split`: se descuenta del neto del show antes de repartir;
- `contra_parte_artista`: se descuenta de lo que le corresponde al artista.

La diferencia es importante. Si se recupera antes del split, Indyana tambien
reduce su aporte economico. Si se recupera contra parte artista, Indyana asume
su porcentaje como inversion.

### Caso Aneley - manager externo paga gastos de inversion

Aneley tiene un responsable externo/familiar que administra parte de la caja y
puede pagar gastos que en realidad corresponden a Indyana.

Regla aprendida:

- el show se liquida igual que siempre;
- el saldo de booking se mantiene como cuenta corriente;
- los gastos externos no deben meterse automaticamente como gasto del show;
- si el manager pago una inversion que corresponde 100% a Indyana, eso genera
  un credito a favor del manager contra la cuenta corriente de booking;
- el gasto igualmente debe quedar en resultado/proyecto de Indyana.

Ejemplo real:

- saldo booking validado a favor de Indyana: 1.532.770
- proyecto: `Set Padel`
- contenido: `Para el Mundo`
- gastos pagados por padre/manager: 562.000
- tratamiento: inversion Indyana 100%
- saldo neto a rendir por manager: 970.770

Esto no es un recupero de artista. Es un gasto de Indyana pagado por un tercero.
Por eso impacta de dos maneras:

- baja la cuenta corriente que el manager tiene con Indyana;
- aumenta la inversion/resultado de Indyana en el proyecto/artista.

## Modelo funcional de la pantalla

La pantalla de `Gastos y cuenta corriente` debe permitir cargar manualmente
movimientos sin depender de planillas externas.

La carga debe empezar simple:

1. elegir artista o proyecto;
2. fecha;
3. concepto;
4. importe;
5. quien pago;
6. area de negocio;
7. categoria/subcategoria;
8. estado de control;
9. comprobante/notas.

Despues, segun el tipo elegido, se muestran campos adicionales.

### Tipo: inversion Indyana

Uso:

- videoclip;
- marketing;
- streaming;
- produccion;
- gastos que Indyana decide asumir.

Impacto:

- impacta caja/resultado de Indyana;
- impacta resultado del artista/proyecto;
- no genera deuda del artista;
- si lo pago un tercero, genera credito de ese tercero contra Indyana.

Campos especiales:

- `pagado_por`: Indyana / artista / manager / tercero;
- `reconocer_como_credito`: si/no;
- `tercero_responsable`: nombre si no es Indyana.

### Tipo: gasto recuperable

Uso:

- DJ set recuperable;
- adelanto recuperable;
- produccion recuperable por contrato.

Impacto:

- genera saldo recuperable;
- puede recuperarse por booking, digitales o manual;
- debe tener proyecto origen;
- cada recupero debe quedar trazado.

Campos especiales:

- porcentaje artista;
- porcentaje Indyana;
- metodo de recupero: `antes_del_split`, `contra_parte_artista`, `manual`;
- fuente de recupero permitida: booking / digitales / manual / mixto;
- saldo original;
- recuperado acumulado;
- saldo pendiente.

### Tipo: adelanto

Uso:

- dinero entregado al artista;
- prestamo;
- pago anticipado.

Impacto:

- genera cuenta corriente contra artista;
- normalmente no afecta resultado de booking;
- puede recuperarse luego de digitales, booking o manualmente.

### Tipo: ajuste de cuenta corriente

Uso:

- diferencia aceptada;
- saldo viejo conciliado;
- error historico que se decide reconocer;
- pago de tercero que compensa deuda.

Impacto:

- mueve cuenta corriente;
- debe tener nota obligatoria;
- no debe esconder errores de liquidacion.

## Vistas necesarias

La futura pagina debe tener al menos estas vistas:

### 1. Carga rapida

Para cargar movimientos nuevos a mano.

Debe ser simple y no contable en apariencia. El usuario no deberia decidir
debitos/creditos, sino responder preguntas de negocio:

- que artista/proyecto es;
- quien pago;
- que tipo de gasto es;
- si se recupera o no;
- contra que se recupera;
- si ya esta controlado.

### 2. Pendientes de control

Lista de movimientos que todavia no impactan oficialmente.

Acciones:

- controlar;
- corregir datos;
- asignar proyecto;
- marcar recuperable;
- descartar;
- aprobar al ledger.

### 3. Cuenta corriente por artista

Debe responder:

- quien debe a quien;
- por que concepto;
- desde que fecha;
- que movimientos lo generaron;
- que pagos o recuperos lo cerraron.

No debe mezclarse con rentabilidad.

### 4. Resultado / inversion por artista

Debe responder:

- cuanto genero el artista por booking;
- cuanto genero por digitales;
- cuanto invirtio Indyana;
- cuanto queda recuperable;
- cuanto se asumio como inversion.

Esta vista puede mostrar perdida economica aun si la cuenta corriente esta en
cero.

### 5. Proyectos

Ejemplos:

- `Set Padel`
- `Para el Mundo`
- `DJ Set Virrshi`
- `Partido de la Costa`

Cada proyecto debe poder agrupar gastos, artistas, responsables, comprobantes y
recuperos.

## Regla de oro para implementar

No convertir la pantalla en un monstruo.

El sistema debe guardar toda la informacion, pero mostrar solo lo necesario en
cada momento:

- si es inversion simple, no mostrar recuperos;
- si es recuperable, mostrar saldo y regla;
- si lo pago un tercero, mostrar credito/cuenta corriente;
- si es solo dato historico, dejarlo pendiente de control.

La complejidad debe estar en el modelo, no en la experiencia del usuario.
