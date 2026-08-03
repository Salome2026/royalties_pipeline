# VPO Corp - esquema cloud operativo v1

Fecha: 2026-06-24

> ESTADO DEL DOCUMENTO: historico/parcialmente superado.
>
> Este documento describe el esquema de migracion inicial. Para cambios actuales
> manda `production_guardrails.md`: Cloud SQL Postgres es la unica base viva y
> SQLite no debe recibir funcionalidades nuevas.

Este documento baja a tierra el paso siguiente del sistema: pasar de snapshots por
snapshots a operacion cloud con base persistente, sin perder el taller local ni
romper lo que ya funciona.

No reemplaza:

- `cloud_operational_postgres_plan.md`;
- `cloud_environment_policy.md`;
- `booking_rules_master.md`;
- `finance_business_master.md`;
- `catalog_core_notes.md`.

Este documento organiza el esquema y el orden de migracion.

## Objetivo del paso cloud

Tener una base operativa unica para:

- usuarios;
- empleados;
- permisos;
- artistas;
- booking vivo;
- movimientos financieros;
- auditoria.

Y mantener fuera de esa base:

- raw statements gigantes;
- parquets standardized completos;
- reportes temporales;
- archivos de trabajo local.

Los marts de regalias y catalogo siguen pudiendo vivir como Parquet en local/GCS.
Las decisiones humanas y operativas deben vivir en la base cloud.

## Decision de arquitectura

### Produccion operativa

- Frontend: Vercel.
- API: Cloud Run.
- DB operativa: Cloud SQL PostgreSQL.
- Archivos pesados/snapshots: Google Cloud Storage.

### Local

Local sigue existiendo como:

- taller de desarrollo;
- ingesta pesada de statements;
- generacion de reportes;
- rebuild de marts/catalogo;
- herramienta admin para Ruben.

Pero si una carga es operativa viva, local debe escribir contra la misma base
cloud, no contra una copia SQLite separada.

## Regla de fuente de verdad

### Datos vivos

Viven en Postgres:

- empleados y usuarios;
- permisos;
- artistas y referencias maestras;
- booking;
- movimientos financieros;
- estados/decisiones humanas del catalogo;
- auditoria.

### Datos reconstruibles

Viven como Parquet/local/GCS:

- `standardized_raw_*`;
- `song_level_*`;
- `statement_summary_*`;
- `catalog_master`;
- metadata externa reconstruible.

### Reportes

Los reportes se generan desde:

- marts para regalias/digitales;
- Postgres para datos operativos vivos;
- catalog status/policies como capa de negocio.

## Modulos cloud v1

### 1. Identidad y permisos

Estado local actual:

- `employees`;
- `employee_functions`;
- `app_users`;
- `app_modules`;
- `module_permissions`;
- `app_audit_log`.

Cloud v1 debe llevar esto primero porque es la base para internet.

Cambios respecto de SQLite:

- separar scopes en tabla propia `permission_scopes`;
- no guardar scopes como JSON como unica fuente;
- mantener `scope_json` solo como compatibilidad temporal si hace falta;
- auditar login, cambios de password y permisos.

### 2. Referencias maestras

Debe incluir:

- artistas;
- aliases de artistas;
- empleados;
- areas de negocio;
- categorias;
- proyectos;
- terceros/proveedores;
- monedas/tipos de cambio;
- adjuntos/comprobantes.

Regla:

- artista, empleado, area, categoria y proyecto deben tender a selector;
- texto libre queda como nota u origen crudo, no como identidad final.

### 3. Booking

Booking conserva sus tres capas:

- liquidacion esperada;
- caja real;
- cuenta corriente.

Cloud v1 debe migrar:

- `booking_shows`;
- `booking_show_expenses`;
- `booking_movements`;
- `booking_pre_split_adjustments`;
- `booking_direct_commissions`;
- `booking_external_shares`;
- `booking_artist_adjustments`;
- `booking_composite_events`;
- `booking_composite_event_expenses`;
- `booking_composite_event_lines`;
- `caserio_events`;
- `caserio_event_lines`.

Ademas debe agregar una tabla explicita:

- `booking_current_account_entries`.

Motivo:

- hoy muchos saldos se leen desde shows;
- para cloud necesitamos poder saldar, compensar y auditar sin reescribir el
  show original.

### 4. Finanzas

Finanzas debe hablar en terminos humanos:

- gasto/inversion;
- recuperable;
- adelanto/prestamo;
- pago/cobro cuenta corriente;
- gasto pagado por tercero;
- proyecto.

Cloud v1 debe migrar:

- `finance_projects`;
- `finance_staging_movements`;
- `finance_recovery_applications`.

Y preparar:

- `finance_movement_lines` para movimientos multi-concepto;
- `finance_recoverables` para saldo recuperable canonico;
- `finance_account_entries` para cuenta corriente financiera;
- `finance_ledger_entries` como ledger posteado futuro, no obligatorio para el
  primer go-live.

Regla:

- un movimiento financiero aprobado no se pisa;
- se anula o se corrige con otro movimiento;
- `legacy` no significa viejo: significa fuente de apoyo no canonica.

### 5. Catalogo y digitales

Cloud v1 no mete todo el catalogo pesado en Postgres.

Postgres guarda decisiones humanas:

- `catalog_status`;
- `catalog_label_overrides`;
- `distributor_account_policies`;
- `custom_report_configs`;
- `report_runs`.

