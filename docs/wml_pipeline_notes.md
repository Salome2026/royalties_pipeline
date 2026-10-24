# WML 91230: ámbito aislado de regalías

WML se incorpora como ámbito separado y desactivado por defecto. El único
ingreso económico es la cuenta 91230. La 91231 y la 91355 nunca se suman a
sus importes; los TXT propios de la 91355 aportan evidencia de porcentajes.

## Importe y trazabilidad

El importe del reporte es la base contractual al 100%, antes de aplicar la
tasa del contrato y las participaciones. No significa efectivo cobrado ni
beneficio, y no presupone que esa base sea toda la facturación de Warner.

Por línea se valida `Royalty Base × Sale Units × Share Tracks / Share Total
Tracks`, o `Receipts` cuando el statement informa directamente el ingreso.
La base multiplicada por la tasa informada tiene que reproducir `Royalty
Payable` con diferencia máxima de USD 0,000001. Se conservan tasa, regalía,
base, número de línea, hash y períodos originales. Las devoluciones conservan
su signo. Una tasa inválida, ausencia de base, cuenta ajena o diferencias de
conciliación impiden publicar. No se aplica un multiplicador global de cuatro.

La carga inicial comprende diez semestres, 3.865.402 líneas, base contractual
de USD 3.846.332,7695696163 y regalía informada de USD 977.028,66356013.
No se transforma el anticipo, gastos ni cargos a terceros de los PDF en
movimientos nuevos de ingresos ni obligaciones confirmadas.

## Separación y control

- Datos locales de validación: `warehouse/isolated/wml`, nunca los marts habituales.
- Crudos seleccionados e inmutables: `raw/wml/91230/objects/<sha256>/` en GCS.
- Paquete publicado: `marts/wml/versions/<release_id>/release_manifest.json`.
- BigQuery exclusivo: `royalties_wml`; no se escribe en `royalties_analytics`.
- Configuración, contratos, estados y auditoría: tablas `royalty_workspace*`
  en Cloud SQL, migración `015_wml_isolated_workspace.sql`.

Control de distribuidoras tiene un interruptor específico **Habilitar WML /
Desactivar WML**. El cambio conserva los datos y no lanza ingesta ni reconstruye
BigQuery. WML habilitada permite elegir explícitamente su ámbito en Catálogo,
Contratos máster, Dashboard de regalías y Reportes de regalías. Cada nueva
sesión vuelve a Royalties habituales. Una consulta WML falla si el ámbito está
desactivado o faltan sus datos; nunca toma los marts habituales como reemplazo.

El contexto de cada pedido es independiente. Un mismo ISRC puede tener estados
y contratos distintos en ambos ámbitos. Los reportes congelan ámbito,
generaciones de GCS, política y decisiones del catálogo para reproducirlos
después, incluso si WML se desactiva. Los reportes históricos no se borran.

Localhost también lee la versión WML publicada en GCS. El directorio local de
marts habituales no cambia ese comportamiento. `VPO_WML_LOCAL_ROOT` se reserva
para verificación offline explícita y exige coincidir con el release publicado.
El control muestra los semestres publicados, incluso si hay un análisis local
anterior preparado en la computadora.

## Frecuencia y actualización

El cierre de cada statement se conserva como junio o diciembre (`YYYY-MM`),
con etiqueta H1/H2, inicio del semestre y meses originales de consumo y recibo.
Las alertas son semestrales; el plazo de recepción es configurable de cero a
seis meses, con tres meses iniciales. Se controlan también huecos intermedios.
Mientras WML está desactivada no genera alertas.

**Actualizar WML** solicita un Cloud Run Job exclusivo, configurado con
`VPO_WML_JOB_PROJECT`, `VPO_WML_JOB_LOCATION` y `VPO_WML_JOB_NAME`. Local y cloud
usan ese mismo Job. La preparación local se limita a seleccionar y subir los
TXT con `scripts/stage_wml_cloud_inputs.py --apply`; `--launch` además solicita
el Job, con acceso operativo PostgreSQL configurado.

El Job se ejecuta con `python -m app.wml_job`, un solo task, cuatro CPU, 16 GiB,
timeout de una hora y sin reintentos automáticos. La transformación del detalle
se procesa en bloques de 50.000 líneas para acotar la memoria. Usa el pool operativo global
y el secreto PostgreSQL existente, permiso de escritura limitado al dataset
WML, lectura/escritura GCS e invocación limitada al Job correspondiente.
La imagen debe incluir `sql/`, además de `app/` y `scripts/`.

Los archivos se identifican por contenido. Copias idénticas del mismo semestre
se omiten; dos versiones distintas del mismo semestre bloquean la carga hasta
elegir la vigente. La huella incluye los TXT económicos, evidencia y versiones
de transformación y referencias. Con la misma huella no se reconstruyen datos.
Si cambian, solo se reconstruye WML.

Se publica primero un paquete inmutable, se cargan y concilian detalle y
agregados en BigQuery y, al terminar, una única actualización PostgreSQL
selecciona la versión para ambos lectores. Las consultas BigQuery fijan ese
release. Una carga fallida conserva la versión anterior y el interruptor
permanece en su estado previo, incluido desactivado.

## Referencias por ISRC

Las referencias son un anexo separado; no se unen a filas económicas para
calcular montos ni completan porcentajes del contrato editable.

- **Informado**: porcentaje escrito en el TXT de una cuenta y tipo de uso.
- **Deducido**: porcentaje compatible con la conciliación previa del conjunto
  del tema; la aplicación a una versión o vigencia sigue pendiente.
- **Hipótesis**: escenario sin confirmación suficiente, como seis puntos por
  participante en Los del Espacio. No es un reparto confirmado.

Se muestran porcentaje sobre base 100%, participante/cuenta, tipo de uso,
alcance, documentos, semestres observados y notas. Un semestre observado no
define la vigencia jurídica. Las tasas 25%, 48% y sincronizaciones al 50% se
conservan separadas por tipo de uso, sin extrapolar entre ellas. El 8,333%
deducido de Bipolar conserva esa precisión. Todos los registros tienen
`applies_automatically=false`. Excel y Google Sheets incluyen el anexo
**referencias WML** de los ISRC incluidos en el informe.

## Verificación

`scripts/qa/qa_wml_workspace.py` prueba base por línea, devoluciones, prorrateos,
25/48/50, recibos, correcciones, duplicados, reuso, alertas, aislamiento de
pedidos concurrentes, bloqueo con WML apagada y reportes sin aplicación de
referencias. La prueba de datos reales verifica la conciliación de las
3.865.402 líneas. Se ejecutan además las verificaciones del pool PostgreSQL,
motor de reportes y guardas operativas, más la compilación web.
