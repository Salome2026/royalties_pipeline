# Google Cloud Storage Publish

This project publishes only final generated marts to Google Cloud Storage.

## Files Published

The publish script uploads:

- `warehouse/marts/standardized_raw_all_sources.parquet`
- `warehouse/marts/song_level_all_sources.parquet`
- `warehouse/marts/catalog_candidates.parquet`

It does not upload:

- `input_raw/`
- `warehouse/detail/`
- `warehouse/registry/`
- `reports/`
- `exports/`
- `_cleanup_archive/`

## Local Secrets

Credentials must live outside Git:

```text
C:\royalties_pipeline\secrets\gcs_service_account.json
```

The `secrets/` directory is ignored by Git.

## Environment

Copy `.env.example` to `.env` and set:

```text
GCS_BUCKET=vpo-corp-royalties-marts
GCS_PREFIX=marts
GOOGLE_APPLICATION_CREDENTIALS=C:\royalties_pipeline\secrets\gcs_service_account.json
```

## Dry Run

```powershell
python .\scripts\publish_marts_to_gcs.py --bucket vpo-corp-royalties-marts --prefix marts
```

## Upload

```powershell
python .\scripts\publish_marts_to_gcs.py --apply
```

The script is dry-run by default. It only uploads when `--apply` is passed.

