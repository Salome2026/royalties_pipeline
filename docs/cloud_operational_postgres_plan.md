# VPO Corp - plan operativo cloud con Postgres

Fecha: 2026-06-24

Este documento manda sobre la migracion de la operacion viva a cloud. No
reemplaza las reglas de booking, finanzas, catalogo o reportes: las organiza en
una arquitectura comun para que usuarios, permisos, auditoria y base persistente
no queden como parches.

## Objetivo

Pasar de snapshots cloud de lectura a una operacion cloud persistente:

- usuarios reales entrando por internet;
- permisos por modulo y alcance;
- booking y movimientos financieros escribiendo en una sola base;
- auditoria de cambios;
- backups;
- posibilidad de seguir usando la PC local para procesos pesados.

## Decision tecnica base

Base operativa recomendada:

- PostgreSQL en Google Cloud SQL.

Motivo:

- soporta relaciones fuertes entre artistas, empleados, shows, proyectos,
  movimientos, permisos y auditoria;
- es portable si algun dia se migra fuera de Google;
- evita sincronizacion peligrosa entre SQLite local y cloud;
- permite transacciones y constraints para datos financieros.

Archivos pesados:

- Google Cloud Storage para snapshots, reportes publicados, adjuntos y backups;
- PC local para raw statements, ingesta pesada, enrichment y auditorias hasta que
  tenga sentido mover workers a cloud.

## Principios no negociables

1. Una sola verdad operativa para booking y finanzas.
2. Local puede ser taller, pero si carga operacion viva debe escribir a la misma
   base cloud.
3. Los raw y standardized de regalias no se modifican.
4. La base operativa no debe llenarse con archivos raw gigantes.
5. Ruben Elkowich debe quedar siempre como super-admin.
6. Los permisos se aplican en backend, no solo escondiendo botones en frontend.
7. Toda escritura importante genera auditoria.
8. No borrar historico: anular, corregir o ajustar con traza.
9. La UI debe hablar idioma humano; el ledger y las tablas tecnicas son motor.
10. Antes de migrar un modulo, debe existir checklist de validacion.

## Capas del sistema

### 1. Identidad y permisos

Entidades operativas:

- empleados;
- funciones del empleado;
- usuarios de login;
- roles globales;
- permisos por modulo;
- alcances por artista/proyecto/area;
- auditoria de sesiones y cambios.

Regla:

- un empleado puede tener muchas funciones;
- un usuario puede estar vinculado a un empleado;
- el usuario operativo default se forma con nombre + inicial del apellido
  normalizado en minusculas, por ejemplo `salomef`, `juanf`, `rubene`;
- todo usuario nuevo puede arrancar con clave temporal `Indyana2026!`, pero
  debe quedar marcado para cambiarla en el primer ingreso;
- la clave se guarda solo como hash, nunca como texto plano;
- el ABM de empleados permite establecer o resetear la contrasena de un usuario;
- un permiso debe poder decir:
  - puede entrar;
  - puede cargar;
  - puede ver historial;
  - puede editar;
  - a que artistas/proyectos aplica.
- para modulos de booking, el alcance por artista puede ser:
  - todos los artistas;
  - solo una lista seleccionada de artistas;
  - ninguno, si se quiere dejar el modulo visible pero sin datos operativos hasta
    terminar la configuracion.
- el login cloud debe leer la base operativa como fuente principal;
- el fallback local queda reservado para Ruben como super-admin, no para usuarios
  operativos comunes.

### 2. Referencias maestras

Entidades:

- artistas;
- aliases de artistas;
- empleados;
- terceros/proveedores;
- categorias;
- areas de negocio;
- proyectos;
- monedas y tipos de cambio;
- adjuntos/comprobantes.

Regla:

- donde haya riesgo de error humano, usar selector;
- preservar texto original cuando venga de una fuente externa;
- permitir normalizacion/override sin pisar el dato crudo.

### 3. Booking

Booking mantiene las tres capas definidas:

- liquidacion esperada;
- caja real;
- cuenta corriente.

La base cloud debe guardar, como minimo:

- shows;
- eventos madre / liquidaciones compuestas;
- lineas de artista;
- gastos generales;
- gastos propios de linea;
- comisiones directas;
- terceros externos;
- senas y movimientos de caja;
- recuperos aplicados;
- estados por capa;
- saldo de show, deuda boliche y cuenta corriente resultante.

Regla:

- un show simple con regla avanzada sigue siendo show simple;
- un evento madre organiza, pero la hija/show operativo conserva la realidad;
- la hija no se pisa automaticamente desde la madre sin accion explicita.

### 4. Finanzas artista

Finanzas no reemplaza booking ni regalias. Lee y conecta fuentes.

