# Configurador Distribuidoras + Catalogo - Fase 1

Fecha: 2026-05-23

## Objetivo

Esta fase documenta el estado real de reportes, catalogo y reglas de negocio antes
de disenar un configurador editable. No cambia datos ni logica productiva.

La decision de fondo es mover reglas de negocio hoy hardcodeadas hacia una capa
configurable y visible:

- reglas por distribuidora/cuenta;
- reglas por obra/catalog_key;
- plantillas de reportes;
- filtros por contrato, release date, cuenta externa y ownership.

## Principio rector

Los reportes no deberian "hacer magia" propia. Deberian leer:

1. marts de ingresos;
2. catalogo general;
3. estado/ownership del catalogo;
4. politica de distribuidora/cuenta;
5. template del reporte.

Los crudos y standardized siguen siendo la verdad historica. El configurador solo
gobierna como se interpretan para reportes.

## Estado actual de piezas principales

### Catalogo

Archivo principal:

- `warehouse/marts/catalog_master.parquet`

Estado observado:

- filas: 2621;
- ya tiene `external_release_date`;
- ya tiene `external_label`;
- se reconstruye desde `song_level_all_sources.parquet` y `standardized_raw_*`.

Campos relevantes actuales:

- `catalog_key`
- `asset_isrc`
- `primary_upc`
- `track_id`
- `track_title`
- `artist_statement`
- `sources`
- `accounts`
- `source_sheets`
- `first_transaction_month`
- `last_transaction_month`
- `external_release_date`
- `external_label`
- `external_match_url`
- `external_metadata_status`

### Estado de catalogo

Archivo:

- `warehouse/registry/catalog_status.parquet`

Estado observado:

- filas: 6;
- columnas:
  - `catalog_key`
  - `active`
  - `status_notes`
  - `updated_at`
  - `include_in_reports`
  - `catalog_business_status`

Uso actual:

- si `include_in_reports = false`, los reportes conectados excluyen la obra;
- si no existe override, se asume que entra en reportes;
- el estado no borra crudos ni marts.

### Metadata externa

Archivos:

- `warehouse/marts/catalog_release_metadata.parquet`
- `warehouse/registry/catalog_release_lookup_cache.parquet`

Uso:

- Spotify por ISRC/UPC;
- YouTube por Video ID;
- texto/artista solo como fallback controlado;
- cache para no repetir consultas externas;
- `external_label` se usa como ayuda humana, no como verdad contractual.

## Reportes auditados

### Reporte por statement

Script:

- `scripts/build_statement_report_from_mart.py`

API:

- `POST /reports/statement`

Frontend:

- tarjeta `Reporte por statement`;
- selector `Reporte viejo` / `Reporte nuevo`.

Usa filtro de catalogo:

- si, mediante `filter_reportable_catalog`.

Version legacy:

- conserva criterio historico;
- FUGA aplica factor `0.977832`;
- SoundOn entra solo por `my_royalty`;
- ONErpm MAWZ entra completo, incluyendo `Masters` y `Shares In & Out`;
- ONErpm Gusty original queda excluido por defecto desde la hoja `Config`;
- agrega variante `onerpm_gusty_dj_post_motorcito`.

Version new:

- FUGA, DashGo, Orchard y SoundOn mantienen criterio base;
- ONErpm Henry entra completo;
- ONErpm MAWZ entra solo `Masters`;
- ONErpm Gusty entra solo post Motorcito por criterio de contenido;
- ONErpm La Nueva Sangre intenta usar release metadata y, si no hay metadata,
  cae a regla provisoria por ancla `Ni Ahi, Ni Aca, Ni Alla`.

Reglas hardcodeadas detectadas:

- `FUGA_STATEMENT_FACTOR = 0.977832`;
- cuentas ONErpm nuevas en `NEW_REPORT_ONERPM_ACCOUNTS`;
- `GUSTY_VARIANT_BASE_ACCOUNT = "gusty_dj"`;
- `GUSTY_VARIANT_ACCOUNT = "gusty_dj_post_motorcito"`;
- terminos de Motorcito;
- terminos de ancla La Nueva Sangre;
- `LA_NUEVA_SANGRE_CONTRACT_CUTOFF_DATE = "2023-06-15"`;
- MAWZ `source_sheet = Masters`;
- exclusion de `Shares In & Out` en reporte nuevo;
- default excluded scope `onerpm_gusty_dj` en reporte legacy.

