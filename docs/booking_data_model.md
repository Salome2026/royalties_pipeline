# Booking Data Model

Este documento baja el diseno de booking a entidades operativas concretas. Las cargas
nuevas viven exclusivamente en Cloud SQL/Postgres. Parquet puede conservarse para
analitica o reportes pesados, pero no es una segunda base transaccional y SQLite no
participa del flujo vivo.

## Convenciones

- Las tablas operativas Cloud SQL usan IDs `bigint` generados por la base.
- Los IDs externos o de integraciones se conservan aparte y nunca reemplazan el ID interno.
- Montos siempre guardados en moneda original, ARS y USD cuando aplique.
- El tipo de cambio queda congelado en cada movimiento.
- Las filas aprobadas no se editan silenciosamente: se corrigen con ajustes.
- Los datos cargados por tour managers entran como borrador hasta aprobacion.

## booking_artists

Catalogo de artistas y personas relevantes para liquidaciones.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| artist_id | string | si | ID interno estable | artist_virrshi |
| display_name | string | si | Nombre visible | Virrshi |
| legal_name | string | no | Nombre legal o razon social |  |
| artist_type | string | si | own_artist, external_artist, dj, producer, other | own_artist |
| default_booking_rule_id | string | no | Regla default de booking | rule_70_30 |
| active | bool | si | Si sigue activo | true |
| notes | string | no | Comentarios |  |

## booking_people

Personas que pueden aparecer como vendedores, managers, tour managers, socios o
beneficiarios.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| person_id | string | si | ID interno | person_facha |
| display_name | string | si | Nombre visible | Facha |
| role_default | string | no | seller, manager, tour_manager, partner, supplier | seller |
| active | bool | si | Si sigue activo | true |
| notes | string | no | Comentarios |  |

## booking_events

Cabecera operativa canonica de Agenda. Puede representar un show, un grupo, un bloqueo,
logistica o un prospecto. No reemplaza la liquidacion economica.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| id | bigint | si | ID interno generado | 55 |
| event_type | string | si | show, show_group, availability_block, logistics, prospect | show |
| event_date | date | si | Fecha principal | 2025-08-09 |
| start_time | time | no | Hora del show si se conoce | 23:30 |
| venue | string | si | Lugar o evento | Club Son |
| city | string | no | Ciudad | Buenos Aires |
| booking_mode | string | si | individual, shared | individual |
| commercial_status | string | si | confirmado, cancelado, prospecto, no_aplica | confirmado |
| operational_status | string | si | programado, realizado, bloqueado, informativo | programado |
| deposit_status | string | si | no_informada, sin_sena, sena_parcial, sena_recibida | sin_sena |
| settlement_status | string | si | no_iniciada, pendiente, rendida, observada, cerrada, no_aplica | no_iniciada |
| contracted_cachet_amount | decimal | no | Cachet pactado inicial | 1500000 |
| currency | string | si | ARS, USD | ARS |
| fx_rate | decimal | no | Tipo de cambio congelado si aplica | 1500 |
| tour_manager | string | no | Responsable operativo | Santiago Mareco |
| seller | string | no | Responsable comercial | Marcelo |
| group_event_id | bigint | no | Agrupador visual del show | 89 |
| group_position | integer | no | Orden dentro del grupo | 1 |
| duplicate_override | bool | si | Confirma que una coincidencia es otro show | false |
| duplicate_override_notes | string | no | Justificacion del override | Segundo show en otra sede |
| notes | string | no | Observaciones | Sociedad con Caserio |
| created_by | string | si | Usuario creador | santiagod |
| created_at | timestamp | si | Alta auditable | 2026-08-16T11:00:00Z |
| updated_at | timestamp | si | Ultimo cambio | 2026-08-16T11:00:00Z |

La agenda consulta esta tabla. No existe `booking_agenda_entries` como segunda verdad.

Los campos identificatorios y economicos iniciales se mantienen sincronizados con la
liquidacion vinculada. `booking_event_source_links.source_text` conserva el valor de
origen y no reemplaza el valor operativo corregido de `booking_events`.

Reglas:

