# Booking VPO - Diseño de pantalla Carga Booking 2

Fecha de trabajo: 2026-05-15

Objetivo: definir una pantalla unificada para cargar booking sin separar artificialmente "booking simple", "liquidacion compuesta" y "casos especiales". Esta pantalla debe ser usable por data entry y suficientemente potente para los casos reales de VPO.

No reemplaza todavia las pantallas actuales. Primero debe existir en modo laboratorio.

## Nombre propuesto

`Carga Booking 2`

Nombre funcional futuro:

`Carga de Shows`

## Principios de uso

- El usuario carga datos, no hace cuentas.
- El sistema calcula sugeridos.
- La caja real se registra separada de la liquidacion sugerida.
- La hija/show operativo es fuente de verdad.
- La madre/evento guarda contexto, reglas y sugeridos.
- Nada se pisa automaticamente sin accion explicita.
- El sistema debe explicar diferencias con alertas claras.

## Layout general

Pantalla en dos columnas en desktop:

- Columna izquierda: formulario de carga.
- Columna derecha: resumen vivo, sugeridos, alertas y links a hijos/madre.

En mobile:

- Formulario por secciones plegables.
- Resumen fijo arriba o al final de cada bloque.

## Paso 1 - Tipo de carga guiada

Primer selector:

- `Show comun`
- `Show con regla especial`
- `Evento con varios artistas`
- `Evento externo / sociedad`
- `Historico / control`

Este selector solo cambia que secciones se muestran primero. No cambia la estructura de datos de fondo.

### Ayudas

Texto corto debajo:

- Show comun: un artista, gastos, split y rendicion.
- Regla especial: terceros, comisiones propias o splits no simples.
- Varios artistas: evento madre con lineas/hijos.
- Externo/sociedad: Caserio u otro evento donde se rinde caja a un tercero.
- Historico/control: cargar algo para visibilidad aunque no cierre aun.

## Paso 2 - Datos del evento

Campos:

- Fecha.
- Venue.
- Ciudad.
- Responsable / PM.
- Artista principal opcional.
- Cachet pactado.
- Cobrado real.
- Moneda.
- Tipo de cambio.
- Estado evento:
  - borrador
  - realizado
  - rendido
  - observado
  - cerrado
  - historico
- Comprobantes / links.
- Notas.

### Reglas

- Si cobrado real es menor que cachet pactado, aparece alerta de deuda boliche.
- Si cobrado real es menor que cachet pactado, el usuario debe elegir:
  - dejar saldo al boliche: se liquida sobre el cachet pactado y queda deuda;
  - ajustar cachet al cobrado: se liquida sobre el cobrado real y no queda deuda.
- Si cobrado real es 0 y cachet pactado > 0, sugerir estado `no cobrado` u `observado`.
- Si moneda es USD o el usuario ingresa `u$`, exigir tipo de cambio.

## Paso 3 - Gastos generales del evento

Lista editable de gastos.

Campos por gasto:

- Categoria desplegable.
- Concepto.
- Importe.
- Moneda opcional.
- Pagado por:
  - VPO
  - artista
  - PM
  - tercero
  - desconocido
- Comprobante.
- Notas.

Categorias base:

- sonido
- musicos
- tour_manager
- traslados_viaticos
- comida
- hotel
- produccion
- comision_externa
- varios

### Calculo

Base evento = cobrado real - gastos generales.

## Paso 4 - Comisiones directas del evento

Seccion opcional, visible para casos como Candu + G Sony.

Boton:

- `Agregar comision directa`

Campos:

- Concepto.
- Porcentaje o importe.
- Calculado sobre:
  - bruto
  - neto despues de gastos generales
  - importe manual
- Destinos:
  - salida directa a tercero
  - incorporar a una linea artistica
  - repartir entre destinos
- Caja manejada por VPO: si/no.
- Comisionable: si/no.
- Notas.

### Ejemplo Candu + G Sony

Comision directa 10%:

- Marcelo 50% salida directa.
- Gaston/Facha 50% incorporado a linea G Sony.

