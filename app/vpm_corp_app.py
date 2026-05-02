from __future__ import annotations

import html
import os
import secrets
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE = Path(r"C:\royalties_pipeline")
SCRIPTS = BASE / "scripts"
REPORTS = BASE / "reports"
ENV_PATH = BASE / ".env"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_keyword_royalty_report import build_report, normalize_keywords  # noqa: E402


def load_local_env(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_local_env(ENV_PATH)

APP_USER = os.environ.get("VPM_USER", "admin")
APP_PASSWORD = os.environ.get("VPM_PASSWORD", "change-me")
APP_HOST = os.environ.get("VPM_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("VPM_PORT", "8000"))

SESSIONS: set[str] = set()


CSS = """
:root {
  color-scheme: light;
  --bg: #f5f7fb;
  --ink: #1d2433;
  --muted: #667085;
  --line: #d8dee9;
  --brand: #17324d;
  --brand-2: #0f766e;
  --panel: #ffffff;
  --danger: #b42318;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
}
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr;
}
header {
  height: 64px;
  background: var(--brand);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
}
.brand {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0;
}
.userbar {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
}
.userbar a { color: #fff; text-decoration: none; opacity: .9; }
main {
  width: min(1180px, calc(100vw - 40px));
  margin: 28px auto 48px;
}
.grid {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  align-items: start;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 22px;
}
h1, h2 {
  margin: 0 0 18px;
  line-height: 1.2;
}
h1 { font-size: 24px; }
h2 { font-size: 18px; }
p { color: var(--muted); line-height: 1.45; margin: 0 0 16px; }
label {
  display: block;
  font-size: 13px;
  font-weight: 700;
  margin: 16px 0 7px;
}
input, select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 11px 12px;
  font-size: 15px;
  background: #fff;
}
.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
button, .button {
  border: 0;
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  background: var(--brand-2);
  color: #fff;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
}
button { width: 100%; margin-top: 20px; }
.button.secondary { background: var(--brand); }
.message {
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 18px;
  background: #ecfdf3;
  border: 1px solid #abefc6;
  color: #05603a;
}
.message.error {
  background: #fef3f2;
  border-color: #fecdca;
  color: var(--danger);
}
.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}
.meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}
.meta div {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  background: #fbfcfe;
}
.meta strong { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}
.login .panel { width: min(420px, 100%); }
@media (max-width: 820px) {
  header { padding: 0 18px; }
  main { width: calc(100vw - 28px); margin-top: 18px; }
  .grid { grid-template-columns: 1fr; }
  .row, .meta { grid-template-columns: 1fr; }
}
"""


def page(title: str, body: str, authenticated: bool = True) -> bytes:
    logout = '<a href="/logout">Salir</a>' if authenticated else ""
    user = html.escape(APP_USER) if authenticated else ""
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">VPM Corp</div>
      <div class="userbar"><span>{user}</span>{logout}</div>
    </header>
    {body}
  </div>
</body>
</html>""".encode("utf-8")


def login_page(error: str = "") -> bytes:
    error_html = f'<div class="message error">{html.escape(error)}</div>' if error else ""
    body = f"""
<div class="login">
  <form class="panel" method="post" action="/login">
    <h1>VPM Corp</h1>
    {error_html}
    <label for="username">Usuario</label>
    <input id="username" name="username" autocomplete="username" required>
    <label for="password">Contrasena</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Ingresar</button>
  </form>
</div>
"""
    return page("VPM Corp", body, authenticated=False)


def dashboard(message: str = "", error: str = "", report_name: str = "") -> bytes:
    message_html = f'<div class="message">{html.escape(message)}</div>' if message else ""
    error_html = f'<div class="message error">{html.escape(error)}</div>' if error else ""
    result_html = ""

    if report_name:
        safe_name = html.escape(report_name)
        result_html = f"""
        <div class="panel">
          <h2>Reporte generado</h2>
          <p>El archivo esta listo para abrir en Excel o importar/subir a Google Sheets.</p>
          <div class="result-actions">
            <a class="button" href="/download?file={safe_name}">Descargar XLSX</a>
          </div>
        </div>
        """

    body = f"""
<main>
  {message_html}
  {error_html}
  <div class="grid">
    <form class="panel" method="post" action="/report">
      <h1>Reporte de royalties</h1>
      <label for="keywords">Palabras clave</label>
      <input id="keywords" name="keywords" placeholder="gusty dj, juli savioli" required>

      <div class="row">
        <div>
          <label for="start_month">Desde</label>
          <input id="start_month" name="start_month" type="month">
        </div>
        <div>
          <label for="end_month">Hasta</label>
          <input id="end_month" name="end_month" type="month">
        </div>
      </div>

      <label for="mode">Coincidencia</label>
      <select id="mode" name="mode">
        <option value="any">Cualquier palabra</option>
        <option value="all">Todas las palabras</option>
      </select>

      <label for="raw_limit">Filas raw maximas</label>
      <input id="raw_limit" name="raw_limit" type="number" min="0" max="50000" value="5000">

      <button type="submit">Generar reporte</button>
    </form>

    <div>
      <div class="panel">
        <h2>Salida</h2>
        <p>El sistema genera un archivo XLSX con hojas separadas, filtros, encabezados fijos, moneda en USD y resumenes listos para importar en Google Sheets.</p>
        <div class="meta">
          <div><strong>Datos</strong>marts nuevos</div>
          <div><strong>Formato</strong>Excel / Google Sheets</div>
          <div><strong>Busqueda</strong>song level + raw sample</div>
          <div><strong>Seguridad</strong>login local</div>
        </div>
      </div>
      {result_html}
    </div>
  </div>
</main>
"""
    return page("VPM Corp | Reportes", body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/login":
            self.respond(HTTPStatus.OK, login_page())
            return

        if parsed.path == "/logout":
            self.logout()
            return

        if parsed.path == "/download":
            if not self.is_authenticated():
                self.redirect("/login")
                return
            self.download(parsed.query)
            return

        if not self.is_authenticated():
            self.redirect("/login")
            return

        self.respond(HTTPStatus.OK, dashboard())

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        data = self.read_form()

        if parsed.path == "/login":
            username = data.get("username", [""])[0]
            password = data.get("password", [""])[0]
            if username == APP_USER and password == APP_PASSWORD:
                token = secrets.token_urlsafe(32)
                SESSIONS.add(token)
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"vpm_session={token}; HttpOnly; SameSite=Lax; Path=/")
                self.end_headers()
                return
            self.respond(HTTPStatus.UNAUTHORIZED, login_page("Usuario o contrasena incorrectos."))
            return

        if not self.is_authenticated():
            self.redirect("/login")
            return

        if parsed.path == "/report":
            self.generate_report(data)
            return

        self.respond(HTTPStatus.NOT_FOUND, b"Not found")

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw)

    def is_authenticated(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie.get("vpm_session")
        return bool(token and token.value in SESSIONS)

    def logout(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie.get("vpm_session")
        if token:
            SESSIONS.discard(token.value)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", "vpm_session=; Max-Age=0; Path=/")
        self.end_headers()

    def generate_report(self, data: dict[str, list[str]]) -> None:
        keywords_raw = data.get("keywords", [""])[0]
        keywords = normalize_keywords([keywords_raw])
        mode = data.get("mode", ["any"])[0]
        start_month = data.get("start_month", [""])[0] or None
        end_month = data.get("end_month", [""])[0] or None

        try:
            raw_limit = int(data.get("raw_limit", ["5000"])[0])
        except ValueError:
            raw_limit = 5000

        raw_limit = max(0, min(raw_limit, 50000))

        if not keywords:
            self.respond(HTTPStatus.BAD_REQUEST, dashboard(error="Ingresa al menos una palabra clave."))
            return

        if mode not in {"any", "all"}:
            mode = "any"

        if start_month and end_month and start_month > end_month:
            self.respond(HTTPStatus.BAD_REQUEST, dashboard(error="El periodo desde no puede ser mayor que hasta."))
            return

        try:
            output_path = build_report(
                keywords=keywords,
                mode=mode,
                raw_limit=raw_limit,
                start_month=start_month,
                end_month=end_month,
            )
        except Exception as exc:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, dashboard(error=f"No se pudo generar el reporte: {exc}"))
            return

        self.respond(
            HTTPStatus.OK,
            dashboard(message="Reporte generado correctamente.", report_name=output_path.name),
        )

    def download(self, query: str) -> None:
        filename = parse_qs(query).get("file", [""])[0]
        path = (REPORTS / filename).resolve()

        if not path.is_file() or REPORTS.resolve() not in path.parents:
            self.respond(HTTPStatus.NOT_FOUND, dashboard(error="No encontre ese reporte."))
            return

        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def respond(self, status: HTTPStatus, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((APP_HOST, APP_PORT), Handler)
    print(f"VPM Corp corriendo en http://{APP_HOST}:{APP_PORT}")
    print(f"Usuario: {APP_USER}")
    print("Para cambiar credenciales: set VPM_USER=... ; set VPM_PASSWORD=...")
    server.serve_forever()


if __name__ == "__main__":
    main()
