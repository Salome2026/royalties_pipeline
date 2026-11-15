from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build as google_build
from googleapiclient.errors import HttpError

from scripts.lib.report_presentation import youtube_video_url


GOOGLE_API_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleSheetReportError(RuntimeError):
    pass


def google_credentials(scopes: list[str]):
    ephemeral_json = os.environ.get("GOOGLE_OAUTH_EPHEMERAL_JSON", "")
    oauth_token_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON", "")
    service_account_json = os.environ.get("GCS_SERVICE_ACCOUNT_JSON", "")
    credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    if ephemeral_json:
        try:
            temporary = json.loads(ephemeral_json)
            expiry = datetime.fromisoformat(temporary["expiry"])
            token = temporary["token"]
            if (expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)
                    or not isinstance(token, str) or not token):
                raise ValueError("invalid or expired")
        except (TypeError, ValueError, KeyError) as exc:
            raise GoogleSheetReportError("La autorización temporal de Google Sheets no está vigente.") from exc
        return UserCredentials(token=token, scopes=scopes, expiry=expiry.astimezone(timezone.utc).replace(tzinfo=None))

    if oauth_token_json:
        try:
            token_info = json.loads(oauth_token_json)
        except json.JSONDecodeError as exc:
            raise GoogleSheetReportError(
                f"GOOGLE_OAUTH_TOKEN_JSON is invalid JSON: {exc}"
            ) from exc
        return UserCredentials.from_authorized_user_info(token_info, scopes=scopes)

    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as exc:
            raise GoogleSheetReportError(
                f"GCS_SERVICE_ACCOUNT_JSON is invalid JSON: {exc}"
            ) from exc
        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )

    if credentials_file:
        credentials_path = Path(credentials_file)
        if not credentials_path.exists():
            raise GoogleSheetReportError(f"Credentials file not found: {credentials_path}")
        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=scopes,
        )

    raise GoogleSheetReportError(
        "Configure GOOGLE_OAUTH_TOKEN_JSON, GCS_SERVICE_ACCOUNT_JSON or "
        "GOOGLE_APPLICATION_CREDENTIALS."
    )


def dataframe_values(dataframe) -> list[list[object]]:
    clean = dataframe.where(dataframe.notna(), "")
    values = [list(clean.columns)]
    for row in clean.astype(object).itertuples(index=False, name=None):
        values.append([value.item() if hasattr(value, "item") else value for value in row])
    return values


VALUE_BATCH_MAX_BYTES = 1_800_000
VALUE_BATCH_MAX_ROWS = 10_000
VALUE_WRITE_MIN_INTERVAL_SECONDS = 1.1


def dataframe_value_batches(
    dataframe,
    *,
    max_bytes: int = VALUE_BATCH_MAX_BYTES,
    max_rows: int = VALUE_BATCH_MAX_ROWS,
):
    """Yield contiguous A1 start rows and bounded bodies, without a detail limit."""
    if max_bytes <= 0 or max_rows <= 0:
        raise ValueError("Los límites del bloque deben ser positivos.")

    def rows():
        yield list(dataframe.columns)
        for offset in range(0, len(dataframe.index), VALUE_BATCH_MAX_ROWS):
            # Reuse the original conversion on bounded slices, including nulls,
            # NumPy values and duplicated public headers.
            yield from dataframe_values(dataframe.iloc[offset:offset + VALUE_BATCH_MAX_ROWS])[1:]

    empty_body_bytes = len(json.dumps({"values": []}).encode("utf-8"))
    first_row = 1
    batch = []
    body_bytes = empty_body_bytes
    for row in rows():
        row_bytes = len(json.dumps(row).encode("utf-8"))
        if empty_body_bytes + row_bytes > max_bytes:
            raise GoogleSheetReportError("Una fila supera el tamaño máximo de un bloque de Sheets.")
        separator_bytes = 2 if batch else 0
        if batch and (len(batch) >= max_rows or body_bytes + separator_bytes + row_bytes > max_bytes):
            yield first_row, batch
            first_row += len(batch)
            batch = []
            body_bytes = empty_body_bytes
            separator_bytes = 0
        batch.append(row)
        body_bytes += separator_bytes + row_bytes
    if batch:
        yield first_row, batch


