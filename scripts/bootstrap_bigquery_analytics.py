from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "sql" / "bigquery" / "analytics_schema.sql"
DEFAULT_READERS = [
    "vpo-marts-publisher@vpo-corp-royalties.iam.gserviceaccount.com",
    "vpo-royalty-report-job@vpo-corp-royalties.iam.gserviceaccount.com",
]


def executable(name: str) -> str:
    resolved = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not resolved:
        raise RuntimeError(f"No se encontro {name} en PATH.")
    return resolved


def run(command: list[str], *, input_text: str | None = None) -> None:
    subprocess.run(command, cwd=ROOT, check=True, input=input_text, text=True)


def rendered_schema(project: str, dataset: str, location: str) -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8").format(
        project=project,
        dataset=dataset,
        location=location,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea la base analitica de BigQuery en modo sombra.")
    parser.add_argument("--project", default="vpo-corp-royalties")
    parser.add_argument("--dataset", default="royalties_analytics")
    parser.add_argument("--location", default="US")
    parser.add_argument("--reader", action="append", dest="readers")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    readers = args.readers or DEFAULT_READERS
    sql = rendered_schema(args.project, args.dataset, args.location)

    if not args.apply:
        print(f"DRY RUN: {args.project}.{args.dataset} en {args.location}")
        print(f"Readers: {', '.join(readers)}")
        print(f"DDL bytes: {len(sql.encode('utf-8'))}")
        return

    bq = executable("bq")
    gcloud = executable("gcloud")
    run(
        [
            bq,
            f"--project_id={args.project}",
            "query",
            f"--location={args.location}",
            "--use_legacy_sql=false",
        ],
        input_text=sql,
    )
    for reader in readers:
        member = f"serviceAccount:{reader}"
        for role in ["roles/bigquery.jobUser", "roles/bigquery.dataViewer"]:
            run(
                [
                    gcloud,
                    "projects",
                    "add-iam-policy-binding",
                    args.project,
                    f"--member={member}",
                    f"--role={role}",
                    "--condition=None",
                    "--quiet",
                ]
            )
    print(f"READY: {args.project}.{args.dataset}")


if __name__ == "__main__":
    main()
