from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


BASE = Path(r"C:\royalties_pipeline")
MARTS_DIR = BASE / "warehouse" / "marts"
ENV_PATH = BASE / ".env"

DEFAULT_FILES = [
    "standardized_raw_all_sources.parquet",
    "song_level_all_sources.parquet",
    "catalog_master.parquet",
    "statement_summary_all_sources.parquet",
    "digital_income_statement_summary.parquet",
    "royalties_dashboard_summary.parquet",
]


@dataclass
class UploadItem:
    local_path: Path
    object_name: str
    size_bytes: int


def load_local_env(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publica los marts finales del pipeline en Google Cloud Storage.",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("GCS_BUCKET"),
        help="Nombre del bucket GCS. Tambien puede venir de GCS_BUCKET.",
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get("GCS_PREFIX", "marts"),
        help="Prefijo/carpeta dentro del bucket. Default: marts.",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Ruta al JSON de service account. Tambien puede venir de GOOGLE_APPLICATION_CREDENTIALS.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta la subida. Sin esto solo muestra un dry-run.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Sube solo estos archivos dentro de warehouse/marts.",
    )
    return parser


def collect_uploads(prefix: str, only: list[str] | None = None) -> list[UploadItem]:
    normalized_prefix = prefix.strip("/").replace("\\", "/")
    uploads = []
    filenames = only or DEFAULT_FILES

    for filename in filenames:
        local_path = MARTS_DIR / filename
        if not local_path.exists():
            raise FileNotFoundError(f"No existe mart requerido: {local_path}")

        object_name = f"{normalized_prefix}/{filename}" if normalized_prefix else filename
        uploads.append(
            UploadItem(
                local_path=local_path,
                object_name=object_name,
                size_bytes=local_path.stat().st_size,
            )
        )

    return uploads


def upload_to_gcs(bucket_name: str, credentials_path: str, uploads: list[UploadItem]) -> None:
    from google.cloud import storage

    client = storage.Client.from_service_account_json(credentials_path)
    bucket = client.bucket(bucket_name)

    for item in uploads:
        blob = bucket.blob(item.object_name)
        blob.upload_from_filename(str(item.local_path))
        print(f"UPLOADED gs://{bucket_name}/{item.object_name}")


def main() -> None:
    load_local_env(ENV_PATH)

    parser = build_parser()
    args = parser.parse_args()

    if not args.bucket:
        parser.error("Falta --bucket o GCS_BUCKET en .env.")

    if args.apply and not args.credentials:
        parser.error("Falta --credentials o GOOGLE_APPLICATION_CREDENTIALS en .env.")

    credentials_path = Path(args.credentials) if args.credentials else Path("(not configured)")
    if args.apply and not credentials_path.exists():
        parser.error(f"No existe credentials JSON: {credentials_path}")

    uploads = collect_uploads(args.prefix or "", args.only)

    print("PUBLISH MARTS TO GCS")
    print(f"Bucket:      {args.bucket}")
    print(f"Prefix:      {args.prefix or '(root)'}")
    print(f"Credentials: {credentials_path}")
    print(f"Mode:        {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    for item in uploads:
        size_mb = item.size_bytes / 1024 / 1024
        print(f"{item.local_path} -> gs://{args.bucket}/{item.object_name} ({size_mb:.2f} MB)")

    if not args.apply:
        print()
        print("DRY RUN terminado. Para subir realmente, agrega --apply.")
        return

    print()
    upload_to_gcs(args.bucket, str(credentials_path), uploads)
    print("Listo.")


if __name__ == "__main__":
    main()