Debe soportar:

- proyectos/inversiones;
- gastos asumidos por Indyana;
- gastos recuperables;
- adelantos/prestamos;
- pagos/cobros de cuenta corriente;
- gastos pagados por artista/manager/tercero;
- aplicaciones de recupero;
- saldo de cuenta corriente por artista.

Regla:

- una inversion no es automaticamente deuda;
- un recuperable no es automaticamente cuenta corriente;
- una cuenta corriente solo responde quien debe a quien;
- un proyecto responde cuanto invertimos, recuperamos y falta.

### 5. Catalogo y digitales

El catalogo sigue siendo una capa maestra reconstruible desde marts y raw
estandarizados.

En Postgres deberian vivir las decisiones humanas:

- activo/inactivo;
- include_in_reports;
- business status;
- label normalized override;
- notas de catalogo;
- configuracion de reportes;
- reglas de distribuidoras/cuentas si pasan a ser editables desde UI.

Los marts grandes pueden seguir como Parquet en Storage/local.

### 6. Auditoria

Cada mutacion importante debe guardar:

- usuario;
- empleado;
- timestamp;
- modulo;
- accion;
- entidad;
- id entidad;
- antes/despues cuando corresponda;
- origen: web local, web cloud, script, importacion, mantenimiento.

## Esquema conceptual inicial

### Identidad

- `employees`
- `employee_functions`
- `users`
- `user_sessions`
- `modules`
- `module_permissions`
- `permission_scopes`
- `audit_log`

### Referencias

- `artists`
- `artist_aliases`
- `business_areas`
- `categories`
- `projects`
- `counterparties`
- `fx_rates`
- `attachments`

### Booking

- `booking_shows`
- `booking_show_expenses`
- `booking_direct_commissions`
- `booking_pre_split_adjustments`
- `booking_external_shares`
- `booking_cash_movements`
- `booking_artist_adjustments`
- `booking_composite_events`
- `booking_composite_event_expenses`
- `booking_composite_event_lines`
- `booking_current_account_entries`

### Finanzas

- `finance_projects`
- `finance_movements`
- `finance_movement_lines`
- `finance_recoverables`
- `finance_recovery_applications`
- `finance_account_entries`

### Catalogo / reportes

- `catalog_status`
- `catalog_label_overrides`
- `distributor_account_policies`
- `custom_report_configs`
- `report_runs`

## Etapas de control

### Etapa 0 - Foto segura

- Backup completo local.
- Backup de SQLite booking actual.
- Export de variables de entorno relevantes sin exponer secretos en git.
- Confirmar que la app local sigue levantando.

Estado: pendiente.

### Etapa 1 - Documento y modelo

- Definir esquema Postgres v1.
- Mapear tablas SQLite actuales contra tablas Postgres.
- Definir permisos por modulo.
- Definir que queda en Parquet/GCS y que pasa a DB.

Estado: en curso.

### Etapa 2 - Infra minima cloud

- Crear Cloud SQL Postgres operativo inicial.
- Crear usuario de DB para API.
- Configurar Secret Manager o variables seguras.
- Conectar Cloud Run a Cloud SQL.
- Mantener min instances 0 mientras sea posible.

Estado: pendiente.

### Etapa 3 - Capa de acceso a datos

- Evitar que el codigo hable directo con SQLite en cada modulo nuevo.
- Crear adapter/repositorio para DB operativa.
- Soportar local apuntando a cloud DB para operacion viva.
- Mantener lectura de SQLite solo como legacy/import/snapshot hasta migrar.

Estado: pendiente.

### Etapa 4 - Usuarios, empleados y permisos

- Crear ABM empleados.
- Crear usuarios vinculados a empleados.
- Implementar Ruben super-admin no bloqueable.
- Implementar permisos por modulo:
  - acceso;
  - cargar;
  - ver historial;
  - editar.
- Implementar scopes por artista/proyecto.
- Backend debe validar permisos.

Estado: iniciado.

Implementado local el 2026-06-24:

- tablas SQLite preparatorias:
  - `employees`;
  - `employee_functions`;
  - `app_modules`;
  - `module_permissions`;
  - `app_audit_log`.
- seed inicial de empleados:
  - Ruben Elkowich;
  - Juan Manuel Fornasari;
  - Carolina Vanesa Alvarez;
  - Salome Fornasari;
  - Santiago Damonte;
  - Santiago Mareco;
  - Lautaro Alarcon;
  - David Carbone;
  - Walter Robales.
- Ruben queda con permisos completos en todos los modulos sembrados y no puede
  desactivarse desde la API.
- endpoint FastAPI `/employees`.
- proxy Next `/api/employees`.
- tarjeta local `ABM de empleados`.

