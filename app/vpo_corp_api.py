from __future__ import annotations

import json
import os
import sys
from calendar import monthrange
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Literal

import polars as pl
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from google.cloud import storage
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field


BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / "scripts"
ENV_PATH = BASE / ".env"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_keyword_royalty_report import build_report, build_report_tables, normalize_keywords  # noqa: E402
from build_statement_report_from_mart import build_statement_report_from_summary  # noqa: E402


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
GOOGLE_OAUTH_TOKEN_JSON = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON", "")
VPO_API_KEY = os.environ.get("VPO_API_KEY", "change-me")
VPO_API_CACHE_DIR = Path(os.environ.get("VPO_API_CACHE_DIR", BASE / "cache" / "gcs_marts"))
VPO_API_REPORTS_DIR = Path(os.environ.get("VPO_API_REPORTS_DIR", BASE / "reports" / "api"))
GOOGLE_SHEETS_SHARE_EMAIL = os.environ.get("GOOGLE_SHEETS_SHARE_EMAIL", "").strip()
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()

SONG_FILE = "song_level_all_sources.parquet"
STANDARDIZED_FILE = "standardized_raw_all_sources.parquet"
CATALOG_FILE = "catalog_candidates.parquet"
STATEMENT_SUMMARY_FILE = "statement_summary_all_sources.parquet"
REQUIRED_MART_FILES = [SONG_FILE, STANDARDIZED_FILE, CATALOG_FILE, STATEMENT_SUMMARY_FILE]


class KeywordReportRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    start_month: str | None = None
    end_month: str | None = None
    period_basis: Literal["transaction_month", "statement_period"] = "transaction_month"
    mode: Literal["any", "all"] = "any"
    raw_limit: int = Field(default=5000, ge=0, le=50000)
    refresh_cache: bool = False


class RefreshRequest(BaseModel):
    refresh_cache: bool = False


class StatementReportRequest(BaseModel):
    refresh_cache: bool = False
    min_artist_total_usd: float = Field(default=0.0, ge=0.0, le=1_000_000.0)


ParticipationPreset = Literal["last_month", "last_3_months", "last_year", "all_history", "custom"]


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
    if GOOGLE_OAUTH_TOKEN_JSON:
        try:
            token_info = json.loads(GOOGLE_OAUTH_TOKEN_JSON)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"GOOGLE_OAUTH_TOKEN_JSON is invalid JSON: {exc}") from exc

        return UserCredentials.from_authorized_user_info(token_info, scopes=scopes)

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


def ensure_marts(refresh_cache: bool = False, filenames: list[str] | None = None) -> dict[str, Path]:
    if not GCS_BUCKET:
        raise HTTPException(status_code=500, detail="GCS_BUCKET is not configured.")

    VPO_API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = gcs_client()
    bucket = client.bucket(GCS_BUCKET)

    paths: dict[str, Path] = {}

    for filename in filenames or REQUIRED_MART_FILES:
        local_path = VPO_API_CACHE_DIR / filename
        paths[filename] = local_path

        if local_path.exists() and not refresh_cache:
            continue

        blob = bucket.blob(object_name(filename))
        if not blob.exists(client):
            raise HTTPException(status_code=500, detail=f"GCS object not found: gs://{GCS_BUCKET}/{blob.name}")

        blob.download_to_filename(str(local_path))

    return paths


def shift_month(month: str, delta: int) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    month_index = year * 12 + month_number - 1 + delta
    shifted_year = month_index // 12
    shifted_month = month_index % 12 + 1
    return f"{shifted_year:04d}-{shifted_month:02d}"


def previous_calendar_month(today: date | None = None) -> str:
    current = today or date.today()
    return shift_month(f"{current.year:04d}-{current.month:02d}", -1)