Necesidad de configurador:

- mover reglas por cuenta/source_sheet a politica de cuenta;
- mover anclas/cortes contractuales a configuracion;
- que reporte viejo/nuevo sean templates, no ramas especiales del script.

### Reporte dinamico por keywords

Script:

- `scripts/build_keyword_royalty_report.py`

API:

- `POST /reports/keyword`
- `GET /reports/keyword-download`
- `POST /reports/google-sheet`

Frontend:

- tarjeta `Reporte de regalias`;
- Excel o Google Sheet.

Usa filtro de catalogo:

- si, tanto en base raw como en song level segun modo.

Reglas actuales:

- busqueda por palabras clave en varias columnas de titulo/artista/codigos;
- puede usar `transaction_month` o `statement_period`;
- permite excluir ISRC puntuales;
- normaliza store/usage/territory para el reporte;
- `raw_limit` es control de salida, no de negocio.

Reglas hardcodeadas detectadas:

- columnas de busqueda;
- normalizacion de store;
- normalizacion de usage;
- fallback de territory;
- exclusion por ISRC se pasa como parametro pero no queda como template persistente.

Necesidad de configurador:

- guardar presets de keywords;
- guardar exclusiones por catalog_key/ISRC;
- guardar fuente/cuenta permitida;
- que presets especiales no dependan de scripts ad hoc.

### Reportes personalizados por titulos

Script:

- `scripts/build_custom_title_royalty_report.py`

API:

- `GET /reports/custom/options`
- `POST /reports/custom/title-list`

Frontend:

- tarjeta `Reportes Personalizados`;
- menu de scripts/templates;
- listado editable de temas/artistas;
- selector distribuidora/cuenta.

Templates actuales:

- `los_anormales`
- `gusty_fuga_contracts`

Usa filtro de catalogo:

- si, en `build_custom_title_royalty_report.py`.

Reglas actuales:

- lineas de busqueda pueden ser `titulo` o `titulo | artista`;
- fechas por statement;
- seleccion por source/account;
- summaries por source, title, statement, store, usage, territory y song matches.

Reglas hardcodeadas detectadas:

- `DEFAULT_LOS_ANORMALES_TERMS`;
- variantes manuales de titulos;
- templates definidos en `app/vpo_corp_api.py`;
- columnas de busqueda y fallback.

Necesidad de configurador:

- persistir templates desde UI;
- guardar lista de titulos/artistas por template;
- guardar cuentas incluidas por template;
- versionar templates para saber con que regla salio cada reporte.

### Reporte FUGA Gusty contratos

Script:

- `scripts/build_fuga_gusty_contract_report.py`

API:

- se ejecuta desde `POST /reports/custom/title-list` cuando `template_key`
  es `gusty_fuga_contracts`.

Usa filtro de catalogo:

- si, al preparar raw FUGA.

Reglas actuales:

- fuente fija: `fuga`;
- cuenta fija: `indyana_records`;
- busca Gusty en multiples columnas;
- clasifica contrato viejo/nuevo usando mapa ONErpm/Motorcito;
- corte base `MOTORCITO_FIRST_MONTH = "2023-04"`;
- soft matches y excepciones manuales para titulos complejos.

Reglas hardcodeadas detectadas:

- fuente/cuenta fija;
- Motorcito como ancla;
- stopwords de signature;
- excepciones puntuales en `report_specific_gusty_match`;
- clasificacion default `CONTRATO NUEVO - SIN MATCH ONErpm`.

Necesidad de configurador:

- representar contrato como objeto de negocio;
- asociar ancla contractual a artista/cuenta;
- permitir override manual por catalog_key;
- evitar que excepciones puntuales vivan dentro del script.

### Script viejo de titulos

Script:

- `scripts/build_title_list_royalty_report.py`

Uso:

- reporte historico/manual para lista fija de titulos.