Pendiente dentro de la etapa:

- scopes por artista/proyecto/area;
- validacion real de permisos en backend por modulo;
- auditoria de cambios de empleados/permisos.

Avance local posterior, 2026-06-24:

- tabla preparatoria `app_users`;
- usuarios operativos vinculados:
  - `rubene` -> Ruben Elkowich, admin, auth operational;
  - `ruben` -> Ruben Elkowich, admin, auth legacy local;
  - `admin` -> Ruben Elkowich, admin, auth legacy local;
  - `juanf` -> Juan Manuel Fornasari, viewer, auth operational;
  - empleados restantes -> usuario generado por nombre + inicial de apellido.
- el alias viejo `jfornasari` queda desactivado para no sostener dos reglas de
  login.
- todos los usuarios operativos nuevos tienen hash de clave y cambio obligatorio
  en primer ingreso.
- el ABM de empleados permite guardar:
  - usuario asociado;
  - rol global;
  - usuario activo/inactivo;
  - contrasena temporal o reseteada;
  - cambio obligatorio de contrasena;
  - permisos por modulo.
- los permisos se guardan y ya filtran visualmente las tarjetas de Inicio;
- todavia falta aplicar la misma autoridad en endpoints backend.

Actualizacion login, 2026-06-24:

- el login Next intenta primero contra `/auth/login` de la API operativa;
- si el usuario tiene `must_change_password`, la app lo obliga a cambiar la
  clave antes de entrar al sistema;
- `/auth/change-password` actualiza el hash y libera el bloqueo;
- el fallback por variables de entorno queda reservado a `ruben` y `admin`, como
  red local de super-admin.

Actualizacion UI permisos, 2026-06-24:

- la pantalla ya no muestra una matriz ancha de cinco checks por modulo;
- muestra un selector humano por modulo:
  - `Sin acceso`;
  - `Ver`;
  - `Cargar`;
  - `Editar`;
  - `Admin`.
- internamente se siguen guardando los cinco permisos:
  - `can_access`;
  - `can_create`;
  - `can_view_history`;
  - `can_edit`;
  - `can_approve`.
- mapeo actual:
  - `Sin acceso`: nada;
  - `Ver`: entrar + historial;
  - `Cargar`: entrar + cargar;
  - `Editar`: entrar + cargar + historial + editar;
  - `Admin`: todos.
- `Inicio` no se configura manualmente como modulo de negocio. La regla es:
  si el usuario tiene acceso a por lo menos un modulo, puede entrar a Inicio; y
  en Inicio solo debe ver las tarjetas permitidas. Por eso `home` puede existir
  internamente, pero no se muestra en el ABM de permisos.
- los modulos `Booking Indyana`, `Resumen Booking`, `Detalle Booking`,
  `Finanzas Artista` y `Movimientos financieros` ya tienen selector de alcance
  por artista en el ABM:
  - todos;
  - seleccionados.
- esas lecturas ya filtran los datos por artista asignado.
- la carga/edicion de shows simples y de movimientos financieros valida que el
  usuario tenga ese artista asignado.
- `Liquidaciones compuestas` y `Caserio` todavia requieren una decision de
  alcance propia antes de exponer un selector similar.

Proximo subpaso:

1. Validar visualmente el ABM de empleados.
2. Definir scopes por artista/proyecto.
3. Aplicar permisos primero a una pantalla testigo, recomendada:
   `Movimientos financieros`.

### Etapa 5 - Migrar referencias maestras

- Artistas.
- Aliases.
- Empleados.
- Categorias.
- Proyectos.
- Terceros.

Estado: pendiente.

### Etapa 6 - Migrar booking operativo

- Migrar SQLite booking a Postgres.
- Validar reportes actuales:
  - Detalle Booking;
  - Resumen Booking;
  - Comisiones;
  - Finanzas artista / booking.
- Mantener snapshots de lectura si hace falta para mostrar avances, pero con origen claro.

Estado: pendiente.

### Etapa 7 - Migrar finanzas operativas

- Migrar movimientos financieros.
- Migrar proyectos.
- Migrar recuperables/aplicaciones.
- Validar Virrshi y Aneley como casos testigo.
- Cerrar diferencias de lenguaje/UI antes de permitir uso masivo.

Estado: pendiente.

### Etapa 8 - Catalogo/status en DB

- Mantener catalog_master como mart reconstruible.
- Pasar decisiones humanas a DB:
  - activo;
  - reportable;
  - label normalized override;
  - notas.
- Sincronizar con reportes personalizados.

Estado: pendiente.

### Etapa 9 - Cloud operativo controlado

