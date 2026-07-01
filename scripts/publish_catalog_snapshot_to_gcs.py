from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


BASE = Path(r"C:\royalties_pipeline")
ENV_PATH = BASE / ".env"
MARTS_DIR = BASE / "warehouse" / "marts"
REGISTRY_DIR = BASE / "warehouse" / "registry"

DEFAULT_ITEMS = [
    ("catalog_master.parquet", MARTS_DIR / "catalog_master.parquet", "marts/catalog_master.parquet", True),
    (
        "catalog_release_metadata.parquet",
        MARTS_DIR / "catalog_release_metadata.parquet",
        "marts/catalog_release_metadata.parquet",
        False,
    ),
    ("catalog_status.parquet", REGISTRY_DIR / "catalog_status.parquet", "marts/catalog_status.parquet", False),
]


@dataclass
class PublishItem:
    label: str
    local_path: Path
    object_name: str
    required: bool


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
        description="Publica un snapshot controlado del Catalogo General en Google Cloud Storage.",
    )
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"), help="Bucket GCS.")
    parser.add_argument(
        "--prefix",
        default=os.environ.get("GCS_PREFIX", "marts"),
        help="Prefijo para objetos de marts. Default: marts.",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Ruta al JSON de service account.",
    )
    parser.add_argument("--apply", action="store_true", help="Ejecuta la subida. Sin esto solo muestra dry-run.")
    return parser


def object_with_prefix(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip("/").replace("\\", "/")
    return f"{clean_prefix}/{filename}" if clean_prefix else filename


def collect_items(prefix: str) -> list[PublishItem]:
    items: list[PublishItem] = []
    for label, local_path, default_object, required in DEFAULT_ITEMS:
        filename = default_object.split("/")[-1]
        items.append(
            PublishItem(
                label=label,
                local_path=local_path,
                object_name=object_with_prefix(prefix, filename),
                required=required,
            )
        )
    return items


def catalog_snapshot_summary(path: Path) -> dict[str, object]:
    try:
        import polars as pl

        df = pl.read_parquet(path)
        summary = {
            "rows": df.height,
            "columns": len(df.columns),
        }
        if "amount_usd" in df.columns:
            summary["amount_usd"] = round(float(df.select(pl.col("amount_usd").sum()).item() or 0), 2)
        if "external_release_date" in df.columns:
            summary["with_release_date"] = df.filter(pl.col("external_release_date").is_not_null()).height
        return summary
    except Exception as exc:
        return {"warning": f"No se pudo leer resumen: {exc}"}


def main() -> None:
    load_local_env(ENV_PATH)
    parser = build_parser()
    args = parser.parse_args()

    if not args.bucket:
        parser.error("Falta --bucket o GCS_BUCKET.")

    credentials_path = Path(args.credentials) if args.credentials else None
    if args.apply and (not credentials_path or not credentials_path.exists()):
        parser.error("Falta --credentials o GOOGLE_APPLICATION_CREDENTIALS valido.")

    items = collect_items(args.prefix or "")
    missing_required = [item.local_path for item in items if item.required and not item.local_path.exists()]
    if missing_required:
        parser.error("Faltan archivos requeridos: " + ", ".join(str(path) for path in missing_required))

    print("PUBLISH CATALOG SNAPSHOT TO GCS")
    print(f"Bucket:      {args.bucket}")
    print(f"Prefix:      {args.prefix or '(root)'}")
    print(f"Mode:        {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    master_path = MARTS_DIR / "catalog_master.parquet"
    if master_path.exists():
        print("Catalog snapshot:")
        for key, value in catalog_snapshot_summary(master_path).items():
            print(f"  {key}: {value}")
        print()

    uploadable = []
    for item in items:
        if not item.local_path.exists():
            print(f"SKIP optional missing: {item.local_path}")
            continue

        size_mb = item.local_path.stat().st_size / 1024 / 1024
        print(f"{item.local_path} -> gs://{args.bucket}/{item.object_name} ({size_mb:.2f} MB)")
        uploadable.append(item)

    if not args.apply:
        print()
        print("DRY RUN terminado. Para subir realmente, agrega --apply.")
        return

    from google.cloud import storage

    client = storage.Client.from_service_account_json(str(credentials_path))
    bucket = client.bucket(args.bucket)

    for item in uploadable:
        blob = bucket.blob(item.object_name)
        blob.upload_from_filename(str(item.local_path))
        print(f"UPLOADED gs://{args.bucket}/{item.object_name}")

    print("Listo.")


if __name__ == "__main__":
    main()
