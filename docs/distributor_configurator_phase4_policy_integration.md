# Configurador de distribuidoras - Fase 4

## Objetivo

Conectar el reporte por statement nuevo a la politica de distribuidoras/cuentas,
sin cambiar los numeros ya validados.

La regla de esta fase es:

1. comparar comportamiento actual hardcodeado contra politica;
2. exigir diferencia cero o diferencia explicada;
3. recien despues usar la politica en el reporte productivo nuevo.

## Cambios realizados

### Simulador

El simulador visual de reglas se retiro de la pantalla para mantener el
configurador limpio.

No se borro la logica de negocio: la decision sigue viviendo en:

- `warehouse/registry/distributor_account_policies.json`
- `warehouse/registry/contract_cutoffs.json`
- `warehouse/registry/catalog_status.parquet`

### QA agregado

Se agrego:

- `scripts/qa/qa_statement_policy_vs_current.py`

Este script compara:

- reporte nuevo actual/hardcodeado;
- reporte nuevo proyectado desde politica.

La comparacion se hace por:

- source;
- account;
- artist;
- statement_period;
- total USD;
- marca `has_share_in_out`.

Outputs:

- `reports/qa/statement_policy_vs_current_summary_*.csv`
- `reports/qa/statement_policy_vs_current_diffs_*.csv`
- `reports/qa/statement_policy_vs_current_top_diffs_*.csv`

### Resultado de validacion

Corrida del 2026-05-23:

| Cuenta | Current USD | Policy USD | Diff |
| --- | ---: | ---: | ---: |
| dashgo / mawzrecords | 26373.92 | 26373.92 | 0.00 |
| fuga / indyana_records | 148270.85 | 148270.85 | 0.00 |
| onerpm / gusty_dj | 129307.36 | 129307.36 | 0.00 |
| onerpm / henry_remix | 25199.17 | 25199.17 | 0.00 |
| onerpm / la_nueva_sangre | 46672.58 | 46672.58 | 0.00 |
| onerpm / mawzrecords | 83758.19 | 83758.19 | 0.00 |
| orchard / mawzrecords | 20110.79 | 20110.79 | 0.00 |
| soundon / soundon | 9719.56 | 9719.56 | 0.00 |

Diff total: `0.00`.

## Reporte conectado

`scripts/build_statement_report_from_mart.py` ahora, para `report_version="new"`:

1. lee `distributor_account_policies.json`;
2. lee `contract_cutoffs.json`;
3. arma la vista statement desde esas reglas;
4. si la politica no existe o no devuelve filas, cae al comportamiento anterior
   hardcodeado como fallback tecnico.

El reporte viejo no se modifico.

## Catalogo conectado

Desde 2026-05-24, `scripts/build_catalog_master.py` tambien lee
`distributor_account_policies.json` para separar generacion de transferencias.

La decision no vive en una policy nueva. Usa la misma policy de
distribuidoras/cuentas:

- `catalog_view = true` + `revenue_basis = generation/correction/legacy_generation`
  suma a `catalog_master.amount_usd`;
- `revenue_basis = transfer`, por ejemplo ONErpm `Shares In & Out`, queda fuera
  de `amount_usd`;
- las transferencias se conservan en `transfer_amount_usd`;
- el bruto observado se conserva en `observed_amount_usd`;
- si una fila no matchea ninguna policy por `source/account/source_sheet`, el
  build falla para evitar magia silenciosa.

Tambien se alinearon los song-level simples para que lleven claves compatibles
con la policy:

- FUGA regular: `standard_statement_csv`;
- FUGA correction: `correction_csv`;
- DashGo: `detail`;
- Orchard: `revenue_detail`;
- Altafonte legacy: `legacy_altafonte`;
- SoundOn y ONErpm ya venian con `source_sheet`.

## Reglas cubiertas

### Cuentas propias simples

Entran completas segun statement view:

- FUGA;
- DashGo;
- Orchard / Altafonte;
- SoundOn `my_royalty`;
- ONErpm Henry.

### ONErpm MAWZ

Para reporte nuevo:

- `Masters`: entra como generacion;
- `Shares In & Out`: no entra como generacion;
- shares quedan disponibles para auditoria/caja.

### ONErpm Gusty DJ

Cuenta mixta.

La regla de negocio es fecha contractual. `Motorcito` es evidencia usada para
estimar la fecha.

Se excluye contenido viejo aunque siga generando en statements posteriores.

### ONErpm La Nueva Sangre

Cuenta mixta.

La regla final preferida es release date por obra.

Si existe metadata de lanzamiento y esta habilitada, se usa esa metadata.
Si no, se usa la regla provisoria por corte contractual estimado desde
`Ni Ahi, Ni Aca, Ni Alla`.

## Como validar

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe C:\royalties_pipeline\scripts\qa\qa_statement_policy_vs_current.py
```

Debe dar:

```text
Diff total: 0.00
```

Para generar un reporte nuevo de control:

```powershell
C:\royalties_pipeline\.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
from scripts.build_statement_report_from_mart import build_statement_report_from_mart
build_statement_report_from_mart(
    output_path=Path(r"C:\royalties_pipeline\reports\qa\statement_new_policy_control.xlsx"),
    report_version="new",
)
PY
```

## Proximo paso

La siguiente fase deberia ser visual/operativa:

1. permitir editar politicas desde el Configurador de distribuidoras;
2. correr QA automatico despues de un cambio;
3. mostrar impacto antes/despues antes de guardar como politica activa;
4. documentar cada cambio de regla con fecha, usuario y motivo.
