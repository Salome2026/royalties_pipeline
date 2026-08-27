# Catalogo general core

El catalogo general es una capa maestra del sistema. No reemplaza los crudos ni los
marts de ingresos; los organiza por obra para poder controlar contratos, actividad,
release dates, reportes especiales y filtros de negocio.

## Principios

- Los statements crudos y standardized no se modifican.
- El catalogo se puede reconstruir todas las veces que haga falta.
- La identidad de una obra se arma con todos los identificadores disponibles:
  - ISRC;
  - UPC;
  - Video ID;
  - track/product ids;
  - titulos y artistas como fallback.
- Si aparece un nuevo statement, puede aparecer una obra nueva o puede enriquecer
  una obra existente con un identificador que antes no teniamos.
- Activo/inactivo no borra datos. Es una capa de estado para reportes.

## Fuentes

El catalogo usa dos capas:

1. `song_level_all_sources.parquet`
   - aporta totales economicos;
   - aporta unidades;
   - aporta primera/ultima transaccion;
   - aporta agrupacion por source/account.

2. `standardized_raw_*.parquet`
   - aporta datos de identidad ricos que el song level no siempre conserva;
   - especialmente UPC, Video ID, Product UPC, Display UPC, ISRC crudo,
     variaciones de titulo y artista.

## Clave canonica

La clave canonica se decide asi:

1. ISRC valido si existe.
2. Video ID si no hay ISRC.
3. Texto normalizado `titulo + artista` solo como fallback.

Regla adicional:

- Si una fila no trae ISRC pero trae UPC, y ese UPC se ve asociado a un unico ISRC
  en otra fuente, la fila se mapea al ISRC canonico.
- Esta asociacion es identidad derivada. No modifica el raw ni el standardized.
- Si el UPC apunta a mas de un ISRC, o la evidencia no alcanza, queda pendiente
  de revision y no se fuerza.

Ejemplo:

- `Raka Taka Taka`
- ISRC: `ARHXW2002581`
- UPC: `655857944481`
- Release date Spotify: `2020-06-19`

Si una fuente trae solo texto/UPC y otra trae ISRC, el catalogo debe terminar con
una unica obra canonica por ISRC.

## FUGA product-level rows

FUGA puede traer filas `Asset/Product = Product`. En esas filas el ingreso viene
por producto/release y no por asset:

- puede traer `Product UPC`;
- puede traer `Product Quantity`;
- puede no traer `Asset ISRC`, `Asset Title` ni `Asset Artist`;
- eso no significa automaticamente error de FUGA.

Caso validado:

- archivo origen:
  `C:\royalties_pipeline\input_raw\fuga\March2026StatementRun_INDYANARECORDSLLC-royalty_product_and_asset.csv`
- UPC: `198474357444`
- tema/producto: `Perreo TL`
- artista/producto: `mamiyosoyelth and Lihueeel`
- fila original: `Product`, `Asset ISRC` vacio, `Amazon`, `Download`;
- el mismo UPC aparece asociado a un unico ISRC: `QZK6L2413497`;
- Spotify confirma el album UPC `198474357444` y el track ISRC
  `QZK6L2413497` en un release de un solo track.

Decision:

- conservar la fila original como producto sin ISRC;
- resolverla en catalogo/reportes hacia `ISRC:QZK6L2413497` solo como identidad
  derivada;
- conservar trazabilidad con columnas conceptuales:
  - `isrc_original`;
  - `upc_original`;
  - `resolved_isrc`;
  - `resolution_method`;
  - `resolution_confidence`;
  - `resolution_note`.

Esta regla debe aplicar tambien a nuevos statements: cada vez que entren archivos
nuevos, el rebuild del catalogo debe reevaluar aliases UPC->ISRC con la evidencia
actual. No se debe agregar una excepcion por tema ni por UPC en scripts de
reportes.

## Release date

La metadata externa vive en:

- `warehouse/marts/catalog_release_metadata.parquet`
- `warehouse/registry/catalog_release_lookup_cache.parquet`

Criterio:

- ISRC es la fuente preferida.
- UPC se usa si Spotify devuelve un unico album.
- Video ID se usa para YouTube cuando aplica.
- Texto/artista global no se usa por defecto porque puede generar falsos positivos.
- Texto/artista solo debe usarse en casos acotados y revisables.

## Label externo y normalizacion

El label externo tambien debe conservarse siempre en su forma original. Es dato de
metadata/auditoria, no una regla final de negocio.

Campos conceptuales:

