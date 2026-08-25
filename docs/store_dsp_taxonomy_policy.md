# Taxonomia rectora de DSP, monetizacion y origen

## Objetivo

Este documento define la unica clasificacion de negocio permitida para resumir
ingresos digitales por plataforma. Aplica a reportes de regalias, reportes por
statement, dashboards, ingresos digitales y cualquier modulo futuro que muestre
Store/DSP.

La taxonomia ordena evidencia ya presente en los statements. No cambia importes,
unidades, identidad de catalogo, reglas de generacion, reglas de caja ni ajustes
porcentuales de VPO.

## Contrato visible universal

Todo resumen por plataforma debe presentar, en este orden:

1. `Distribuidora`: fuente del statement, por ejemplo FUGA, ONErpm o ADA.
2. `DSP / Store`: servicio normalizado, por ejemplo Spotify, YouTube o Apple Music.
3. `Monetizacion`: forma en que se genero economicamente el ingreso.
4. `Origen`: clase de contenido que produjo el ingreso.
5. `Ingresos USD`.
6. `Unidades`.

`Plan` no forma parte del contrato visible, no es clave de agrupacion y no debe
aparecer en reportes ni dashboards. Individual, Family, Duo, Student y Bundle
son variantes de una misma monetizacion `Premium`. Si una fuente entrega el
subtipo, el dato original se conserva en el detalle para auditoria, pero no
multiplica filas del resumen.

`store_report_label` puede conservarse internamente como alias tecnico para
consumidores del mart, pero su valor es solamente el nombre limpio de
`DSP / Store`. No concatena monetizacion, origen ni ningun plan, y nunca debe
aparecer como una segunda columna visible junto a `DSP / Store`.

## Valores canonicos

### Monetizacion

| Valor visible | Significado |
| --- | --- |
| `Premium` | Suscripcion paga, cualquiera sea su plan comercial. |
| `Ads` | Ingreso financiado por publicidad. |
| `Trial / Promo` | Prueba, promocion u oferta explicitamente informada. |
| `Download` | Compra o descarga permanente. |
| `License / Sync` | Licencia o sincronizacion explicitamente informada. |
| `Adjustment` | Correccion, recupero, deduccion, fraude, breakage u otro ajuste no atribuible a una reproduccion normal. |
| `No informado` | La distribuidora no permite demostrar una categoria anterior. |

`No informado` es una conclusion valida y no un error. No se transforma en
Premium o Ads por conocer el modelo comercial habitual de una plataforma.

### Origen

| Valor visible | Significado |
| --- | --- |
| `Audio / Master` | Explotacion del master de audio en un DSP tradicional. |
| `Music / Art Track` | YouTube Music, Art Track o equivalente explicitamente informado. |
| `Video / Channel` | Ingreso de canal o video identificado como tal por la fuente. |
| `UGC / Content ID` | Contenido generado por usuarios, fingerprinting o Content ID no identificado como otro origen mas preciso. |
| `Shorts` | YouTube Shorts u otro ingreso explicitamente identificado como short-form. |
| `Audio Library / Partner Provided` | Catalogo provisto por VPO o sus socios para biblioteca musical, stickers o usos sociales equivalentes. |
| `Manual Claim` | Reclamo manual explicitamente informado. |
| `No informado` | El statement no permite demostrar el origen. |

`Monetizacion` y `Origen` responden preguntas diferentes. Por ejemplo, una fila
de YouTube puede ser `Premium + UGC / Content ID` o `Ads + Music / Art Track`.

## Evidencia y niveles de clasificacion

La clasificacion usa tres estados:

- `exact`: el statement informa de forma directa la monetizacion y el origen;
- `partial`: una de las dos dimensiones se conoce y la otra queda `No informado`;
- `unknown`: no se puede demostrar DSP, monetizacion ni origen. Altafonte legacy
  es el caso esperado principal.

Solo se admite una inferencia por contrato de fuente cuando la propia
distribuidora usa categorias mutuamente excluyentes dentro del mismo campo. La
regla debe estar escrita en este mapa. No se admiten inferencias particulares
por artista, tema, cuenta o reporte.

## Mapa por distribuidora

### ADA

