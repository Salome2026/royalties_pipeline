# Liquidacion individual de regalias

En Reporte de regalias > PDF > Tipo de PDF, `Liquidacion individual del artista`
produce el formato de Indyana suministrado por el usuario el 2026-11-02.
Selecciona exactamente un artista y un periodo por statement. Nombre de cobro,
DNI y correo se entregan vacios, como campos PDF editables e imprimibles.
No se guardan ni se consultan datos personales para rellenarlos automaticamente.

La plantilla mantiene el tamano 842 x 595 pt, logo, empresa, direccion,
encabezados, cinco columnas y colores del original. El activo
`app/royalty_reports/assets/artist_settlement_header.pdf` contiene solo el
encabezado fijo; se eliminaron los importes, el artista, las fechas y los datos
personales del ejemplo. Los titulos largos ocupan varias lineas sin truncarse.
Si no entran todos los temas, se repite el encabezado en las paginas siguientes;
el total y los campos de cobro aparecen solamente al final.

El modo `artist_settlement` reutiliza `royalty_executive` y el contrato vigente
de Cloud Run Jobs, sin migracion ni nuevas tablas. Aplica los mismos permisos
de regalías y contratos a crear, listar, consultar y descargar. WML no admite
este modo. El selector se habilita cuando la API anuncia soporte.

Los pedidos fijan catalogo, contratos, asociados, dashboard y policies igual
que el PDF contractual. El trabajador consulta las versiones congeladas y
reutiliza `analyze_contractual_income` y `allocation_rows`. La liquidacion solo
muestra la parte final del artista seleccionado despues de contratos internos.
El total coincide con el importe individual del PDF contractual para el mismo
pedido. Ese total se distribuye entre temas con la misma regla de centavos,
incluidos ajustes negativos. El neto de cada tema mantiene todo el periodo.

El porcentaje efectivo usa el importe sin redondear dividido por el neto del
tema. El contractual muestra la participacion final del neto establecida por el
contrato aplicable, incluidos contratos internos. Si hay varios porcentajes
aplicables muestra `Variable`; si el neto es cero, el efectivo muestra `-`.
Ante ingresos sin contrato cerrado, identidad asociada o vigencia aplicable,
el trabajo falla con una explicacion: no emite una liquidacion incompleta.

Son regalias devengadas del periodo, como el ejemplo; no calcula saldos luego
de pagos anteriores ni registra una orden de pago en Finanzas.

Validacion: `scripts/qa/qa_artist_settlement.py` comprueba participacion individual,
contratos internos, cambios de vigencia, negativos, conciliacion de centavos,
permisos, entrada API/worker, paginas y campos AcroForm. La muestra visual usa
los datos del PDF de referencia, no una nueva liquidacion de produccion.