- `external_label`: valor original devuelto por Spotify/YouTube u otra fuente;
- `label_normalized`: limpieza tecnica para agrupar variantes obvias;
- `label_group`: agrupacion de negocio revisada por humano.

Primera normalizacion validada para analizar labels:

- quitar prefijos de copyright tipo `(P)` / `P`;
- quitar años `19xx` / `20xx`;
- unificar mayusculas/minusculas;
- limpiar espacios y separadores redundantes.

Esta normalizacion se usa solo como capa derivada. Nunca debe pisar
`external_label`.

Implementacion vigente:

- `external_label`: valor original devuelto por Spotify/YouTube u otra fuente;
- `label_normalized_auto`: limpieza tecnica reconstruible;
- `label_normalized_override`: correccion humana guardada en
  `catalog_status.parquet`;
- `label_normalized`: valor operativo visible, usando override si existe y si no
  el valor automatico;
- la edicion manual desde Catalogo General solo modifica
  `label_normalized_override`.

Normalizacion automatica aplicada:

- quitar prefijos de copyright tipo `(P)` / `P`;
- quitar prefijos de copyright tipo `(C)` / `C`;
- quitar `P`/`C` sueltos solo si anteceden un año legal;
- quitar años `19xx` / `20xx` al inicio;
- limpiar espacios redundantes.

Regla validada en conversacion:

- `GUSTY DJ | Mawz Records` debe agruparse con `GUSTY DJ / Mawz Records`.

Motivo: en este caso el separador `|` representa la misma relacion de label que
`/`. Se valida puntualmente para este grupo y no como reemplazo global ciego de
todos los separadores, porque en otros labels el separador puede tener otro
sentido.

Analisis preliminar al 2026-05-23:

- obras totales en catalogo: `2621`;
- obras con label: `497`;
- obras sin label: `2124`;
- labels originales distintos: `88`;
- labels normalizados por regla minima: `49`;
- reduccion aproximada: `44%`.

Uso esperado:

- `external_label` sirve para auditoria y trazabilidad;
- `label_normalized` ayuda a revisar patrones;
- `label_group` podra alimentar filtros humanos del catalogo;
- ninguna de estas capas reemplaza contrato, split ni ownership por obra.

## Scripts

### Reconstruir catalogo

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\build_catalog_master.py
```

Output:

- `warehouse/marts/catalog_master.parquet`

### Enriquecer release date global

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\build_catalog_global_release_metadata.py --min-amount-usd 100 --limit 40
```

Este proceso es incremental:

- conserva lo ya resuelto;
- procesa pendientes por prioridad;
- usa cache para no pegarle siempre a APIs externas.