Evidencia: `Digital Service Provider(DSP)`, `Dist Chan Desc`, `Price Desc` y
`Config Type`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| `Dist Chan Desc = Subscription` | Premium | Segun DSP; Spotify y DSP de audio: Audio / Master |
| `Dist Chan Desc = Ad Supported` o `Ad Channel` | Ads | Segun evidencia de DSP/origen |
| `Payment Top - Up` o `Audit Recovery` | Adjustment | Segun evidencia de DSP/origen |
| DSP `YouTube Music` | Segun canal | Music / Art Track |
| DSP `YouTube` sin mayor detalle | Segun canal | No informado |
| Modalidades como `Broadcast`, `Digital Radio` o `Cloud Locker` sin equivalencia explicita | No informado | Segun evidencia disponible |

ADA no informa plan comercial. No se crea Individual, Family ni Duo.

### DashGo

Evidencia: `Store`, `Product Type` y `Use Type`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| Spotify `P`, `FAM6` o `DUO` | Premium | Audio / Master |
| Spotify `A` | Ads | Audio / Master |
| Codigos con `TRIAL`, `WINBACK`, `2FOR1` o equivalentes explicitos | Trial / Promo | Audio / Master |
| `PDS` y codigos no documentados | No informado | Audio / Master |
| Store `Youtube Premium` | Premium | Segun `Use Type` |
| Store `Youtube AD` | Ads | Segun `Use Type` |
| `Use Type = UGC` | Segun Store | UGC / Content ID |
| `Use Type = Partner-provided` | Segun Store | Audio Library / Partner Provided |
| Store `Youtube Shorts` | No informado salvo evidencia adicional | Shorts |
| Store `Youtube Audio Tier` | Segun evidencia de modalidad | Music / Art Track |

Los subtipos familiares, duo o estudiante no aparecen como columna ni separan
filas del resumen.

### FUGA

Evidencia: `DSP`, `Sale Store Name`, `Sale Type`, `Sale User Type` y
`Asset/Product`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| `Sale User Type = Premium`, Family, Duo, Student o Bundle | Premium | Segun Store |
| `Sale User Type = Ad-supported` | Ads | Segun Store |
| `Sale User Type = Trial` | Trial / Promo | Segun Store |
| `Sale Type = Download` | Download | Audio / Master salvo evidencia contraria |
| Sale Type de licencia/sync | License / Sync | Segun Store |
| Breakage, correction o ajuste equivalente | Adjustment | Segun Store |
| `YouTube Art Track` o DSP `Youtube Music` con evidencia musical | Segun usuario | Music / Art Track |
| `YouTube Channel Income` | Segun usuario | Video / Channel |
| `YouTube UGC`, Content ID o fingerprinting | Segun usuario | UGC / Content ID |
| `YouTube Manual Claim` | Segun usuario | Manual Claim |
| Audio Library, music sticker o catalogo provisto | Segun evidencia | Audio Library / Partner Provided |
| TikTok/Meta `User generated content` | No informado salvo evidencia adicional | UGC / Content ID |
| TikTok/Meta `Partner-provided` | No informado salvo evidencia adicional | Audio Library / Partner Provided |

El nombre del DSP nunca convierte por si solo todo TikTok o Meta en UGC.

### ONErpm

Evidencia: `source_sheet`, `Store`, `Product Type`, `Sale Type` y
`content_type`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| `Spotify Ad Supported` | Ads | Audio / Master |
| `Spotify Discovery Mode` | Adjustment | Audio / Master |
| `Spotify` simple, cuando convive en el mismo layout con las categorias anteriores | Premium | Audio / Master |
| `Youtube Premium` | Premium | Segun hoja y tipo de contenido |
| `YouTube` simple, cuando convive con `Youtube Premium` | Ads | Segun hoja y tipo de contenido |
| `YouTube Audio Tier` | No informado salvo evidencia adicional | Music / Art Track |
| `Youtube Shorts Flat Fee` | No informado salvo evidencia adicional | Shorts |
| Hoja `Youtube Channels` | Segun Store | Video / Channel |
| Hoja `Masters` de un DSP de audio | Segun Store | Audio / Master |
| YouTube en `Masters` sin evidencia de Music, Channel o UGC | Segun Store | No informado |