- solo `event_type=show` puede iniciar una liquidacion;
- `show_group` no se suma en reportes y contiene shows hijos;
- `availability_block`, `logistics` y `prospect` usan liquidacion `no_aplica`;
- un show hijo siempre tiene `group_event_id` y `group_position` juntos;
- el grupo no reemplaza una madre economica multiartista.

## booking_event_source_links

Trazabilidad entre una fila o celda de una fuente validada y la Agenda canonica.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| id | bigint | si | ID interno | 501 |
| event_id | bigint | si | Evento vinculado | 55 |
| source_system | string | si | Origen estable | agenda_indyana_excel |
| source_reference | string | si | Archivo, hoja y renglon | agenda_20260816:Agenda:166 |
| source_role | string | si | imported, linked_existing, group_child | imported |
| source_text | string | no | Texto original preservado | Teodolina las 2 x 9,5 |
| source_payload_json | json | si | Datos estructurados de auditoria | {} |
| created_by | string | si | Usuario o proceso | system_agenda_import |
| created_at | timestamp | si | Alta auditable | 2026-08-16T18:00:00Z |

La unicidad por evento, sistema y referencia hace que una importacion sea repetible.
Una referencia puede vincular varios eventos cuando la fuente resume varios shows.

## booking_event_artists

Relacion ordenada entre evento y artistas. Permite agenda multiartista sin duplicar la
cabecera comercial.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| id | string | si | ID interno | bea_001 |
| event_id | string | si | Evento | evt_2026_08_22_festival_norte |
| artist_id | string | no | Artista del ABM | artist_virrshi |
| artist_name | string | si | Snapshot legible | Virrshi |
| position | integer | si | Orden visible | 1 |
| created_at | timestamp | si | Auditoria | 2026-08-16T11:00:00Z |

Reglas:

- un artista activo genera `booking_mode=individual`;
- dos o mas artistas generan `booking_mode=shared`;
- el usuario debe tener alcance sobre todos los artistas seleccionados;
- cambiar participantes antes de liquidar puede recalcular el modo;
- luego de iniciar una liquidacion, un cambio de modo requiere permiso de aprobacion y
  auditoria.

## booking_event_deposits

Senias efectivamente recibidas para el evento. Se modelan en filas separadas porque un
show puede tener mas de una entrega, en fechas, monedas, receptores o medios distintos.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| id | bigint | si | ID interno | 102 |
| event_id | bigint | si | Evento asociado | 55 |
| movement_date | date | si | Fecha real de la entrega | 2026-08-16 |
| amount | decimal | si | Importe en moneda original | 500000 |
| currency | string | si | ARS, USD | ARS |
| fx_rate | decimal | no | Tipo de cambio congelado | 1500 |
| received_by | string | si | indyana, artista, empleado, tercero | indyana |
| payment_method | string | si | transferencia, efectivo, otro | transferencia |
| counterparty | string | no | Quien entrego el dinero | Club Norte |
| proof_refs_json | json | si | Comprobantes | [] |
| notes | string | no | Observaciones | Primera seña |
| created_by | string | si | Usuario creador | santiagod |
| created_at | timestamp | si | Auditoria | 2026-08-16T11:00:00Z |

Una seña es caja real vinculada al evento, pero no es ingreso ganado ni cierra la
liquidacion. Al iniciar la liquidacion se reutiliza como movimiento de cobro; no se
vuelve a cargar ni se duplica.

## booking_event_partners

Socios o partes del evento madre.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| event_partner_id | string | si | ID interno | ep_001 |
| event_id | string | si | Evento madre | evt_caserio_2025_08_09 |
| partner_type | string | si | vpo, partner, artist, other | partner |
| partner_id | string | no | Persona/entidad vinculada | person_caserio |
| share_pct | float | no | Porcentaje del resultado del evento | 0.5 |
| settlement_rule | string | no | Regla especial | profit_split |
| notes | string | no | Comentarios |  |

## booking_shows

