# VPO Corp docs

Este directorio separa documentos rectores vigentes de notas historicas. Para
cambios nuevos, leer primero los documentos de la seccion "Leer primero" y luego
el documento rector del area afectada.

Si una nota historica contradice un documento rector vigente, manda el documento
vigente.

## Leer primero

- [Production guardrails](production_guardrails.md)
- [Cloud environment policy](cloud_environment_policy.md)
- [Secure operational DB connection](secure_operational_db_connection.md)
- [UI period control policy](ui_period_control_policy.md)

Regla vigente: Cloud SQL Postgres es la unica base operativa viva. SQLite queda
solo como foto historica/recuperacion controlada y no debe recibir funcionalidad
nueva.

## Reglas rectoras por area

### Finanzas, caja y cuenta corriente

- [Modelo financiero operativo VPO v2](finance_operational_model_v2.md)
- [Maqueta de carga dinamica](finanzas_carga_dinamica_maqueta.md)
- [Finanzas VPO - soporte visual/tecnico](finance_business_master.md)
- [Finanzas de artista y ledger](artist_finance_ledger_model.md)
- [Notas de cambio financiero](finance_change_notes.md)
- [Optimizar sistema](optimizar_sistema.md)

Antes de modificar Finanzas Artista, Movimientos Financieros, recibos,
documentos financieros, empleados/sueldos o aplicaciones de pagos, leer primero
`finance_operational_model_v2.md`.

### Booking

- [Booking rules master](booking_rules_master.md)
- [Booking data model](booking_data_model.md)
- [Booking operational rules](booking_operational_rules.md)
- [Booking unified model plan](booking_unified_model_plan.md)
- [Booking unified validation matrix](booking_unified_validation_matrix.md)
- [Booking go-live workflow](booking_go_live_workflow.md)

Antes de tocar saldos de shows, senas, compensaciones, comisiones, recuperos o
estado cerrado/pendiente, validar contra `booking_rules_master.md` y
`booking_unified_validation_matrix.md`.

### Catalogo, distribuidoras y reportes

- [Catalogo general core](catalog_core_notes.md)
- [Normalizacion de identidad](identity_normalization_policy.md)
- [Reporte por statement](statement_report_notes.md)
- [Marts and reports](marts_and_reports_notes.md)
- [Statement period policy](statement_period_policy.md)
- [Control de distribuidoras](source_monitor_notes.md)
- [Configurador distribuidoras - integracion con policies](distributor_configurator_phase4_policy_integration.md)
- [Gusty reports working notes](gusty_reports_working_notes.md)

Policies y diccionarios vivos:

- Distributor account policies: Cloud SQL (`distributor_account_policies`,
  `distributor_policy_settings`, `distributor_policy_audit`)
- [Statement source dictionary](../warehouse/registry/statement_source_dictionary.json)
- [Report templates](../warehouse/registry/report_templates.json)
- [Contract cutoffs](../warehouse/registry/contract_cutoffs.json)

### Ingest por distribuidora

- [FUGA](fuga_pipeline_notes.md)
- [DashGo](dashgo_pipeline_notes.md)
- [Orchard / Altafonte](orchard_pipeline_notes.md)
- [ONErpm](onerpm_pipeline_notes.md)
- [SoundOn](soundon_pipeline_notes.md)
- [ADA](ada_pipeline_notes.md)

Regla base: el pipeline nuevo escribe marts en `warehouse\marts`. El pipeline
viejo archivado no debe usarse para decidir pendientes, publicar datos ni
alimentar la web.

### Cloud, web y operacion

- [Cloud Run deployment](cloud_run_deployment.md)
- [Production API notes](production_api_notes.md)
- [Google Cloud Storage publish](google_cloud_storage_publish.md)
- [Vercel frontend notes](vercel_frontend_notes.md)
- [Web users admin](web_users_admin.md)
- [Local dev mode](local_dev_mode.md)

## Historico

Las notas de fases, migraciones cerradas, validaciones puntuales y disenos
reemplazados viven en:

- [_historico](./_historico/README.md)

Esos documentos conservan contexto y decisiones pasadas, pero no son fuente
operativa si contradicen los documentos rectores actuales.

## Reglas importantes

- No cargar summaries como royalties si duplican detalle.
- No inventar artista/tema cuando la fuente no lo trae.
- Conservar columnas originales siempre que sea razonable.
- Usar `scripts\lib\fx.py` para conversion FX.
- No pisar identificadores originales: si una fila nueva viene sin ISRC pero con
  UPC, la resolucion a ISRC pertenece al catalogo/reportes y debe seguir
  `identity_normalization_policy.md`.
- Todo modulo operativo nuevo debe usar Cloud SQL Postgres, no SQLite.
