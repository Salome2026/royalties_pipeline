from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


BASE = Path(r"C:\royalties_pipeline")
CLIENT_SECRET_PATH = BASE / "secrets" / "google_oauth_client.json"
TOKEN_OUTPUT_PATH = BASE / "secrets" / "google_oauth_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def main() -> None:
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(f"No existe OAuth client JSON: {CLIENT_SECRET_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
    )

    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        prompt="consent",
        authorization_prompt_message="Abri esta URL para autorizar VPO Corp: {url}",
    )

    token_payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

    TOKEN_OUTPUT_PATH.write_text(
        json.dumps(token_payload, indent=2),
        encoding="utf-8",
    )

    print("Token OAuth guardado en:")
    print(TOKEN_OUTPUT_PATH)
    print()
    print("Para Render, copia este JSON completo en GOOGLE_OAUTH_TOKEN_JSON.")


if __name__ == "__main__":
    main()
