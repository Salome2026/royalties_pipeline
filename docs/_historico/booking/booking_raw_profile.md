# Booking Raw Profile

## Objetivo

Este documento resume el primer perfilado de los Excel historicos de booking. La idea es separar fuente primaria, hojas derivadas y reportes de control antes de construir la capa `standardized_booking`.

## Fuentes Ingeridas

Los datos raw se guardan en:

`warehouse/booking/raw`

Archivos principales:

- `booking_google_sample.xlsx`
- `Ingresos x Booking Indyana-MAWZ.xlsx`
- `PM David Carbone (1).xlsx`
- `PM Lautaro.xlsx`
- `PM Salome.xlsx`
- `PM Santiago (2).xlsx`

Cada fila conserva trazabilidad:

- `source_file_name`
- `source_file_path`
- `source_sheet`
- `source_row`
- `source_dataset`
- `ingested_at`

## Decision Principal

`Presentaciones` no debe ser fuente primaria.

Segun la logica real de la planilla, `Presentaciones` se arma automaticamente a partir de `Ingresos` y `Egresos`, filtrando por fecha, venue/evento y artista. Por lo tanto:

- `Ingresos` y `Egresos` son la base operativa.
- `Presentaciones` sirve como validacion y control contra la planilla historica.
- Los reportes al owner sirven como salida historica de referencia, no como verdad transaccional.

## Decision Sobre Duplicados

`booking_google_sample.xlsx` se conserva en raw, pero no se usa en la capa `standardized_booking_movements`.

Motivo:

- Las filas y totales de `booking_google_sample.xlsx` coinciden con `PM Lautaro.xlsx`.
- Si ambos entran en standardized, esa parte del booking se duplica.
- La capa standardized toma como fuente productiva los archivos `PM*.xlsx`.
- El sample queda disponible para auditoria o comparacion historica.

## Datasets Operativos

### Ingresos

Datasets:

- `booking_raw_ingresos`
- `booking_raw_pm_ingresos`

Columnas comunes:

- `FECHA`
- `ARTISTA`
- `Categoria`
- `Sub Categoria`
- `Evento / Detalle`
- `CONCEPTO`
- `Importe en $`
- `Importe en u$`
- `Factura`
- `Pagado`
- `Saldo`
- `Estado`
- `Medio`
- `Origen`
- `Beneficiario`
- `T/C`
- `Porcentaje`

Perfil inicial:

- La categoria de ingresos observada es principalmente `Booking`.
- La subcategoria principal es `Show`.
- Tambien aparecen casos de `Videoclip` y `Gastos o Viaticos`.
- `Estado`, `Medio`, `Origen` y `Beneficiario` vienen incompletos en gran parte de la data historica.
- Hay filas con fecha nula o importe cero que deben conservarse como raw, pero probablemente excluirse o marcarse en `standardized_booking`.

### Egresos

Datasets:

- `booking_raw_egresos`
- `booking_raw_pm_egresos`

Columnas comunes:

- `FECHA`
- `ARTISTA`
- `Categoria`
- `Sub Categoria`
- `Evento / Detalle`
- `CONCEPTO`
- `Importe en $`
- `Importe en u$`
- `Factura`
- `Pagado`
- `Saldo`
- `Estado`
- `Medio`
- `Origen`
- `Beneficiario`
- `T/C`
- `Porcentaje`

Columna adicional observada:

- `Recuperable`

Perfil inicial:

- La categoria dominante es `Booking`.
- Tambien aparecen `Label` y algun caso de `Management`.
- La subcategoria dominante es `Show`.
- Tambien aparecen `Videoclip`, `Estrenos`, `Mix & Master`, `Marketing`, `Streaming`, `Adelanto`, `Produccion Musical`.
- Esto confirma que no todo egreso pertenece al resultado de un show. La capa estandarizada debe distinguir gasto de booking, gasto de label, adelanto y gasto recuperable.

## PM David

`PM David Carbone (1).xlsx` no trae `Ingresos`/`Egresos` con la misma estructura que otros PM. En cambio trae:

- `Raw`
- `GASTOS - INDYANA RECORDS`
- `Presentaciones`
- `Caja`

Lectura inicial:

- `Raw` parece una hoja de gastos/movimientos operativos con artista, fecha, concepto e importes.
- `GASTOS - INDYANA RECORDS` parece separar gastos imputables a Indyana/label.
- No conviene forzar este archivo al mismo parser de `Ingresos`/`Egresos` sin una regla especifica.

## Llave Tentativa Para Armar Shows

Para reconstruir shows desde ingresos y egresos, la union inicial deberia basarse en:

- `source_file_name`
- `ARTISTA`
- `FECHA`
- `Evento / Detalle`
- `Categoria`
- `Sub Categoria`

Pero esta llave no debe asumirse perfecta. Antes de automatizar liquidaciones, hay que generar un reporte de matching que marque:

- ingresos sin egresos asociados
- egresos sin ingreso asociado
- fechas nulas
- eventos duplicados con mismo artista y fecha
- importes cero
- categorias que no sean `Booking`
- subcategorias que no sean `Show`

## Capa Siguiente Propuesta

Crear `standardized_booking_movements.parquet` con una fila por movimiento raw normalizado.

Campos sugeridos:

- `movement_id`
- `source_file_name`
- `source_sheet`
- `source_row`
- `movement_type`: `income` o `expense`
- `movement_date`
- `artist_statement`
- `business_area`: `booking`, `label`, `management`, `unknown`
- `movement_category`
- `movement_subcategory`
- `event_detail`
- `concept`
- `amount_ars`
- `amount_usd`
- `fx_rate`
- `payment_status`
- `payment_method`
- `payer_or_origin`
- `payee_or_beneficiary`
- `percentage`
- `is_recoverable`
- `standardization_status`
- `standardization_notes`

Luego, desde esa tabla:

1. Construir `booking_shows` agrupando movimientos de `Booking / Show`.
2. Validar contra `Presentaciones`.
3. Separar gastos de label y adelantos hacia cuenta corriente de artista.
4. Modelar casos especiales aparte, sin contaminar la logica simple.