## Paso 5 - Lineas artisticas

Toda carga tiene al menos una linea.

Botones:

- `Agregar artista VPO`
- `Agregar artista externo`
- `Agregar tercero/comision`

Campos por linea:

- Tipo de linea:
  - artista_vpo
  - artista_externo
  - tercero
  - comision
- Artista desplegable si es VPO.
- Descripcion.
- Base asignada:
  - igual entre artistas VPO
  - porcentaje de base evento
  - importe manual
  - desde comision incorporada
- Ajuste de base.
- Gastos propios de la linea.
- Recuperos aplicados de gastos recuperables.
- Terceros externos de la linea.
- Split:
  - % artista
  - % Indyana
  - % terceros si corresponde
- Pagado artista.
- Recibido Indyana.
- Comisionable:
  - si
  - no
  - historico/no definido
- Motivo de comisionabilidad.
- Notas.

### Sugeridos por linea

Mostrar siempre:

- Base calculada.
- Gastos linea.
- Base split.
- Pago sugerido artista.
- Indyana sugerido.
- Terceros sugeridos.
- Marca de exclusion de comision general, si aplica.
- Diferencia artista.
- Diferencia Indyana.

Los sugeridos deben mostrar centavos cuando existan. Los totales generales pueden verse redondeados, pero los botones `Usar sugerido` deben cargar el valor exacto.

### Recuperos aplicados

Seccion opcional dentro de cada linea artistica.

Solo debe aparecer expandida si:

- El artista tiene gastos recuperables abiertos.
- O el usuario toca `Agregar recupero`.

Campos:

- Gasto recuperable origen:
  - desplegable con gastos abiertos del artista
  - ejemplo: `DJ set - saldo artista 140.000 / saldo total 200.000`
- Importe a recuperar.
- Tipo de recupero:
  - `contra parte artista` (default)
  - `antes del split`
  - `contra parte Indyana`
  - `manual`
- Importe aplicado a artista.
- Importe aplicado a Indyana.
- Saldo restante artista.
- Saldo restante total.
- Nota.

Comportamiento:

- Si el recupero es `contra parte artista`, baja solo el saldo recuperable del artista.
- Si el recupero es `antes del split`, baja la base de la linea/show y reparte el impacto segun el split contractual.
- Si el recupero es `contra parte Indyana`, baja solo la parte asumida por Indyana.
- Si es `manual`, Ruben define los importes.

Regla de negocio default:

- Para gastos recuperables con split contractual, el default debe ser `contra parte artista`.
- `Antes del split` se usa solo si explicitamente se quiere recuperar desde el bruto antes de repartir.

La pantalla no debe obligar a usar esta seccion si no hay recuperos. Debe ser clara y plegable.

### Importante

Si la linea tiene un show hijo existente, estos datos vivos deben leerse del show hijo.

La madre puede mostrar sugeridos, pero no debe pisar:

- gastos propios
- terceros
- pagado artista
- recibido Indyana
- estado de cierre

salvo que el usuario use una accion explicita.

## Paso 6 - Caja, señas y movimientos reales

Movimientos reales de dinero.

Boton:

- `Agregar movimiento de caja`

Campos:

- Recibio:
  - Indyana
  - artista
  - PM
  - tercero
  - Caserio/externo
- Concepto:
  - seña
  - saldo show
  - reintegro
  - pago artista
  - pago tercero
  - otro
- Importe.
- Metodo:
  - transferencia
  - efectivo
  - otro
- Pagado por / recibido de.
- Comprobante.
- Notas.

### Regla

La caja no reemplaza el sugerido. Si lo real no coincide, se genera saldo/alerta.

## Paso 7 - Resumen vivo

Panel fijo con:

- Cachet pactado.
- Cobrado real.
- Deuda boliche.
- Gastos generales.
- Base evento.
- Total asignado a lineas.
- Diferencia no asignada.
- Indyana ganado total.
- Comisiones aplicables estimadas.
- Neto Indyana despues de comisiones.
- Caja Indyana esperada.
- Caja Indyana recibida.
- Saldo Indyana.
- Saldos artista/terceros.
- Estado sugerido.
- Estado por capas:
  - boliche / cliente
  - caja show
  - artistas / terceros
  - cuenta corriente

