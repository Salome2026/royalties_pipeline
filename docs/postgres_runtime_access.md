# Acceso operativo a PostgreSQL

## Proposito

Este documento define la unica forma productiva de acceder a Cloud SQL
PostgreSQL desde la API y los Cloud Run Jobs de VPO Corp.

## Regla rectora

- Cloud SQL PostgreSQL es la unica base operativa viva.
- Todo acceso de aplicacion entra por `app/operational_db.py`.
- La API reutiliza conexiones mediante un pool global por instancia.
- Un request toma una conexion, confirma o revierte su transaccion y la devuelve
  al pool. No abre ni cierra una conexion fisica por cada operacion.
- El ciclo de vida de FastAPI abre el pool al iniciar y lo cierra al apagar.
- Los Jobs usan el mismo adapter y cierran su pool antes de finalizar.
- Localhost usa el mismo modelo mediante Cloud SQL Auth Proxy.
- No se agregan conexiones directas, pools por modulo ni caminos SQLite.

## Capacidad

Cloud SQL dispone actualmente de 25 conexiones. La configuracion inicial de la
API es:

- minimo por instancia: 1;
- maximo por instancia: 4;
- espera maxima para obtener una conexion: 10 segundos;
- solicitudes en espera por instancia: 16;
- vida maxima de una conexion: 30 minutos;
- inactividad maxima de una conexion excedente: 5 minutos.

Con un maximo futuro de cuatro instancias de API, el techo de la API es 16
conexiones. Las restantes quedan disponibles para Jobs, administracion y margen
operativo. Aumentar el pool exige revisar primero `max_connections`, cantidad de
instancias y concurrencia real.

Los Jobs de reportes parten de 0 y usan un maximo de 2 conexiones por ejecucion porque su
trabajo de datos ocurre sobre Parquet/GCS y PostgreSQL conserva solo estado y
auditoria.

## Configuracion

- `VPO_POSTGRES_APPLICATION_NAME`
- `VPO_POSTGRES_POOL_MIN_SIZE`
- `VPO_POSTGRES_POOL_MAX_SIZE`
- `VPO_POSTGRES_POOL_TIMEOUT_SECONDS`
- `VPO_POSTGRES_POOL_MAX_WAITING`
- `VPO_POSTGRES_POOL_MAX_LIFETIME_SECONDS`
- `VPO_POSTGRES_POOL_MAX_IDLE_SECONDS`

Los valores se configuran por servicio. No se guardan credenciales en archivos
versionados.

## Observabilidad

Query Insights debe estar activo en la instancia productiva. La API y cada Job
declaran un `application_name` distinto para poder reconocer sus conexiones.
El endpoint `/health` informa estado y ocupacion del pool sin exponer secretos.

Los indices se agregan solo con evidencia. La medicion previa al corte encontro:

- `booking_event_source_links`: 201.994 escaneos secuenciales para 80 filas;
- `booking_show_expenses`: 1.174 escaneos secuenciales para 1.784 filas;
- `booking_movements`: 925 escaneos secuenciales para 3.864 filas.

La migracion `013_postgres_access_indexes.sql` agrega indices por `event_id` o
`show_id` para esas lecturas. No se agregan indices especulativos al resto de las
tablas pequenas.

## Validacion

Cada cambio de esta capa debe comprobar:

1. Reutilizacion de la misma conexion entre operaciones sucesivas.
2. Commit al finalizar correctamente y rollback ante error.
3. Cierre ordenado del pool al apagar API o Job.
4. Salud local mediante proxy y salud cloud mediante socket.
5. Limite total compatible con Cloud SQL.
6. Consultas de Booking, Agenda, empleados, permisos y finanzas sin cambios de
   resultado.
