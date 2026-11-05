# DashGo pipeline notes

## Objetivo

Replicar el pipeline viejo de DashGo y conservar todas las columnas utiles para reportes por artista, tema, ISRC, tienda, region y tipo de uso.

## Inputs

- Carpeta: `C:\royalties_pipeline\input_raw\dashgo`
- Archivos: CSV DashGo

## Scripts principales

- `scripts\ingest_dashgo_incremental.py`: pipeline viejo hacia `warehouse\detail\royalties_detail.parquet`
- `scripts\ingest_standardized_dashgo.py`: pipeline nuevo hacia `warehouse\marts\standardized_raw_dashgo.parquet`
- `scripts\build_song_level_dashgo.py`: mart agregado por tema
- `scripts\audit_song_level_dashgo.py`: auditoria del song-level

## Reglas de monto

- Columna base: `Payable`
- `amount_usd`, `net_amount`, `net_amount_usd`: se derivan de `Payable`
- No hay conversion FX en el standardized actual de DashGo porque el monto ya esta en la moneda usada para reporting USD.

## Reglas de fechas

- `transaction_month`: se deriva de `Transaction Date`, formato `YYYY-MM`
- `statement_period`: se deriva del nombre del archivo, con la misma logica del ingest viejo

## Reglas de artista/tema

- `artist_statement_style`: principalmente `Artist Name`
- Si `Artist Name` falta y `Track Title` indica asset auto generado, se usa `No Identificado`
- Si no, fallback a `Track Title`

Campos relevantes conservados:

- `track_statement_style`
- `artist_name_statement`
- `track_artist_statement`
- `asset_isrc`
- `product_upc`
- `store_name`
- `territory`
- `product_type`
- `use_type`
- `units`

## Outputs

- `warehouse\marts\standardized_raw_dashgo.parquet`
- `warehouse\marts\song_level_dashgo.parquet`

## Validacion esperada

El total de `song_level_dashgo.amount_usd` debe cerrar contra `standardized_raw_dashgo.amount_usd`.

Tambien debe cerrar contra el pipeline viejo en el reporte por statement.

## Evidencia para DSP y monetizacion

La clasificacion usa `Store`, `Product Type` y `Use Type`. Para Spotify estan
validados por negocio:

- `P`: Premium, plan individual.
- `FAM6`: Premium, plan familiar.
- `DUO`: Premium, plan duo.
- `A`: Ads.
- `PDS`: significado pendiente; debe permanecer `Unknown`.

Individual, familiar y duo son evidencia raw, pero el resumen visible los
agrupa bajo monetizacion `Premium`; no existe una columna `Plan`. Los codigos
promocionales explicitamente identificables se clasifican como `Trial / Promo`.

YouTube distingue Store Premium, Ads, Shorts, Audio Tier y ajustes. `Use Type`
permite separar UGC de partner-provided cuando viene informado. No se debe
inventar Art Track o video oficial si la fila no lo demuestra.

UGC se presenta como `UGC / Content ID`; partner-provided como
`Audio Library / Partner Provided`. El contrato completo esta en
`docs/store_dsp_taxonomy_policy.md`.

## Correccion de admision de pies, 2026-11-04

`scripts/lib/dashgo_row_classes.py` reconoce ventas, controles y separadores
antes de validar Payable. Verifica la correspondencia de cada registro CSV con
la lectura y la estructura fisica del pie: cinco controles de trece campos,
sus etiquetas y secuencia, y tres registros separadores. Un pie incompleto o
alterado se rechaza; una venta sin importe sigue siendo una venta invalida.

La validacion monetaria se aplica solo a ventas. La salida standardized conserva
todas las filas y celdas originales, incluidos controles y separadores. No se
cambian formulas, identidades, contratos, asociados, clasificacion ni reportes.
Esta entrega publica codigo; no reconstruye ni reemplaza datos historicos.

La guarda comun agregada el 2026-10-30 validaba tambien los pies como ventas y
rechazaba los 35 originales. La prueba aislada de la correccion conserva
499.977 ventas, USD 28.212,27238360, 50.739.925 unidades, 175 controles y 105
separadores. Los nueve auxiliares Mechanical Royalty historicos incompletos
siguen fuera del alcance; su recuperacion al releer ya existe en el lector
publicado desde la preservacion lexical de noviembre, no en esta correccion.