def first_business_day(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    current = date(year, month_number, 1)
    while current.weekday() >= 5:
        current = current.replace(day=current.day + 1)
    return current.isoformat()


def last_business_day(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-", 1))
    current = date(year, month_number, monthrange(year, month_number)[1])
    while current.weekday() >= 5:
        current = current.replace(day=current.day - 1)
    return current.isoformat()


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


def column_width(column_name: str, dataframe) -> int:
    lower_name = column_name.lower()

    sample_values = [str(column_name)]
    if column_name in dataframe.columns:
        sample_values.extend(
            str(value)
            for value in dataframe[column_name].head(80).fillna("").tolist()
        )

    max_len = max((len(value) for value in sample_values), default=10)
    calculated = max_len * 7 + 24

    min_width = 90
    max_width = 220

    if "texto coincidente" in lower_name:
        max_width = 360
        min_width = 180
    elif "tema" in lower_name or "title" in lower_name or "artista" in lower_name or "artist" in lower_name:
        max_width = 260
        min_width = 140
    elif "archivo" in lower_name:
        max_width = 280
        min_width = 160
    elif "generado" in lower_name:
        max_width = 180
        min_width = 130
    elif lower_name in {"ingresos usd", "importe neto"}:
        max_width = 130
        min_width = 115
    elif lower_name in {"unidades", "filas", "filas song level", "filas raw"}:
        max_width = 120
        min_width = 95
    elif lower_name in {"desde", "hasta", "mes", "fuente", "cuenta", "tipo de contenido", "isrc"}:
        max_width = 150
        min_width = 100

    return int(min(max(calculated, min_width), max_width))


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
    title = sheet_title(keywords, start_month, end_month)

    if GOOGLE_DRIVE_FOLDER_ID:
        try:
            drive_file = drive_service.files().create(
                body={
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [GOOGLE_DRIVE_FOLDER_ID],
                },
                fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Drive file create failed in folder {GOOGLE_DRIVE_FOLDER_ID}: {exc.reason}",
            ) from exc

        spreadsheet_id = drive_file["id"]
        spreadsheet_url = drive_file.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

        try:
            metadata = sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties(sheetId,title)",
            ).execute()
            first_sheet_id = metadata["sheets"][0]["properties"]["sheetId"]
            setup_requests = [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": first_sheet_id,
                            "title": sheet_names[0],
                        },
                        "fields": "title",
                    }
                }
            ]
            setup_requests.extend(
                {"addSheet": {"properties": {"title": name}}}
                for name in sheet_names[1:]
            )
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": setup_requests},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets setup failed: {exc.reason}",
            ) from exc
    else:
        try:
            spreadsheet = sheets_service.spreadsheets().create(
                body={
                    "properties": {"title": title},
                    "sheets": [{"properties": {"title": name}} for name in sheet_names],
                },
                fields="spreadsheetId,spreadsheetUrl,sheets.properties",
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets create failed: {exc.reason}",
            ) from exc

        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = spreadsheet["spreadsheetUrl"]

    for sheet_name, dataframe in tables.items():
        values = dataframe_values(dataframe)
        if not values:
            continue

        try:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!A1",
                valueInputOption="USER_ENTERED",
                body={"values": values},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets write failed on {sheet_name}: {exc.reason}",
            ) from exc

    metadata = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)",
    ).execute()
    sheet_id_by_title = {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in metadata["sheets"]
    }

    amount_headers = {
        "amount_usd",
        "song_level_amount_usd",
        "net_amount",
        "Ingresos USD",
        "Importe neto",
    }
    integer_headers = {
        "units",
        "rows",
        "song_level_rows",
        "raw_sample_rows",
        "Unidades",
        "Filas",
        "Filas song level",
        "Filas raw",
    }

    requests = []
    for sheet_name, dataframe in tables.items():
        sheet_id = sheet_id_by_title[sheet_name]
        column_count = max(1, len(dataframe.columns))
        row_count = max(1, len(dataframe.index) + 1)
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

        requests.append({
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    }
                }
            }
        })

        for idx, column_name in enumerate(dataframe.columns):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {
                        "pixelSize": column_width(str(column_name), dataframe),
                    },
                    "fields": "pixelSize",
                }
            })

            if column_name in amount_headers:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": idx,
                            "endColumnIndex": idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })
            elif column_name in integer_headers:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": idx,
                            "endColumnIndex": idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "NUMBER",
                                    "pattern": "#,##0",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })

    if requests:
        try:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Sheets format failed: {exc.reason}",
            ) from exc

    if GOOGLE_SHEETS_SHARE_EMAIL:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": GOOGLE_SHEETS_SHARE_EMAIL,
                },
                sendNotificationEmail=False,
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Drive share failed for {GOOGLE_SHEETS_SHARE_EMAIL}: {exc.reason}",
            ) from exc

    return spreadsheet_url


