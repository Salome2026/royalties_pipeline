# Configurador Distribuidoras + Catalogo - Fase 2 Design

Fecha: 2026-05-23

## Objetivo

Esta fase define el diseno funcional del configurador antes de programarlo.

No cambia reportes, no cambia marts y no cambia datos productivos. El objetivo es
dejar una estructura clara para que las reglas que hoy viven en scripts pasen a
una capa visible, auditable y editable con control.

La primera distribuidora/cuenta a modelar debe ser ONErpm, porque ahi conviven
los casos mas dificiles:

- cuenta propia simple;
- cuenta propia con shares;
- cuenta externa historica;
- cuenta externa/mixta con catalogo viejo migrado;
- cortes contractuales por obra y no solo por mes.

## Principio de diseno

Los datos crudos y standardized no se corrigen desde el configurador.

El configurador responde una pregunta distinta:

> Dado que tengo estos datos, que parte entra en cada vista de negocio?

Vistas de negocio iniciales:

- `catalog_view`: todo lo que sirve para entender catalogo.
- `statement_view`: lo que se muestra en reportes por statement.
- `cash_view`: lo que representa caja o movimientos economicos de una cuenta.
- `audit_view`: datos que no entran a reportes principales, pero se conservan
  para investigar.

## Regla de trabajo documental

Antes de cambiar una regla de negocio o tocar un reporte productivo, el flujo de
trabajo debe ser:

1. leer la documentacion vigente relacionada;
2. verificar si la regla ya existe;
3. si la regla cambia, actualizar primero el documento correspondiente;
4. validar el cambio de criterio;
5. recien despues modificar codigo, configuracion o datos.

Esto evita parches aislados. Si durante una prueba aparece una excepcion nueva,
esa excepcion debe convertirse en regla documentada o quedar marcada como caso
manual pendiente. No debe quedar solamente escondida en un script.

## Capas del modelo

1. `standardized_raw`
   - verdad tecnica de lo que vino en cada archivo.
   - no se borra contenido por reglas de negocio.

2. `catalog_master`
   - una fila por obra/candidato de obra.
   - contiene ISRC, UPC, titulo, artista, fuentes, cuentas y metadata externa.

3. `distributor_account_policy`
   - politica por fuente/cuenta.
   - define si la cuenta es propia, externa, mixta o legacy.
   - define que hojas entran a cada vista.

4. `statement_source_dictionary`
   - diccionario humano de hojas, archivos y columnas originales.
   - explica que significa cada hoja del statement antes de decidir si entra.

5. `catalog_business_override`
   - excepcion humana por obra.
   - permite marcar activo/inactivo, ownership y segmento contractual.

6. `contract_cutoff`
   - fecha contractual de corte.
   - puede tener evidencia auxiliar, como Motorcito para Gusty o Ni Ahi para
     La Nueva Sangre, pero la regla de negocio es la fecha.

7. `report_template`
   - define que fuente/cuenta/regla usa cada reporte.
   - el reporte ejecuta el template; no inventa reglas propias.

## Entidad 1: distributor_account_policy

Representa la politica de una cuenta dentro de una distribuidora.

Campos propuestos:

| Campo | Uso |
| --- | --- |
| `policy_id` | Identificador estable de politica |
| `source` | Distribuidora: `onerpm`, `fuga`, `dashgo`, etc |
| `account` | Cuenta normalizada |
| `display_name` | Nombre visible en UI/reportes |
| `account_type` | `owned`, `external`, `mixed`, `legacy`, `inactive` |
| `ownership_default` | `vpo`, `artist`, `mixed`, `unknown` |
| `monitoring_active` | Si se alerta por archivos nuevos |
| `catalog_view_enabled` | Si aporta al catalogo |
| `statement_view_enabled` | Si aporta a reportes por statement |
| `cash_view_enabled` | Si aporta a caja/cuenta propia. Puede ser `true`, `false` o una regla parcial |
| `cash_view_mode` | Lectura humana de caja: `complete`, `partial_by_rule`, `excluded` |
| `cash_view_label` | Etiqueta visible: Caja completa, Caja parcial por regla, No caja |
| `cash_view_description` | Explicacion para evitar confundir cuenta completa con cuenta parcial |
| `default_time_basis` | `statement_period`, `transaction_month`, `release_date` |
| `sheet_rules_json` | Reglas por hoja: Masters, Shares, Youtube, etc |
| `shares_policy` | `income`, `transfer`, `audit_only`, `exclude` |
| `external_account_policy` | Como tratar cuentas externas |
| `contract_cutoff_id` | Fecha contractual opcional |
| `notes` | Explicacion humana |
| `updated_at` | Auditoria |

