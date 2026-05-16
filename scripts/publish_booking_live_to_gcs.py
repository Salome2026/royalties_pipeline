from __future__ import annotations

import argparse
import os
from pathlib import Path


BASE = Path(r"C:\royalties_pipeline")
ENV_PATH = BASE / ".env"
DEFAULT_DB = BASE / "warehouse" / "booking" / "live" / "booking_live.sqlite"
DEFAULT_OBJECT = "booking/live/booking_live.sqlite"


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
        description="Publica la base SQLite live de booking en Google Cloud Storage.",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Ruta local a booking_live.sqlite.")
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"), help="Bucket GCS.")
    parser.add_argument("--object", default=os.environ.get("VPO_BOOKING_GCS_OBJECT", DEFAULT_OBJECT), help="Objeto destino en GCS.")
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Ruta al JSON de service account.",
    )
    parser.add_argument("--apply", action="store_true", help="Ejecuta la subida. Sin esto solo muestra dry-run.")
    return parser


def main() -> None:
    load_local_env(ENV_PATH)
    parser = build_parser()
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"No existe DB local: {db_path}")

    if not args.bucket:
        parser.error("Falta --bucket o GCS_BUCKET.")

    credentials_path = Path(args.credentials) if args.credentials else None
    if args.apply and (not credentials_path or not credentials_path.exists()):
        parser.error("Falta --credentials o GOOGLE_APPLICATION_CREDENTIALS valido.")

    object_name = args.object.strip("/").replace("\\", "/")
    size_mb = db_path.stat().st_size / 1024 / 1024

    print("PUBLISH BOOKING LIVE DB TO GCS")
    print(f"DB:          {db_path}")
    print(f"Bucket:      {args.bucket}")
    print(f"Object:      {object_name}")
    print(f"Size:        {size_mb:.2f} MB")
    print(f"Mode:        {'APPLY' if args.apply else 'DRY RUN'}")

    if not args.apply:
        print()
        print("DRY RUN terminado. Para subir realmente, agrega --apply.")
        return

    from google.cloud import storage

    client = storage.Client.from_service_account_json(str(credentials_path))
    bucket = client.bucket(args.bucket)
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(db_path))
    print()
    print(f"UPLOADED gs://{args.bucket}/{object_name}")


if __name__ == "__main__":
    main()
