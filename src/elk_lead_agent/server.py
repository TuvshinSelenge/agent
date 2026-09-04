"""A tiny static file server to make generated HTML reports linkable.

Deploy the ``output/`` directory behind any static host in production; this
helper is a zero-dependency way to serve it (e.g. for local/staging use) so the
"Report öffnen" link in the e-mail resolves to the nicely formatted page.
"""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(directory: str | Path = "output", host: str = "0.0.0.0", port: int = 8000) -> None:
    directory = str(Path(directory).resolve())
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"Serving {directory} at http://{host}:{port}/ (Strg+C zum Beenden)")
    print(f"Report:  http://{host}:{port}/report_latest.html")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        httpd.server_close()
