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

## Etapa 3: marco visual y navegacion

La navegacion visible, el modulo de permisos y la presentacion de cada vista
salen de un unico registro. Una tarjeta no puede definir por separado su nombre,
su icono y su clave de permiso.

Implementacion canonica:

- `web/app/components/VpoAppFrame.tsx`
- `web/app/components/VpoHome.tsx`
- `web/app/components/vpo-app-frame.css`
- `web/app/shared/navigation/views.ts`

Los modulos pueden tener navegacion interna, pero no deben crear una segunda
barra lateral global. Booking usa una barra de herramientas propia dentro del
marco comun.

## Etapa 4: Reporte por statement

El Reporte por statement es responsable de sus opciones, estado de generacion,
descarga y presentacion. La ruta productiva y el motor de negocio no se duplican.

Implementacion canonica:

- `web/app/features/statements/StatementReportModule.tsx`
- `web/app/features/statements/StatementReportModule.module.css`
- `web/app/features/statements/api.ts`

## Etapa 5: Reporte de regalias

La tarjeta Reporte de regalias conserva una sola entrada con tres salidas:
Excel detallado, PDF ejecutivo y Google Sheet. El modulo es responsable de sus
filtros, periodo, estado y descarga; los calculos y policies siguen viviendo en
el backend productivo y en los documentos rectores de catalogo/reportes.

Implementacion canonica:

- `web/app/features/royalties/RoyaltyReportModule.tsx`
- `web/app/features/royalties/RoyaltyReportModule.module.css`
- `web/app/features/royalties/api.ts`

Reglas de frontera:

- usa `PeriodControl` con perfil `monthly_report`;
- conserva `transaction_month` y `statement_period` como criterios distintos;
- no interpreta marts, catalogo, taxonomia ni ajustes porcentuales en frontend;
- Excel mantiene busqueda obligatoria;
- PDF permite busqueda vacia y alcance por distribuidora/cuenta;
- no queda una implementacion paralela en `page.tsx`.

## Orden de extraccion posterior

1. Reportes personalizados.
2. Ingresos digitales y Participacion.
3. Catalogo y distribuidoras.
4. Artistas y configuracion de comisiones.
5. Booking y agenda restantes.
6. Finanzas y documentos financieros.

Cada etapa debe cerrar con compilacion, validacion de permisos y comprobacion de
que no existen dos implementaciones para la misma responsabilidad.