Prestacion artistica concreta. Puede o no pertenecer a un evento madre.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| show_id | string | si | ID interno | show_2025_08_09_virrshi |
| booking_event_id | bigint | si para nuevas cargas desde Agenda | Cabecera operativa asociada | 55 |
| show_date | date | si | Fecha del show | 2025-08-09 |
| primary_artist_id | string | si | Artista principal | artist_virrshi |
| show_name | string | si | Evento / detalle | Animal - Neuquen |
| venue | string | no | Lugar | Animal |
| city | string | no | Ciudad | Neuquen |
| status | string | si | pendiente, realizado, rendido, aprobado, cancelado, no_cobrado | pendiente |
| tour_manager_id | string | no | TM asignado | person_luciano |
| seller_id | string | no | Vendedor | person_colo |
| booking_rule_id | string | no | Regla default | rule_70_30 |
| notes | string | no | Observaciones |  |

Los shows historicos pueden no tener `booking_event_id` hasta completar el backfill. Toda carga
nueva desde Agenda debe tenerlo. El backfill no altera importes ni estados financieros.

El backfill se ejecuta solo despues de aprobar un informe de conciliacion. Los eventos
compartidos se migran desde su cabecera y sus shows hijos solo se vinculan; nunca se
crea una segunda cabecera por cada hija. Los shows individuales independientes generan
una cabecera. No se recalculan liquidaciones durante esa operacion.

Las madres historicas de Caserio siguen la misma regla: una sola cabecera de Agenda
apunta a `caserio_events`; sus shows VPO hijos conservan el vinculo mediante
`caserio_event_lines.booking_show_id` y no generan cabeceras adicionales.

Cuando la historia no permite reconstruir una seña separada con evidencia suficiente,
la cabecera usa `deposit_status=no_informada`. No se interpreta como ausencia de seña.

## booking_show_participants

Participantes economicos del show.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| participant_id | string | si | ID interno | sp_001 |
| show_id | string | si | Show | show_2025_08_09_virrshi |
| participant_type | string | si | artist, producer, manager, seller, commission_agent, partner | artist |
| party_id | string | no | artist_id o person_id | artist_virrshi |
| is_internal | bool | si | Si pertenece a VPO | true |
| settlement_basis | string | si | gross, net_after_expenses, producer_share, manual | net_after_expenses |
| share_pct | float | no | Porcentaje | 0.7 |
| fixed_amount | float | no | Monto fijo si aplica |  |
| currency | string | no | Moneda del monto fijo | ARS |
| priority_order | int | si | Orden de aplicacion | 20 |
| notes | string | no | Comentarios | 70% artista |

## booking_income_items

Ingresos economicos asociados a show o evento. No necesariamente son caja ya cobrada.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| income_id | string | si | ID interno | inc_001 |
| event_id | string | no | Evento madre | evt_caserio_2025_08_09 |
| show_id | string | no | Show asociado | show_2025_08_09_virrshi |
| artist_id | string | no | Artista relacionado | artist_virrshi |
| income_type | string | si | cachet, deposit, balance, sponsor, door, adjustment | cachet |
| description | string | si | Detalle | Cachet show |
| amount_original | float | si | Monto original | 1000000 |
| currency_original | string | si | ARS, USD | ARS |
| amount_ars | float | si | Monto ARS congelado | 1000000 |
| amount_usd | float | si | Monto USD congelado | 851.06 |
| fx_rate | float | no | ARS por USD | 1175 |
| fx_rate_type | string | no | blue_avg, manual | blue_avg |
| fx_rate_date | date | no | Fecha de tasa | 2026-05-05 |
| expected_or_actual | string | si | expected, actual | expected |
| status | string | si | draft, approved, cancelled | approved |
| source | string | no | agenda, manual, import | manual |
| notes | string | no | Comentarios |  |

## booking_expense_items

