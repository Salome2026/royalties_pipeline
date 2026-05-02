from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from google.cloud import storage
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
from pydantic import BaseModel, Field


BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / "scripts"
ENV_PATH = BASE / ".env"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_keyword_royalty_report import build_report, build_report_tables, normalize_keywords  # noqa: E402


def load_local_env(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(ENV_PATH)

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "marts").strip("/")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
GCS_SERVICE_ACCOUNT_JSON = os.environ.get("GCS_SERVICE_ACCOUNT_JSON", "")
VPO_API_KEY = os.environ.get("VPO_API_KEY", "change-me")
VPO_API_CACHE_DIR = Path(os.environ.get("VPO_API_CACHE_DIR", BASE / "cache" / "gcs_marts"))
VPO_API_REPORTS_DIR = Path(os.environ.get("VPO_API_REPORTS_DIR", BASE / "reports" / "api"))
GOOGLE_SHEETS_SHARE_EMAIL = os.environ.get("GOOGLE_SHEETS_SHARE_EMAIL", "").strip()

SONG_FILE = "song_level_all_sources.parquet"
STANDARDIZED_FILE = "standardized_raw_all_sources.parquet"
CATALOG_FILE = "catalog_candidates.parquet"
REQUIRED_MART_FILES = [SONG_FILE, STANDARDIZED_FILE, CATALOG_FILE]


class KeywordReportRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    start_month: str | None = None
    end_month: str | None = None
    mode: Literal["any", "all"] = "any"
    raw_limit: int = Field(default=5000, ge=0, le=50000)
    refresh_cache: bool = False


app = FastAPI(title="VPO Corp Royalties API", version="0.1.0")

GOOGLE_API_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def require_api_key(x_vpo_api_key: str | None) -> None:
    if not VPO_API_KEY or VPO_API_KEY == "change-me":
        raise HTTPException(
            status_code=500,
            detail="VPO_API_KEY is not configured.",
        )

    if x_vpo_api_key != VPO_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")


def gcs_client() -> storage.Client:
    if GCS_SERVICE_ACCOUNT_JSON:
        try:
            service_account_info = json.loads(GCS_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GCS_SERVICE_ACCOUNT_JSON is invalid JSON: {exc}") from exc

        return storage.Client.from_service_account_info(service_account_info)

    if GOOGLE_APPLICATION_CREDENTIALS:
        credentials_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
        if not credentials_path.exists():
            raise HTTPException(status_code=500, detail=f"Credentials file not found: {credentials_path}")

        return storage.Client.from_service_account_json(str(credentials_path))

    raise HTTPException(
        status_code=500,
        detail="Configure GCS_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS.",
    )


def google_credentials(scopes: list[str]):
    if GCS_SERVICE_ACCOUNT_JSON:
        try:
            service_account_info = json.loads(GCS_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GCS_SERVICE_ACCOUNT_JSON is invalid JSON: {exc}") from exc

        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )

    if GOOGLE_APPLICATION_CREDENTIALS:
        credentials_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
        if not credentials_path.exists():
            raise HTTPException(status_code=500, detail=f"Credentials file not found: {credentials_path}")

        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=scopes,
        )

    raise HTTPException(
        status_code=500,
        detail="Configure GCS_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS.",
    )


def object_name(filename: str) -> str:
    return f"{GCS_PREFIX}/{filename}" if GCS_PREFIX else filename


def ensure_marts(refresh_cache: bool = False) -> dict[str, Path]:
    if not GCS_BUCKET:
        raise HTTPException(status_code=500, detail="GCS_BUCKET is not configured.")

    VPO_API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = gcs_client()
    bucket = client.bucket(GCS_BUCKET)

    paths: dict[str, Path] = {}

    for filename in REQUIRED_MART_FILES:
        local_path = VPO_API_CACHE_DIR / filename
        paths[filename] = local_path

        if local_path.exists() and not refresh_cache:
            continue

        blob = bucket.blob(object_name(filename))
        if not blob.exists(client):
            raise HTTPException(status_code=500, detail=f"GCS object not found: gs://{GCS_BUCKET}/{blob.name}")

        blob.download_to_filename(str(local_path))

    return paths


def dataframe_values(dataframe) -> list[list[object]]:
    clean = dataframe.where(dataframe.notna(), "")
    values = [list(clean.columns)]

    for row in clean.astype(object).itertuples(index=False, name=None):
        values.append([value.item() if hasattr(value, "item") else value for value in row])

    return values


def sheet_title(keywords: list[str], start_month: str | None, end_month: str | None) -> str:
    keyword_part = " ".join(keywords)[:60] or "keyword"
    period_part = ""
    if start_month or end_month:
        period_part = f" {start_month or 'start'} to {end_month or 'end'}"
    return f"VPO Royalties - {keyword_part}{period_part}"


def create_google_sheet(
    tables,
    keywords: list[str],
    start_month: str | None,
    end_month: str | None,
) -> str:
    credentials = google_credentials(GOOGLE_API_SCOPES)
    sheets_service = google_build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive_service = google_build("drive", "v3", credentials=credentials, cache_discovery=False)

    sheet_names = list(tables.keys())
    spreadsheet = sheets_service.spreadsheets().create(
        body={
            "properties": {"title": sheet_title(keywords, start_month, end_month)},
            "sheets": [{"properties": {"title": name}} for name in sheet_names],
        },
        fields="spreadsheetId,spreadsheetUrl,sheets.properties",
    ).execute()

    spreadsheet_id = spreadsheet["spreadsheetId"]
    spreadsheet_url = spreadsheet["spreadsheetUrl"]

    for sheet_name, dataframe in tables.items():
        values = dataframe_values(dataframe)
        if not values:
            continue

        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    metadata = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)",
    ).execute()
    sheet_id_by_title = {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in metadata["sheets"]
    }

    requests = []
    for sheet_name, dataframe in tables.items():
        sheet_id = sheet_id_by_title[sheet_name]
        column_count = max(1, len(dataframe.columns))
        requests.extend([
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": column_count,
                    }
                }
            },
        ])

    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()

    if GOOGLE_SHEETS_SHARE_EMAIL:
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={
                "type": "user",
                "role": "writer",
                "emailAddress": GOOGLE_SHEETS_SHARE_EMAIL,
            },
            sendNotificationEmail=False,
        ).execute()

    return spreadsheet_url


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "bucket": GCS_BUCKET,
        "prefix": GCS_PREFIX,
    }


@app.post("/reports/keyword")
def keyword_report(
    request: KeywordReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)

    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    keywords = normalize_keywords(request.keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required.")

    marts = ensure_marts(refresh_cache=request.refresh_cache)

    output_path = build_report(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
        output_dir=VPO_API_REPORTS_DIR,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.post("/reports/google-sheet")
def keyword_google_sheet(
    request: KeywordReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    require_api_key(x_vpo_api_key)

    if request.start_month and request.end_month and request.start_month > request.end_month:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    keywords = normalize_keywords(request.keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required.")

    marts = ensure_marts(refresh_cache=request.refresh_cache)

    tables = build_report_tables(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
    )

    spreadsheet_url = create_google_sheet(
        tables=tables,
        keywords=keywords,
        start_month=request.start_month,
        end_month=request.end_month,
    )

    return {"url": spreadsheet_url}
