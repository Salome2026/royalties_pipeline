# UI period control policy

## Objetivo

Todo selector mensual de reportes o vistas operativas debe usar una unica entidad
de UI y una unica interpretacion de negocio: `PeriodControl`.

No crear nuevos selects sueltos de `Desde` / `Hasta`, inputs `type="month"` o
rangos manuales salvo que el caso sea una vigencia contractual o una fecha diaria.

## Regla base

Un mes representa siempre el mes completo.

Ejemplos:

- `2026-03` significa todo marzo 2026.
- `2026-03` a `2026-04` significa todo marzo y todo abril.
- Si se transforma a fechas: desde `2026-03-01` inclusive hasta `2026-05-01`
  exclusivo.

El sistema no debe interpretar `2026-03` a `2026-04` como `1 de marzo` a
`1 de abril`, porque eso dejaria afuera abril.

## Modos

- `all`: todo el historico disponible.
- `single_month`: un mes puntual completo.
- `closed_range`: rango cerrado de meses completos.
- `last_6_months`: ultimos seis meses disponibles.
- `last_12_months`: ultimos doce meses disponibles.
- `from_month`: desde un mes en adelante, solo cuando la pantalla lo muestre
  explicitamente.
- `until_month`: acumulado hasta un mes, solo cuando la pantalla lo muestre
  explicitamente.

## Perfiles por tarjeta

- `monthly_report`: reportes de regalias en Excel o PDF ejecutivo. Un mes solo
  es mes puntual y el selector se comparte entre ambos formatos.
- `custom_report`: reportes personalizados. Si el template tiene desde/hasta, un
  mes solo es mes puntual; si el template es acumulado, se usa `until_month`.
- `preset_or_range`: vistas con presets y rango custom, como Participacion en
  distribuidoras.
- `dashboard_period`: dashboards como Ingresos Digitales. El default puede ser
  `last_6_months`, pero debe mostrarse asi; `Todo` debe ser una decision visible.
- `activity_window`: Catalogo General. Un mes solo significa obras con actividad
  en ese mes; un rango significa actividad en esa ventana.
- `commission_period`: Comisiones. Un mes solo es mes puntual; sin periodo es
  todo.
- `validity_range`: vigencia de reglas. No es un filtro de reporte: `Desde` sin
  `Hasta` significa vigente desde ese mes.

## Checklist para tarjetas nuevas

Si una tarjeta usa meses, statements, transaction month, fechas de catalogo o
rangos de liquidacion:

1. Usar `PeriodControl`.
2. Elegir un perfil de esta politica.
3. No implementar una interpretacion local de `Desde` / `Hasta`.
4. Documentar cualquier excepcion antes de tocar codigo.

Las vigencias de reglas pueden usar campos propios, pero deben estar rotuladas
como `Vigencia`, no como `Periodo`.
