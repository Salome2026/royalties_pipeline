# Booking VPO - Modelo unificado propuesto

Fecha de trabajo: 2026-05-15

Este documento resume el modelo objetivo para unificar la carga de booking sin romper lo ya cargado. La idea no es borrar las pantallas actuales de golpe, sino definir una logica comun que pueda servir para shows simples, liquidaciones compuestas, Caserio, managers externos, señas, recuperos y cuenta corriente.

## Principio central

La carga no deberia obligar al usuario a saber si esta creando un "show simple", una "liquidacion compuesta" o un "caso especial". El sistema deberia guiar con bloques:

- Evento
- Gastos generales
- Comisiones directas del evento
- Lineas artisticas
- Gastos propios de cada linea/artista
- Terceros externos
- Caja, señas y rendicion
- Cierre y saldos

Internamente puede seguir existiendo una madre/hijos cuando haga falta. La pantalla no deberia hacer que el operador piense en esa arquitectura.

## Regla de arquitectura madre/hija

La hija, es decir el show operativo del artista, es la fuente de verdad para la liquidacion real de ese artista.

La madre no debe duplicar datos vivos de la hija. La madre debe guardar:

- Contexto del evento.
- Reglas de reparto.
- Gastos generales del evento.
- Comisiones directas del evento.
- Caja global si existe.
- Vinculos a shows hijos.
- Sugeridos calculados.

La hija debe guardar:

- Gastos propios del artista.
- Terceros externos de esa linea.
- Pagos al artista.
- Recibido por Indyana.
- Caja propia de esa linea.
- Estado de cierre de esa linea.
- Saldos de artista, Indyana, boliche o tercero.

### Cachet pactado, cobrado real y politica de diferencia

El modelo unificado debe separar tres datos:

- cachet pactado;
- cobrado real;
- politica de diferencia.

La politica de diferencia puede ser:

- `deuda_boliche`: mantiene el cachet pactado como base de liquidacion y deja la diferencia viva como deuda del boliche/cliente.
- `ajustar_cachet`: usa el cobrado real como base de liquidacion y deja el pactado solo como referencia.

Default: `deuda_boliche`.

Esto evita que un pago parcial se confunda con una renegociacion del cachet. Tambien permite cargar casos historicos en cero sin perder trazabilidad.

Consecuencia:

- Si se edita una hija y se agrega un gasto, al abrir la madre ese gasto debe verse porque la madre lo lee desde la hija.
- Si se edita una madre, no debe pisar automaticamente datos reales de una hija ya trabajada.
- Si la madre recalcula sugeridos y hay diferencias contra la hija, debe mostrarlas como alerta.
- La accion de aplicar sugeridos de madre a hija debe ser explicita.
- La accion de recalcular madre desde hijas tambien debe ser explicita.

La madre organiza y controla. La hija manda como show operativo.

## Diferencias madre vs hija

La madre guarda regla, contexto y sugeridos. La hija guarda la realidad operativa.

Si madre e hija difieren, no se debe pisar nada automaticamente. El sistema debe mostrar la diferencia y proponer acciones.

Tipos de diferencia:

- Base distinta.
- Gastos propios distintos.
- Terceros distintos.
- Caja distinta.
- Estado distinto.
- Comisionabilidad distinta.

Regla:

- Por defecto gana la hija como realidad operativa.
- La madre puede recalcularse desde hijas.
- Aplicar sugeridos madre -> hija requiere accion explicita, preview y confirmacion.
- Una diferencia puede quedar marcada como observada si Ruben la acepta.

Acciones posibles:

- `Aceptar hija como realidad`.
- `Aplicar sugerido madre a hija`.
- `Mantener diferencia observada`.

## Conceptos que no se deben mezclar

### Indyana ganado

Es la ganancia economica de Indyana/productora por el show o por una linea del show.

Ejemplo: si una linea genera 1.000.000 netos y el split es 70/30, Indyana ganado es 300.000.

### Base comisionable

Es la parte de Indyana ganado sobre la cual corresponde pagar comisiones internas de booking.

No siempre coincide con Indyana ganado.

Ejemplos:

