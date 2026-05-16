# Cloud environment policy

Este documento define como usamos cloud sin mezclar laboratorio local, demo y produccion.

## Idea central

- Local es el taller de trabajo: aca probamos, rompemos, corregimos y cargamos historico.
- Cloud demo es una vidriera controlada: muestra solo funciones estables y datos publicados a proposito.
- Produccion futura va a ser otro paso: escritura controlada, backups, permisos y auditoria.

Mientras estemos en etapa demo, cloud debe leer snapshots validados. No debe recibir pruebas sueltas.

## Servicios actuales

### Vercel

Frontend Next.js:

- URL: `https://vpo-corp.vercel.app/`
- Proyecto: `vpo-corp`
- Branch: `main`
- Root directory: `web`

Variables importantes:

- `NEXT_PUBLIC_VPO_MENU_MODE=demo`
- `VPO_API_URL=https://vpo-corp-api-259971998447.us-central1.run.app`
- `VPO_API_KEY`
- `VPO_WEB_USERS_JSON`
- `VPO_SESSION_SECRET`

En modo demo, la web debe mostrar solo tarjetas aprobadas para compartir. Hoy la tarjeta publica de prueba es `Detalle Booking`.

### Google Cloud Run

Backend FastAPI:

- Servicio: `vpo-corp-api`
- Proyecto: `vpo-corp-royalties`
- Region: `us-central1`
- Min instances: `0`
- Max instances: `1`
- Billing: request-based

Variables de lectura booking demo:

- `VPO_BOOKING_READONLY_GCS=true`
- `VPO_BOOKING_GCS_OBJECT=booking/live/booking_live.sqlite`
- `VPO_BOOKING_DB_PATH=/tmp/vpo-corp/booking/booking_live.sqlite`
- `VPO_BOOKING_REFRESH_ON_REQUEST=false`

Con esta configuracion, Cloud Run descarga una copia SQLite desde GCS y la usa como lectura. No escribe sobre la base local ni sobre el bucket.

### Google Cloud Storage

Bucket:

- `vpo-corp-royalties-marts`

Objetos principales:

- `marts/`: marts de regalias publicados.
- `booking/live/booking_live.sqlite`: snapshot validado de booking para demo.

Regla: subir solo artefactos elegidos. No subir carpetas crudas, backups locales ni archivos de prueba.

## Publicar datos de booking a demo

Publicar solo cuando la base local este revisada:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\publish_booking_live_to_gcs.py --apply
```

Despues verificar:

```powershell
Invoke-RestMethod https://vpo-corp-api-259971998447.us-central1.run.app/health
```

Si `VPO_BOOKING_REFRESH_ON_REQUEST=false`, Cloud Run puede conservar una copia en `/tmp` mientras la instancia viva. Para forzar que lea el snapshot nuevo, redeploy o reiniciar la revision.

## Que no se sube

- `input_raw/`
- `reports/`
- `exports/`
- `warehouse/detail/`
- `warehouse/registry/`
- backups SQLite sueltos
- `.env`, `.env.local`
- `secrets/`
- service account JSON
- scripts experimentales sin validar
- cambios locales de laboratorio en booking

## Regla para commits cloud

No usar `git add .` para deploy.

Para cambios de cloud/demo, preferir un worktree limpio como:

```powershell
C:\royalties_pipeline_deploy
```

Checklist antes de push:

- Ver que `git status` no tenga archivos inesperados.
- Stagear solo los archivos necesarios.
- Probar build o endpoint relevante.
- Hacer commit chico y claro.
- Push a `main`.

## Control de costos

- Cloud Run debe quedar con `min instances = 0`.
- No dejar jobs o servidores locales replicando datos a cloud en loop.
- No subir reportes grandes temporales a GCS.
- Mantener `max instances = 1` mientras sea demo interna.
- Para demos puntuales, publicar snapshots chicos y estables.

## Cuando pasemos de demo a produccion

Antes de permitir escritura real en cloud, definir:

- base persistente oficial;
- backups automaticos;
- auditoria de cambios;
- usuarios y roles definitivos;
- separacion entre `demo` y `prod`;
- procedimiento de rollback.

Hasta entonces, cloud es lectura controlada.
