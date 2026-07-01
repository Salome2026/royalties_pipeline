# Reporte por statement

## Objetivo

El reporte por statement muestra ingresos digitales agrupados por:

- fuente;
- cuenta;
- artista de statement;
- mes de statement.

El reporte no busca reconstruir caja diaria ni pagos finales a terceros. Es una vista mensual para entender ingresos digitales por liquidacion.

## Inputs

El reporte se alimenta de:

- `warehouse\marts\statement_summary_all_sources.parquet` cuando se ejecuta desde la API;
- `warehouse\marts\standardized_raw_all_sources.parquet` para variantes que necesitan mirar detalle de tema, hoja o transaction month.

Script principal:

- `scripts\build_statement_report_from_mart.py`

Endpoint:

- `POST /reports/statement`

Frontend:

- Tarjeta `Reporte por statement`
- Selector `Reporte viejo` / `Reporte nuevo`

## Reporte viejo

El reporte viejo conserva el criterio historico usado para comparar contra los listados previos.

Reglas:

- FUGA entra igual que antes y mantiene el factor de ajuste `0.977832`.
- DashGo entra completo segun mart de DashGo.
- Orchard / Altafonte entra completo segun mart de Orchard.
- SoundOn entra solo desde `my_royalty`; los summary no se cargan como royalties.
- ONErpm Henry entra completo.
- ONErpm MAWZ entra completo segun la vista historica, incluyendo `Masters` y `Shares In & Out`.
- ONErpm Gusty original queda excluido por defecto del total mediante la hoja `Config`.
- Se agrega una variante `onerpm_gusty_dj_post_motorcito`.

### Gusty post Motorcito en reporte viejo

La variante vieja `onerpm_gusty_dj_post_motorcito` era una ayuda historica.

Su limitacion importante:

- en `Youtube Channels` no siempre podia identificar bien la obra/video porque no usaba todos los campos actuales (`Video Title`, `Video ID`, `ID`, `Parent ID`);
- por eso muchas filas de YouTube sin clave quedaban incluidas;
- el total podia ser mayor que el criterio contractual estricto.

Esta variante se conserva para referencia historica, no como criterio final del nuevo reporte.

## Reporte nuevo

El reporte nuevo busca medir cuanto genera el catalogo/artista bajo el criterio de negocio actual, independientemente de a que cuenta fue el dinero.

Antes de agrupar, el reporte cruza las filas contra el Catalogo General. Si un
`catalog_key` esta marcado con `include_in_reports = false`, no se suma al Excel.
La decision queda en `warehouse\registry\catalog_status.parquet`, no escondida en
la logica del reporte.

El reporte nuevo no es una vista de caja bancaria. Es una vista de generacion
reportable/administrada por VPO. Esto permite incluir catalogo que VPO administra
aunque el dinero haya entrado en una cuenta externa, y tambien permite excluir
obras que aparecen en statements pero no pertenecen al negocio VPO.

Separacion conceptual:

- `generacion reportable`: lo que genero el catalogo que VPO decide reportar;
- `caja`: lo que efectivamente deposito cada distribuidora/cuenta;
- `participacion Indyana`: lo que corresponde a VPO luego de aplicar contratos y
  splits por obra;
- `cuenta corriente artista`: saldos o deudas que nacen cuando caja, generacion y
  participacion no coinciden.

Ejemplo: `Boxindanga` puede aparecer en ONErpm La Nueva Sangre y tener dinero en
el statement. Debe permanecer en catalogo/auditoria, pero si el catalogo lo marca
como `include_in_reports = false`, no aparece en el reporte por statement VPO.
Si ese dinero genera una deuda personal del artista, se tratara en cuenta
corriente, no como ingreso de royalties VPO.

Reglas por fuente:

- FUGA: igual que reporte viejo.
- DashGo: igual que reporte viejo.
- Orchard / Altafonte: igual que reporte viejo.
- SoundOn: igual que reporte viejo.
- ONErpm Henry: entra completo.
- ONErpm MAWZ: entra solo `Masters`; no suma `Shares In & Out`.
- ONErpm Gusty DJ: entra solo contenido posterior a Motorcito bajo criterio de obra/contenido.
- ONErpm La Nueva Sangre: entra solo contenido posterior al ancla detectada en MAWZ para `Ni Ahi, Ni Aca, Ni Alla`.

## ONErpm MAWZ en reporte nuevo

El reporte nuevo usa MAWZ para medir generacion de masters.

Por eso:

- incluye `source_sheet = Masters`;
- excluye `source_sheet = Shares In & Out`;
- mantiene los shares en los datos crudos/marts para auditoria, pero no los suma al reporte nuevo.

Motivo:

- `Masters` representa generacion del master/tema;
- `Shares In & Out` representa transferencias de participacion;
- sumar ambos mezclaria generacion de catalogo con movimientos de participacion.

## ONErpm Gusty DJ en reporte nuevo

El criterio contractual es por contenido, no solo por mes de statement.

Regla:

1. Se detecta la primera aparicion de `Motorcito`.
2. Para el corte contractual se mira `transaction_month`, no solamente `statement_period`.
3. Se construye una clave de contenido usando, en este orden, datos disponibles:
   - `asset_isrc` / `ISRC`;
   - `label_track_id` / `Track ID` / `Video ID` / `ID` / `Parent ID`;
   - titulo + artista cuando no hay identificador mejor.