- Show normal Virrshi 70/30: Indyana ganado probablemente tambien sea base comisionable.
- G Sony con regla especial: Indyana puede ganar, pero la linea puede ser no comisionable porque la comision ya se resolvio por Facha/Marce.
- Historico importado: puede quedar como no definido o historico hasta revision.

Campos objetivo:

- `indyana_amount`
- `commissionable_amount`
- `commissionable_flag`
- `commission_rule`
- `commission_notes`

## Casos reales detectados

### Shows simples

Artistas/casos:

- Dormun
- Dj Plaga
- Toti
- More Savan
- Laalo DJ
- Gusty DJ
- Facuu DJ cuando es show directo
- Lazer K cuando es show directo

Logica:

- Cachet pactado.
- Cobrado real.
- Gastos del show.
- Base = cobrado real - gastos.
- Split artista/productora.
- Caja/rendicion.
- Cierre si boliche, artista e Indyana estan conciliados.

### Virrshi

Particularidades:

- Puede tener caja y señas.
- Puede tener recuperos vinculados a gastos de artista, por ejemplo DJ set.
- El recupero puede tener reparto contractual, por ejemplo 70/30.
- Puede haber pagos al artista por deudas previas o viaticos.

Regla general que aporta:

- Toda carga debe permitir movimientos de caja reales separados de la liquidacion sugerida.
- Los recuperos/gastos del artista no deben quedar escondidos como gastos comunes si tienen impacto de cuenta corriente.

### Gastos recuperables y recuperos

Un gasto recuperable debe poder vivir mas alla de un show puntual.

Ejemplo:

- DJ set Virrshi: costo total 200.000.
- Regla contractual 70/30.
- Responsabilidad artista: 140.000.
- Responsabilidad Indyana: 60.000.

El sistema debe distinguir:

- Costo total.
- Parte recuperable del artista.
- Parte asumida por Indyana.
- Recuperado total.
- Recuperado contra artista.
- Recuperado contra Indyana.
- Saldo total.
- Saldo artista.
- Saldo Indyana.

Cuando se carga un show, una linea artistica puede aplicar recuperos contra gastos abiertos.

Tipos de recupero:

- `contra parte artista`: default recomendado. Baja la deuda del artista sin bajar la ganancia de booking de Indyana.
- `antes del split`: baja la base antes de repartir y reparte el impacto segun split.
- `contra parte Indyana`: baja la parte asumida por Indyana.
- `manual`: permite definir importes especificos.

La logica default de negocio es que Indyana asume su parte como inversion. Por eso, para gastos recuperables con split contractual, el recupero por defecto debe ir contra la parte del artista.

No hace falta implementar todo el modulo de gastos ahora, pero booking debe quedar preparado para:

- listar gastos recuperables abiertos del artista;
- aplicar recupero total o parcial desde un show;
- dejar trazabilidad del show que recupero;
- saber cuanto falta recuperar.

### Aneley

Particularidades:

- Manager/familia puede manejar caja.
- Hay cuenta corriente contra lo que ellos informan.
- Se importaron y revisaron hojas historicas con saldos.
- Algunos saldos fueron aceptados por practicidad aunque la cuenta no cerrara perfecto.

Regla general que aporta:

- Debe existir una cuenta corriente por artista/manager independiente del cierre operativo del show.
- Un show puede estar cerrado como show, pero aun formar parte de una cuenta corriente.
- El sistema debe distinguir "rendicion del show" de "saldo con el artista/manager".

### G Sony solo

Particularidades:

- G Sony tiene un manager/socio externo asociado a la parte no artista.
- Indyana y el socio externo comparten la parte no artista.
- Existe un booking agent externo, Gaston Facha, que cobra comision, normalmente 15%, aunque puede variar.

Modelo:

- Cachet - gastos generales = base artistica.
- Gaston Facha puede descontarse como gasto/comision propia de la linea.
- Luego se calcula la parte de G Sony, Indyana y tercero externo.

Esto no debe ser tratado como excepcion; es una linea artistica con terceros y comision propia.

### Candu + G Sony

Particularidades:

- El evento llega como una liquidacion conjunta.
- Candu se liquida con su regla normal, por ejemplo 70/30.
- G Sony se liquida con su regla propia.
- Hay una comision directa del evento, por ejemplo 10%.
- Esa comision se divide:
  - 50% Marcelo cobra directo.
  - 50% se incorpora a la base de G Sony.