Usa filtro de catalogo:

- no se detecto uso de `filter_reportable_catalog`.

Reglas hardcodeadas:

- `REQUESTED_TITLES`;
- `MANUAL_VARIANTS`;
- periodo hasta `end_month`;
- busqueda textual por columnas fijas.

Decision recomendada:

- no seguir extendiendolo;
- reemplazar su uso por `build_custom_title_royalty_report.py`;
- si se conserva, conectarlo al filtro de catalogo para no romper gobierno.

### Reporte Super Junte investigacion

Script:

- `scripts/generate_super_junte_investigation_report.py`

Uso:

- auditoria especial YouTube / unidades / statements;
- contiene constante `YOUTUBE_PUBLIC_VIEWS = 88478836`;
- contiene keyword fija `super junte`;
- contiene corte fijo `END_STATEMENT_PERIOD = "2025-03"`.

Usa filtro de catalogo:

- no se detecto uso directo de `filter_reportable_catalog`;
- reutiliza helpers de keyword report para busqueda/normalizacion.

Reglas hardcodeadas:

- keyword;
- fecha de corte;
- views publicas;
- foco en YouTube video;
- hojas especiales de auditoria.

Decision recomendada:

- mantener como reporte investigativo, no operativo general;
- si se convierte en template, parametrizar keyword, fecha y views publicas;
- conectarlo al filtro de catalogo si sus resultados se usan para pagos.

### Reporte viejo ingresos por statement desde marts

Script:

- `scripts/build_ingresos_por_statement_from_marts.py`

Uso:

- antecesor del statement report actual;
- conserva logica basica por archivo standardized;
- tiene FUGA factor y alerta visual de shares.

Usa filtro de catalogo:

- no se detecto uso de `filter_reportable_catalog`.

Decision recomendada:

- considerar deprecated para UI/producto;
- dejarlo solo como referencia historica;
- no usarlo como base del configurador.

## Source monitor

API:

- `GET /source-monitor`
- `POST /source-monitor/{id}/process`
- `POST /source-monitor/publish`
- `PATCH /source-monitor/{id}`

Frontend:

- tarjeta `Control de distribuidoras`.

Config:

- path esperado: `warehouse/registry/source_monitor_config.json`;
- estado observado: archivo no existe, por lo tanto la API usa defaults de
  `app/vpo_corp_api.py`.

Reglas actuales:

- monitorea carpetas de `input_raw`;
- compara raw files contra marts;
- puede ejecutar pipeline por source/account;
- puede publicar datos analiticos a cloud;
- `monitoring_active = false` solo apaga alertas, no excluye historico.

Reglas hardcodeadas detectadas:

- listado default de sources/accounts en API;
- rutas input/output;
- scripts de pipeline por source;
- tolerancias por frecuencia;
- notas de negocio de cuentas externas dentro del codigo.

Necesidad de configurador:

- separar monitoreo operativo de politica de reporte;
- una cuenta inactiva para monitoreo puede seguir entrando en reportes;
- una cuenta activa para monitoreo puede tener contenido excluido por catalogo.

## Catalogo web

API:

- `GET /catalog`
- `PATCH /catalog/status`

Frontend:

- tarjeta `Catalogo General`.

Capacidades actuales:

- filtrar por distribuidora/source;
- filtrar por cuenta;
- filtrar por artista;
- filtrar por palabra clave;
- filtrar por rango de meses;
- filtrar por estado;
- marcar incluir/excluir de reportes.

Limitacion actual:

- el estado es por `catalog_key`;
- no hay todavia politica por distribuidora/cuenta;
- no hay ownership por cuenta;
- no hay contrato/split por obra;
- no hay versionado de reglas de reporte.

## Matriz de uso de catalog_status

| Reporte/script | Usa catalog_status | Comentario |
| --- | --- | --- |
| `build_statement_report_from_mart.py` | Si | Conectado en base general y variantes nuevas |
| `build_keyword_royalty_report.py` | Si | Conectado en raw/song segun modo |
| `build_custom_title_royalty_report.py` | Si | Conectado para templates personalizados |
| `build_fuga_gusty_contract_report.py` | Si | Conectado al raw FUGA |
| `build_title_list_royalty_report.py` | No | Candidato a deprecated o refactor |
| `build_ingresos_por_statement_from_marts.py` | No | Historico/deprecated |
| `generate_super_junte_investigation_report.py` | No directo | Investigativo, deberia conectarse si afecta pagos |