### Valores para account_type

- `owned`: cuenta propia de VPO/Indyana. En principio entra a statement y caja.
- `external`: cuenta de un artista o tercero. Puede aportar catalogo, pero no
  necesariamente caja.
- `mixed`: cuenta donde conviven catalogo propio y catalogo ajeno.
- `legacy`: cuenta o regla historica que se conserva por comparacion.
- `inactive`: no se monitorea mas, pero el historico no desaparece.

### Valores para caja

La caja no debe leerse como un booleano simple, porque hay cuentas mixtas.

- `complete`: la cuenta se considera caja propia para toda la parte reportable.
  Ejemplo: FUGA, DashGo, Orchard, SoundOn, ONErpm Henry.
- `partial_by_rule`: la cuenta no se toma completa, pero una parte si puede
  entrar como ingreso/caja VPO segun contrato, catalogo o release date.
  Ejemplo: ONErpm Gusty DJ y ONErpm La Nueva Sangre.
- `excluded`: la cuenta u hoja sirve para auditoria/catalogo, pero no impacta
  caja.

Para cuentas mixtas, la UI debe mostrar "Caja parcial por regla" y explicar la
regla. Evitar mostrar "Caja: no" porque se interpreta como si se ignorara toda
la cuenta.

## Decision final reportable

La auditoria de una cuenta no debe mostrar solamente si una obra entra por regla
contractual. Esa es una capa tecnica, no la decision final de negocio.

La decision final debe combinar:

1. regla de cuenta/distribuidora;
2. regla contractual de fecha;
3. estado del catalogo (`active` e `include_in_reports`);
4. excepciones manuales documentadas;
5. template del reporte que se esta ejecutando.

Ejemplo: una obra puede cumplir la fecha contractual y quedar `included` por
regla, pero si el catalogo la marca como inactiva o fuera de reportes, el
resultado final debe ser `excluded_by_catalog`. Esta capa evita que una obra
como Boxindanga vuelva a entrar en reportes solo porque cumple una fecha.

Estados de decision final:

| Estado | Significado |
| --- | --- |
| `reportable` | Entra por regla y esta activa/reportable en catalogo |
| `excluded_by_rule` | Queda fuera por fecha, cuenta u hoja |
| `excluded_by_catalog` | Entraria por regla, pero el catalogo la excluye |
| `manual_review` | Falta informacion suficiente o no hay match claro en catalogo |

La pantalla principal no debe listar todas las obras. Debe mostrar:

- resumen monetario por estado final;
- reglas aplicadas en lenguaje humano;
- alertas que requieren mirada;
- auditoria completa plegada como detalle secundario.

Esto mantiene la pantalla orientada a negocio y evita que el usuario pierda el
horizonte mirando cientos de renglones.

### Ejemplo sheet_rules_json

```json
{
  "Masters": {
    "catalog_view": true,
    "statement_view": true,
    "cash_view": true,
    "revenue_basis": "generation"
  },
  "Shares In & Out": {
    "catalog_view": false,
    "statement_view": false,
    "cash_view": true,
    "revenue_basis": "transfer",
    "audit_view": true
  },
  "Youtube Channels": {
    "catalog_view": true,
    "statement_view": true,
    "cash_view": true,
    "revenue_basis": "generation"
  }
}
```

## Entidad 2: statement_source_dictionary

Representa el diccionario humano de cada statement original.

Su objetivo no es procesar datos, sino explicar:

- que hojas o archivos trae cada distribuidora;
- que significa cada hoja;
- que columna contiene el ingreso;
- que columna contiene moneda, periodo, artista, tema o identificador;
- si la hoja representa generacion, transferencia, resumen, correccion o
  auditoria;
