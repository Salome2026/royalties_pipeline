# Identidad Dormun y reapertura por participantes

Autorizacion de Ruben: realinear con produccion actual y publicar solo despues de los controles, conservando los cambios manuales.

Base de integracion: cf02d604682e06f91f6e0715fd1463a7c592b7c3, posterior a la copia ae2c87f del 27/10. Se conservan las nuevas reglas de asociaciones manuales, ingresos sin identificar y las ocho identidades nativas agregadas a produccion. No se cambia el frontend, el configurador, Shares In & Out ni el calculo de reportes.

## Regla obligatoria de identidad

Consultar scripts/lib/catalog_identity_corrections.json antes de agrupar por ISRC. La entrada humana DORMUN-EL-FARSANTE-ISRC-20261027 distingue dos grabaciones:

| Grabacion | ISRC canonico | Evidencia |
| --- | --- | --- |
| El Farsante / Dormun | ARDL12600160 | FUGA/indyana_records, referencia 1001863737555, UPC 8721093907237, video vBW2vx8zlVg |
| Somos 3 / LIT killah y Nicki Nicole | ARDL12400078 | ADA/mawz, UPC 5034644050102 |

No crear un alias global entre los dos ISRC. Las ventas antiguas de ESA grabacion de Dormun con el codigo viejo y las futuras con el nuevo forman una sola identidad. Conservar el codigo informado, el archivo original y la evidencia aplicada. No deduplicar ventas por compartir identidad. Si la evidencia contradice la correccion, detener con error explicito en lugar de mezclar grabaciones.

Aplicacion: lector FUGA, consolidacion, construccion del catalogo, participantes, metadata de lanzamiento y relaciones de video. Los titulos externos de Dormun tampoco deben incorporarse a la ficha de Lit Killah por el ISRC reutilizado. La correccion de identidades no cambia dinero, unidades ni splits.

## Regla obligatoria de revision contractual

La publicacion compara conjuntos canonicos de participantes. Altas o bajas reales reabren los contratos guardados que requieren revision. Alias aprobados, acentos y orden no causan reapertura.

Los integrantes faltantes se precargan SIN porcentaje; se conservan los porcentajes, periodos, asociados y notas existentes. Se respetan exclusiones y eliminaciones deliberadas. El usuario puede asignar porcentaje, cero o eliminar. No hay redistribucion automatica.

Mientras el contrato este abierto NO aplica en nuevos reportes contractuales, sin respaldo oculto de la ultima version cerrada. Los reportes ya congelados siguen usando su snapshot. El dashboard general sigue sin splits.

El evento se conserva en catalog_participant_changes.json dentro del manifiesto inmutable. Tanto API como publicador de linea de comandos usan la misma regla; el Job durable de catalogo reintenta eventos pendientes antes de declarar listo el nuevo dashboard. Las escrituras se serializan y versionan sobre los contratos productivos mas recientes. Repetir el evento no genera nuevas versiones ni vuelve a abrir un contrato ya revisado. WML conserva su circuito independiente.

## Controles de adopcion

- Codigo actual, 314 pruebas y siete grupos frontend correctos, incluido el arranque aislado del proceso automatico.
- 13.075.096 movimientos protegidos celda por celda; sin altas/bajas economicas.
- Dormun: 8.481 filas, USD 410,0552582357718 historicos. Lit Killah/Nicki Nicole: 34.959 filas, USD 19.242,62449649 historicos.
- Catalogo actual 3.124 -> 3.125 fichas: separar dos grabaciones antes agrupadas. Las otras fichas, incluidas las ocho incorporadas posteriormente, se conservan.
- Conciliacion completa en 776 grupos por statement y consumo, con importes, unidades, filas e identidades verificados.
- Cinco tablas BigQuery y ambos snapshots listos conciliados. 25 controles HTTP y seis formularios desktop/movil correctos.
- Ciclo real de reapertura/cierre en PostgreSQL privado, revertido por completo. En la foto inicial habia 259 contratos; ninguna ficha afectada tenia un contrato guardado que reabrir. No se dejan datos falsos para simular ese caso.

## Publicacion controlada

Se prepara un release nuevo, inicialmente inactivo, con los mismos movimientos economicos y la identidad corregida. Los releases anteriores y sus archivos permanecen disponibles para reportes congelados; solo una version conciliada es la activa. No se importan contratos de prueba ni se reemplaza la base operativa.

La activacion requiere codigo y Jobs alineados, conciliacion nueva, comprobacion del manifiesto padre y aplicacion idempotente de la revision sobre el SQL productivo vigente. Se preservan status de catalogo, configuraciones, permisos y cambios manuales. Despues se verifica el Job de catalogo, readiness sin fallback, las dos fichas, contratos y dashboard sin splits.

Evidencia y resultado definitivo: C:/royalties_pipeline/staging/catalogo_lectura/20261028_identity_contract_release. publication.json registra cada fase; certification.json solo se emite cuando la comprobacion productiva final termina correctamente. La copia anterior y sus certificados no se reescriben.
