# Google Cloud Storage Publish

This project publishes only final generated marts to Google Cloud Storage.
Every complete publish creates an immutable release and activates it by
writing `release_manifest.json` only after all six files are available.

## Files Published

The publish script uploads these files under
`marts/releases/<release_id>/`:

- `warehouse/marts/standardized_raw_all_sources.parquet`
- `warehouse/marts/song_level_all_sources.parquet`
- `warehouse/marts/catalog_master.parquet`
- `warehouse/marts/statement_summary_all_sources.parquet`
- `warehouse/marts/digital_income_statement_summary.parquet`
- `warehouse/marts/royalties_dashboard_summary.parquet`

It also refreshes the canonical `marts/<filename>` objects for older
consumers. The API reads the immutable object names and generations from the
manifest, so it never observes a half-published package.

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
C:\royalties_pipeline\.secrets\gcs_service_account.json
```

The `.secrets/` directory is ignored by Git.

## Environment

Copy `.env.example` to `.env` and set:

```text
GCS_BUCKET=vpo-corp-royalties-marts
GCS_PREFIX=marts
GOOGLE_APPLICATION_CREDENTIALS=C:\royalties_pipeline\.secrets\gcs_service_account.json
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
A complete publish uploads all immutable files before activating a manifest.
From the second release onward, the previous manifest remains active until
canonical compatibility objects are updated and the new manifest is written
last. During the one-time migration, the first complete immutable release is
activated before those compatibility copies so legacy generation polling
cannot observe a mixed package. `--only` updates only the requested canonical
objects and deliberately does not activate a new release.

## API Cache

Set `VPO_MART_MANIFEST_CHECK_SECONDS` to control how often each API instance
checks for a new manifest; the default is 15 seconds. The API stores files
under a directory identified by release and manifest generation. Downloads go
to a unique staging directory, are checked for expected size and valid Parquet
metadata, and become active only after validation. Concurrent requests in one
process share a lock. Existing requests can continue reading the previous
immutable directory while a new release is activated.

If a new release cannot be downloaded or validated, normal requests keep the
last healthy local release and expose the error in `/health` under
`mart_cache`. A forced `refresh_cache=true` fails instead of silently using
the previous release. Before the first manifest exists, the API uses a
compatibility identity derived from the six canonical GCS generations.

Dashboard and Digital Income requests never rebuild summaries in production;
those summaries must be prepared and included in the published release.

Special-report auxiliary marts that are not part of the six-file analytics
package remain individually generation-aware under `cache/auxiliary/`. They do
not change the active release manifest. An auxiliary report still requires its
canonical GCS object to exist; the cache does not synthesize missing inputs.

## Catalog snapshot

The catalog can be published independently from the full marts publish:

```powershell
python .\scripts\publish_catalog_snapshot_to_gcs.py
python .\scripts\publish_catalog_snapshot_to_gcs.py --apply
```

This uploads only:

- `warehouse/marts/catalog_master.parquet`
- `warehouse/marts/catalog_release_metadata.parquet` if present
- `warehouse/registry/catalog_status.parquet` if present

Use this when the web needs a refreshed Catalogo General snapshot without
publishing unrelated local experiments.
