# ADA: lectura obligatoria de Excel

## Alcance y fuente unica

Regla vigente desde 2026-10-07: SOLO Excel .xlsx para Mawz e Indyana.
No hay lector TXT, prioridad de formatos, fallback ni dependencia de GPID.
Los archivos anteriores son respaldo historico fuera de ingesta, no una fuente.

| Cuenta | Carpeta | Identificador original |
| --- | --- | --- |
| mawz | input_raw/ada/mawz | 99205 |
| indyana_records | input_raw/ada/Indyana Records | 99500 |

Un solo ingestor produce standardized_raw_ada y song_level_ada para ambas cuentas.
Se valida la cuenta de Contract contra filename y carpeta; no se mezclan cuentas.

## Validacion del archivo

- Nombre: cuenta_YYYYMM_YYYYMM_cuenta_DTL.xlsx, meses validos e iguales.
- Hoja Distribution Statement; localizar columnas por nombre, no por posicion.
- Contract y Royalties Statement for Period deben coincidir con cuenta y mes.
- Rechazar columnas duplicadas, campos obligatorios ausentes y dos archivos por mes.
- Rechazar formatos distintos de .xlsx en la carpeta activa; no leerlos en silencio.
- Omitir solo filas vacias y pies Sub Totals, Previously Accounted Deductions y Totals.
- Preservar las columnas originales y duplicados economicos reales.
- Conservar filename, ruta, hash y fecha de ingesta como trazabilidad.

## Mapa obligatorio

| Columna Excel | Significado y destino |
| --- | --- |
| Artist Name | Credito original literal; artist_statement_original para auditoria |
| Catalogue Title | Tema; track_statement_style y asset_title_statement |
| Project Title | Lanzamiento; release_statement_style |
| ISRC | ISRC valido normalizado; asset_isrc |
| Catalogue Number | Identidad nativa; catalog_number y source_asset_id |
| UPC | UPC explicito, solo con GTIN valido |
| Parent Product ID | Contexto de lanzamiento; UPC alternativo validado |
| Local Product Number | Contexto original, NO supuesto UPC |
| Reported Month | Consumo; transaction_month, YYYYMM a YYYY-MM |
| Filename y encabezado | Liquidacion; statement_period |
| Territory | Plataforma / DSP; store_name. NO es el pais |
| Country Code | Pais; territory |
| Country Description | Descripcion original del pais |
| Revenue Type Desc | Modalidad; use_type |
| Price Name | Precio / producto; product_type |
| Sales | Unidades, incluidas correcciones negativas; units |
| Receipts Value | Bruto; gross_royalty_usd |
| Distribution Fees | Deduccion ADA; deductible_fees_usd |
| Bruto menos deduccion | amount_usd, net_amount y net_amount_usd |
| Marketing Owner | Contexto original; NO prueba de contrato ni titularidad |

ADA Excel no informa fecha de acreditacion bancaria: receipt_month queda vacio.
Consumo sirve para tendencias; statement sirve para liquidar. Nunca intercambiarlos.

## Dinero y policies

Calcular Receipts Value menos Distribution Fees con Decimal, sin redondear filas.
Validar importes y unidades numericos, no vacios y finitos.
Artist Royalties, Mechanical Fees, Admin Fees, Upload Fees y Other Fees fueron
auditados en cero; si cambian o son invalidos, detener la ingesta para revisar.
Nunca cambiar el dinero para que cierre ni descartar una fila invalida.

Las flags y revenue_basis se leen de la policy vigente de Cloud SQL. Mantener
sin cambios los ajustes de reportes de cada cuenta. El lector NO aplica splits,
no convierte ingresos en cobros bancarios y no descuenta otra vez la policy.

## Identidades y lanzamientos