La interpretacion de Spotify y YouTube simples es una regla de contrato de
fuente: ONErpm publica por separado Ads/Discovery y Premium respectivamente.
No se extiende esa inferencia a otros DSP.

`Shares In & Out` conserva su tratamiento de transferencia/caja/auditoria y no
se convierte en generacion por tener un Store clasificable.

### Orchard moderno y Altafonte legacy

Evidencia Orchard: `STORE`, `SERVICE DETAIL`, `TRANSACTION TYPE`,
`TRANSACTION SUBTYPE` y `ROYALTY TYPE`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| `Subscription ... Streams` | Premium | Segun Store y Transaction Type |
| `Ad Supported ... Streams` | Ads | Segun Store y Transaction Type |
| Promotional, deduction, fraudulent o unqualified | Adjustment | Segun Store |
| Download | Download | Audio / Master salvo evidencia contraria |
| License/sync | License / Sync | Segun Store |
| Audio Streams from Art Track Videos | Segun modalidad | Music / Art Track |
| Streams from Partnered Channels | Segun modalidad | Video / Channel |
| Streams from UGC | Segun modalidad | UGC / Content ID |
| Short-form Video User Generated Revenue | No informado salvo evidencia adicional | Shorts |
| Partner-provided Art Track dentro de Content ID | Segun modalidad | Music / Art Track |

Altafonte legacy no informa Store ni modalidades confiables. Se conserva como
`unknown`, sin completar DSP, monetizacion u origen por inferencia.

### SoundOn

Evidencia: `Store Name`, `Sales Type`, `Sales Sub Type` y `Royalty Type`.

| Evidencia original | Monetizacion | Origen |
| --- | --- | --- |
| `INDIVIDUAL`, `FAMILY`, `DUO`, `STUDENT` o `BUNDLE` | Premium | Segun Store |
| `AD_SUPPORTED` | Ads | Segun Store |
| `TRIAL` | Trial / Promo | Segun Store |
| `DEFAULT` u `OTHER` sin otra evidencia | No informado | Segun Store |
| Spotify | Segun subtipo | Audio / Master |
| `YouTube Music / Content ID` | Segun subtipo | No informado si no puede separarse Music de UGC |
| TikTok/Meta con evidencia `UGC` | No informado salvo evidencia adicional | UGC / Content ID |
| TikTok/Meta con evidencia `PGC` o contenido provisto | No informado salvo evidencia adicional | Audio Library / Partner Provided |

El texto combinado `YouTube Music / Content ID` no autoriza a elegir Music o
UGC sin otra columna que lo demuestre.

## Presentacion y detalle

- El resumen usa exclusivamente Distribuidora, DSP/Store, Monetizacion y Origen.
- `No informado` se muestra como texto humano; no se presenta `Unknown` al usuario.
- El detalle puede conservar Store y campos de modalidad originales al final de
  la hoja para trazabilidad.
- El detalle tampoco muestra una columna normalizada `Plan`.
- Ningun reporte implementa diccionarios propios. Toda clasificacion sale de la
  taxonomia central.

## Validaciones obligatorias

Antes de publicar un cambio de taxonomia:

1. ingresos y unidades deben cerrar exactamente antes y despues;
2. ninguna fila puede entrar o salir de generacion por esta clasificacion;
3. se validan casos reales de ADA, DashGo, FUGA, ONErpm, Orchard y SoundOn;
4. Spotify Premium y Ads deben quedar separados cuando la fuente lo demuestra;
5. YouTube debe conservar monetizacion y origen como dimensiones independientes;
6. TikTok/Meta partner-provided no puede convertirse automaticamente en UGC;
7. Altafonte legacy debe continuar sin granularidad inventada;
8. reportes Excel y dashboard deben producir la misma agrupacion para el mismo alcance.

## Alcance de implementacion posterior

Este documento gobierna la siguiente etapa, pero no la ejecuta. La aplicacion
posterior debe actualizar la taxonomia central, sus pruebas, los marts derivados,
los reportes y el dashboard en ese orden. No se crean rutas de compatibilidad ni
reglas paralelas por reporte.