- Luego sobre la base de G Sony ajustada, Gaston Facha cobra su comision.

Modelo:

- Evento madre:
  - Bruto.
  - Gastos generales.
  - Comision directa del evento.
  - Distribucion de esa comision: salida directa / incorporacion a linea.
- Linea Candu:
  - Base propia.
  - Gastos propios si hay.
  - Split Candu/Indyana.
  - Comisionable segun regla.
- Linea G Sony:
  - Base propia + ajuste incorporado.
  - Comision Facha.
  - Split G Sony / Indyana / tercero externo.
  - Habitualmente no comisionable si la comision ya fue resuelta por regla especial.

### Caserio

Particularidades:

- Caserio es una sociedad/evento externo.
- Puede tener artistas VPO dentro.
- La caja de Caserio y la caja de Indyana deben separarse.
- Si toca un artista VPO dentro de Caserio, se genera tambien un show interno de ese artista.

Modelo:

- Evento Caserio:
  - Bruto/cobrado.
  - Gastos generales.
  - Artistas externos, bajan la caja a rendir a Caserio.
  - Artistas VPO, generan show interno.
- Caja:
  - Lo que corresponde rendir a Caserio.
  - Lo que corresponde a Indyana por artistas VPO.

### Historico importado

Particularidades:

- Splits raros pueden venir de como estaba expresado el historico.
- Shows 0/0 se preservan por visibilidad.
- No se deben usar estos casos para definir reglas futuras sin revision.

Modelo:

- Estado historico.
- No obligar cierre perfecto.
- Permitir revision futura.

## Estados necesarios

### Estado del evento/show

- `programado`
- `realizado`
- `rendido`
- `aprobado`
- `cancelado`
- `no_cobrado`
- `historico`

### Estado de cierre

Separar cierre operativo de cuenta corriente:

- `pendiente`
- `cerrado`
- `historico`
- `observado`

Un show puede tener:

- Boliche cerrado.
- Artista cerrado.
- Indyana cerrado.
- PM/manager cerrado.
- Cuenta corriente pendiente.

## Flujo de pantalla propuesto

### Paso 1 - Tipo de carga guiada

El usuario elige una opcion entendible:

- Show comun.
- Show con regla especial.
- Evento con varios artistas.
- Evento externo / sociedad.
- Historico / control.

Esta eleccion no debe bloquear. Solo decide que secciones aparecen primero.

### Paso 2 - Datos del evento

Campos:

- Fecha.
- Venue.
- Ciudad.
- Responsable.
- Cachet pactado.
- Cobrado real.
- Moneda y tipo de cambio.
- Comprobantes.
- Notas.

### Paso 3 - Gastos generales

Campos por gasto:

- Categoria.
- Concepto.
- Importe.
- Moneda.
- Responsable/pagado por.
- Notas.

### Paso 4 - Comisiones directas del evento

Seccion opcional.

Campos:

- Concepto.
- Porcentaje o importe.
- Destino:
  - Sale directo a tercero.
  - Se incorpora a una linea artistica.
  - Se reparte entre varios destinos.
- Caja manejada por VPO si/no.
- Comisionable si/no.

Caso Candu + G Sony:

- 10% booking directo.
- Marcelo: 50% salida directa.
- Gaston: 50% incorporado a linea G Sony.

### Paso 5 - Lineas artisticas

Una linea por artista o tercero relevante.

Campos:

- Tipo:
  - Artista VPO.
  - Artista externo.
  - Tercero/comision.
- Artista.
- Base asignada:
  - Manual.
  - Partes iguales.
  - Porcentaje del neto.
  - Importe desde comision directa incorporada.
- Gastos propios.
- Split artista/Indyana.
- Terceros externos.
- Caja artista.
- Caja Indyana.
- Comisionable si/no.
- Motivo de comisionabilidad.

### Paso 6 - Caja y señas

Movimientos reales:

- Recibio Indyana.
- Recibio artista.
- Recibio manager/tercero.
- Metodo:
  - transferencia
  - efectivo
  - seña
  - otro
- Comprobante.
- Notas.

