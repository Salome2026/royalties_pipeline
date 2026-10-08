# Participantes de master: lectura por distribuidora

## Alcance y principio

Estas reglas alimentan **solo las sugerencias de participantes en Contratos**. No
alteran statements, catalogo historico, dashboard, splits guardados ni reportes.
Un credito comercial no prueba titularidad ni porcentaje contractual. Un nombre
abreviado, un artista del lanzamiento y un escritor no se convierten
automaticamente en participantes del master.

Fuente de auditoria: `warehouse/marts/standardized_raw_<source>.parquet`, que
conserva las columnas originales y la ruta/nombre del statement. Las cifras
abajo son la foto local de 2026-10-06; deben repetirse tras nuevas ingestas.

| Distribuidora | Campo de pista usado | Contexto que no se suma automaticamente | Evidencia y regla |
| --- | --- | --- | --- |
| ADA | `Artist Name` | `Project Title`, `Product Title` | 274 ISRC; `Artist Name` tiene tope observado de 30 caracteres. En 157 ISRC llega al tope. Se descarta el ultimo fragmento truncado; solo se reconstruye un invitado de La Juntada cuando `Project Title` lo nombra como unico artista antes de `/ Enganchado` o `/ LA JUNTADA` y coincide con el fragmento. 113 de esos 157 ISRC se resuelven asi; 44 quedan con advertencia. No se expande `& S` globalmente: puede representar distintos artistas. |
| FUGA | `Asset Artist` en filas con ISRC | `Product Artist` | 699 ISRC. En 386.969 filas con ISRC ambos campos difieren; un producto puede reunir artistas ausentes de una pista particular. `Product Artist` se muestra como contexto pero nunca se suma al reparto de esa pista. 47 ISRC tienen variantes distintas de `Asset Artist`; las discrepancias se marcan para revision. Separadores observados: coma, `and`, `featuring`. |
| ONErpm | `artists_raw` con rol `performer` o `featuring` | roles `writer` y datos de video/canal | 392 ISRC; pestañas `Masters` y `Shares In & Out` pueden repetir el mismo credito con distinto espaciado. Se conserva el rol de interprete/invitado y se excluye escritor. 42 ISRC tienen variantes textuales de `artists_raw`; se comparan los conjuntos resultantes, no el texto bruto. |
| Orchard | `TRACK ARTIST` | `PRODUCT ARTIST` | 406 ISRC; 110 muestran separador `|` en el artista de pista. `PRODUCT ARTIST` puede ser un sello o artista de album, por ejemplo `Caserio Records`, y no se agrega a la pista. 97 ISRC tienen variantes de `TRACK ARTIST`, a menudo solo cambia el orden. Si cambia el primer nombre, el artista principal requiere confirmacion manual. |
| SoundOn | `artist_catalog_style` cuando hay referencia ISRC aprobada; si no, `Track Artists` | `Album Title`, orden de artistas de un UPC | 17 ISRC con datos de pista; la lista usa comas. Los dos cambios de orden conocidos se resuelven contra la referencia ISRC versionada; el primer artista de esa referencia es el principal. Cambios de participantes o nuevos principales sin referencia se advierten, sin inferir contratos. Leer `soundon_pipeline_notes.md`. |
| DashGo | `Track Artist` | `Artist Name`, `Album Name` | 125 ISRC. En esta foto, `Track Artist` y `Artist Name` coinciden en todas las filas con ambos campos presentes. Se usa el primero como credito de pista; el segundo queda visible como control, sin duplicar. No se parte un nombre de grupo por `y` o `&`. |

## Reglas de decision

1. Agrupar por ISRC, nunca por titulo: dos versiones con el mismo titulo son
   assets distintos.
2. Usar solamente campos del nivel pista para proponer participantes. Los
   campos de producto/release sirven para contrastar, no para anexar personas.
3. ADA es la excepcion acotada: `Project Title` puede completar un invitado
   truncado si identifica exactamente uno, el ISRC corresponde al registro y
   la inicial coincide. Si no alcanza la evidencia, conservar solo nombres
   completos y advertir. Ejemplo comprobado: `BK4DA2634549` -> La Juntada
   de los Artistas + Sofi B. Statement
   `input_raw/ada/Indyana Records/Statement_99500_5965_99500_20260831.txt`.
4. Si dos creditos de pista completos discrepan para el mismo ISRC, proponer
   solo los nombres comunes y mostrar ambos originales. No unir listas
   contradictorias. Si cambia el primero, advertir que el principal es
   incierto, aun cuando el conjunto coincida, y dejar el principal del
   borrador sin precargar.
5. Conservar nombre de campo, fuente y valor crudo en la ficha. Un nombre
   sugerido nunca se considera split aprobado; el usuario confirma nombres,
   titulares y porcentajes antes de cerrar.
6. Si el crudo no esta disponible, el catalogo historico solo es fallback
   advertido. Un fragmento final de un campo de 30 caracteres no se propone
   como artista.

## Pendientes de certificacion

- Auditar manualmente los 44 ISRC de ADA con artista truncado sin resolucion
  univoca, contrastando metadata del release/track o confirmacion del equipo.
- Revisar los 47 ISRC FUGA con creditos de pista variantes, los 97 Orchard
  con variantes y los 2 SoundOn con orden invertido. Diferenciar variacion
  de orden/ortografia de una contradiccion real; no inferir percentages.
- Confirmar si los roles de ONErpm para `Shares In & Out` son siempre
  equivalentes a `Masters`; diferencias nuevas deben aparecer como alerta.
- Evaluar una tabla persistente de creditos verificados por ISRC con
  fuente, estado, responsable y fecha. Un nombre aprobado por el equipo no
  debe depender de heuristicas futuras ni modificar los crudos.
- No propagar esta lectura al catalogo general, dashboard o reportes hasta
  cotejar un lote de ISRC con Ruben y registrar equivalencia. Los reportes
  actuales permanecen sin cambios.
