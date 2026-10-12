#!/usr/bin/env python3
"""Build a one-file offline copy of the existing local review page.

The output embeds the current review UI JavaScript and stylesheet. It contains
no evaluation data; the owner selects a private review JSON file in the page.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
SOURCE = WEB / "review.html"
STYLESHEET = WEB / "src/review/review.css"
ENTRY = WEB / "src/review/main.ts"
ESBUILD = WEB / "node_modules/.bin/esbuild"
DEFAULT_OUTPUT = ROOT / ".state/outputs/chat-evaluations/f2-stage1-blind/review-offline.html"


def _set_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "posix":
        return
    state_root = ROOT / ".state"
    if state_root == path or state_root in path.parents:
        cursor = path
        while True:
            os.chmod(cursor, 0o700)
            if cursor == state_root:
                break
            cursor = cursor.parent
    else:
        os.chmod(path, 0o700)


def build(output: Path = DEFAULT_OUTPUT) -> Path:
    if not SOURCE.is_file() or not STYLESHEET.is_file() or not ENTRY.is_file():
        raise FileNotFoundError("Faltan las fuentes existentes del visor web de revisión")
    if not ESBUILD.is_file():
        raise FileNotFoundError("Falta web/node_modules/.bin/esbuild; ejecuta npm ci en web/")
    bundled = subprocess.run(
        [
            str(ESBUILD), str(ENTRY), "--bundle", "--format=iife", "--target=es2022",
            "--minify", "--legal-comments=none", "--log-level=error",
        ],
        cwd=WEB,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if re.search(r"(?m)^\s*import\s", bundled) or "from\"" in bundled:
        raise ValueError("El bundle todavía contiene imports externos")
    html = SOURCE.read_text(encoding="utf-8")
    css_link = '<link rel="stylesheet" href="src/review/review.css">'
    js_entry = '<script type="module" src="src/review/main.ts"></script>'
    if html.count(css_link) != 1 or html.count(js_entry) != 1:
        raise ValueError("La estructura de review.html cambió; actualiza el paso de inline")
    css = STYLESHEET.read_text(encoding="utf-8")
    # Prevent an inline closing tag from terminating its HTML container.
    bundled = re.sub(r"</script", r"<\\/script", bundled, flags=re.IGNORECASE)
    css = re.sub(r"</style", r"<\\/style", css, flags=re.IGNORECASE)
    html = html.replace(css_link, f"<style>\n{css}\n</style>")
    html = html.replace(js_entry, f"<script>\n{bundled}\n</script>")
    html = html.replace('<meta name="color-scheme" content="light">',
                        '<meta name="color-scheme" content="light">\n  <meta name="offline-review" content="single-file, no-network, local-file-input">')
    if "src/review/" in html or "assets/" in html or "type=\"module\"" in html:
        raise ValueError("El HTML de salida aún contiene dependencias de archivos externos")
    _set_private_directory(output.parent)
    output.write_text(html, encoding="utf-8")
    if os.name == "posix":
        os.chmod(output, 0o600)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = build(args.out)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