Gastos economicos. Pueden o no estar pagados.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| expense_id | string | si | ID interno | exp_001 |
| event_id | string | no | Evento madre | evt_caserio_2025_08_09 |
| show_id | string | no | Show asociado | show_2025_08_09_virrshi |
| artist_id | string | no | Artista imputado | artist_virrshi |
| category | string | si | booking, label, digital, general | booking |
| subcategory | string | no | show, videoclip, marketing, advance | show |
| concept | string | si | Sonido, viaticos, cachet artista | Sonido |
| beneficiary_id | string | no | Persona/proveedor | person_sonidista |
| amount_original | float | si | Monto original | 300000 |
| currency_original | string | si | ARS, USD | ARS |
| amount_ars | float | si | Monto ARS | 300000 |
| amount_usd | float | si | Monto USD | 255.32 |
| fx_rate | float | no | ARS por USD | 1175 |
| fx_rate_type | string | no | blue_avg, manual | blue_avg |
| fx_rate_date | date | no | Fecha FX | 2026-05-05 |
| expense_basis | string | si | show_deductible, artist_recoupable, company_expense, pass_through | show_deductible |
| recoup_source | string | no | show, royalties, ledger, none | show |
| status | string | si | draft, submitted, approved, paid, cancelled | approved |
| notes | string | no | Comentarios |  |

## booking_cash_movements

Movimientos reales de caja. Un ingreso economico puede existir sin caja cobrada y un
movimiento de caja puede liquidar varios conceptos.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| cash_movement_id | string | si | ID interno | cash_001 |
| movement_date | date | si | Fecha del movimiento | 2026-05-05 |
| movement_type | string | si | cash_in, cash_out, transfer, adjustment | cash_in |
| event_id | string | no | Evento asociado | evt_caserio_2025_08_09 |
| show_id | string | no | Show asociado | show_2025_08_09_virrshi |
| artist_id | string | no | Artista relacionado | artist_virrshi |
| amount_original | float | si | Monto original | 500000 |
| currency_original | string | si | ARS, USD | ARS |
| amount_ars | float | si | Monto ARS | 500000 |
| amount_usd | float | si | Monto USD | 425.53 |
| fx_rate | float | no | ARS por USD | 1175 |
| fx_rate_type | string | no | blue_avg, manual | blue_avg |
| payer_id | string | no | Quien paga | promoter_x |
| receiver_id | string | no | Quien recibe | person_tm |
| responsible_id | string | no | Quien carga/rinde | person_tm |
| payment_method | string | no | cash, bank_transfer, other | cash |
| status | string | si | draft, submitted, approved, posted, cancelled | submitted |
| attachment_count | int | no | Cantidad de comprobantes | 2 |
| notes | string | no | Observaciones | Sena cobrada |

## booking_commission_rules

Reglas de comisiones comerciales o especiales.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| commission_rule_id | string | si | ID interno | comm_colo_20 |
| applies_to_type | string | si | seller, manager, commission_agent, partner | seller |
| applies_to_id | string | no | person_id | person_colo |
| artist_id | string | no | Si aplica a un artista especifico | artist_virrshi |
| base | string | si | gross_revenue, net_after_show_expenses, producer_share, event_profit, manual_amount | producer_share |
| percentage | float | no | Porcentaje | 0.2 |
| include_booking_fee_paid_shows | boolean | no | Si la regla cobra tambien sobre shows marcados como `Excluye comision general` | false |
| priority_order | int | no | Orden de cobro en cascada, obligatorio si la regla esta activa y con porcentaje; unico por artista entre reglas activas | 1 |
| fixed_amount | float | no | Monto fijo |  |
| currency | string | no | Moneda monto fijo | ARS |
| legacy_priority_order | int | no | Campo historico de orden si se migra desde modelos viejos | 30 |
| active_from | date | no | Vigencia desde | 2025-08-01 |
| active_to | date | no | Vigencia hasta |  |
| notes | string | no | Comentarios | Comision Colo |

## booking_settlement_runs

Una corrida de liquidacion de un show o evento.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| settlement_run_id | string | si | ID interno | set_001 |
| scope_type | string | si | show, event, period | show |
| scope_id | string | si | show_id/event_id/periodo | show_2025_08_09_virrshi |
| run_at | datetime | si | Fecha de calculo | 2026-05-05T10:00:00 |
| status | string | si | draft, approved, posted, voided | draft |
| created_by | string | no | Usuario | ruben |
| approved_by | string | no | Usuario aprobador |  |
| notes | string | no | Comentarios |  |

## booking_settlement_lines

