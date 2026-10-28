# Destinatarios de distribucion

Solo Distribucion con reparto inicial admite `distribution_recipients`.
Son puntos porcentuales del ingreso total, no porcentajes de la bolsa.
Con comercializacion 30, los destinatarios pueden recibir 20 y 10.
No se usan ni modifican los titulares del master para este fin.

## Compatibilidad

- Sin el campo nuevo, se conserva `company_name` y el calculo existente.
- Un destinatario recibe automaticamente todo `master_pool_percent`.
- Al volver a uno solo, la interfaz vuelve al esquema escalar anterior.
- No se migran ni reescriben contratos guardados durante el despliegue.
- El servidor omite el valor nulo nuevo al guardar contratos anteriores.
- La interfaz habilita agregar cuando la ficha confirma soporte del servidor,
  evitando guardar campos nuevos contra una version anterior durante el despliegue.

## Validacion

- Entre uno y doce destinatarios; nombres repetidos no permitidos.
- Multiples: se completan porcentajes absolutos, nunca se reescalan solos.
- La suma no puede superar la comercializacion, ni siquiera en borradores.
- Se permite guardar incompleto, pero para cerrar debe sumar exactamente la bolsa.
- Un cambio en comercializacion conserva los porcentajes multiples y valida otra vez.
- Sin indicador adicional: solo controles de nombre, porcentaje, agregar/quitar y errores.

La simulacion y el lector contractual optativo usan la misma distribucion.
La lectura de los contratos anteriores conserva sus resultados; no se modifica
el formato ni se regeneran reportes existentes. Dashboard sin splits, reportes
generales, configurador, asociados e ingesta no cambian.

## Evidencia

Pruebas locales de reglas, centavos positivos/negativos y compatibilidad.
Comparacion de los 287 contratos de la linea base con el calculo publicado anterior.
Escrituras reales y pruebas de pantalla solo en la copia cloud, con restauracion
exacta de contratos, historiales y estados de revision al terminar.

Evidencias: `C:/royalties_pipeline/staging/catalogo_lectura/20261028_distribution_recipients`.
