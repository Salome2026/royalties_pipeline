# Finanzas - notas de cambio controlado

## 2026-07-06 - Reordenamiento de Movimientos Financieros

Checkpoint antes de cambios:

- `git HEAD`: `d069512`
- Estado previo observado: el arbol ya tenia cambios sin commitear en backend,
  schema, booking docs y frontend. Esta entrada no valida ni revierte esos
  cambios; solo deja trazabilidad del nuevo trabajo financiero.
- Archivos que se planea tocar primero:
  - `docs/finance_operational_model_v2.md`
  - `docs/README.md`

Decision validada:

- `finance_operational_model_v2.md` pasa a ser el documento rector operativo
  para finanzas.
- `recuperable` no debe ser un tipo principal de movimiento. Debe ser un
  tratamiento financiero aplicable a un gasto, inversion, adelanto o proyecto.
- La pantalla de Movimientos Financieros debe empezar por una pregunta humana:
  `Que estas cargando?`
- La complejidad debe aparecer en bloques dinamicos y permisos, no como una
  sabana de campos siempre visible.

Si el enfoque no funciona:

1. Volver a tratar `finance_operational_model_v2.md` como borrador.
2. Restaurar el criterio anterior: tipos principales con `Gasto recuperable`
   separado.
3. No cambiar datos ya cargados sin una migracion explicita.
4. No tocar Booking ni Regalias para corregir problemas de pantalla financiera.

### Auditoria rapida de pantalla actual

Archivo revisado:

- `web/app/page.tsx`

Hallazgos:

- La pantalla actual muestra al mismo nivel:
  - datos del hecho: fecha, artista, area, categoria, proyecto, concepto,
    contraparte, importe, pagado, moneda, tipo de cambio;
  - tratamiento financiero: recuperable, porcentaje, metodo, impacto esperado,
    costo artista/productora;
  - control tecnico: estado, origen, referencia origen;
  - auditoria: comprobantes/notas.
- El selector `Tipo` actual mezcla hechos y tratamientos:
  - `gasto`, `ingreso`, `adelanto`, `prestamo`, `ajuste`, `pago` son hechos;
  - `recupero` es ambiguo porque puede ser una aplicacion contra un recuperable,
    no el gasto/proyecto original.
- El campo `Origen` muestra valores tecnicos como `legacy`, `booking`,
  `royalties` e `import`. Eso debe quedar en avanzado/admin, no como parte
  central de la carga diaria.
- `Multiples conceptos` hoy no guarda un movimiento padre con lineas hijas:
  guarda varias filas separadas con los mismos datos generales. Sirve como
  operacion rapida, pero no como estructura financiera definitiva.

Clasificacion propuesta para la UI:

- Siempre visible:
  - fecha;
  - que estas cargando;
  - artista/proyecto/empleado/proveedor segun corresponda;
  - area;
  - categoria;
  - concepto;
  - importe;
  - moneda/tipo de cambio;
  - quien pago;
  - a quien se pago o de quien viene;
  - estado de pago;
  - comprobantes/notas.
- Dinamico:
  - recuperable;
  - cuenta corriente;
  - proveedor pendiente;
  - salario/periodo;
  - financiacion mixta;
  - distribucion interna;
  - aplicacion a shows o recuperables.
- Admin/avanzado:
  - impacto esperado;
  - origen tecnico;
  - referencia origen;
  - estado aprobado/aplicado/anulado;
  - ajustes excepcionales.

Siguiente paso recomendado:

Reordenar solo la interfaz de `Movimientos financieros`, usando los mismos datos
y endpoints. No migrar tablas todavia. El objetivo es que Ruben pueda cargar lo
mismo que hoy, pero con flujo por intencion y sin campos tecnicos visibles de
entrada.

### Cambio UI inicial permitido

Alcance:

- Solo `web/app/page.tsx`.
- Sin cambios de base.
- Sin cambios de API.
- Sin migracion de datos.

Cambios esperados:

- `Tipo` pasa a mostrarse como `Que estas cargando?`.
- `Recuperable / impacto / metodo` queda agrupado como `Tratamiento financiero`.
- `Estado`, `Origen` y `Referencia origen` pasan a `Avanzado / auditoria`.
- Se conserva el mismo payload para evitar riesgo operativo.

### Sueldos y estructura - primer corte

Decision:

- el ABM de empleados guarda la condicion estable de compensacion;
- Movimientos Financieros registra cada pago real de sueldo, deuda, anticipo o
  gasto de oficina/estructura;
- las comisiones de booking siguen en su configurador propio y no se mezclan
  con salario fijo.

Campos estables en empleado:

- tipo de compensacion: sin fija, salario mensual, salario + comision booking,
  solo comision booking;
- salario pactado;
- moneda;
- frecuencia mensual;
- notas.

Primer alcance:

- no genera pagos automaticos;
- no calcula liquidacion mensual todavia;
- deja la base lista para proyecciones y BI.

Nota operativa:

- mientras `finance_movements` siga exigiendo un campo `artist`, los gastos de
  salario/oficina/estructura usan la unidad interna `VPO Corp / estructura`;
- esa unidad no debe convertirse en artista de booking;
- para permisos finos futuros, lo correcto es agregar alcance por unidad/proyecto
  financiero, no ensuciar el ABM de artistas.

### Distribucion economica de pagos

Nueva regla:

- el movimiento principal guarda caja/compromiso real;
- la distribucion economica define cuanto es costo Indyana y cuanto queda como
  cuenta por cobrar a terceros u otra imputacion;
- por defecto, sin distribucion cargada, se interpreta 100% costo Indyana;
- con distribucion manual, la suma debe cerrar con el compromiso total del
  movimiento.

Caso guia:

- salario Pablo USD 1.000 pagado por Indyana;
- costo oficina Indyana USD 500;
- cuenta por cobrar a productora externa USD 500.
