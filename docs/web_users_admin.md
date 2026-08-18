# Usuarios web VPO Corp

## Regla actual

Los usuarios ya no se administran desde variables de entorno web.

La web de Vercel y localhost autentican contra la API (`/auth/login`) y la API
valida contra la base operativa Cloud SQL. No usar `VPO_WEB_USERS_JSON` ni
`VPO_WEB_PASSWORD`.

## Variables web vigentes

En Vercel Production deben quedar solo:

- `VPO_API_URL`: URL de Cloud Run.
- `VPO_API_KEY`: misma clave que usa Cloud Run.
- `VPO_SESSION_SECRET`: secreto estable para firmar cookies web.

El menu de la web se controla por permisos de modulo/artista desde la base
operativa. No usar variables de entorno para ocultar tarjetas por fuera de los
permisos.

Cada tarjeta configurable debe estar registrada en el catalogo canonico
`app_modules` mediante una migracion de produccion antes de exponerse en el
ABM. La interfaz y la clave foranea de `module_permissions` deben compartir la
misma lista; un modulo presente solo en codigo no se considera operativo.

## Administracion de usuarios

Los usuarios pertenecen al modelo operativo:

- `employees`
- `app_users`
- permisos por modulo
- alcance por artistas cuando corresponda

Crear, desactivar o cambiar permisos desde el ABM de empleados/usuarios. Si se
necesita una correccion puntual por base, debe hacerse contra Cloud SQL con una
nota de auditoria.

## Usuarios retirados

`jfornasari` fue retirado como usuario web. El usuario operativo correcto para
Juan Manuel Fornasari es `juanf`, con los permisos que tenga asignados en la
base viva.