- si hoy entra o no entra a cada vista;
- por que se tomo esa decision.

Esta capa evita que el conocimiento quede solamente en la memoria o en scripts.
Una persona nueva deberia poder abrir la ficha y entender que esta mirando antes
de decidir si entra o sale.

Campos propuestos:

| Campo | Uso |
| --- | --- |
| `source` | Distribuidora |
| `account` | Cuenta si la explicacion cambia por cuenta |
| `raw_sheet_or_file_type` | Hoja, archivo o patron original |
| `human_name` | Nombre visible |
| `human_description` | Explicacion humana |
| `business_meaning` | `generation`, `transfer`, `summary`, `correction`, `audit`, `unknown` |
| `amount_column` | Columna de importe principal |
| `currency_column` | Columna de moneda |
| `period_column` | Columna de periodo |
| `artist_column` | Columna de artista principal |
| `title_column` | Columna de titulo principal |
| `identifier_columns` | ISRC, UPC, video id u otros |
| `default_catalog_view` | Decision default para catalogo |
| `default_statement_view` | Decision default para reportes |
| `default_cash_view` | Decision default para caja |
| `decision_reason` | Motivo de la decision |
| `known_risks` | Riesgos conocidos |
| `last_reviewed_at` | Ultima revision |
| `reviewed_by` | Responsable |

Ejemplo ONErpm:

| Hoja | Significado humano | Tipo | Statement | Caja | Nota |
| --- | --- | --- | --- | --- | --- |
| `Masters` | Ingresos generados por masters/catalogo | `generation` | Si | Depende cuenta | Base principal |
| `Youtube Channels` | Ingresos de canales/videos YouTube | `generation` | Si | Depende cuenta | Puede no traer ISRC |
| `Shares In & Out` | Transferencias de participacion entre cuentas | `transfer` | No en reporte nuevo | Si/auditoria | No sumar a generacion |
| `Summary` | Resumen del statement | `summary` | No | No | No usar como detalle |

Ejemplo FUGA:

| Archivo/hoja | Significado humano | Tipo | Statement | Nota |
| --- | --- | --- | --- | --- |
| statement normal | Detalle de royalties por producto/asset | `generation` | Si | `Reported Royalty` es ingreso real |
| correction | Correccion puntual de FUGA | `correction` | Si, con control | No tratar como statement comun |

Pantalla sugerida:

- en la vista principal solo mostrar la decision resumida;
- boton por cuenta: `Ver explicacion del statement`;
- abrir modal/panel con columnas, significado, riesgos y decision actual;
- no mezclar esta explicacion con el formulario operativo principal.

## Entidad 3: catalog_business_override

Representa una decision humana sobre una obra especifica.

Campos propuestos:

| Campo | Uso |
| --- | --- |
| `catalog_key` | Clave del catalogo |
| `active` | Si la obra esta activa en catalogo operativo |
| `include_in_reports` | Si entra en reportes |
| `business_status` | `owned`, `excluded`, `pending`, `external`, `legacy` |
| `ownership` | `vpo`, `artist_personal`, `third_party`, `mixed`, `unknown` |
| `contract_segment` | `old_contract`, `new_contract`, `not_applicable`, `pending` |
| `manual_release_date` | Fecha manual si la externa no alcanza |
| `release_date_source` | `spotify`, `youtube`, `manual`, `statement`, `unknown` |
| `external_label_review_status` | `ok`, `suspicious`, `pending` |
| `notes` | Motivo de la decision |
| `updated_by` | Usuario |
| `updated_at` | Auditoria |

Regla importante:

- `external_label` ayuda a revisar, pero no debe excluir ni incluir
  automaticamente una obra.

## Entidad 4: contract_cutoff

Define una fecha contractual que separa contenido viejo/nuevo.

La fecha es el dato de negocio. Las canciones usadas para descubrir o estimar
esa fecha son evidencia auxiliar, no la regla principal. Si en algun momento se
consigue la fecha real del contrato, se ingresa esa fecha y el sistema debe usar
ese valor sin depender de la cancion que ayudo a encontrarla.

