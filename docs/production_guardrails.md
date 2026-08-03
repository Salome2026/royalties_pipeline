# Production guardrails

Este documento manda sobre cualquier duda de arquitectura operativa actual.
Si otro documento viejo contradice estas reglas, este documento y
`cloud_environment_policy.md` prevalecen.

## Base viva

- La unica base operativa viva es Cloud SQL Postgres `vpo_corp`.
- Localhost no es otra base: cuando opera datos vivos, usa la misma base Cloud SQL
  mediante proxy.
- SQLite queda congelado como foto historica/recuperacion controlada. No es
  entorno operativo, no es fallback funcional y no debe recibir funcionalidad
  nueva.

## Regla para modulos nuevos

Todo modulo nuevo que guarde datos operativos debe ser Postgres-only desde el
primer commit.

Antes de agregar una tabla, endpoint o flujo nuevo:

1. Verificar si la informacion es operativa viva o snapshot analitico.
2. Si es operativa viva, crear/actualizar schema en `database/postgres_schema_v1.sql`.
3. Crear migracion/ensure solo para Postgres.
4. No agregar `CREATE TABLE`, `ALTER TABLE` ni `ensure_sqlite_column` para esa
   funcionalidad.
5. Si el codigo cae en SQLite por configuracion, debe fallar claro con un mensaje
   que diga que la funcionalidad usa Cloud SQL Postgres.
6. Probar local contra Cloud SQL por proxy y cloud contra Cloud SQL socket.

## Regla para codigo existente con SQLite

Puede existir codigo con `sqlite3`, `booking_connect()` o helpers de
compatibilidad porque el sistema fue migrado en etapas. Esa compatibilidad no
autoriza a extender SQLite.

Permitido:

- mantener rutas existentes hasta migrarlas completamente a queries nativas;
- leer la foto congelada para auditoria historica o recuperacion controlada;
- usar scripts de comparacion SQLite -> Postgres cuando se audita la migracion.

Prohibido:

- crear tablas nuevas en SQLite;
- agregar columnas nuevas en SQLite para funcionalidades posteriores al corte
  cloud;
- usar SQLite como plan B silencioso;
- llamar "legacy" a un dato real viejo para meterlo en una capa paralela.

## Checklist antes de cerrar un cambio operativo

- `git diff` no muestra ramas nuevas de SQLite para una funcionalidad nueva.
- `python scripts\qa\qa_operational_db_guardrails.py` pasa antes de commitear un
  cambio que toque base operativa.
- `rg "ensure_sqlite_column|CREATE TABLE IF NOT EXISTS" app database` fue revisado
  cuando el cambio toca base de datos.
- `python -m py_compile app\vpo_corp_api.py` pasa.
- `npm run build` pasa si se toca frontend.
- `/health` muestra `driver=postgres` y `status=ok` en local/cloud.
- El cambio queda documentado en el documento rector del area correspondiente,
  no solo en notas sueltas.
