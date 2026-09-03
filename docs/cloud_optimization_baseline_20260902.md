# Cloud optimization baseline - 2026-09-02

## Purpose

This document freezes the production state before the cloud optimization work.
It is an operational reference only: no service capacity, application route,
database schema, business data, report policy, or deployment was changed while
creating it.

Snapshot time: `2026-09-02T14:27:59-03:00`.

## Recovery points

- Git repository: clean before this document was created.
- Git commit: `3cf9fe7066f5ae3c548ab562b78c15873044d511`.
- Git remote: `https://github.com/Salome2026/royalties_pipeline.git`.
- Cloud SQL on-demand backup: `1788369855690`.
- Backup description: `Pre cloud optimization baseline 2026-09-02`.
- Backup status: `SUCCESSFUL`.
- Backup interval: `2026-09-02T17:24:15.701Z` to
  `2026-09-02T17:24:56.382Z`.
- Cloud Run immutable ready revision: `vpo-corp-api-00147-lbp`.
- Container image:
  `us-central1-docker.pkg.dev/vpo-corp-royalties/cloud-run-source-deploy/royalties_pipeline/vpo-corp-api:3cf9fe7066f5ae3c548ab562b78c15873044d511`.

No secret value was copied into this snapshot.

## Effective production configuration

### Vercel

- Public application: `https://vpo-corp.vercel.app/`.
- Project name: `vpo-corp`.
- Project ID: `prj_9AMDFe3zlt4IvWG3FlcJeDOMkVEA`.
- Owner ID: `team_YVdoJvG0GP56C1SHsAECfsv6`.

### Cloud Run API

- Project: `vpo-corp-royalties`.
- Region: `us-central1`.
- Service: `vpo-corp-api`.
- CPU: `1`.
- Memory: `2Gi`.
- Container concurrency: `4`.
- Request timeout: `1800` seconds.
- Maximum instances: `1`.
- Minimum instances: not configured; the service can scale to zero.
- Cloud SQL attachment:
  `vpo-corp-royalties:us-central1:vpo-corp-postgres`.
- Service account:
  `vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com`.

The production health response confirmed:

- API status: `ok`.
- Marts mode: `gcs`.
- Operational driver: `postgres`.
- PostgreSQL connection mode: `cloudsql_socket`.
- Direct TCP allowed by the application: `no`.
- Operational database status: `ok`.

### Cloud SQL

- Instance: `vpo-corp-postgres`.
- State: `RUNNABLE`.
- Database: `vpo_corp`.
- PostgreSQL: `16.14`.
- Tier: `db-f1-micro`.
- Storage: `10 GB PD_HDD`.
- Automatic growth: enabled, limit `20 GB`.
- Availability: zonal.
- Automated backups: enabled, retention `7`.
- Deletion protection: enabled.
- Public IPv4 exists, but the application uses the Cloud SQL socket.

### Report queue

- Queue: `vpo-report-jobs`.
- State: `RUNNING`.
- Maximum concurrent dispatches: `1`.
- Maximum dispatch rate: `1/s`.
- Maximum attempts: `1`.

### Cloud Storage

- Bucket: `gs://vpo-corp-royalties-marts`.
- Location: `US`.
- Uniform bucket-level access: enabled.
- Public access prevention: enforced.
- Soft delete: `7` days.
- `reports/jobs/` lifecycle deletion: `30` days.

## Performance baseline

Cloud Run request logs, previous seven days, sampled at snapshot time:

| Metric | Value |
| --- | ---: |
| Requests | 175 |
| Median latency | 0.057 s |
| Average latency | 18.399 s |
| P95 latency | 20.005 s |
| Maximum latency | 1552.063 s |
| HTTP 200 | 107 |
| HTTP 202 | 4 |
| HTTP 429 | 54 |
| HTTP 500 | 9 |

Longest observed requests:

| Route | Time | Status |
| --- | ---: | ---: |
| `POST /reports/jobs/4/execute` | 1552.063 s | 200 |
| `POST /reports/jobs/3/execute` | 771.280 s | 200 |
| `POST /reports/executive` | 373.830 s | 200 |
| `POST /reports/jobs/4/execute` | 102.220 s | 200 |
| `POST /reports/jobs/5/execute` | 82.900 s | 200 |
| `POST /auth/login` | 35.460 s | 200 |

Live probes taken sequentially:

- First API health request after inactivity: `17.175 s`.
- Following four API health requests: `0.525-0.560 s`.
- Three Vercel home requests: `0.155-0.239 s`.

This baseline shows that ordinary requests are fast when capacity is available,
but long report requests occupy the only Cloud Run instance and cause queueing,
HTTP 429 responses, and visible delays in unrelated routes.

## Report witnesses

These existing GCS outputs are frozen as behavioral witnesses. They were not
downloaded, regenerated, or modified.

| Job | Artifact | Bytes | MD5 (base64) | Observed execution |
| --- | --- | ---: | --- | ---: |
| 1 | `regalias_ejecutivo_todas_las_distribuidoras_super_junte_2023_11_a_2026_05_20260828_133600.pdf` | 8,596 | `6Xt2Mk4d1e7grk1VNGQV/A==` | not present in the seven-day request sample |
| 2 | `keyword_royalty_report_flor_alvarez_2025-01_to_2026-07_20260831_115541.xlsx` | 581,279 | `deVwoBJYd9gLBN/sSvuULQ==` | not present in the retained request sample |
| 3 | `keyword_royalty_report_flor_alvarez_20260831_150341.xlsx` | 550,631 | `FlM52r1ZK5HN/fNjPqps2w==` | 771.280 s |
| 4 | `keyword_royalty_report_flor_alvarez_20260831_153420.xlsx` | 594,130 | `RkBHjNOXxrFYukGY3XZzrA==` | 1552.063 s |

## Scope boundary

Step 1 ends with this snapshot. Cloud Run scaling, connection pooling, report
modules, Cloud Run Jobs, Cloud SQL sizing, ingestion, and analytics remain
unchanged and belong to later approved steps.
