# Marts and reports notes

## Pipeline nuevo

El pipeline nuevo sigue esta forma:

```text
input_raw
  -> standardized_raw_*
  -> song_level_*
  -> consolidated marts
  -> statement/digital summaries
  -> catalog_master
  -> reports
```

## Standardized marts

Archivos actuales:

- `warehouse\marts\standardized_raw_dashgo.parquet`
- `warehouse\marts\standardized_raw_fuga.parquet`
- `warehouse\marts\standardized_raw_onerpm.parquet`
- `warehouse\marts\standardized_raw_orchard.parquet`
- `warehouse\marts\standardized_raw_soundon.parquet`
- `warehouse\marts\standardized_raw_ada.parquet`

Objetivo:

- Conservar columnas originales.
- Agregar columnas normalizadas comunes.
- Evitar volver a leer CSV/Excel pesados.
- Permitir validaciones contra el pipeline viejo.

Columnas comunes esperadas:

- `source`
- `account`
- `statement_period`
- `transaction_month`
- `artist_statement_style`
- `amount_usd`
- `net_amount`
- `net_amount_usd`
- `statement_file_name`
- `statement_file_hash`
- `ingested_at`

## Song-level marts

Archivos actuales:

- `warehouse\marts\song_level_dashgo.parquet`
- `warehouse\marts\song_level_fuga.parquet`
- `warehouse\marts\song_level_onerpm.parquet`
- `warehouse\marts\song_level_orchard.parquet`
- `warehouse\marts\song_level_soundon.parquet`
- `warehouse\marts\song_level_ada.parquet`

Objetivo:

- Agregar por tema/ISRC/artista/mes.
- Mantener totales cerrados contra standardized.
- Servir como base para reportes por catalogo, tema, artista, splits y tendencias.

## Consolidated marts

Scripts:

- `scripts\build_consolidated_marts.py`
- `scripts\audit_consolidated_marts.py`
- `scripts\audit_marts_general.py`

Outputs:

- `warehouse\marts\standardized_raw_all_sources.parquet`
- `warehouse\marts\song_level_all_sources.parquet`

El consolidado incluye `mart_source_file` para saber de que mart individual vino cada fila.

Una distribuidora puede aportar varias cuentas al mismo mart individual. ADA,
por ejemplo, conserva `mawz` e `indyana_records` dentro de
`standardized_raw_ada.parquet` y `song_level_ada.parquet`. Todos los reportes y
selectores deben distinguirlas por `source + account`; no se crean marts ni
reglas de reporte paralelas por cuenta.

### Dimensiones normalizadas de DSP y tipo de ingreso

`standardized_raw_all_sources.parquet` agrega dimensiones de reporte derivadas
sin modificar los campos originales ni los importes:

- `dsp_normalized`
- `monetization_normalized`
- `content_origin_normalized`
- `plan_normalized`
- `classification_status`
- `store_report_label`

La interpretacion se apoya en las columnas originales declaradas en
`warehouse/registry/statement_source_dictionary.json`. Las politicas de cuenta
siguen decidiendo si una fila representa generacion, caja, transferencia o
auditoria. La normalizacion de Store/DSP nunca convierte Shares In & Out en
generacion y nunca completa informacion que la fuente no demuestra.

Los motores de reportes deben priorizar estas dimensiones y conservar los
campos originales en el detalle cuando se necesite auditoria. No se deben crear
normalizaciones particulares dentro de un reporte.

### Contrato obligatorio para resumen por Store/DSP

Toda pantalla o Excel que resuma ingresos por plataforma debe partir de las
filas reportables de `standardized_raw_all_sources.parquet` y agrupar por:

- `source` cuando el informe necesita identificar la distribuidora;
- `dsp_normalized`;
- `monetization_normalized`;
- `content_origin_normalized`;
- `plan_normalized`.

`store_report_label` es una etiqueta humana derivada de esas dimensiones. No
reemplaza las columnas separadas cuando el plan o el origen forman parte del
analisis. Los campos originales de Store, modalidad y uso se conservan en el
detalle de auditoria, pero no gobiernan el resumen normalizado.

La implementacion compartida vive en
`scripts/lib/store_taxonomy.py::build_normalized_store_summary`. Los reportes
no deben volver a agrupar por `store_raw`, `usage_type`, `Sale Type` ni otra
columna original para construir un resumen por plataforma.

Controles obligatorios:

1. el total del resumen normalizado debe cerrar exactamente contra las filas
   reportables que lo alimentan;
2. una modalidad desconocida permanece `Unknown` y nunca se infiere;
3. Spotify Premium y Ads no pueden colapsar en una sola fila cuando el crudo
   las distingue;
4. en YouTube, monetizacion y origen se mantienen como dimensiones distintas;
5. el resumen por tema sigue agrupando por identidad de catalogo y no incorpora
   Store/DSP como clave.

### Mapa rector de identidad y resumen por tema

Este mapa aplica a todos los reportes genericos de regalias, sin excepciones por
artista o busqueda:

1. **Ingest standardized**
   - conserva todas las columnas originales;
   - completa columnas canonicas comprobables (`asset_isrc`, `product_upc`,
     `video_id`, `channel_id`, `track_statement_style`, `content_type`);
   - no infiere un identificador que el archivo no demuestra.