La caja no debe reemplazar la liquidacion sugerida. La caja explica lo que paso; la liquidacion dice lo que debio pasar.

### Paso 7 - Sugeridos y alertas

El sistema debe sugerir:

- Pago artista.
- Indyana esperado.
- Terceros esperados.
- Caja esperada.
- Base comisionable.
- Diferencia boliche.
- Diferencia artista.
- Diferencia Indyana.
- Diferencia PM/manager.

Alertas:

- Falta cobrar boliche.
- Falta pagar artista.
- Falta rendir Indyana.
- La suma de splits supera 100%.
- Hay ingreso Indyana no comisionable.
- Hay historico/revision pendiente.

## Reglas de cierre

El cierre debe entenderse por capas. Un unico "cerrado" no alcanza si quedan saldos vivos.

Capas:

1. Boliche / cliente.
   - Verifica si pago el cachet pactado.
   - Si no pago todo, queda deuda boliche.

2. Caja del show.
   - Verifica si la plata real rendida coincide con la caja esperada.
   - Incluye señas, efectivo, transferencias y pagos realizados.

3. Liquidacion de artistas y terceros.
   - Verifica si artista, Indyana y terceros cobraron o rindieron lo correspondiente.
   - Los terceros externos no caja VPO deben quedar marcados como tales.

4. Cuenta corriente.
   - Si algo no se salda en el momento, puede pasar a cuenta corriente.
   - El show puede quedar operativo/caja cerrado, pero con cuenta corriente abierta.

Estados visuales objetivo:

- abierto
- observado
- cerrado
- cerrado con cuenta corriente
- historico pendiente
- historico revisado

Un show no deberia mostrarse simplemente como cerrado si tiene una cuenta corriente viva. Debe mostrarse como `cerrado con cuenta corriente`.

Un show o linea se cierra completamente si:

- No hay deuda de boliche relevante.
- La parte de artista esta saldada o marcada como cuenta corriente.
- La parte de Indyana esta saldada o marcada como cuenta corriente.
- Terceros estan saldados o marcados como no caja VPO.
- No hay alertas bloqueantes.

## Regla de exactitud de caja

La caja debe cerrar exacta internamente.

No debe existir tolerancia automatica por redondeo para cerrar caja. Si hay una diferencia de 0,50 o 1 peso, sigue siendo diferencia hasta que se cargue el valor correcto o se marque como observado con nota.

Reglas:

- Los totales visuales pueden mostrarse redondeados para facilitar lectura.
- Los sugeridos, helpers y botones de carga deben mostrar centavos cuando existan.
- `Usar sugerido` debe cargar el valor exacto.
- El cierre debe evaluar contra diferencia exacta 0.
- Una diferencia menor puede quedar como `observado`, pero no como cerrado automatico.

Ejemplo:

- Total visual: 255.000
- Sugerido de caja: 255.000,50
- Si se carga 255.000, queda pendiente por 0,50.

La madre puede cerrar aunque una cuenta corriente quede abierta, pero el sistema debe mostrarlo distinto.

Ejemplo:

- Evento cerrado.
- Caja VPO cerrada.
- Cuenta corriente artista pendiente.

## Migracion prudente

No reemplazar de golpe.

Fases:

1. Mantener pantallas actuales.
2. Crear una pantalla experimental `Carga Booking 2`.
3. Usar la misma base, pero no ocultar la carga vieja.
4. Probar contra casos reales:
   - Show simple Laalo/Gusty.
   - Virrshi con recupero.
   - Aneley con manager externo/cuenta corriente.
   - G Sony solo.
   - Candu + G Sony.
   - Caserio con artistas VPO.
   - Historico 0/0.
5. Validar reportes:
   - Shows por artista.
   - Resumen booking.
   - Indyana ganado.
   - Base comisionable.
   - Saldos por artista/manager.
6. Recién despues, decidir si se reemplazan las pantallas actuales.

## No negociables

- No perder historico.
- No borrar shows 0/0.
- No mezclar Indyana ganado con base comisionable.
- No esconder terceros dentro de gastos genericos si afectan liquidacion.
- No depender de Excel externo para calcular: el sistema calcula y el Excel se usa como dato de entrada/referencia.
- Toda modificacion grande debe tener backup previo.