## Paso 8 - Acciones explicitas

Botones importantes:

- `Guardar borrador`
- `Guardar y recalcular`
- `Aplicar sugeridos a lineas`
- `Aplicar caja sugerida a lineas`
- `Crear shows hijos`
- `Actualizar hijos con sugeridos`
- `Recalcular madre desde hijos`
- `Cerrar lineas que esten en cero`
- `Marcar saldo como cuenta corriente`
- `Cerrar evento`

### Reglas de seguridad

- `Actualizar hijos con sugeridos` debe mostrar preview de cambios.
- Si una hija tiene edicion manual posterior, pedir confirmacion.
- Nunca borrar gastos/terceros/pagos de una hija sin mostrarlo.
- Si la hija esta cerrada/historica, no pisarla salvo confirmacion especial.
- Si madre e hija difieren, gana la hija como realidad operativa por defecto.
- Debe existir accion explicita para aceptar hija como realidad, aplicar madre a hija o mantener diferencia observada.

## Paso 9 - Vista de relaciones

Si existe madre/hijos:

Mostrar:

- Evento madre #ID.
- Hijas generadas:
  - artista
  - show_id
  - estado
  - Indyana esperado
  - recibido
  - saldo
  - boton `Abrir hija`
- En cada hija:
  - link `Abrir madre`
- estado de sync:
    - OK
    - difiere de sugerido
    - hija modificada manualmente
  - acciones:
    - aceptar hija como realidad
    - aplicar sugerido madre a hija
    - mantener diferencia observada

## Alertas necesarias

- El boliche debe plata.
- La linea supera 100% de split.
- Hay base no asignada.
- Indyana recibido no coincide con sugerido.
- Artista pagado no coincide con sugerido.
- Hay tercero con caja VPO pendiente.
- Hay tercero externo no caja VPO.
- La linea excluye comision general.
- La madre esta cerrada pero hay hijas pendientes.
- La hija fue editada despues de la madre.
- Hay historico pendiente de revision.
- El show esta cerrado operativamente pero tiene cuenta corriente viva.
- La caja no cierra exacta aunque la diferencia sea menor a 1 peso.

## Casos de prueba obligatorios

### 1. Show comun

Laalo/Gusty directo.

Debe:

- Calcular split.
- Registrar seña.
- Cerrar si caja coincide.

### 2. Virrshi con recupero

Debe:

- Separar show de recupero.
- Registrar cuenta corriente.
- Mostrar Indyana ganado y recupero.

### 3. Aneley

Debe:

- Permitir caja externa/manager.
- Mantener cuenta corriente.
- Cerrar show sin perder saldo global.

### 4. G Sony solo

Debe:

- Permitir Facha como comision/gasto de linea.
- Permitir Fede como tercero externo.
- Marcar exclusion de comision general si aplica.

### 5. Candu + G Sony

Debe:

- Crear madre.
- Crear hijos Candu y G Sony.
- Aplicar comision directa.
- Incorporar parte de Facha a G Sony.
- No pisar hijas si se editan.

### 6. Caserio

Debe:

- Separar caja Caserio de caja Indyana.
- Crear hijos para artistas VPO.
- Mantener artistas externos como egreso/caja Caserio.

### 7. Historico 0/0

Debe:

- Guardar para visibilidad.
- No afectar comisiones.
- Marcar como historico pendiente.

## Implementacion sugerida

Fase 1:

- Crear pantalla nueva sin borrar las actuales.
- Reusar endpoints existentes si se puede.
- No migrar datos.

Fase 2:

- Agregar capa de preview/calculo.
- Mostrar diferencias madre/hija.

Fase 3:

- Permitir crear/actualizar hijos con acciones explicitas.

Fase 4:

- Reportes de Indyana bruto, comisiones aplicables y neto Indyana.