1. ISRC valido: ISRC:<ISRC>. Distintos ISRC son distintos assets, aun con igual titulo.
2. Sin ISRC: ADA:<cuenta original>:CATALOG:<Catalogue Number>.
3. Sin ambos identificadores: detener ingesta. No inferir GPID, ISRC ni video.
4. Venta de album/producto permanece independiente; no repartirla entre pistas.
5. UPC relaciona lanzamientos con assets; NO reemplaza la identidad de pista.
6. UPC primero, Parent Product ID despues: GTIN de 8/12/13/14 digitos con checksum
   valido, distinto de cero. Preservar ceros iniciales. Contradiccion valida: error.
7. Un album sin UPC puede recibir el codigo unico de sus pistas SOLO en el mismo
   statement, con Project Title y Artist Name identicos, y Catalogue Title igual
   a Project Title. Marcar same_statement_release / derived_release.
8. Sin evidencia, queda vacio. No buscar en Internet ni usar archivos retirados.

## Participantes sin invenciones

Artist Name se conserva literal. No inferir invitados desde Project Title.
Para un credito de 30 caracteres, usar una version mas larga SOLO cuando hay
una unica coincidencia de prefijo en otro Excel del mismo ISRC. Conservarla en
artist_catalog_style con estado confirmed_prefix y el archivo de evidencia.
artist_statement_style expone ese mismo credito resuelto a dashboard, ingresos,
busquedas y reportes; no dejar el nombre corto en las vistas operativas.
Artist Name y artist_statement_original conservan el credito recibido para auditar.
Al reprocesar, conservar el original y recalcular la evidencia desde los Excel.
Conflictos quedan conflicting_prefix; sin evidencia possible_truncation.
Tener 30 caracteres no demuestra por si solo que un nombre este mal.
Creditos, orden principal y porcentajes contractuales son cosas distintas.
No aplicar contratos a los reportes actuales.

## Circuito y controles de reemplazo

Procesar ejecuta ingest_standardized_ada.py y build_song_level_ada.py, luego
consolidado, statement summary, catalogo y summaries de ingresos/dashboard.
Publicar activa un release inmutable de GCS y carga/conciliacion en BigQuery.
Las columnas originales permanecen en Parquet; BigQuery conserva identidad,
lanzamiento, participantes originales/evidencia, fechas, DSP/pais, unidades,
bruto, fees, neto y trazabilidad. La columna historica gpid en BigQuery queda
nula en nuevos releases ADA; no se utiliza para interpretar Excel.

Antes de reemplazar, respaldar y conciliar por cuenta, statement, consumo,
ISRC, Catalogue Number, DSP, pais, modalidad y precio: bruto, fees, neto y unidades.
Los Excel pueden agrupar filas antes separadas sin alterar esas dimensiones.
En el reemplazo revisado, Revenue Type Desc difiere de las modalidades del
publicado anterior (incluye Bundle, Settlement y Unclassified). Cuatro grupos
antes DSP Not Reported ahora informan WEA LATINA INC. Registrar estas diferencias
de metadata, no copiar clasificaciones viejas ni alterar dinero para ocultarlas.
Verificar tambien otras distribuidoras, dashboard, policies y catalog keys.
No borrar releases historicos ni actualizar catalogo de otros proyectos.

Inventario completo revisado: 28 Excel Mawz (2024-05 a 2026-08) y 3 Excel Indyana
(2026-06 a 2026-08). Febrero-abril 2024 Mawz estaban confirmados sin actividad;
son antecedentes de continuidad, no filas economicas inventadas ni archivos
activos necesarios. Agosto Mawz es nuevo: neto USD 12633.68009634.
Evidencia del reemplazo: C:/royalties_pipeline/staging/ada_excel_only_20261007.

Pruebas obligatorias al cambiar estas reglas: qa_ada_excel_replacement.py,
qa_ada_artist_display.py,
qa_ada_release_codes.py, qa_ada_accounts.py, qa_master_contracts_pilot.py,
qa_store_reporting_dimensions.py, qa_bigquery_release_transform.py y conciliacion BigQuery.
Leer tambien identity_normalization_policy.md, statement_period_policy.md,
store_dsp_taxonomy_policy.md y statement_source_dictionary.json ANTES de editar.
