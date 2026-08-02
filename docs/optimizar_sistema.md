# Optimizar sistema

Fecha de nota: 2026-07-10

## Objetivo

Dejar documentado el diagnostico tecnico sobre la lentitud general al guardar y leer datos en VPO Corp, para retomarlo mas adelante sin convertirlo en un parche puntual.

La conclusion principal es que el problema no es "guardar salario" ni una pantalla aislada. El problema es transversal: acceso a base de datos, endpoints que hacen demasiado trabajo por request, consultas repetidas, falta de pool de conexiones y algunas migraciones/validaciones ejecutandose en runtime.

## Contexto actual

- El sistema ya esta en etapa productiva.
- La base viva debe ser Postgres / Cloud SQL.
- SQLite debe quedar solo como historico o respaldo congelado, no como fuente operativa.
- Localhost y Cloud deben compartir la misma logica de negocio.
- La validacion de usuarios y permisos debe ser consistente entre local y cloud.
- No se quieren capas de compatibilidad permanentes, rutas demo, ni parches especificos por pantalla.

## Mediciones observadas

Mediciones hechas desde local contra la API local conectada a Postgres / Cloud SQL:

- `health` sin DB: entre 15 ms y 60 ms.
- Abrir conexion Postgres + `SELECT 1`: entre 1.6 s y 2.7 s.
- `GET /booking/shows?limit=5`: entre 4.2 s y 4.7 s.
- `GET /booking/artists`: aproximadamente 3.4 s.
- `GET /employees?include_inactive=true`: aproximadamente 14.7 s.
- `GET /employees/commission-options`: llego a timeout en 20 s.

Esto muestra que el costo no esta solamente en el frontend. La API esta pagando mucho costo por request.

## Causas detectadas

### 1. Conexion nueva a Postgres por request

`app/operational_db.py` abre conexiones con `psycopg.connect` sin un pool compartido.

Eso significa que muchas rutas pagan el costo completo de abrir conexion contra Cloud SQL. Desde localhost, atravesando Cloud SQL Proxy hacia `us-central1`, ese costo se siente mucho.

### 2. Queries secuenciales y N+1

Hay endpoints que consultan datos principales y despues hacen muchas consultas adicionales por cada item.

Ejemplo en empleados:

- Hay 22 empleados.
- Hay 18 funciones.
- Hay 15 usuarios.
- Hay 398 permisos de modulo.
- Al construir cada empleado, el backend consulta funciones, usuario y permisos por separado.

Eso convierte una pantalla simple en muchas consultas.

### 3. Migraciones o validaciones de schema en runtime

En empleados se detecto que cada GET/POST/PUT llama a `ensure_employee_compensation_columns(conn)`.

Esa funcion ejecuta `ALTER TABLE employees ADD COLUMN IF NOT EXISTS ...`.

Aunque Postgres lo tolere, no corresponde hacerlo en cada request productivo. El schema debe estar migrado antes, y la aplicacion solo debe leer/escribir datos.

### 4. Endpoints que devuelven mas de lo necesario

En algunas rutas el frontend pide muchos registros aunque la pantalla muestre pocos.

Ejemplo detectado:

- `web/app/api/booking/route.ts` pide `booking/shows?limit=1000`.
- La UI puede estar mostrando solo las ultimas cargas o una pagina parcial.

Esto hace lenta la pantalla y confunde la medicion real.

### 5. Guardado demasiado amplio

Al guardar un dato chico, como salario de empleado, el sistema no guarda solamente ese campo.

Actualmente el frontend manda el empleado completo y el backend actualiza:

- ficha del empleado;
- funciones;
- usuario vinculado;
- permisos;
- respuesta completa del empleado.

El problema no debe resolverse creando un endpoint especial "guardar salario" como parche. La solucion debe ser ordenar el patron general de escritura.

## Decision tecnica

No hacer soluciones puntuales por pantalla.

La optimizacion debe hacerse como una mejora transversal de arquitectura:

1. Base viva unica en Postgres.
2. Pool de conexiones para la API.
3. Migraciones separadas del runtime.
4. Lecturas batcheadas, sin N+1.
5. Writes con comandos claros y acotados.
6. Respuestas razonables: devolver lo necesario, no listas completas si no hace falta.
7. Paginacion real donde corresponda.
8. Cache solo para catalogos estables y con invalidacion clara.
9. Logs de performance por endpoint para detectar regresiones.

## Plan propuesto para cuando se retome

### Fase 1: baseline e instrumentacion

Sin cambiar reglas de negocio:

- Medir tiempos por endpoint.
- Separar tiempo de conexion, tiempo SQL y tiempo de serializacion.
- Identificar rutas mas lentas.
- Guardar una tabla corta de referencia antes de tocar codigo.

### Fase 2: sacar DDL del runtime

Objetivo:

- Ningun request normal debe ejecutar `ALTER TABLE`, `CREATE TABLE`, migraciones o reparaciones de schema.

Acciones:

- Revisar todas las funciones `ensure_*`.
- Mover lo que sea schema a migraciones en `database/`.
- Dejar validaciones livianas de startup si hacen falta, pero no en cada request.

### Fase 3: pool de conexiones Postgres

Objetivo:

- La API debe reutilizar conexiones.

Acciones:

- Implementar pool en `app/operational_db.py`.
- Integrarlo con ciclo de vida FastAPI.
- Verificar comportamiento local y Cloud Run.
- Mantener una forma clara de cerrar conexiones al apagar.

### Fase 4: optimizar empleados/permisos

Objetivo:

- ABM empleados debe cargar rapido y guardar sin demoras absurdas.

Acciones:

- Evitar consultas por empleado.
- Leer funciones, usuarios y permisos en batch.
- Armar el objeto final en memoria.
- Revisar guardado para que no reescriba areas no modificadas si no corresponde.

### Fase 5: optimizar Booking Indyana

Objetivo:

- Booking debe seguir siendo operativo y rapido.

Acciones:

- Revisar `booking/shows`.
- Revisar carga de relaciones: gastos, caja, ajustes, recuperos, comisiones, terceros y aplicaciones de cuenta corriente.
- Evitar pedir 1000 shows si la pantalla necesita 5 o una pagina.
- Mantener buscador y edicion sin perder informacion.

### Fase 6: optimizar catalogos y selects

Objetivo:

- Listas de artistas, empleados, categorias, proyectos y labels deben ser rapidas.

Acciones:

- Cachear listas estables.
- Invalidar cache al modificar ABM correspondiente.
- No mezclar cache con datos vivos de caja o ledger.

### Fase 7: limpieza final

Objetivo:

- Codigo mas legible y sistema productivo sin ruido.

Acciones:

- Remover referencias demo/legacy que ya no correspondan.
- Confirmar que SQLite no se use como fuente viva.
- Alinear local, cloud y git.
- Documentar la nueva forma correcta de acceder a datos.

## Regla para futuras pantallas

Cuando se cree una tarjeta nueva, debe seguir este criterio:

- No abrir conexiones manuales si ya existe adapter/pool.
- No leer mas datos de los necesarios.
- No ejecutar migraciones desde endpoints.
- No inventar otra logica de permisos.
- No duplicar reglas de negocio.
- Si necesita rango de fechas, usar el componente/politica comun.
- Si necesita artistas/empleados/categorias, usar las listas normalizadas.

## Pendiente

Este documento no implementa cambios. Solo guarda el diagnostico y el plan para retomarlo mas adelante.

Antes de tocar codigo, validar con Ruben:

- si se empieza por pool de conexiones;
- si se empieza por sacar DDL de runtime;
- si se prioriza empleados o booking;
- si se hace backup y commit previo.

