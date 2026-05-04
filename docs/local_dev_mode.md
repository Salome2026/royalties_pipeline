# VPO Corp - modo local

El modo local sirve para probar reportes y cambios usando la PC, sin pasar por Cloud Run.

## URLs

- Web local: `http://localhost:3000`
- API local: `http://127.0.0.1:8011`
- Produccion: `https://vpo-corp.vercel.app`

## Levantar todo

Desde PowerShell:

```powershell
C:\royalties_pipeline\scripts\start_vpo_local.ps1
```

Esto abre dos ventanas:

- API FastAPI local en puerto `8011`.
- Web Next.js local.

## Levantar por separado

API:

```powershell
C:\royalties_pipeline\scripts\start_vpo_api_local.ps1
```

Web:

```powershell
C:\royalties_pipeline\scripts\start_vpo_web_local.ps1
```

## Datos usados

La API local usa:

```text
C:\royalties_pipeline\warehouse\marts
```

No descarga marts desde Google Cloud Storage mientras `VPO_LOCAL_MARTS_DIR` apunte a esa carpeta.

## Verificacion

```powershell
Invoke-RestMethod http://127.0.0.1:8011/health
```

Debe responder con:

```text
marts_mode = local
```

## Produccion

La web productiva en Vercel sigue usando Cloud Run. No hace falta cambiar nada para mostrar el sistema a terceros.
