# Contratos: lectura liviana de asociados

## Alcance

El panel usa `GET /master-contracts/{isrc}/associations?include_income=false`.
La ficha ya obtiene los ingresos; el panel no vuelve a calcularlos.
El modo predeterminado conserva la respuesta completa, incluidos los ingresos.
La actualizacion de totales despues de guardar sigue usando ese modo completo.

Ambos modos consultan permisos, contrato y version actuales, decisiones y
asignaciones de codigos. Comparten el mismo lector de asociados y sus evidencias.
No se agrega cache ni se omiten validaciones de version o errores bloqueantes.

## Protecciones

- Sin cambios de catalogo, importes, asociados, contratos o reportes.
- Sin ingesta, cambios de tablas, publicacion de marts ni nueva version de datos.
- Sin cambios de pantalla, estilos, configurador o Shares In & Out.
- La apertura inicial de la ficha conserva sus calculos; esta mejora acelera
  solamente la consulta adicional del panel de asociados.

## Validacion

- Diez pruebas nuevas del lector y controles del proxy de la web.
- Regresion de contratos, ingresos, identidad, participantes y asociados.
- Comparacion cloud de respuestas completa/liviana y mediciones alternadas.
- Navegador: abrir ficha y asociados, UGC separado, escritorio y movil, sin guardar.
- Publicacion condicionada a los controles; despues se comprueban datos,
  contratos, configurador, dashboard sin splits y alineacion de API, Jobs y web.

Control cloud: cinco ISRC, treinta mediciones alternadas en el mismo servicio.
Mediana completa: 5.585 s; liviana: 2.140 s (61.7% menos).
Las respuestas completas antes/despues coinciden; la liviana solo omite `income`.
Pasaron 324 pruebas Python y siete grupos existentes de controles de la web,
ademas de los controles nuevos del proxy y del modo liviano.

Evidencias locales: `C:/royalties_pipeline/staging/catalogo_lectura/20261028_contract_associations_fast_read`.