Campos propuestos:

| Campo | Uso |
| --- | --- |
| `cutoff_id` | Identificador estable |
| `source` | Fuente donde se detecta la referencia |
| `account` | Cuenta de referencia |
| `business_entity` | Artista/proyecto/contrato |
| `contract_start_date` | Fecha contractual real o estimada |
| `contract_start_month` | Mes contractual si solo se conoce el mes |
| `date_status` | `real`, `estimated`, `pending` |
| `cutoff_basis` | `transaction_month`, `statement_period`, `release_date` |
| `evidence_type` | `track_reference`, `manual_note`, `contract`, `conversation`, `unknown` |
| `evidence_terms` | Terminos usados solo como evidencia |
| `evidence_catalog_key` | Obra de referencia si existe en catalogo |
| `old_content_policy` | Que hacer con contenido viejo |
| `new_content_policy` | Que hacer con contenido nuevo |
| `confidence` | `high`, `medium`, `low`, `manual_review` |
| `notes` | Explicacion humana |

## Entidad 5: report_template

Define como se arma un reporte operativo o especial.

Campos propuestos:

| Campo | Uso |
| --- | --- |
| `template_key` | Clave estable |
| `title` | Nombre visible |
| `report_family` | `statement`, `keyword`, `title_list`, `contract`, `investigation` |
| `time_basis` | `statement_period`, `transaction_month`, `release_date` |
| `source_account_scope` | Fuentes/cuentas incluidas |
| `uses_catalog_status` | Si respeta `catalog_business_override` |
| `uses_account_policy` | Si respeta `distributor_account_policy` |
| `output_profile` | Hojas/columnas esperadas |
| `default_filters` | Filtros por defecto |
| `rule_version` | Version de regla usada |
| `enabled` | Si aparece en UI |
| `notes` | Explicacion humana |

## ONErpm seed inicial

Esta matriz es el primer borrador de configuracion. Antes de programar debe
validarse contra reportes actuales.

| Cuenta | account_type | Catalog view | Statement view | Cash view | Regla principal |
| --- | --- | --- | --- | --- | --- |
| `henry_remix` | `owned` | Si | Si | Si | Cuenta simple; entra completa segun mart actual |
| `mawzrecords` | `owned` | Si | Si | Si | En reporte nuevo, `Masters` representa generacion; `Shares In & Out` queda para caja/auditoria |
| `gusty_dj` | `external` / `mixed` | Si | Solo catalogo posterior a fecha contractual | No por defecto | Motorcito se usa como evidencia para inferir la fecha, no como regla final |
| `la_nueva_sangre` | `external` / `mixed` | Si | Solo catalogo posterior a fecha contractual | No por defecto | Ni Ahi se usa como evidencia para inferir la fecha, no como regla final |

### Henry Remix

Criterio inicial:

- cuenta propia/simple;
- entra al reporte por statement nuevo;
- si en el futuro aparecen hojas de shares relevantes, se revisa la politica
  antes de sumarlas.

Pendiente de QA:

- confirmar si todas las hojas actuales que entran en el mart deben entrar en
  `statement_view` o si conviene separar `Masters`/`Youtube Channels`.

### MAWZ Records

Criterio inicial:

- cuenta propia;
- `Masters` entra a generacion de catalogo;
- `Shares In & Out` no entra en el reporte por statement nuevo;
- `Shares In & Out` se conserva para caja/auditoria;
- `Youtube Channels`, si aparece con datos, debe revisarse con la misma logica
  de generacion, no ignorarse automaticamente.

Riesgo:

- mezclar `Masters` con `Shares In & Out` infla o distorsiona reportes de
  generacion.

### Gusty DJ

Criterio inicial:

- cuenta externa historica;
- sirve para catalogo y auditoria;
- solo contenido posterior a la fecha contractual entra al reporte nuevo;
- Motorcito no es la regla de negocio: se uso como pista/evidencia para
  encontrar una fecha aproximada de inicio contractual;
- el corte debe expresarse como fecha contractual validada o estimada;
- el corte se aplica por contenido, no por mes de statement;
- si una obra anterior a la fecha contractual sigue generando despues del corte,
  sigue excluida.

