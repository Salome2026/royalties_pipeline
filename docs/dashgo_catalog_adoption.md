# DashGo: metadata comun y Contratos

Regla: `DASHGO-LECTURA-1`. Adaptador: `DASHGO-CAT003-adapter-1`.

La lectura validada conserva `Track Artist` como credito de pista y `Artist Name`
como contexto de producto/video, sin convertir compositores o album en nuevos
participantes. No hay separador multiartista certificado: no fragmentar nombres
de grupos por palabras o signos arbitrarios. Las discrepancias entre fuentes
se conservan visibles; no se resuelven por recorte ni por similitud de titulo.

El builder completa las cuatro columnas `catalog_artists`,
`catalog_artist_statement`, `catalog_artist_rule` y `catalog_artist_evidence`.
Contratos reutiliza esa evidencia para principal y participantes sugeridos.
Los contratos guardados y sus historiales no se reescriben. Los participantes
no definen porcentajes ni derechos; eso se configura en los contratos.

La adopcion es exclusivamente de metadata: no sustituye el lector financiero,
no modifica Payable, periodos, unidades, claves, aliases o asociados. Mantiene
el display legacy de reportes y el dashboard actual sin splits. Los auxiliares
historicos y ORCH-INT-02 permanecen fuera de esta publicacion.

La candidata del 2026-10-22 parte de la produccion actual, conservando
`FUGA-ARTISTS-2`, los cinco contratos recientes de Ruben y la revision protegida
de catalogo versus Spotify. No se promueven usuarios, permisos, configuraciones
o contratos de la base de prueba a la base operativa.

La actualizacion web de seguridad cambia solo package.json/package-lock.json:
Next.js 16.3.8 y dependencias transitivas corregidas. El resto de la interfaz,
sus rutas y los motores de reportes conservan la fuente productiva vigente.

La publicacion requiere pruebas contra la copia cloud actualizada, guardas de
preservacion, build productivo correcto y comprobaciones posteriores de API,
Jobs y Vercel. Los resultados y las referencias inmutables se registran en
`C:/royalties_pipeline/staging/catalogo_lectura/20261022_dashgo_release_current`.