Regresion permanente: `scripts/qa/qa_dashgo_row_classes.py`, incluida en
`cloudbuild.yaml`. Evidencia aislada inmutable:
`C:/royalties_pipeline/tmp/dashgo_footer_trial_20261104/evidence`.
Evidencia de publicacion y comprobaciones antes/despues:
`C:/royalties_pipeline/staging/catalogo_lectura/20261104_dashgo_footer_release`.

## Retiro de excepcion de presentacion, 2026-11-04

Se retira del codigo la excepcion por titulo, video, canal y periodo de
Te Prestaria Mis Ojos. No se reemplaza por una inferencia general por nombre.
Una referencia sin codigo y otra con VideoId mantienen identidades separadas
hasta que exista evidencia de catalogo independiente de los contratos.

La presentacion no asigna un VideoId a la fila textual ni combina sus importes
o columnas contractuales con otra identidad. La regla previa de compactacion
de importes pequenos es independiente y no se modifica en este retiro.

La revision completa de DashGo abarca todos los originales disponibles,
identidad de grabacion/video/producto/referencia, Store, monetizacion, origen,
periodos, unidades y trazabilidad. No define derechos ni porcentajes.
Evidencia: `C:/royalties_pipeline/tmp/dashgo_complete_audit_20261104`.
El retiro se entrega como cambio de codigo sin reconstruir datos. Su activacion
y comprobaciones constan en
`C:/royalties_pipeline/staging/catalogo_lectura/20261104_dashgo_remove_report_exception/certification.json`.
La definicion general siguiente permanece como propuesta; no crea asociaciones.

## Revision integral y definicion propuesta, 2026-11-04

Alcance comprobado: todos los 35 CSV disponibles de mawzrecords, tres firmas de
columnas, octubre de 2023 a agosto de 2026. No certifica otras cuentas o formatos
de DashGo que no esten en esos originales. Se examinaron 499.977 ventas,
USD 28.212,27238360 y 50.739.925 unidades; los 175 controles y 105 separadores
se verificaron aparte. Los originales y los datos publicados quedan intactos.

La evidencia confirma 119 grabaciones/119 fichas con DASHGO-LECTURA-1, todas con
resolucion comun de participantes valida. Se conservan los 15 creditos textuales
de pista distintos; un credito puede representar un grupo, no una persona legal.
La clasificacion publicada coincide con la regla central en todas las ventas.

| Nivel nativo | Ventas | Payable USD |
| --- | ---: | ---: |
| ISRC valido | 492.643 | 27.732,70231956 |
| VideoId, sin ISRC ni UPC | 483 | 35,70891346 |
| UPC de producto, sin ISRC ni VideoId | 12 | 46,79245380 |
| Sin esos tres identificadores | 6.839 | 397,06869678 |

Se observan 1.601 VideoId: 113 se relacionan con varios ISRC. Ocho UPC contienen
varias grabaciones. Lucete y Fluye en mi tienen dos ISRC cada uno. Son casos
previstos por D05, no motivos para fusionar grabaciones. Las 330 combinaciones
nativas de titulo/Artist Name/canal sin codigo pertenecen al mismo ChannelId:
24 tienen importe y 306 contienen solo ventas cero. No son 330 canciones
confirmadas; cero es una venta y conserva sus unidades, no un control de pie.

Hay 173 perfiles Store/Use Type/Product Type con monetizacion No informado,
por USD 5.108,05322009 ya contabilizados. Esto conserva la regla aprobada: campo
ausente o codigo sin significado acreditado no autoriza a inventar Premium/Ads.
La evidencia incluye Amazon con Use Type vacio y codigos como PDS/PDIB/FAMIB.
Una ampliacion semantica exige evidencia de fuente y cambios en la taxonomia
central. No es una perdida de dinero ni una reclasificacion realizada aqui.

La definicion completa propuesta conserva las capas ya aprobadas:

1. Observacion: una venta original con archivo/SHA-256/registro CSV, cuenta,
   fechas de statement y consumo, pais, campos nativos, importe y unidades.
   Vincular identidad no elimina ni duplica observaciones, incluso las de cero.