- Habilitar escritura real para modulos aprobados.
- Mantener permisos por usuario.
- Backups automaticos.
- Auditoria visible para admin.
- Separar snapshot de lectura y operacion viva.

Estado: pendiente.

### Etapa 10 - Workers y procesamiento pesado

- Mantener ingesta pesada local al principio.
- Publicar marts validados a Storage.
- Mas adelante evaluar Cloud Run Jobs / Batch para:
  - ingest;
  - rebuild catalog;
  - reportes pesados;
  - metadata workers.

Estado: pendiente.

## Checklist antes de tocar codigo

Para cada cambio:

1. Que modulo afecta?
2. Que fuente de verdad usa hoy?
3. Que tabla Postgres futura corresponde?
4. Hay permisos involucrados?
5. Hay auditoria involucrada?
6. Se rompe cloud temporal?
7. Se rompe localhost?
8. Hay que migrar datos existentes?
9. Hay caso testigo?
10. Hay rollback?

## Nota de vigencia

Este documento contiene parte del razonamiento historico de migracion. La regla
vigente esta en `cloud_environment_policy.md`, `secure_operational_db_connection.md`
y `web_users_admin.md`.

Las menciones a `VPO_WEB_USERS_JSON`, `VPO_WEB_PASSWORD`, SQLite como base
operativa o snapshot temporal corresponden a etapas anteriores y no deben guiar el
estado productivo actual.

## Primer bloque recomendado

No empezar por migrar booking completo.

Primer bloque:

1. Crear schema SQL/migracion inicial para identidad y permisos.
2. Crear ABM Empleados usando SQLite actual o Postgres local segun decision de
   infraestructura inmediata.
3. Conectar login actual con la idea de empleado/permisos sin romper
   `VPO_WEB_USERS_JSON`.
4. Validar permisos solo en una tarjeta chica antes de aplicarlo a todo.

Motivo:

- empleados/permisos son la base de cloud operativo;
- el riesgo de datos de negocio es bajo;
- permite probar backend + frontend + auditoria;
- deja preparado el camino para booking y finanzas.

## Estado tecnico detectado al iniciar

Revision inicial del 2026-06-24:

- El backend principal esta en `app/vpo_corp_api.py`.
- La base operativa actual es SQLite:
  `warehouse/booking/live/booking_live.sqlite`.
- La funcion central de conexion actual es `booking_connect()`.
- `booking`, `caserio`, `liquidaciones compuestas`, `finance_projects`,
  `finance_staging_movements` y `finance_recovery_applications` se crean hoy
  dentro de `init_booking_db()`.
- El frontend esta en `web/app/page.tsx`.
- El login actual esta en `web/app/api/_auth.ts`.
- Los usuarios web actuales viven en `VPO_WEB_USERS_JSON` o en el acceso
  legacy `VPO_WEB_PASSWORD`.
- El backend FastAPI no conoce aun al usuario final; solo valida
  `X-VPO-API-Key`.
- Las rutas Next aplican roles globales `viewer`, `editor`, `admin`, pero no
  permisos granulares por modulo/artista/proyecto.
- `requirements.txt` aun no tiene driver Postgres.
- `package.json` no necesita cambios para Postgres porque la DB la manejara el
  backend.

Backup previo a esta fase:

- `backups/cloud_postgres_permissions_20260624_131115`

Conclusion:

- No conviene migrar booking completo de golpe.
- Primero hay que crear la identidad/permisos y la abstraccion de base operativa.
- Luego se migra modulo por modulo con validacion.

## Avance 2026-06-24 - Empleados, usuarios y menu

- Se creo la primera version local de ABM Empleados sobre la base operativa actual.
- Se agregaron empleados, funciones, usuarios, modulos, permisos por modulo y auditoria base.
- Ruben queda como super-admin inicial y no debe poder bloquearse desde la UI.
- `Inicio` no se configura como permiso manual: se considera disponible si el usuario tiene acceso a por lo menos un modulo.
- La UI de permisos usa niveles por modulo:
  - `Sin acceso`
  - `Ver`
  - `Cargar`
  - `Editar`
  - `Admin`
- El menu de `Inicio` ya filtra visualmente las tarjetas por permisos de modulo:
  - admin ve todo;
  - usuario no admin ve solo modulos con `can_access`;
  - todas las tarjetas deben tener un modulo de permisos;
  - no hay fallback por rol viewer: si una tarjeta se ve, es porque existe permiso explicito. En la vista compartida inicial, Juan Manuel Fornasari tenia permiso de lectura explicito en `Detalle Booking` y `Catalogo General`.
- Esta capa actual es navegacion/visual. La seguridad profunda por endpoint queda para la etapa de autenticacion backend real y Postgres.
