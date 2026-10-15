# Cruces automaticos de futuros Extended

La carga habitual procesa los ISRC nuevos sin decisiones manuales ni propuestas pendientes. La auditoria financiera del Extended sigue siendo obligatoria antes de incorporar metadatos.

- El constructor de catalogo ejecuta la resolucion despues de construir las fichas de los statements nuevos.
- Si llega solamente un Extended, el proceso abre el catalogo existente y aplica la misma resolucion sin reconstruir ingresos.
- Un puente nativo unico por Sale ID confirma la relacion con un audio existente. Los puentes contradictorios se cierran sin vincular.
- Cuando falta ese puente, un candidato unico con titulo y artista coincidentes se verifica contra Spotify por ISRC exacto y contra los IDs de video de YouTube. Se exige coincidencia de titulo y version, fecha de publicacion dentro de dos dias y duracion dentro de siete segundos. No constituye comparacion acustica.
- Sin evidencia suficiente, catalogo ambiguo, proveedor no disponible o versiones distintas: cierre sin vinculo, con motivo y sin solicitar confirmacion. Se vuelve a evaluar automaticamente en la siguiente carga; no hay tareas para usuarios.
- Las decisiones historicas confirmadas se conservan. Las nuevas no crean temas, no fusionan filas economicas ni agregan alias financieros.
- La evidencia y el resultado viajan en `fuga_youtube_extended_metadata.parquet`, columna `automatic_resolution_json`, incluido en la publicacion habitual. Los resultados positivos externos se reutilizan para los mismos identificadores.
- Las credenciales de proveedores se obtienen de la configuracion habitual. Su ausencia no convierte una coincidencia de titulo en confirmacion.

Validacion: pruebas de ISRC ficticios futuros, puentes ambiguos, falta de audio, proveedores caidos, versiones en vivo, diferencias de duracion, idempotencia y preservacion por ficha de ingresos, unidades y filas economicas.