2. Entidades independientes: grabacion (ISRC), video (VideoId), producto (UPC)
   y referencia de origen incompleta. Una venta puede informar varias entidades.
   Un video no es un alias universal de una grabacion; las relaciones multiples
   se conservan con procedencia, nivel, estado y evidencia.
3. Resolucion: una correspondencia confirmada se registra aparte, versionada y
   acotada a la evidencia de origen. No rellena el campo nativo vacio ni convierte
   tokens de titulos en codigos nativos. Nombres o contratos cerrados no prueban
   identidad. Los casos incompletos/conflictivos permanecen visibles.
4. Dimensiones: DSP, monetizacion y origen provienen de la taxonomia central y
   se mantienen por observacion. Resolver identidad no copia la monetizacion o
   el origen de otra venta. No informado conserva su evidencia y razon.
5. Consumo: catalogo, consultas y reportes usan la misma resolucion versionada.
   Un resumen por identidad puede mostrar totales; un corte por monetizacion y
   origen conserva esas claves. Nunca se reconstruye el detalle desde un resumen
   que haya descartado dimensiones. La compactacion visual no resuelve identidad.
6. Contratos: etapa posterior e independiente para derechos, porcentajes y
   vigencias. El catalogo no los define ni usa sus inclusiones para decidir que
   dos entidades fisicas son una sola. Esta revision solo verifica su preservacion.

Pendientes explicitamente separados: correspondencias sin identificador;
semantica no acreditada de modalidades; etiqueta legacy ugc por ausencia de
ISRC; compactacion visual de importes pequenos; nueve auxiliares historicos;
compatibilidad futura de unidades desconocidas (ORCH-INT-02). No se reemplaza
el lector financiero ni se aplican esos cambios durante esta auditoria.

Resultados y ejemplos ajenos a Juli en source_summary.json, identity_levels.json,
business_dimensions.json, native_monetization_unresolved_profiles.json,
multiple_recordings_per_video.json y same_title_distinct_recordings.json bajo
la carpeta de evidencia indicada arriba. La definicion es propuesta para revision;
no instala asociaciones nuevas ni define contratos.

## Videos con distinta monetizacion en Resumen por tema, candidata 2026-11-04

Ruben pide reunir en Resumen por tema los ingresos del mismo video aunque
DashGo informe Ads y Premium por separado. El detalle y los cortes por
monetizacion/origen se conservan. Compartir contrato sigue siendo una relacion
independiente: no demuestra por si solo que dos items sean el mismo asset.

`scripts/lib/dashgo_video_identity.py` compila la evidencia de la version completa
antes de seleccionar meses o palabras. Exige cuenta/canal nativo/titulo completo
compatibles, un unico VideoId observado y una contraparte nativa sin ISRC/UPC.
Los identificadores competidores de todo el historico vetan la coincidencia.
La regla no contiene artistas, temas, videos, canales ni periodos fijos.
Los titulos genericos/incompletos y Auto generated asset quedan fuera; no se
convierte un token textual en VideoId nativo. ISRC/productos conservan su nivel.

El constructor comun agrega solo una clave derivada al resumen. Las ventas,
campos originales, detalle y dimensiones permanecen iguales. Los fragmentos
contractuales usan esa clave para conciliar el resumen, pero resuelven cada
contrato por sus identificadores/decisiones originales: no trasladan cobertura
desde Premium a Ads. No se modifica ni guarda una asociacion contractual.

Alcance de prueba: todos los 35 archivos disponibles de mawzrecords, sin filtro
por artista; ambos ejes temporales y columnas de contratos. Evidencia y
comparacion en
`C:/royalties_pipeline/staging/catalogo_lectura/20261104_dashgo_video_summary_copy`.
Regresiones en `qa_dashgo_report_summary.py`, ya incluida en Cloud Build.
Publicacion autorizada por Ruben el 2026-11-04. El despliegue y las comprobaciones
antes/despues se certifican en
`C:/royalties_pipeline/staging/catalogo_lectura/20261104_dashgo_video_summary_release/certification.json`.
El catalogo y los datos productivos no se reconstruyen ni se modifican.
