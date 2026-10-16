# Actualizacion de la prueba cloud ONErpm

Fecha: 2026-10-15. Responsable: Codex. Estado: alineacion y controles completos.
Autorizacion: alinear la copia con produccion y repetir controles; NO publicar
en produccion ni modificar economia, asociados, contratos cerrados, reportes
actuales o Shares In & Out.

## Base actualizada

- Codigo productivo inicial: b2394eef8cec399f60dfd972129938b6be55aea1.
- Codigo productivo mas reciente observado: 3f79197603c5b98cf6f791a7b0670e13e0654714.
- API mas reciente observada: vpo-corp-api-00255-7q5.
- Datos publicados: 20261015T143123Z-c149bbe1e666.
- Catalogo publicado: 3055 fichas, 65 columnas.
- Copia SQL: 244 contratos y 268 versiones historicas, mas contratos de artistas,
  policies y permisos pertinentes. Sin Booking, finanzas o salarios.
- BigQuery: 13 snapshots de tablas y tres vistas, incluyendo las incorporaciones
  posteriores a la prueba inicial. Ninguna tabla productiva se sobrescribe.

URL conservada:
https://vpo-onerpm-web-preview-20261015-32v4t5iawa-uc.a.run.app

La copia anterior queda preservada en su base original
vpo_onerpm_preview_20261015 y previous_preview_archive.json. No se detectaron
ediciones humanas adicionales en sus contratos fuera del fixture QA conocido.
La nueva revision usa vpo_onerpm_preview_20261015_r2 y
royalties_preview_onerpm_20261015_r2, con el mismo rol limitado e identidad
cloud; se conserva la prohibicion de acceso a contratos productivos para ese rol.
El bucket de prueba mantiene objetos inmutables por release y se actualiza su
manifest mediante condicion de generacion. Ninguna escritura apunta al bucket
productivo.

## Codigo

La imagen se construye desde un Git archive del commit productivo 3f79197 y
solamente 14 archivos de la mejora ONErpm/participantes. Se comprueba que los
otros archivos sean identicos a ese commit. El worktree dedicado conserva su
HEAD local anterior c758b0d sin commit/push; sus archivos se reconciliaron con
la version productiva, sin tocar los otros worktrees ni cambios ajenos.

Primer build de la actualizacion: eb9c1511-325f-433d-8d50-ec7b61602883.
Build alineado al ultimo codigo: 09fd2092-2a5e-4a25-87e5-21fff8199b3e.
Durante el cierre aparecio una nueva publicacion externa de codigo. Se
conservaron los artefactos del primer build en code_versions/b2394ee... y
se repitio la integracion sobre 3f79197. Los marts, las 13 tablas BigQuery,
los contratos y sus historiales no cambiaron, por lo que no se reingestan
datos ni se reconstruyen innecesariamente las copias economicas.
Los unicos destinos de deploy son los dos servicios vpo-onerpm-*-preview.
No se ejecuta el pipeline de produccion ni se modifica Vercel.

## Controles

- [x] Preservar la prueba anterior y congelar la ultima foto publicada.
- [x] Conciliar codigo contra el commit productivo exacto.
- [x] Repetir 131 pruebas Python y seis grupos de controles TypeScript.
- [x] Revalidar los mismos 182 XLSX y la resolucion de 400 ISRC.
- [x] Verificar que solo cambien las cuatro columnas artisticas del catalogo.
- [x] Conservar las otras 61 columnas y los 22142 aliases de la nueva base.
- [x] Validar idempotencia y orden independiente del enriquecimiento.
- [x] Comparar AST del lector economico ONErpm: funciones sin cambios.
- [x] Mantener la entrada legacy de los PDF y las inferencias de asociados.
- [x] Comparacion HTTP de ingresos/meses/asociados de cuatro casos.
- [x] Ocho recorridos reales de pantalla sobre el primer build actualizado.
- [x] Verificacion posterior de todos los contratos originales e historiales.
- [x] Repetir los ocho recorridos de pantalla con la imagen basada en 3f79197.
- [x] Cerrar el contraste HTTP y los invariantes sobre esa imagen.
- [x] Verificacion final de invariantes productivos y certificacion.