Lineas resultantes de una liquidacion. Estas son las que alimentan reportes y cuenta
corriente.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| settlement_line_id | string | si | ID interno | line_001 |
| settlement_run_id | string | si | Corrida | set_001 |
| line_type | string | si | income, expense, commission, artist_share, producer_share, adjustment | artist_share |
| beneficiary_type | string | si | artist, company, person, partner | artist |
| beneficiary_id | string | no | ID beneficiario | artist_virrshi |
| source_item_id | string | no | income_id/expense_id/etc | inc_001 |
| base_amount_ars | float | no | Base usada ARS | 700000 |
| base_amount_usd | float | no | Base usada USD | 595.74 |
| percentage | float | no | Porcentaje aplicado | 0.7 |
| amount_ars | float | si | Resultado ARS | 490000 |
| amount_usd | float | si | Resultado USD | 417.02 |
| priority_order | int | si | Orden aplicado | 40 |
| explanation | string | no | Texto auditable | 70% artista sobre neto |

## booking_fx_rates

Cache de dolar blue/manual para booking.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| fx_rate_id | string | si | ID interno | fx_2026_05_05_blue |
| rate_date | date | si | Fecha | 2026-05-05 |
| currency_from | string | si | ARS | ARS |
| currency_to | string | si | USD | USD |
| rate_type | string | si | blue_avg, manual, other | blue_avg |
| buy_rate | float | no | Compra | 1165 |
| sell_rate | float | no | Venta | 1185 |
| avg_rate | float | si | Promedio usado | 1175 |
| source | string | no | API/manual | manual |
| created_at | datetime | si | Fecha carga | 2026-05-05T10:00:00 |
| notes | string | no | Comentarios |  |

## booking_attachments

Comprobantes, fotos y recibos.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| attachment_id | string | si | ID interno | att_001 |
| related_type | string | si | cash_movement, expense, income, show, event | cash_movement |
| related_id | string | si | ID relacionado | cash_001 |
| file_name | string | si | Nombre archivo | comprobante.jpg |
| storage_path | string | si | Ruta bucket/disco | booking/attachments/... |
| mime_type | string | no | image/jpeg, application/pdf | image/jpeg |
| uploaded_by | string | no | Usuario | tm_luciano |
| uploaded_at | datetime | si | Fecha subida | 2026-05-05T10:00:00 |
| verified_by | string | no | Quien valido | ruben |
| verified_at | datetime | no | Fecha validacion |  |
| status | string | si | uploaded, verified, rejected | uploaded |
| notes | string | no | Comentarios |  |

## artist_ledger_entries

Cuenta corriente consolidada por artista. Puede recibir lineas desde booking, royalties,
adelantos, gastos label o ajustes manuales.

| Campo | Tipo | Obligatorio | Descripcion | Ejemplo |
| --- | --- | --- | --- | --- |
| ledger_entry_id | string | si | ID interno | led_001 |
| artist_id | string | si | Artista | artist_virrshi |
| entry_date | date | si | Fecha contable | 2026-05-05 |
| source_module | string | si | booking, royalties, label, manual | booking |
| source_id | string | no | settlement_line_id u otro | line_001 |
| entry_type | string | si | credit_artist, debit_artist, payment, recoup, adjustment | credit_artist |
| description | string | si | Detalle | Share show Animal |
| amount_ars | float | si | Importe ARS, positivo/debito segun convencion | 490000 |
| amount_usd | float | si | Importe USD | 417.02 |
| status | string | si | draft, posted, voided | posted |
| notes | string | no | Comentarios |  |

## Datasets Raw Para Migracion

Para historico conviene conservar copia estructurada de las planillas originales:

- booking_raw_ingresos;
- booking_raw_egresos;
- booking_raw_presentaciones;
- booking_raw_owner_report;
- booking_raw_special_cases.

Estos datasets no deben ser la verdad final. Sirven para trazabilidad y migracion.

## Primer Corte Implementable

Para el MVP tecnico inicial, alcanza con crear:

1. `booking_raw_ingresos`
2. `booking_raw_egresos`
3. `booking_shows`
4. `booking_income_items`
5. `booking_expense_items`
6. `booking_settlement_lines`
7. `booking_fx_rates`

Luego se agregan:

1. rendiciones mobile;
2. cash movements;
3. attachments;
4. event mothers;
5. commission rules avanzadas;
6. artist ledger consolidado con royalties.
