"""A tiny on-demand web app: open a page and click a button to run the agent.

Provides:
  GET  /                     control page (buttons + embedded latest report)
  POST /run                  run the orchestrator now (field ``email=1`` also sends the mail)
  GET  /report_latest.html   the latest generated report (and other output files)

Zero extra dependencies (built on http.server) so it runs anywhere the package
is installed. Intended to be exposed on a port the user can reach.
"""

from __future__ import annotations

import html
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Config, load_config
from .orchestrator import Orchestrator
from .runner import write_outputs
from .state import StateStore

_PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ELK Lead Agent</title>
<style>
  body {{ font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin:0; color:#1a1a1a; }}
  header {{ background:#0b5; color:#fff; padding:16px 22px; }}
  header h1 {{ margin:0; font-size:20px; }}
  header p {{ margin:4px 0 0; opacity:.9; font-size:13px; }}
  .bar {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:16px 22px; background:#f4f7f5; border-bottom:1px solid #e2e2e2; }}
  button {{ font-size:15px; font-weight:600; padding:11px 18px; border:none; border-radius:6px; cursor:pointer; }}
  .primary {{ background:#0b5; color:#fff; }}
  .secondary {{ background:#fff; color:#0b5; border:1px solid #0b5; }}
  button:disabled {{ opacity:.6; cursor:wait; }}
  .flash {{ padding:12px 22px; font-size:14px; }}
  .ok {{ background:#e7f7ec; color:#0a5; border-bottom:1px solid #b9e6c7; }}
  .err {{ background:#fdecec; color:#b3261e; border-bottom:1px solid #f5c2c0; }}
  iframe {{ width:100%; border:none; height:calc(100vh - 190px); }}
  .empty {{ padding:40px 22px; color:#666; }}
</style></head>
<body>
  <header>
    <h1>ELK Lead Agent</h1>
    <p>Neue Projekte in Österreich · temporäres Wohnen / Beherbergung · Holz-/Modulbau</p>
  </header>
  <div class="bar">
    <form method="post" action="/run" onsubmit="lock(this)">
      <button class="secondary" type="submit">🔄 Jetzt aktualisieren</button>
    </form>
    <form method="post" action="/run" onsubmit="lock(this)">
      <input type="hidden" name="email" value="1">
      <button class="primary" type="submit">📧 Aktualisieren &amp; per E-Mail senden</button>
    </form>
    <span style="color:#666;font-size:13px;">Empfänger: {recipients}</span>
  </div>
  {flash}
  {body}
  <script>
    function lock(f) {{
      for (const b of f.querySelectorAll('button')) {{ b.disabled = true; b.textContent = '… läuft'; }}
    }}
  </script>
</body></html>
"""


class LeadAgentServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, *, config: Config, output_dir: Path):
        super().__init__(addr, handler)
        self.config = config
        self.output_dir = output_dir


class Handler(BaseHTTPRequestHandler):
    server_version = "ELKLeadAgent/0.1"

    # ---- helpers ----------------------------------------------------------
    @property
    def cfg(self) -> Config:
        return self.server.config  # type: ignore[attr-defined]

    @property
    def out_dir(self) -> Path:
        return self.server.output_dir  # type: ignore[attr-defined]

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _render_page(self, flash: str = "") -> str:
        report = self.out_dir / "report_latest.html"
        if report.exists():
            body = f'<iframe src="/report_latest.html?ts={report.stat().st_mtime_ns}"></iframe>'
        else:
            body = (
                '<div class="empty">Noch kein Report vorhanden. '
                'Klicken Sie auf „Jetzt aktualisieren".</div>'
            )
        recipients = ", ".join(self.cfg.email.recipients) or "(keine konfiguriert)"
        return _PAGE.format(flash=flash, body=body, recipients=html.escape(recipients))

    def _flash(self, params: dict[str, list[str]]) -> str:
        if params.get("ok"):
            msg = params["ok"][0]
            return f'<div class="flash ok">✅ {html.escape(msg)}</div>'
        if params.get("err"):
            return f'<div class="flash err">⚠️ {html.escape(params["err"][0])}</div>'
        return ""

    # ---- routing ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            params = urllib.parse.parse_qs(parsed.query)
            self._send_html(self._render_page(self._flash(params)))
            return
        self._serve_file(path)

    def _serve_file(self, path: str) -> None:
        name = Path(path.lstrip("/")).name  # prevent path traversal
        target = self.out_dir / name
        if not name or not target.is_file():
            self._send_html("<h1>404</h1>", status=404)
            return
        ctype = "text/html; charset=utf-8" if name.endswith(".html") else "application/octet-stream"
        if name.endswith(".json"):
            ctype = "application/json; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/run":
            self._send_html("<h1>404</h1>", status=404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = urllib.parse.parse_qs(raw)
        want_email = bool(form.get("email"))

        try:
            report = Orchestrator(config=self.cfg, state=StateStore(enabled=False)).run(
                persist_state=False
            )
            write_outputs(report, self.out_dir)
            msg = f"Report aktualisiert: {len(report.projects)} Projekte, {len(report.leads)} Leads."
            if want_email:
                self._send_email(report)
                msg += f" E-Mail gesendet an {', '.join(self.cfg.email.recipients)}."
            self._redirect(f"/?ok={urllib.parse.quote(msg)}")
        except Exception as exc:  # noqa: BLE001
            self._redirect(f"/?err={urllib.parse.quote(str(exc))}")

    def _send_email(self, report) -> None:
        # Imported lazily so the web app also works when SMTP isn't configured.
        from .emailer import send_report_email

        send_report_email(report, self.cfg)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter logging
        return


def run_web(
    host: str = "0.0.0.0",
    port: int = 8000,
    output_dir: str | Path = "output",
    config_path: str | Path | None = None,
) -> None:
    config = load_config(config_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    httpd = LeadAgentServer((host, port), Handler, config=config, output_dir=out)
    print(f"ELK Lead Agent Web-UI: http://{host}:{port}/  (Strg+C zum Beenden)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        httpd.server_close()