def video_code_link_request(dataframe, sheet_id: int) -> dict | None:
    if not {"Codigo", "Tipo codigo"}.issubset(dataframe.columns):
        return None
    rows = []
    has_links = False
    for code, kind in dataframe[["Codigo", "Tipo codigo"]].itertuples(index=False, name=None):
        url = youtube_video_url(code, kind)
        cell = {"userEnteredFormat": {"textFormat": {"link": {"uri": url}}}} if url else {}
        rows.append({"values": [cell]})
        has_links |= url is not None
    if not has_links:
        return None
    return {"updateCells": {
        "start": {"sheetId": sheet_id, "rowIndex": 1,
                  "columnIndex": list(dataframe.columns).index("Codigo")},
        "rows": rows,
        "fields": "userEnteredFormat.textFormat.link",
    }}


def sheet_title(keywords: list[str], start_month: str | None, end_month: str | None) -> str:
    keyword_part = " ".join(keywords)[:60] or "keyword"
    period_part = ""
    if start_month or end_month:
        period_part = f" {start_month or 'start'} to {end_month or 'end'}"
    return f"VPO Royalties - {keyword_part}{period_part}"


def column_width(column_name: str, dataframe, column_index: int | None = None) -> int:
    lower_name = column_name.lower()
    sample_values = [str(column_name)]
    if column_index is None:
        column_index = next((i for i, name in enumerate(dataframe.columns) if name == column_name), None)
    if column_index is not None:
        sample_values.extend(
            str(value)
            for value in dataframe.iloc[:, column_index].head(80).fillna("").tolist()
        )

    max_len = max((len(value) for value in sample_values), default=10)
    calculated = max_len * 7 + 24
    min_width = 90
    max_width = 220

    if "texto coincidente" in lower_name:
        max_width = 360
        min_width = 180
    elif any(value in lower_name for value in ("tema", "title", "artista", "artist")):
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
    elif lower_name == "tipo de contenido":
        max_width = 220
        min_width = 100
    elif lower_name in {
        "desde",
        "hasta",
        "mes",
        "fuente",
        "cuenta",
        "isrc",
    }:
        max_width = 150
        min_width = 100

    return int(min(max(calculated, min_width), max_width))


GOOGLE_SHEETS_CELL_CAPACITY = 20_000_000
DEFAULT_GRID_ROWS = 1000
DEFAULT_GRID_COLUMNS = 26


def complete_sheet_grid(tables):
    if not tables:
        raise GoogleSheetReportError('No hay hojas para entregar.')
    return {name:{"rowCount":max(DEFAULT_GRID_ROWS,len(frame.index)+1),
                  "columnCount":max(DEFAULT_GRID_COLUMNS,len(frame.columns))}
            for name,frame in tables.items()}


