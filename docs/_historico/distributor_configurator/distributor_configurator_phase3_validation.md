# Configurador Distribuidoras + Catalogo - Fase 3 Validacion

Fecha: 2026-05-23

## Objetivo de esta fase

Validar que la pantalla read-only/edicion limitada del configurador permite
entender las reglas de negocio sin cambiar todavia la logica productiva de los
reportes.

Fase 3 no debe:

- mover los reportes a leer la politica nueva;
- cambiar resultados productivos;
- calcular splits contractuales;
- mezclar caja, finanzas o booking.

## Estado general

La pantalla ya muestra:

- politica por distribuidora/cuenta;
- decision de caja completa, parcial por regla o excluida;
- impacto directo de la cuenta;
- impacto de obras relacionadas en catalogo;
- decision final de negocio para cuentas con regla contractual;
- alertas cuando el catalogo pisa una inclusion contractual;
- diccionario de statements;
- impacto en reportes;
- auditoria completa plegada.

## Casos validados

| Caso | Resultado esperado | Estado actual |
| --- | --- | --- |
| `onerpm / la_nueva_sangre` | Cuenta mixta con caja parcial por regla. La decision final debe combinar release/fecha contractual y catalogo. | OK. Directo USD 58,359.78. Reportable final USD 46,559.63. Boxindanga queda `excluded_by_catalog`. |
| `onerpm / gusty_dj` | Cuenta mixta con caja parcial por regla. La fecha contractual manda; Motorcito es evidencia, no regla de negocio. | OK. Directo USD 314,839.77. Reportable final USD 129,310.21. Excluido por regla USD 185,529.54. |
| `onerpm / mawzrecords` | Cuenta propia. Masters representa generacion; Shares In & Out queda para caja/auditoria, no para generacion nueva. | OK visual. Directo USD 136,042.27, separado en Masters USD 83,758.51 y Shares USD 52,283.76. |
| `onerpm / henry_remix` | Cuenta propia simple. No debe romperse por introducir el configurador. | OK. Directo USD 25,199.19, Masters solamente. |
| `dashgo / mawzrecords` | Cuenta propia simple. Puede tener diferencia entre directo y obras relacionadas si la misma obra genero en otra fuente. | OK. Directo USD 26,373.95. Obras relacionadas USD 26,799.28. |
| `fuga / indyana_records` | Cuenta propia simple. Debe conservar la logica validada de FUGA y corrections trazables. | OK visual. Directo USD 151,632.62. |
| `orchard / mawzrecords` | Cuenta propia simple con Altafonte legacy bajo continuidad Orchard. | OK visual. Directo USD 20,110.89. |
| `soundon / soundon` | Cuenta propia simple. Solo `my_royalty` entra; summaries excluidos. | OK visual. Directo USD 9,719.56. |

## Observaciones

### Directo vs relacionado

La pantalla diferencia:

- `Generacion directa de cuenta`: lo que vino por `source + account`.
- `Generacion total de obras relacionadas`: suma de obras de catalogo donde
  aparece esa cuenta, aunque tambien generen en otras fuentes/cuentas.

Esto explica casos como DashGo, donde algunas obras aparecen tambien en ONErpm.

### Catalogo pisa regla contractual

Si una obra entra por fecha contractual pero el catalogo la marca con
`include_in_reports = false`, la decision final es `excluded_by_catalog`.

Ejemplo validado:

- `Boxindanga`
- Cuenta: `onerpm / la_nueva_sangre`
- Regla contractual: incluido
- Catalogo: inactivo/fuera de reportes
- Decision final: excluido por catalogo

### Caja parcial por regla

En cuentas mixtas no debe decir simplemente "No caja".

Debe decir:

- `Caja parcial por regla`

Esto aplica a:

- `onerpm / gusty_dj`
- `onerpm / la_nueva_sangre`

## Pendientes dentro de Fase 3

Estos pendientes siguen dentro del alcance de Fase 3 porque no cambian importes
productivos:

1. Revisar si conviene permitir edicion limitada persistente de:
   - notas de cuenta;
   - monitoreo activo/inactivo;
   - fecha contractual;
   - evidencia de fecha;
   - notas del diccionario de statement.

2. Revisar textos de pantalla para que una persona nueva entienda:
   - que directo no es lo mismo que relacionado;
   - que reportable no significa 100% propio;
   - que shares son transferencia/caja, no generacion de master.

3. Preparar export simple de configuracion para auditoria humana.

## Simulador de reglas

Se probo un simulador de regla contractual y se retiro de la pantalla antes de
pasar a Fase 4 para mantener el configurador limpio.

Conclusion:

- la simulacion fue util para validar que fecha/base de corte modifican los
  numeros esperados;
- no se guardo como funcionalidad operativa;
- no gobierna reportes ni marts;
- si vuelve en el futuro, debe hacerlo como herramienta controlada de QA, no como
  edicion productiva directa.

## Criterio para pasar a Fase 4

Fase 4 recien deberia empezar cuando:

- esta pantalla este validada visualmente;
- los casos anteriores esten aceptados;
- el seed read-only represente correctamente las reglas actuales;
- el usuario confirme que la lectura humana es clara.

Fase 4 sera:

1. hacer que `build_statement_report_from_mart.py` pueda leer la politica nueva;
2. generar QA comparando hardcoded actual vs politica;
3. exigir diff cero o diferencias explicadas;
4. recien despues reemplazar reglas hardcodeadas.
