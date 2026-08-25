# Arquitectura modular del frontend

## Objetivo

El frontend operativo debe crecer por modulos de negocio y no volver a concentrar
sesion, permisos, datos, acciones y pantallas en `web/app/page.tsx`.

La modularizacion es gradual. Cada extraccion debe conservar el comportamiento
local y cloud antes de avanzar al modulo siguiente.

## Regla de incorporacion

- Las pantallas nuevas no se implementan directamente en `page.tsx`.
- Cada modulo es responsable de sus tipos, acceso a datos, estado y componentes.
- Las funciones compartidas solo viven en `shared` cuando sirven a mas de un
  modulo real.
- Extraer significa mover la responsabilidad y retirar la implementacion anterior;
  no mantener dos caminos compatibles.
- La API y la base operativa siguen siendo unicas.

## Etapa 1: sesion y permisos

La primera frontera compartida comprende:

- validacion de la sesion vigente;
- login y logout;
- cambio obligatorio de contrasena;
- carga de permisos del usuario;
- evaluacion de acceso, alta, edicion y aprobacion por modulo;
- mapa entre vistas y modulos autorizables.

Implementacion canonica:

- `web/app/shared/auth/useSession.ts`
- `web/app/shared/auth/types.ts`
- `web/app/shared/navigation/views.ts`

`page.tsx` puede consumir esta base, pero no debe volver a implementar esas
reglas internamente.

## Etapa 2: ABM Empleados

El ABM de empleados es responsable de su carga, edicion, compensacion pactada,
usuario web y permisos. La pantalla principal solo decide si muestra el modulo.

Implementacion canonica:

- `web/app/features/employees/EmployeesModule.tsx`
- `web/app/features/employees/useEmployees.ts`
- `web/app/features/employees/api.ts`
- `web/app/features/employees/model.ts`
- `web/app/features/employees/types.ts`
- componentes visuales dentro de `web/app/features/employees/`
- estilos de la vista dentro de `web/app/features/employees/employees.css`

La normalizacion de alcance por artista vive en
`web/app/shared/auth/permissions.ts` porque tambien la usan Comisiones y
Movimientos Financieros.

## Orden de extraccion posterior

1. Artistas y configuracion de comisiones.
2. Booking y agenda.
3. Finanzas y documentos financieros.
4. Regalias, catalogo y distribuidoras.

Cada etapa debe cerrar con compilacion, validacion de permisos y comprobacion de
que no existen dos implementaciones para la misma responsabilidad.