Despues de enriquecer metadata, reconstruir catalogo otra vez:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\build_catalog_master.py
```

Reglas de seguridad del enriquecimiento:

- Si una obra ya tiene `release_date`, no se vuelve a consultar.
- Si una busqueda ya quedo como `not_found`, no se repite en cada corrida.
- Si Spotify devuelve `429`, el job marca `rate_limited` y corta sin quedarse
  esperando horas.
- Las siguientes corridas deben ser por lotes chicos y priorizados.
- El fallback por texto/artista esta desactivado por defecto en el global; se usa
  solo con `--allow-text` y revision humana.

## Spotify batch APIs

Spotify tiene endpoints batch como `Get Several Tracks` y `Get Several Albums`.
Hay que usarlos donde realmente reducen llamadas:

- Discovery: buscar por ISRC/UPC sigue requiriendo `search`; Spotify no ofrece un
  batch directo por lista de ISRC/UPC.
- Hydration: una vez que ya tenemos `spotify_track_id` o `spotify_album_id`, si
  queremos completar metadata adicional, ahi si conviene pedir varios tracks o
  albums por request.
- Para release date, el resultado de `search` ya trae album/release date, asi que
  hacer un batch posterior no reduce el cuello principal si todavia no tenemos IDs.

Estrategia futura:

1. Guardar siempre `spotify_track_id` y `spotify_album_id` en cache cuando el
   search encuentra match.
2. Si mas adelante necesitamos label, portada, tipo de album u otra metadata,
   hidratar esos IDs con batch.
3. No usar batch como excusa para repetir searches ya cacheadas.

## Flujo luego de nuevos statements

1. Cargar standardized de la distribuidora.
2. Rebuild de song level / marts agregados.
3. Reconstruir `catalog_master`.
4. Revisar aliases de identidad generados por catalogo:
   - UPC -> ISRC solo cuando el UPC tenga un unico ISRC;
   - video/text fallback solo cuando no exista identificador mejor;
   - filas sin evidencia suficiente quedan pendientes.
5. Ejecutar metadata global incremental para nuevos pendientes.
6. Reconstruir `catalog_master` para incorporar release dates.
7. Publicar marts si el control visual da OK.

El publish a GCS debe incluir `catalog_master.parquet`; ya no es un archivo
auxiliar opcional, porque los reportes lo usan para resolver `catalog_key` y
estado de negocio.

## Estado activo/inactivo

El estado de cada obra se guarda separado:

- `warehouse/registry/catalog_status.parquet`

Esto permite marcar obras activas/inactivas sin tocar:

- standardized raw;
- song level;
- reportes historicos;
- statements originales.

En web/cloud este archivo tambien es dato de negocio, no cache. La API puede
sincronizarlo con GCS:

- variable: `VPO_CATALOG_STATUS_SYNC_GCS=1`;
- objeto default: `marts/catalog_status.parquet`;
- override opcional: `VPO_CATALOG_STATUS_GCS_OBJECT`.

Asi, si desde la web se marca una obra fuera de reportes, Cloud Run no pierde esa
decision al reiniciar.

## Gobierno de reportes por catalogo

La regla de negocio queda centralizada en el catalogo:

- cada fila de royalties/statement se traduce a `catalog_key`;
- se cruza contra `catalog_status.parquet`;
- si `include_in_reports = false`, esa fila no entra en reportes operativos;
- si no existe override para el `catalog_key`, se asume `include_in_reports = true`.

Campos de estado:

- `active`: visibilidad operativa general del item;
- `include_in_reports`: si participa o no en reportes de royalties/statements;
- `catalog_business_status`: clasificacion de negocio (`vpo_catalog`, `artist_personal`, `external_catalog`, `pending_review`, `inactive`);
- `status_notes`: explicacion humana.

Ejemplo: si una obra como `Boxindanga` aparece en statements pero no pertenece al
catalogo VPO, se marca en el catalogo como fuera de reportes. Los crudos siguen
existiendo y el item sigue siendo trazable, pero los reportes dejan de sumarlo.

## Catalogo, caja y generacion reportable

Una obra puede existir en statements sin ser ingreso VPO. Por eso el catalogo no
debe confundirse con caja ni con ganancia final.

Capas separadas:

1. `catalogo/auditoria`
   - conserva toda obra detectada en statements;
   - incluso obras externas, personales del artista o no reportables;
   - permite explicar por que algo entra o sale.

2. `generacion reportable VPO`
   - obras que deben aparecer en reportes operativos de VPO;
   - respeta `include_in_reports`;
   - no significa que Indyana/VPO retenga el 100%.

3. `caja`
   - dinero que efectivamente deposita cada distribuidora/cuenta;
   - puede venir de cuenta propia, cuenta externa o shares;
   - no debe mezclarse con generacion de obra.

4. `split / contrato`
   - define cuanto corresponde a Indyana, artista, owner o terceros;
   - se resuelve por obra/contrato, no por distribuidora;
   - es una etapa posterior a decidir si una obra es reportable.

Ejemplo conceptual:

- `Boxindanga` aparece en ONErpm La Nueva Sangre.
- Debe existir en Catalogo General y en auditoria.
- Si el negocio define que no pertenece al catalogo VPO, queda
  `include_in_reports = false`.
- No entra al reporte por statement VPO ni a generacion administrada VPO.
- Si el artista debe ese dinero personalmente, eso pertenece a una cuenta
  corriente/deuda del artista, no al reporte principal de royalties.

Otro ejemplo conceptual:

- Un master puede haber sido personal de un artista en ONErpm Gusty.
- Luego puede migrar a FUGA, donde el dinero se deposita a Indyana.
- Si VPO solo distribuye y retiene un porcentaje, la obra debe ser reportable,
  pero el split contractual debe indicar que Indyana no retiene el 100%.

Regla clave:

> Reportable no significa 100% nuestro. Reportable significa que la obra entra en
> la vista operativa de VPO. La participacion economica se resuelve despues con
> contrato/split por obra.

Implementacion reutilizable:

- `scripts/lib/catalog_report_filter.py`

Reportes conectados:

- reporte por statement;
- reporte dinamico de regalias por keywords;
- reportes personalizados de titulos;
- reporte especial FUGA Gusty contratos.

Importante: el filtro no modifica `standardized_raw`, `song_level` ni statements
originales. Solo gobierna la salida de reportes.

Desde 2026-08-15, `scripts/lib/catalog_report_filter.py` tambien cruza cada fila
contra la policy viva de distribuidoras almacenada en Cloud SQL. El filtro operativo
de generacion reportable requiere:

- `include_in_reports = true` en el catalogo;
- `catalog_view = true` en la policy de distribuidora/cuenta/hoja;
- `statement_view` distinto de `false`;
- `revenue_basis` de tipo `generation`, `correction` o `legacy_generation`.

Esto separa dos verdades que antes podian mezclarse:

- generacion de obra: entra en reportes de regalias;
- transferencias/shares/caja: quedan para control de caja o auditoria.

Caso testigo validado:

- `Hechizado` en ONErpm Gusty/MAWZ;
- `Masters` y `Youtube Channels` son generacion;
- `Shares In & Out` de MAWZ es transferencia positiva de caja/auditoria;
- esa transferencia no debe sumarse al reporte de regalias porque inflaria la
  generacion de la obra.

## Generacion vs transferencias

El campo principal `catalog_master.amount_usd` representa generacion de obra,
no caja ni transferencias entre cuentas.

Desde 2026-08-15, `scripts/build_catalog_master.py` lee la misma policy viva
desde Cloud SQL. No existe una copia JSON operativa ni un fallback local.

La regla es:

- entran a `amount_usd` solo filas con `catalog_view = true`;
- la base debe ser `generation`, `correction` o `legacy_generation`;
- hojas de tipo `transfer`, como ONErpm `Shares In & Out`, no suman a
  generacion;
- esos importes quedan conservados en `transfer_amount_usd`;
- el total bruto observado queda conservado en `observed_amount_usd`;
- si una fila de song level no matchea una policy, el build debe fallar en vez
  de inventar un fallback silencioso.

Ejemplo ONErpm:

- `Masters` y `Youtube Channels` son generacion;
- `Shares In & Out` son transferencia/caja/auditoria segun la cuenta;
- sumar `Shares In & Out` a `Masters` infla el catalogo y mezcla conceptos.

Para que la policy sea aplicable, los marts `song_level_*` deben conservar
`source_sheet` y `revenue_basis` alineados al diccionario de statements.

## Worker de metadata externa

El worker de Spotify/YouTube enriquece el catalogo con `release_date` y `label`.
No debe convertirse en un proceso agresivo ni reconsultar datos ya cacheados.

Reglas operativas:

- si un item ya tiene `release_date`, no se vuelve a consultar;
- si un `release_date` ya existe en `catalog_release_lookup_cache.parquet` pero
  todavia no subio a `catalog_release_metadata.parquet`, el worker debe
  promoverlo desde cache sin consultar de nuevo;
- si Spotify devuelve `rate_limited`, ese lookup queda en cooldown;
- el cooldown default es `VPO_SPOTIFY_RATE_LIMIT_COOLDOWN_SECONDS=86400`;
- no correr el worker infinito con `min_amount=0`;
- el script se niega a ejecutar `--max-batches 0 --min-amounts 0` salvo override
  explicito con `--allow-infinite-zero-floor`;
- si Spotify devuelve un `Retry-After` mayor a `--max-retry-after-seconds`, el
  worker se detiene en vez de insistir.

Arranque seguro:

- usar `scripts/start_catalog_metadata_worker.ps1`;
- ese arranque trabaja por tandas finitas y prioriza montos `100,50,10`;
- dejar `min_amount=0` solo para corridas manuales, finitas y supervisadas.

## Interfaz operativa

La busqueda libre de tema, artista o identificador usa la regla comun de
keywords: no distingue mayusculas, tildes ni `n`/`ñ`. La equivalencia existe
solo durante la comparacion y no modifica la identidad ni la metadata mostrada.

La unica interfaz operativa de Catalogo general vive en:

- `web/app/features/catalog/CatalogModule.tsx`;
- `web/app/features/catalog/api.ts`;
- `web/app/features/catalog/types.ts`.

La pantalla principal `web/app/page.tsx` solo monta el modulo y le entrega el
permiso vigente. No conserva una segunda implementacion ni interpreta catalogo.

Comportamiento rector:

- el rango usa perfil `activity_window` y filtra actividad por mes completo;
- source, account, artista, label normalizado y estado son filtros de la misma
  consulta canonica;
- Configurador de distribuidoras puede abrir el catalogo prefiltrado por cuenta;
- activar/inactivar actualiza estado e inclusion en reportes, no elimina la obra;
- editar label modifica solamente `label_normalized_override`;
- `external_label` permanece visible como dato original y nunca se pisa;
- usuarios sin permiso de edicion pueden consultar, pero no alterar estado ni
  normalizacion.
