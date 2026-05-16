# Usuarios web VPO Corp

Este documento explica como agregar usuarios a la web de VPO Corp sin cambiar codigo.

## Modelo actual

La web usa login con usuario y contrasena.

Roles disponibles:

- `viewer`: puede entrar y ver.
- `editor`: puede entrar, ver y guardar/editar.
- `admin`: permisos completos. Por ahora se usa como editor avanzado; el ABM web de usuarios queda para una etapa posterior.

Las rutas de lectura aceptan `viewer`.
Las rutas de escritura piden `editor` o `admin`.

## Variable de entorno

Los usuarios se configuran en la variable:

```text
VPO_WEB_USERS_JSON
```

Formato:

```json
[
  {
    "username": "jfornasari",
    "password_hash": "scrypt$...",
    "role": "viewer",
    "active": true
  }
]
```

Importante: si `VPO_WEB_PASSWORD` sigue configurada, el sistema conserva el acceso legacy para `ruben` y `admin` con esa contrasena. Esto evita bloquear a Ruben al agregar usuarios nuevos.

## Crear hash de clave

Desde la carpeta web:

```powershell
cd C:\royalties_pipeline\web
npm run hash-password -- "clave-del-usuario"
```

Copiar el resultado completo, incluyendo el prefijo `scrypt$`.

## Usuario creado inicialmente

Juan Manuel Fornasari:

```json
{
  "username": "jfornasari",
  "password_hash": "scrypt$JojA3ThX1Jj3cCS-5VDaCw$b26S6TdytL3EbxXpSEXYzJqEKb6iSa7GjaGTfVYEtyU",
  "role": "viewer",
  "active": true
}
```

## Como agregar otro usuario

1. Generar hash con `npm run hash-password -- "clave"`.
2. Agregar un objeto nuevo al array de `VPO_WEB_USERS_JSON`.
3. Elegir rol: `viewer`, `editor` o `admin`.
4. Guardar la variable en Vercel.
5. Redeploy si Vercel no lo hace automaticamente.

Ejemplo con dos usuarios:

```json
[
  {
    "username": "jfornasari",
    "password_hash": "scrypt$JojA3ThX1Jj3cCS-5VDaCw$b26S6TdytL3EbxXpSEXYzJqEKb6iSa7GjaGTfVYEtyU",
    "role": "viewer",
    "active": true
  },
  {
    "username": "otro_usuario",
    "password_hash": "scrypt$PEGAR_HASH_AQUI",
    "role": "viewer",
    "active": true
  }
]
```

## Cambiar permiso

Cambiar solo el campo `role`.

Ejemplo:

```json
"role": "editor"
```

## Desactivar usuario

No borrar el usuario si queremos conservar historial administrativo. Cambiar:

```json
"active": false
```
