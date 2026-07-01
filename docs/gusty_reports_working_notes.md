# Gusty reports working notes

Fecha: 2026-05-23

## Ayuda memoria

Cuando Ruben diga "vamos a trabajar con reportes de Gusty", retomar desde este
criterio antes de tocar codigo o datos.

El reporte `Gusty Fuga contratos nuevo & viejo` no debe pensarse como un script
aislado. Debe servir como caso testigo para un modelo general de cuentas mixtas y
migracion contractual.

## Objetivo real

Construir una forma defendible y reutilizable de clasificar ingresos por obra
cuando un artista tiene catalogo viejo y catalogo nuevo mezclado entre
distribuidoras.

La secuencia conceptual debe ser:

1. identificar obras;
2. mapearlas al catalogo general;
3. determinar ownership/contrato;
4. decidir si entran al reporte;
5. explicar por que;
6. recien despues sumar importes.

## Gusty como caso testigo

Gusty/FUGA es el primer caso testigo.

El reporte actual:

- reporta ingresos de `fuga / indyana_records`;
- usa `onerpm / gusty_dj` solo como fuente auxiliar de referencia;
- clasifica contrato viejo/nuevo con Motorcito como evidencia;
- Motorcito no debe ser la regla final de negocio;
- la regla final debe ser una fecha contractual o un override por obra/catalogo.

## Direccion futura

El reporte deberia evolucionar hacia:

- fuente reportada explicita;
- fuente auxiliar explicita;
- corte contractual leido desde configuracion;
- clasificacion por `catalog_key` cuando sea posible;
- overrides humanos por obra;
- modo operativo y modo auditoria;
- motivos visibles de inclusion/exclusion.

No avanzar con cambios profundos sin validar primero el objetivo concreto del
reporte que se quiere generar.