2. **Catalogo**
   - resuelve aliases de ISRC, UPC y video hacia un `catalog_key` estable;
   - nunca une dos ISRC validos diferentes solo por texto parecido.
3. **Filtro del reporte**
   - aplica las policies de generacion/caja y el estado activo del catalogo;
   - agrega el `catalog_key` resuelto antes de resumir.
4. **Resumen por tema**
   - agrupa una sola vez por `catalog_key`;
   - Store/DSP, territorio, monetizacion y origen de contenido no multiplican
     temas;
   - los codigos originales quedan como trazabilidad, no como clave economica.
5. **Detalle**
   - conserva filas y codigos de origen para poder explicar el total.

La busqueda por palabras usa coincidencia literal normalizada: no distingue
mayusculas y tolera espacios, guiones y guiones bajos. Por ejemplo,
`superjunte` encuentra `Super Junte`. No se usa fuzzy matching ni se unen obras
por similitud aproximada.

Caso testigo validado el 2026-08-13:

- busqueda: `superjunte` / `super junte`;
- periodo: statement 2026-04 a 2026-06;
- ambas variantes recuperan 10.665 filas y USD 3.074,282234;
- el resumen anterior generaba 53 filas tecnicas por Store/tipo;
- el resumen canonico genera 9 identidades y reconcilia con resumen mensual,
  Store, territorio y detalle.

### Regla YouTube: monetizacion y origen son dimensiones separadas

- `Premium` / `Ads` describe como monetizo la fila.
- `Music / Art Track`, `Video / Channel`, `UGC / Content ID` o `Shorts`
  describe el origen del contenido.
- Si el statement identifica explicitamente `YouTube Channel Income` o
  `Partnered Channel`, el origen es `Video / Channel`, aunque el DSP o plan diga
  `YouTube Music` o `Premium`.
- Esta clasificacion no cambia importes ni identidad.

## Catalogo master

Script:

- `scripts\build_catalog_master.py`

Output:

- `warehouse\marts\catalog_master.parquet`

El catalogo master es parte obligatoria del cierre analitico. No es un cache
decorativo: resuelve identidad de obras, actividad por transaction month,
estado activo/inactivo, labels normalizados, release dates y gobierno de
reportes.

Despues de reconstruir consolidated/song-level marts, tambien debe
reconstruirse `catalog_master.parquet`. Si los marts de ingresos llegan a un mes
posterior al catalogo, el paquete queda inconsistente y no debe publicarse como
vigente.

## Reporte por statement desde marts

Script:

- `scripts\build_statement_report_from_mart.py`

Output:

- `reports\reporte_ingresos_digitales_por_mes_de_statement_marts.xlsx`

Replica el formato del reporte viejo:

- Hoja `TOTAL`
- Hojas por `source/account`
- Artistas por fila
- Statement periods por columna
- TOTAL USD por hoja

La documentacion completa de los criterios viejo/nuevo esta en:

- `docs\statement_report_notes.md`

## Diferencias conocidas contra reporte viejo

### ONErpm MAWZ

El reporte nuevo incluye `mawzrecords 2024-02 Masters`, recuperado por normalizacion `RUR -> RUB`.

### ONErpm Henry

El reporte nuevo usa conversion FX; el viejo usaba `net_amount` directo.

## SoundOn Summary

`Summary` no se carga al standardized principal. Solo se usa como control en `audit_soundon.py`.

## Resumen operativo del dashboard de regalias

`royalties_dashboard_summary.parquet` se construye desde
`standardized_raw_all_sources.parquet` y aplica la misma policy de generacion,
estado del catalogo que los reportes. Conserva el neto reportable base.

La personalizacion porcentual no se materializa en este parquet. Dashboard y
reportes leen la version vigente de Cloud SQL y aplican el ajuste al generar la
respuesta o el archivo. Cambiar un porcentaje no requiere reconstruir ni
publicar el mart.

Control especifico:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\qa\qa_distributor_policy_runtime.py
```

El control falla si reaparece el JSON operativo, si Cloud SQL no tiene policies
activas o si el dashboard vuelve a guardar columnas de policy dentro del mart.

Cuando el consolidado supera 256 MB, el cierre no agrupa el universo completo
en memoria. Primero separa el standardized por `statement_period` en lotes
acotados que preservan exactamente el schema; despues procesa cada mes con la
misma funcion de negocio y une los resultados compactos.

Reglas tecnicas obligatorias:

- no renombrar columnas originales para facilitar la particion;
- no usar una base SQL ni un pipeline alternativo para este cierre;
- escribir los fragmentos solamente en `staging`;
- reemplazar el dashboard vigente de forma atomica al finalizar;
- limpiar todos los fragmentos aun cuando falle un periodo;
- conservar el dashboard anterior si el nuevo cierre no termina.

## Auditorias recomendadas

Despues de regenerar marts, correr:

```powershell
python C:\royalties_pipeline\scripts\audit_marts_general.py
python C:\royalties_pipeline\scripts\audit_consolidated_marts.py
```

Y reconstruir catalogo:

```powershell
python C:\royalties_pipeline\scripts\build_catalog_master.py
```

Para SoundOn:

```powershell
python C:\royalties_pipeline\scripts\audit_soundon.py
```