El `catalog_master.parquet` sigue siendo reconstruible y publicable a GCS.

Regla:

- activar/desactivar una obra;
- sacar de reportes;
- cambiar label normalizado;
- guardar notas de negocio.

Eso es dato operativo y debe persistir aunque Cloud Run reinicie.

## Esquema tecnico propuesto

El borrador SQL inicial queda en:

```text
database/postgres_schema_v1.sql
```

Ese archivo no se ejecuta todavia. Sirve para revisar entidades, relaciones e
indices antes de crear Cloud SQL.

## Estrategia de migracion

### Fase A - Preparacion sin tocar produccion

1. Congelar un backup completo local.
2. Exportar schema SQLite actual.
3. Crear schema Postgres v1 en archivo SQL.
4. Crear migrador dry-run SQLite -> Postgres, sin ejecutar contra cloud.
5. Generar reportes de conteo por tabla.

Salida esperada:

- mismo conteo por tabla;
- ids preservados o mapeados;
- Ruben admin activo;
- `juanf` con permisos de lectura acotados;
- empleados y artistas disponibles.

### Fase B - Cloud SQL dev

1. Crear instancia Cloud SQL PostgreSQL chica.
2. Crear DB `vpo_corp_dev`.
3. Crear usuario API con permisos limitados.
4. Guardar credenciales en Secret Manager o variables seguras.
5. Ejecutar schema v1.
6. Migrar copia de SQLite a dev.

No conectar usuarios reales todavia.

### Fase C - API con adapter

Crear una capa de acceso:

- `operational_db`;
- `sqlite_operational_db`;
- `postgres_operational_db`.

Objetivo:

- dejar de llamar `booking_connect()` directo en cada endpoint nuevo;
- permitir que local use SQLite o Postgres segun variable fue una capacidad de
  transicion. Actualmente local operativo debe usar Cloud SQL Postgres por proxy;
- permitir que Cloud Run use Postgres para operacion viva.

Variable propuesta:

```text
VPO_OPERATIONAL_DB_DRIVER=sqlite|postgres
VPO_OPERATIONAL_DATABASE_URL=...
```

### Fase D - Primer modulo vivo

No empezar con todo.

Modulo recomendado:

1. Empleados/usuarios/permisos.
2. ABM artistas.
3. Detalle Booking lectura.

Despues:

4. Booking carga/edicion.
5. Movimientos financieros.
6. Finanzas artista.

### Fase E - Snapshot temporal vs operativo

Mantener dos modos:

- `snapshot_temporal`: lee GCS snapshots, sin escritura real.
- `operational_cloud`: lee/escribe Postgres.

Variables propuestas:

```text
VPO_DATA_MODE=snapshot_temporal|operational_cloud
```

Regla:

- no mezclar un frontend temporal con un backend que escribe en prod sin querer;
- cada entorno debe decir claramente que fuente usa.

## Backups y rollback

Antes de habilitar escritura:

- backup automatico Cloud SQL diario;
- export manual antes de cada migracion;
- bucket separado para backups;
- script local para restaurar a SQLite de emergencia o exportar snapshot.

Rollback minimo:

1. Desactivar escritura en Cloud Run.
2. Volver Vercel a snapshot temporal.
3. Restaurar Cloud SQL desde backup si el error fue de datos.
4. Mantener SQLite local como copia historica congelada.

## Permisos y seguridad

Backend debe validar siempre:

- usuario autenticado;
- modulo;
- accion;
- alcance por artista/proyecto;
- rol global admin.

Frontend puede ocultar botones, pero eso no es seguridad.

Ruben:

- super-admin;
- no bloqueable desde UI;
- puede operar local y cloud.

Usuarios comunes:

- login cloud;
- clave hasheada;
- cambio obligatorio si es clave temporal;
- scopes por modulo.

## Checklist antes de implementar Cloud SQL

1. El schema SQL esta revisado?
2. Hay backup local actualizado?
3. El migrador tiene dry-run?
4. Los conteos coinciden?
5. Ruben puede entrar?
6. Un viewer limitado ve solo lo suyo?
7. Un editor no puede editar fuera de su scope?
8. Cloud temporal sigue funcionando por snapshots?
9. La app local puede apuntar a cloud si se desea?
10. Hay documentacion para volver atras?

## Casos testigo para validar

### Usuario/permisos

- `rubene`: ve y edita todo.
- `juanf`: puede ver tarjetas asignadas.
- `salomef`: solo debe ver lo que se le asigne.
- `santiagod`: debe respetar artistas asignados.

### Booking

- show simple comun;
- G Sony simple con comision externa;
- Candu + G Sony con evento madre e hijas;
- Virrshi con recupero;
- Aneley con cuenta corriente;
- Caserio separado.

### Finanzas

- Virrshi: recuperables + aplicaciones;
- Aneley: gastos pagados por manager y saldo booking;
- Bianca: inversiones no recuperables;
- movimiento pendiente proveedor.

### Catalogo

- obra activa;
- obra inactiva/no reportable;
- label normalizado override;
- reporte que respeta catalog status.

## Orden recomendado inmediato

1. Revisar este documento.
2. Revisar `database/postgres_schema_v1.sql`.
3. Crear script `scripts/export_sqlite_operational_snapshot.py` para conteos y
   validacion.
4. Crear migrador dry-run `scripts/migrate_sqlite_to_postgres.py`.
5. Recién despues crear Cloud SQL dev.

No hacer go-live cloud escribible hasta pasar los casos testigo.