@app.get("/health")
def health() -> dict[str, str]:
    sheets_auth_mode = "oauth_user" if GOOGLE_OAUTH_TOKEN_JSON else "service_account"
    return {
        "status": "ok",
        "bucket": GCS_BUCKET,
        "prefix": GCS_PREFIX,
        "sheets_auth_mode": sheets_auth_mode,
        "drive_folder_configured": "yes" if GOOGLE_DRIVE_FOLDER_ID else "no",
        "share_email_configured": "yes" if GOOGLE_SHEETS_SHARE_EMAIL else "no",
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

    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE])

    output_path = build_report(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
        output_dir=VPO_API_REPORTS_DIR,
    )

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
    )


@app.post("/reports/statement")
def statement_report(
    request: StatementReportRequest,
    x_vpo_api_key: str | None = Header(default=None),
) -> FileResponse:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[STATEMENT_SUMMARY_FILE])
    VPO_API_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = VPO_API_REPORTS_DIR / f"reporte_ingresos_por_statement_marts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    output_path = build_statement_report_from_summary(
        summary_path=marts[STATEMENT_SUMMARY_FILE],
        output_path=output_path,
        min_artist_total_usd=request.min_artist_total_usd,
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

    marts = ensure_marts(refresh_cache=request.refresh_cache, filenames=[SONG_FILE, STANDARDIZED_FILE])

    tables = build_report_tables(
        keywords=keywords,
        mode=request.mode,
        raw_limit=request.raw_limit,
        start_month=request.start_month,
        end_month=request.end_month,
        period_basis=request.period_basis,
        song_path=marts[SONG_FILE],
        standardized_path=marts[STANDARDIZED_FILE],
    )

    try:
        spreadsheet_url = create_google_sheet(
            tables=tables,
            keywords=keywords,
            start_month=request.start_month,
            end_month=request.end_month,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google Sheet generation failed: {exc}") from exc

    return {"url": spreadsheet_url}


@app.get("/participation/distributors")
def distributor_participation(
    refresh_cache: bool = False,
    preset: ParticipationPreset = "last_year",
    start_month: str | None = None,
    end_month: str | None = None,
    x_vpo_api_key: str | None = Header(default=None),
) -> dict:
    require_api_key(x_vpo_api_key)
    marts = ensure_marts(refresh_cache=refresh_cache, filenames=[SONG_FILE])

    month_bounds = (
        pl.scan_parquet(marts[SONG_FILE])
        .filter(pl.col("transaction_month").is_not_null())
        .select([
            pl.min("transaction_month").alias("min_month"),
            pl.max("transaction_month").alias("max_month"),
        ])
        .collect()
    )

    available_start = month_bounds["min_month"][0]
    available_end = month_bounds["max_month"][0]

    if not available_end:
        return {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "preset": preset,
            "start_month": None,
            "end_month": None,
            "start_date": None,
            "end_date": None,
            "available_start_month": None,
            "available_end_month": None,
            "total_amount_usd": 0.0,
            "items": [],
        }

    report_end_month = previous_calendar_month()

    if preset == "custom":
        effective_start = start_month or available_start
        effective_end = end_month or report_end_month
    elif preset == "last_month":
        effective_start = report_end_month
        effective_end = report_end_month
    elif preset == "last_3_months":
        effective_start = shift_month(report_end_month, -2)
        effective_end = report_end_month
    elif preset == "all_history":
        effective_start = available_start
        effective_end = report_end_month
    else:
        effective_start = shift_month(report_end_month, -11)
        effective_end = report_end_month

    effective_start = max(effective_start, available_start)

    if effective_start > effective_end:
        raise HTTPException(status_code=400, detail="start_month cannot be greater than end_month.")

    df = (
        pl.scan_parquet(marts[SONG_FILE])
        .filter(pl.col("transaction_month").is_not_null())
        .filter(pl.col("transaction_month") >= effective_start)
        .filter(pl.col("transaction_month") <= effective_end)
        .group_by("source")
        .agg(pl.sum("amount_usd").alias("amount_usd"))
        .sort("amount_usd", descending=True)
        .collect()
    )

    total = float(df["amount_usd"].sum()) if df.height else 0.0

    items = []
    for row in df.iter_rows(named=True):
        amount = float(row["amount_usd"] or 0)
        items.append({
            "source": row["source"],
            "amount_usd": amount,
            "percentage": (amount / total * 100) if total else 0,
        })

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "preset": preset,
        "start_month": effective_start,
        "end_month": effective_end,
        "start_date": first_business_day(effective_start),
        "end_date": last_business_day(effective_end),
        "available_start_month": available_start,
        "available_end_month": available_end,
        "total_amount_usd": total,
        "items": items,
    }