Regla actual a modelar:

- evidencia/ancla: Motorcito;
- `cutoff_basis`: `transaction_month`;
- clasificacion por identificador cuando existe; fallback por titulo/artista.

Regla final esperada:

- `contract_start_date` o `contract_start_month` debe vivir en configuracion;
- Motorcito debe quedar guardado como evidencia historica de como se estimo esa
  fecha;
- si aparece el contrato real o una fecha mas precisa, se actualiza la fecha
  contractual sin reescribir la logica del reporte.

### La Nueva Sangre

Criterio inicial:

- cuenta externa/mixta;
- puede contener catalogo nuevo propio y catalogo viejo migrado del artista;
- el statement por si solo no alcanza para decidir ownership;
- la regla de negocio debe ser una fecha contractual ingresable;
- `external_release_date` sirve para clasificar cada obra contra esa fecha;
- los overrides manuales corrigen casos donde la metadata externa no alcanza.

Regla actual a modelar:

- evidencia auxiliar: Ni Ahi, Ni Aca, Ni Alla;
- fecha estimada actual: `transaction_month = 2023-06`;
- si aparece la fecha real de contrato, se ingresa en `contract_start_date` y
  reemplaza la estimacion;
- regla final esperada: comparar release date por obra contra fecha contractual.

Riesgo:

- si una obra vieja se migro tarde a La Nueva Sangre, `transaction_month` puede
  hacerla parecer nueva. Por eso catalogo + release date debe mandar.

## Pantalla propuesta para Fase 3

Primera version sugerida: read-only con edicion limitada.

### Panel Distribuidoras/Cuentas

Mostrar por cuenta:

- source;
- account;
- tipo de cuenta;
- entra a catalogo;
- entra a statement;
- entra a caja;
- regla de hojas;
- ancla contractual;
- notas.

Acciones iniciales:

- ver detalle;
- exportar configuracion;
- no editar masivamente todavia.

### Panel Catalogo/Excepciones

Mostrar:

- obra;
- artista;
- ISRC/UPC;
- fuentes/cuentas;
- release date;
- label externo;
- estado activo;
- incluir en reportes;
- ownership;
- contrato;
- notas.

Acciones iniciales:

- activar/desactivar en reportes;
- agregar nota;
- marcar pendiente de revision.

### Panel Impacto en reportes

Panel secundario, solo lectura.

No define reglas y no permite modificar configuracion. Su funcion es explicar
donde se usa una cuenta o politica, para auditoria y debug.

Ejemplos de informacion:

- si una cuenta entra al reporte por statement viejo;
- si entra al reporte por statement nuevo;
- si entra solo como catalogo;
- si una hoja como `Shares In & Out` queda fuera de generacion pero disponible
  para auditoria/caja;
- si un template personalizado depende de esa cuenta.

Utilidad esperada:

- entender por que dos reportes pueden dar distinto;
- detectar si una exclusion viene del catalogo o de la politica de cuenta;
- anticipar que podria cambiar si se modifica una politica.

Este panel no es obligatorio para operar el sistema. Si en pruebas no aporta
claridad, puede eliminarse sin afectar el modelo principal.

### Panel Templates de Reporte

Mostrar:

- template;
- fuentes/cuentas incluidas;
- uso de catalogo;
- uso de politica de cuenta;
- version de regla;
- fecha de ultima ejecucion si existe.

## Que no hacer todavia

- No mover logica productiva de reportes en esta fase.
- No cambiar resultados del reporte viejo ni nuevo.
- No borrar scripts historicos todavia.
- No usar `external_label` como regla automatica.
- No calcular splits contractuales por obra todavia.
- No mezclar configurador de distribuidoras con finanzas/booking.
- No convertir reportes investigativos en operativos sin validacion.

## Splits contractuales

Los splits no forman parte de esta fase.

En esta etapa el configurador decide:

- si una cuenta entra o no entra;
- si una obra entra o no entra;
- si una obra es propia, externa, mixta o pendiente;
- que vista de negocio usa cada hoja o cuenta.