def create_google_sheet(
    tables,
    keywords: list[str],
    start_month: str | None,
    end_month: str | None,
) -> str:
    grid_plan=complete_sheet_grid(tables)
    required=sum(grid['rowCount']*grid['columnCount'] for grid in grid_plan.values())
    if required>GOOGLE_SHEETS_CELL_CAPACITY:
        formatted=lambda value:f'{value:,}'.replace(',','.')
        raise GoogleSheetReportError(
            f'El informe completo necesita {formatted(required)} celdas y Google Sheets admite '
            f'{formatted(GOOGLE_SHEETS_CELL_CAPACITY)}. Elegí Excel para conservar el detalle completo.'
        )
    credentials = google_credentials(GOOGLE_API_SCOPES)
    sheets_service = google_build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive_service = google_build("drive", "v3", credentials=credentials, cache_discovery=False)

    sheet_names = list(tables.keys())
    title = sheet_title(keywords, start_month, end_month)
    drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    share_email = os.environ.get("GOOGLE_SHEETS_SHARE_EMAIL", "").strip()

    if drive_folder_id:
        try:
            drive_file = drive_service.files().create(
                body={
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [drive_folder_id],
                },
                fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            raise GoogleSheetReportError(
                f"Google Drive file create failed in folder {drive_folder_id}: {exc.reason}"
            ) from exc

        spreadsheet_id = drive_file["id"]
        spreadsheet_url = drive_file.get("webViewLink") or (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        )
        try:
            metadata = sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties(sheetId,title)",
            ).execute()
            first_sheet_id = metadata["sheets"][0]["properties"]["sheetId"]
            setup_requests = [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": first_sheet_id, "title": sheet_names[0]},
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
            raise GoogleSheetReportError(
                f"Google Sheets setup failed: {exc.reason}"
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
            raise GoogleSheetReportError(
                f"Google Sheets create failed: {exc.reason}"
            ) from exc
        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = spreadsheet["spreadsheetUrl"]

    metadata = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title,gridProperties)",
    ).execute()
    properties_by_title = {sheet["properties"]["title"]: sheet["properties"] for sheet in metadata["sheets"]}
    grid_requests = []
    for sheet_name, grid in grid_plan.items():
        current = properties_by_title[sheet_name]
        grid_requests.append({"updateSheetProperties": {
            "properties": {"sheetId": current["sheetId"], "gridProperties": grid},
            "fields": "gridProperties(rowCount,columnCount)",
        }})
    # A write whose start row is outside the existing grid is rejected, even
    # though an A1 write can expand it. Reserve the complete grid before blocks.
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": grid_requests},
    ).execute(num_retries=5)

    last_write_started = None
    for sheet_name, dataframe in tables.items():
        for first_row, values in dataframe_value_batches(dataframe):
            if last_write_started is not None:
                remaining = VALUE_WRITE_MIN_INTERVAL_SECONDS - (time.monotonic() - last_write_started)
                if remaining > 0:
                    time.sleep(remaining)
            last_write_started = time.monotonic()
            quoted_name = sheet_name.replace("'", "''")
            try:
                # Retrying the same explicit range with the same body does not
                # append or duplicate rows after an uncertain response.
                request = sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{quoted_name}'!A{first_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                )
                plain = request.body.encode("utf-8") if isinstance(request.body, str) else request.body
                request.body = gzip.compress(plain, mtime=0)
                request.headers["content-encoding"] = "gzip"
                request.headers["content-length"] = str(len(request.body))
                request.execute(num_retries=5)
            except HttpError as exc:
                raise GoogleSheetReportError(
                    f"Google Sheets write failed on {sheet_name}: {exc.reason}"
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
        if sheet_name == "resumen por tema":
            video_links = video_code_link_request(dataframe, sheet_id)
            if video_links:
                requests.append(video_links)
        requests.extend(
            [
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
                                "textFormat": {
                                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                    "bold": True,
                                },
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
            ]
        )
        requests.append(
            {
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
            }
        )

        for idx, column_name in enumerate(dataframe.columns):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": column_width(str(column_name), dataframe, idx)},
                        "fields": "pixelSize",
                    }
                }
            )
            if column_name in amount_headers:
                number_format = {"type": "CURRENCY", "pattern": "$#,##0.00"}
            elif column_name in integer_headers:
                number_format = {"type": "NUMBER", "pattern": "#,##0"}
            else:
                continue
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": idx,
                            "endColumnIndex": idx + 1,
                        },
                        "cell": {"userEnteredFormat": {"numberFormat": number_format}},
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )

    if requests:
        try:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()
        except HttpError as exc:
            raise GoogleSheetReportError(
                f"Google Sheets format failed: {exc.reason}"
            ) from exc

    if share_email:
        try:
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "user", "role": "writer", "emailAddress": share_email},
                sendNotificationEmail=False,
            ).execute()
        except HttpError as exc:
            raise GoogleSheetReportError(
                f"Google Drive share failed for {share_email}: {exc.reason}"
            ) from exc

    return spreadsheet_url
