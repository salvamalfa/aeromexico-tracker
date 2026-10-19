"""Generate an offline review HTML from the same editorial UI and public inputs."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from scripts.monthly.validate import ROOT, validate_all

WEB = ROOT / "web"
DEFAULT_OUTPUT = ROOT / "prototypes/airline-monthly/septiembre-2026.html"


def build(output: Path = DEFAULT_OUTPUT) -> Path:
    validate_all()
    output = output.resolve()
    # A preview never replaces publication inputs, receipts, or site/.
    if output.suffix != ".html" or (
        output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / "prototypes")
    ):
        raise ValueError("La vista previa debe ser un HTML fuera del código o bajo prototypes/")
    bundle = subprocess.run(
        [str(WEB / "node_modules/.bin/esbuild"), "src/monthly/main.ts", "--bundle",
         "--format=iife", "--target=es2022", "--minify", "--legal-comments=none"],
        cwd=WEB, check=True, capture_output=True, text=True,
    ).stdout
    bundle = re.sub(r"</script", r"<\\/script", bundle, flags=re.IGNORECASE)
    html = (WEB / "monthly.html").read_text(encoding="utf-8")
    for path in ["src/styles/base.css", "src/monthly/monthly.css"]:
        css = (WEB / path).read_text(encoding="utf-8")
        css = re.sub(r"</style", r"<\\/style", css, flags=re.IGNORECASE)
        html = html.replace(f'<link rel="stylesheet" href="{path}">', f"<style>\n{css}\n</style>")
    html = html.replace('<script type="module" src="src/monthly/main.ts"></script>', f"<script>\n{bundle}\n</script>")
    html = html.replace('href="index.html"', 'href="https://salvamalfa.github.io/aeromexico-tracker/"')
    if 'type="module"' in html or '<link rel="stylesheet"' in html:
        raise ValueError("La estructura cambió; quedaron dependencias externas")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build(args.out))


if __name__ == "__main__":
    main()