Los splits pertenecen a una capa posterior de liquidacion/pago. En el futuro
seran necesarios para reportes contractuales y liquidaciones a artistas, pero no
deben modificar las decisiones actuales de inclusion, ownership o generacion.

Por lo tanto:

- una obra puede estar incluida aunque todavia no tenga split cargado;
- una obra puede estar excluida aunque tenga split teorico;
- el split no debe usarse como sustituto de `include_in_reports`;
- el catalogo debe dejar espacio para sumar splits mas adelante sin romper la
  politica actual.

## Validaciones antes de programar

Casos que deben usarse para probar la Fase 3:

1. `Boxindanga`
   - debe poder excluirse desde catalogo sin tocar scripts.

2. Gusty fecha contractual
   - contenido anterior a la fecha contractual debe quedar fuera aunque genere despues;
   - Motorcito queda solo como evidencia para estimar o validar la fecha.

3. La Nueva Sangre
   - obra con release date viejo debe quedar fuera;
   - obra nueva debe entrar;
   - obra sin release date debe quedar pendiente o usar fallback validado.

4. MAWZ `Shares In & Out`
   - debe seguir disponible para auditoria/caja;
   - no debe entrar a generacion del reporte nuevo.

5. Henry Remix
   - no debe romper el criterio simple actual.

6. FUGA/DashGo/Orchard/SoundOn
   - no deben cambiar por introducir el configurador.

7. Catalogo inactivo
   - si `include_in_reports = false`, todos los reportes conectados deben
     excluirlo.

## Proxima fase recomendada

Fase 3 deberia crear una configuracion seed, primero read-only con edicion muy
limitada:

- `warehouse/registry/distributor_account_policies.json`
- `warehouse/registry/statement_source_dictionary.json`
- `warehouse/registry/report_templates.json`
- `warehouse/registry/contract_cutoffs.json`

Luego conectar una pantalla para visualizar esa configuracion.

Orden de creacion recomendado:

1. `statement_source_dictionary.json`
   - primero explicar que significa cada hoja/archivo original.

2. `distributor_account_policies.json`
   - despues definir politica por distribuidora/cuenta.

3. `contract_cutoffs.json`
   - luego cargar fechas contractuales reales o estimadas.

4. `report_templates.json`
   - finalmente documentar templates de reportes.

Durante Fase 3 estos archivos son seed/read-only para comparacion. No gobiernan
todavia los reportes productivos.

Alcance inicial del seed:

1. ONErpm con detalle:
   - `henry_remix`;
   - `mawzrecords`;
   - `gusty_dj`;
   - `la_nueva_sangre`.

2. Distribuidoras simples:
   - `fuga / indyana_records`;
   - `dashgo / mawzrecords`;
   - `orchard / mawzrecords`;
   - `soundon / indyana_records` o la cuenta normalizada que use el mart.

3. Diccionario inicial:
   - FUGA statement normal;
   - FUGA corrections;
   - DashGo detail;
   - Orchard detail;
   - SoundOn `my_royalty`;
   - SoundOn summaries excluidos;
   - ONErpm `Masters`;
   - ONErpm `Youtube Channels`;
   - ONErpm `Shares In & Out`;
   - ONErpm `Summary` si aparece.

Fuera de alcance de este seed:

- splits;
- booking;
- finanzas de artista;
- gastos/inversiones;
- cloud/deploy;
- reglas de liquidacion a artistas.

Edicion permitida en primera version:

- notas humanas de una cuenta;
- estado de monitoreo: activo/inactivo;
- fecha contractual cuando aplica;
- estado de fecha: real, estimada o pendiente;
- evidencia usada para estimar una fecha;
- notas del diccionario de statement;
- apertura de la ficha real del Catalogo General para editar sus campos ya
  existentes.

Solo lectura en primera version:

- tipo de cuenta;
- reglas de hojas;
- reglas de shares;
- reglas de reportes;
- templates;
- cualquier campo que pueda cambiar importes.

Recien despues de validar visualmente la configuracion contra reportes actuales,
se deberia pasar a Fase 4:

- hacer que `build_statement_report_from_mart.py` lea la politica;
- generar reporte de QA comparando hardcoded actual vs politica nueva;
- exigir diff cero o explicar cada diferencia.