4. Todo contenido cuya primera aparicion sea anterior al corte queda fuera.
5. Si ese contenido viejo sigue generando en statements posteriores, tambien queda fuera.
6. Lo que queda se agrupa por `statement_period`, porque el reporte sigue siendo mensual por statement.

Esto corrige la limitacion del reporte viejo, especialmente en `Youtube Channels`.

## ONErpm La Nueva Sangre en reporte nuevo

La Nueva Sangre se trata como cuenta externa tipo Gusty.

Regla final esperada:

1. Usar metadata de lanzamiento por obra.
2. Para `Masters`, priorizar consulta por ISRC.
3. Para `Youtube Channels`, usar `Video ID` y/o matching contra masters.
4. Incluir solo obras con release date igual o posterior al inicio contractual.
5. Lo anterior evita confundir catalogo viejo migrado con catalogo nuevo.

Implementacion actual:

- Si `warehouse\marts\catalog_release_metadata.parquet` existe, tiene `release_date` para La Nueva Sangre y se activa `VPO_USE_RELEASE_METADATA_IN_STATEMENT=1`, el reporte nuevo filtra por `include_after_release_cutoff`.
- Si todavia no hay release dates cargadas, el reporte conserva la regla provisoria por ancla para no mover numeros sin validacion.

Regla provisoria:

1. Se busca en ONErpm MAWZ la primera aparicion del tema ancla `Ni Ahi, Ni Aca, Ni Alla`.
2. La busqueda contempla variantes:
   - `ni ahi`;
   - `ni ah`;
   - `ni aca`;
   - `ni ac`;
   - `ni alla`;
   - `ni all`;
   - `ni aya`.
3. El corte se toma por `transaction_month`.
4. En La Nueva Sangre se excluye todo contenido cuya primera aparicion sea anterior a ese corte.
5. Si contenido viejo sigue generando despues, queda fuera.
6. Lo restante se agrupa por `statement_period`.

Control actual:

- El ancla en MAWZ aparece con `transaction_month = 2023-06`.

Limitacion detectada:

- La cuenta La Nueva Sangre puede recibir catalogo viejo migrado desde otra distribuidora.
- En ese caso, `statement_period` o `transaction_month` de ONErpm no alcanzan para decidir si una obra pertenece al contrato nuevo.
- La regla final deberia usar metadata externa de lanzamiento por obra.

Camino definido:

- Para `Masters`, consultar release date principalmente por ISRC.
- Si el ISRC no aparece en Spotify, usar fallback controlado:
  - `upc:{UPC}` solo si Spotify devuelve un unico album;
  - texto solo si el titulo matchea exacto y el artista principal tambien matchea.
- Si el match es dudoso, queda como `pending_manual_review` / `not_found`; no se inventa fecha.
- Para `Youtube Channels`, consultar `publishedAt` por `Video ID` y/o matchear contra masters cuando corresponda.
- Cachear los resultados para no consultar APIs cada vez.
- Revisar pendientes manualmente antes de usar esa metadata como filtro productivo.

Herramienta inicial:

- `scripts\build_catalog_release_metadata.py`
- Output mart/cache:
  - `warehouse\marts\catalog_release_metadata.parquet`
  - `warehouse\registry\catalog_release_lookup_cache.parquet`
- Output de revision:
  - `reports\qa\catalog_release_metadata_review.csv`

## Shares In/Out

Los shares se tratan distinto segun la cuenta y el objetivo del reporte.

### MAWZ

- En reporte viejo: se incluyen porque el viejo representa la vista historica/cuenta.
- En reporte nuevo: no se incluyen porque se busca generacion de masters.

### Gusty DJ

- No se cargan como ingreso en el reporte.
- Se usan como alerta visual sobre Masters cuando matchean por identificador.
- Las celdas amarillas indican `has_share_in_out = 1`.

Interpretacion:

- `Masters` muestra generacion antes de shares.
- `Shares In & Out` muestra transferencias de participacion.
- Para ver caja neta despues de shares hay que analizar `Masters + Shares In/Out`, pero ese no es el objetivo del reporte nuevo.

## Validaciones recomendadas

## Filtro de artistas chicos

El filtro `No mostrar artistas menores a USD` se aplica sobre el total consolidado
de cada `source + account + artist`, no sobre cada mes individual.

Reglas:

- minimo `0` + `Incluir artistas exactamente en cero = no`: muestra cualquier
  artista con total distinto de cero, incluso importes chicos como `0.01`;
- minimo `0` + `Incluir artistas exactamente en cero = si`: muestra tambien los
  artistas cuyo total consolidado es exactamente `0`;
- minimo mayor a `0`: muestra solo artistas cuyo total absoluto consolidado sea
  igual o mayor al minimo indicado.

Despues de cambios en este reporte:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe -m py_compile C:\royalties_pipeline\scripts\build_statement_report_from_mart.py
```

Generar control:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
from scripts.build_statement_report_from_mart import build_statement_report_from_mart

build_statement_report_from_mart(
    output_path=Path(r"C:\royalties_pipeline\reports\qa\statement_nuevo_control.xlsx"),
    report_version="new",
)
PY
```

Verificar que:

- el reporte viejo siga disponible como `legacy`;
- el reporte nuevo salga como `new`;
- la hoja `onerpm_mawzrecords` del reporte nuevo coincida con `Masters` solamente;
- `onerpm_gusty_dj` use criterio post Motorcito por contenido;
- `onerpm_la_nueva_sangre` use el ancla de MAWZ y excluya contenido previo.
