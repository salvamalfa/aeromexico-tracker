"""Build the canonical portable report, apply a scoped Windows fix, verify, promote."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from src.analysis_agent.stage13 import OUTPUT
from src.analysis_agent.stage13_report import artifact
from src.config import PATHS


def run(tools_dir: Path) -> dict:
    source = OUTPUT / "artifact.json"
    source.write_text(json.dumps(artifact(), ensure_ascii=False, indent=2), encoding="utf-8")
    target = PATHS.root / "prototypes/etapa-13/financial_history.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("financial_history.pending.html")
    subprocess.run(["node", str(tools_dir / "build_portable_artifact.mjs"),
                    "--input", str(source), "--output", str(temporary)], check=True)
    html = temporary.read_text(encoding="utf-8")
    # The packaged reader uses 100vw on its top bar; classic Windows scrollbars
    # make that wider than the document. Keep the bar inside its parent instead.
    html = html.replace("</head>", '<style id="stage13-windows-scrollbar-fix">'
                        '.analytics-top-bar{width:100%!important;margin-inline:0!important}'
                        '</style></head>', 1)
    temporary.write_text(html, encoding="utf-8")
    result = subprocess.run(["node", str(tools_dir / "verify_portable_artifact.mjs"),
                             "--html", str(temporary), "--artifact", str(source)],
                            check=True, capture_output=True, text=True, encoding="utf-8")
    receipt = json.loads(result.stdout)
    if not receipt.get("ok"):
        raise ValueError("Portable report verification failed")
    temporary.replace(target)
    receipt["html"] = "prototypes/etapa-13/financial_history.html"
    (OUTPUT / "html_validation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, required=True,
                        help="Installed data-analytics skills/build-report/scripts directory")
    print(json.dumps(run(parser.parse_args().tools_dir), indent=2))
