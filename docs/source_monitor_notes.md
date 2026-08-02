# Control de distribuidoras

Esta pantalla controla si las distribuidoras fueron revisadas y si los ultimos statements llegaron al sistema.

## Regla clave

`monitoring_active = false` significa solamente:

- no generar alerta operativa;
- no exigir revision mensual.

No significa excluir datos de reportes. Los datos historicos cargados en marts siguen contando en regalias, statements y reportes.

## Que compara

La pantalla cruza dos capas del pipeline nuevo:

- `input_raw`: archivos descargados manualmente desde cada distribuidora.
- `warehouse/marts/standardized_raw_all_sources.parquet`: statements ya disponibles para reportes nuevos.

Con eso muestra:

- ultimo `statement_period` cargado;
- cantidad de archivos raw;
- ultimo archivo raw detectado;
- cantidad de archivos cargados en marts;
- posibles raw no procesados, comparando solamente contra los marts nuevos;
- archivos ignorados con regla explicita;
- estado operativo.

Importante: esta pantalla no usa `processed_files.parquet` ni ninguna marca del pipeline viejo. La verdad operativa del sistema nuevo es el mart nuevo.

## Clasificacion de archivos raw

La pantalla no trata todos los archivos que no matchean contra el mart como error. Primero los clasifica:

- `loaded_to_mart`: el archivo ya esta representado en `standardized_raw_all_sources.parquet`.
- `pending_real`: archivo real que no aparece en el mart nuevo y requiere procesar.
- `ignored_empty`: archivo reconocido pero sin filas utiles, por ejemplo statements vacios.
- `ignored_summary`: resumen que se omite a proposito para evitar duplicar detalle granular, por ejemplo SoundOn summary.
- `legacy_manual`: carga historica excepcional documentada, por ejemplo Altafonte legacy dentro de Orchard/Altafonte.

Solo `pending_real` bloquea la publicacion a cloud.

## Estados

- `ok`: el ultimo statement esta dentro de la tolerancia.
- `attention`: hay algo para mirar, por ejemplo raw que no figura en el mart nuevo.
- `alert`: la fuente esta atrasada o no tiene statement detectado.
- `inactive`: no se monitorea, pero los datos siguen incluidos.

## Configuracion

La configuracion se guarda en:

```text
warehouse/registry/source_monitor_config.json
```

Campos importantes:

- `id`
- `source`
- `account`
- `display_name`
- `input_path`
- `max_age_months`
- `monitoring_active`
- `alert_silenced`
- `portal_url`
- `notes`
- `last_manual_review_at`

## Flujo operativo recomendado

1. Abrir `Control de distribuidoras`.
2. Mirar fuentes en `alert` o `attention`.
3. Entrar al portal de la distribuidora.
4. Comparar contra el ultimo statement cargado.
5. Si hay archivo nuevo, descargarlo en su carpeta de `input_raw`.
6. Usar `Procesar nuevos`.
7. Revisar el resumen visual de statements, filas e importes USD.
8. Volver a abrir la pantalla y confirmar que bajo la alerta.
9. Si todo esta validado y no hay pendientes reales, usar `Publicar datos analiticos`.
10. Si la fuente ya no se usa, marcar `No monitorear`.

## Procesar nuevos

El boton `Procesar nuevos` corre el pipeline nuevo de la fuente:

- `ingest_standardized_*`
- `build_song_level_*`
- `build_consolidated_marts.py`
- `build_statement_summary_mart.py`
- `build_catalog_master.py`

El resumen de Ingresos Digitales tambien forma parte del paquete publicado. Si
se reconstruye desde la API, debe quedar actualizado antes de publicar. No debe
quedar mas viejo que los marts de ingreso que alimentan esa pantalla.

Para ONErpm, el script procesa las subcuentas configuradas juntas porque comparten el mismo mart `standardized_raw_onerpm.parquet`. El resumen visual se filtra por la cuenta elegida, por ejemplo `henry_remix`.

Si un archivo ONErpm existe en `input_raw` pero no tiene filas en las hojas que esa cuenta carga al mart, se muestra como ignorado por regla y no como pendiente. Ejemplo: cuentas externas tipo Gusty o La Nueva Sangre pueden tener `Shares In & Out` sin `Masters`/`Youtube Channels`; esos shares quedan para auditoria/flags, pero no son filas de ingreso.

Despues de procesar, revisar:

- archivos procesados;
- ultimo statement antes y despues;
- pendientes restantes;
- filas por statement;
- total USD por statement.
- rango de actividad del catalogo reconstruido.

No publicar a cloud si ese resumen no tiene sentido.

## Publicar datos analiticos

El boton `Publicar datos analiticos` sube el paquete validado desde
`warehouse/marts` al bucket configurado. No es solo una publicacion de ingresos:
incluye tambien el catalogo que gobierna identidad, activo/inactivo y
reportabilidad.

- `song_level_all_sources.parquet`
- `standardized_raw_all_sources.parquet`
- `catalog_candidates.parquet`
- `catalog_master.parquet`
- `statement_summary_all_sources.parquet`
- `digital_income_statement_summary.parquet`

La publicacion queda bloqueada si hay archivos `pending_real`. Los archivos ignorados por regla no bloquean.

Antes de publicar, el sistema debe validar que `catalog_master.parquet` este
reconstruido contra los marts actuales. Si `song_level_all_sources.parquet` tiene
actividad posterior a `catalog_master.parquet`, el paquete no esta cerrado y no
debe considerarse publicable.

## Pendiente futuro

- Boton para abrir carpeta local.
- Campo editable de URL del portal desde la web.
- Mejorar la edicion de reglas por fuente desde la web.