El nuevo catalogo permite ampliar participantes en 25 fichas, frente a 23 en
la foto anterior. Es un resultado contra una base distinta, no una relajacion
del lector: los 182 originales y los 400 ISRC resueltos son los mismos.
No se conserva artificialmente el conteo anterior ni se modifica dinero para
hacerlo coincidir. Los artistas propuestos no reciben porcentajes inventados.

En esta copia se vuelve a crear el fixture US7VG2308889 SOLO para comprobar
un contrato abierto guardado al que falta un participante. No sustituye un
contrato productivo. Los guardados de QA quedan exclusivamente en la copia.

La primera pasada de pantalla expiro esperando el catalogo frio a los 30 s,
sin errores JavaScript ni escrituras; el harness anterior pasaba el timeout
en el argumento incorrecto. Se corrigio solo el harness para esperar hasta
180 s. No se cambia la aplicacion ni se certifican metas de rendimiento.
Las capturas moviles esperan ademas el fin de la animacion existente del menu;
sin esa espera, una captura inmediata registra el panel mientras se oculta.

En QZGLS2518430 los 21 asociados son los mismos de produccion, incluidos los
dos videos agregados por la publicacion anterior. La comparacion inicial
detecta solamente orden distinto de variantes de titulo/artista: el lector
existente usa ARRAY_AGG(DISTINCT ...) sin ORDER BY para esos campos. El control
ordena solo esas dos listas antes de comparar; identidad, firma, inclusion,
estado, seleccionabilidad y clasificacion UGC se exigen exactas. No se cambia
la consulta ni el motor de asociados.

Las policies se comparan mediante serializacion canonica, conservando valores
exactos. Esto permite contrastar Decimal/fechas de Postgres con sus cadenas
equivalentes del snapshot JSON, sin omitir porcentajes, campos o timestamps.

Al arrancar la ultima revision, una llamada de readiness recibio HTTP 500 del
frontal Cloud Run por no haber instancia disponible (minimo cero, maximo uno).
El log indica explicitamente esa causa; la siguiente llamada respondio 200,
sin errores de aplicacion. Se conserva preview_startup_transient.json y los
controles finales se ejecutan con la instancia lista. No se cambia la escala,
no se oculta ese evento y no se certifican tiempos de respuesta/cold start.

## Resultado final

Los cuatro casos HTTP coinciden en ingresos, meses por statement y asociados:
US7VG2308889 (USD 804.3022296; un codigo), QZW9L2346202
(USD 37156.0536616627; dos codigos), QZGLS2518430 (USD 763.9284874106;
21 codigos) y QZW9L2430233 (USD 14983.8583619405; 343 codigos).
La tolerancia maxima de comparacion es USD 0.0000001 por representacion binaria;
no se ajustan movimientos ni porcentajes para hacer coincidir resultados.

Se preservan los 244 contratos originales, 268 versiones historicas, cuatro
contratos de artista y cinco versiones de estos, diez policies y su fila de
settings. Los cinco marts no artistico/economicos mantienen el checksum
publicado; las otras 61 columnas del catalogo y sus aliases son identicos.
Las pruebas sobre la ultima imagen son 131 Python y ocho recorridos de
pantalla, ademas de los seis grupos TypeScript. Capturas desktop/mobile
verificadas, sin errores JavaScript ni desborde horizontal.

La comprobacion final confirma que datos, contratos y policies productivos no
cambiaron desde el snapshot de datos, y que API, trafico y Job no cambiaron
desde la ultima captura de codigo 3f79197. Las 13 tablas BigQuery productivas
conservan sus etags. La funcionalidad nueva de exclusiones sigue ausente del
schema publico; no se publico esta mejora en produccion.

Queda pendiente exclusivamente la validacion humana y una autorizacion
separada para cualquier promocion. Una nueva publicacion productiva posterior
a esta certificacion exige repetir el control de vigencia de la base.

## Evidencia

C:/royalties_pipeline/staging/catalogo_lectura/20261015_onerpm_cloud_refresh/.
Se conservan baseline.json, archivos originales congelados por hash,
database_snapshot.json (privado), production_http_before.json, manifiestos,
imagenes inmutables, pruebas y capturas. certification.json se emite solo
cuando todos los controles finales son correctos.

El resultado no autoriza promocion productiva. No copiar bases de QA, fixtures,
usuarios de prueba o snapshots sobre produccion. Una publicacion posterior
requiere autorizacion y una nueva comprobacion de que la base no cambio.