## Reglas de negocio que deben salir de scripts

### Por distribuidora/cuenta

- tipo de cuenta: propia, externa, mixta, legacy;
- entra en cash view;
- entra en statement view;
- entra en catalog view;
- hojas incluidas para generacion (`Masters`, `Youtube Channels`, `my_royalty`);
- hojas excluidas para generacion (`Shares In & Out`, summaries);
- si shares son ingreso, alerta, transferencia o solo auditoria;
- si se monitorea la carpeta;
- frecuencia esperada;
- notas operativas.

### Por catalog_key

- activo/inactivo;
- incluir en reportes;
- ownership: VPO, artista personal, externo, pendiente;
- contrato viejo/nuevo;
- release date validada/manual;
- label externo de control;
- nota humana.

### Por template de reporte

- nombre visible;
- objetivo;
- base temporal: statement o transaction;
- sources/accounts incluidas;
- reglas de exclusion;
- filtros por catalog_status;
- hojas de salida esperadas;
- si sirve para pago o solo investigacion;
- version de regla.

## Huecos documentales detectados

1. No existe todavia un documento que una distribuidora/cuenta + catalogo + reportes.
2. `source_monitor_config.json` no existe; la configuracion real vive como default en codigo.
3. Las reglas ONErpm especiales siguen parcialmente hardcodeadas.
4. Los templates personalizados viven en API/codigo, no en configuracion persistente.
5. No hay versionado de reglas usadas para generar un reporte.
6. No hay una tabla de ownership por cuenta/catalog_key.
7. No hay campo de split contractual por obra; solo se dejo pensado.
8. Reportes investigativos pueden no respetar `catalog_status`.
9. La diferencia entre "generacion de master" y "caja neta/shares" esta documentada,
   pero no modelada como politica reutilizable.

## Riesgos actuales

- Cambiar una regla en script puede modificar reportes pasados sin visibilidad.
- Una cuenta externa puede mezclar catalogo viejo y nuevo si no hay release date o override.
- Un item excluido en catalogo puede no quedar excluido en scripts no conectados.
- `Shares In & Out` puede confundirse con generacion si no se explicita la vista.
- Los reportes especiales crecen por excepciones manuales si no se vuelven templates.

## Recomendacion para Fase 2

Disenar un modelo minimo con cuatro entidades:

1. `distributor_account_policy`
   - source;
   - account;
   - ownership_default;
   - account_type;
   - monitor_active;
   - report_active;
   - cash_view_policy;
   - statement_view_policy;
   - catalog_view_policy;
   - sheet_rules;
   - notes.

2. `catalog_business_override`
   - catalog_key;
   - include_in_reports;
   - business_status;
   - ownership;
   - contract_segment;
   - manual_release_date;
   - notes.

3. `report_template`
   - template_key;
   - title;
   - report_family;
   - time_basis;
   - source_account_scope;
   - catalog_filter_required;
   - output_profile;
   - rule_version.

4. `contract_anchor`
   - artist/business_entity;
   - source/account;
   - anchor_type: release_date, track_reference, manual_date;
   - anchor_terms;
   - cutoff_date/month;
   - old_content_policy;
   - new_content_policy.

## Proxima validacion humana

Antes de programar Fase 2, validar estas preguntas:

1. El configurador debe empezar por ONErpm o por todas las distribuidoras?
2. La primera pantalla debe ser read-only o editable limitada?
3. `build_title_list_royalty_report.py` se depreca formalmente?
4. `generate_super_junte_investigation_report.py` queda investigativo o se convierte
   en template configurable?
5. En reporte nuevo, MAWZ `Masters only` queda como politica oficial?
6. Para La Nueva Sangre, release date + catalog override pasa a ser regla final?
7. `external_label` se usa solo como ayuda visual, no como regla automatica?
