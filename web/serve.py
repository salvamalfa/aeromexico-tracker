"""Serve web/ locally for manual checks and the Playwright tests.

    uv run python -m src.web_export --out web/public/data/v1
    uv run python web/serve.py [port]

Equivalent to ``python -m http.server -d web [port]``; kept as a tiny
script so ``web/README.md`` has one command to point at, and so tests can
import ``serve`` to start/stop a server in-process without shelling out.
"""

from __future__ import annotations

import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent


def serve(port: int = 8000) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(WEB_ROOT))
    with HTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Sirviendo {WEB_ROOT} en http://127.0.0.1:{port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
