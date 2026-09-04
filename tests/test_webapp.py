import http.client
import threading

from elk_lead_agent.config import load_config
from elk_lead_agent.webapp import Handler, LeadAgentServer


def _server(tmp_path):
    srv = LeadAgentServer(("127.0.0.1", 0), Handler, config=load_config(), output_dir=tmp_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, srv.server_address[1]


def test_get_control_page(tmp_path):
    srv, port = _server(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "ELK Lead Agent" in body
        assert "per E-Mail senden" in body
    finally:
        srv.shutdown()


def test_post_run_generates_report(tmp_path):
    srv, port = _server(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("POST", "/run", body="", headers={"Content-Length": "0"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 303
        assert "/?ok=" in resp.getheader("Location")
        # A report file must now exist and be served.
        assert (tmp_path / "report_latest.html").is_file()

        conn.request("GET", "/report_latest.html")
        r2 = conn.getresponse()
        assert r2.status == 200
        assert b"Neue Projekte" in r2.read()
    finally:
        srv.shutdown()


def test_post_run_email_without_smtp_redirects_error(tmp_path, monkeypatch):
    for var in ("SMTP_HOST", "SMTP_FROM", "SMTP_USERNAME", "SMTP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    srv, port = _server(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        body = "email=1"
        conn.request(
            "POST",
            "/run",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 303
        assert "/?err=" in resp.getheader("Location")
    finally:
        srv.shutdown()
