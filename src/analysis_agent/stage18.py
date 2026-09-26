"""Offline consumer integration. Only exact, currently authorized versions enter HTML."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import tempfile

from bs4 import BeautifulSoup
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.executive_summary_html import render_executive_html
from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import integration_flight_payload
from . import lifecycle as flow
from .stage16_html import render as render_review
from .analyst import emphasized


STYLE = """
.narrative-card{background:#fff}
.analysis-context{font-size:13px;line-height:1.7;border-left:3px solid #a8bbd0;padding:12px 16px;margin-top:20px;background:#fafbfc}
.analysis-summary{padding-left:22px;line-height:1.8}
.analysis-summary li{margin:16px 0}
.analysis-actions{display:flex;flex-wrap:wrap;gap:24px;margin-top:20px}
.analysis-actions button,.analysis-dialog .reference{background:none;border:0;color:#073576;font:inherit;cursor:pointer;text-decoration:underline;padding:6px 0}
.analysis-dialog{background:#fff;color:#092654;border:1px solid #c5d4e7;border-radius:16px;padding:0;width:min(940px,calc(100% - 24px));max-height:88dvh}
.analysis-dialog::backdrop{background:#062046aa}
.analysis-dialog .bar{position:sticky;top:0;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 22px;border-bottom:1px solid #d7e2f0}
.analysis-dialog .bar h2{font-size:20px;margin:0}
.analysis-dialog .close{background:white;border:1px solid #b4cae5;border-radius:8px;padding:8px 14px;cursor:pointer}
.analysis-dialog .modal-content{padding:16px 24px;line-height:1.75}
.analysis-dialog .hash,.analysis-dialog blockquote{overflow-wrap:anywhere}
.analysis-dialog blockquote{white-space:pre-wrap;margin:12px 0;padding-left:12px;border-left:3px solid #b4cae5}
.analysis-dialog details{padding:10px;background:#f5f7fa;margin:12px 0;border-radius:8px}
.analysis-dialog summary{cursor:pointer}
.analysis-dialog .evidence-card{border-bottom:1px solid #d7e2f0;padding:16px 0;scroll-margin-top:90px}
.analysis-dialog button:focus-visible,.analysis-actions button:focus-visible{outline:3px solid #b98505;outline-offset:3px}
"""

SCRIPT = """
(()=>{
 const label=document.getElementById('narrative-period');
 const sync=()=>{
   let found=false;
   document.querySelectorAll('[data-analysis-period]').forEach(el=>{
     el.hidden=el.dataset.analysisPeriod!==label.textContent.trim();found=found||!el.hidden;
   });
   document.getElementById('analysis-empty').hidden=found;
   document.querySelectorAll('.analysis-dialog[open]').forEach(d=>d.close());
 };
 new MutationObserver(sync).observe(label,{childList:true,characterData:true,subtree:true});sync();
 document.querySelectorAll('[data-analysis-open]').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.analysisOpen).showModal()));
 document.querySelectorAll('.analysis-dialog [data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
 document.querySelectorAll('.analysis-dialog [data-evidence]').forEach(b=>b.addEventListener('click',()=>{
   const prefix=b.closest('dialog').dataset.prefix,d=document.getElementById(prefix+'evidence');
   if(!d.open)d.showModal();document.getElementById(prefix+'evidence-'+b.dataset.evidence).scrollIntoView({block:'start'});
 }));
 document.querySelectorAll('.analysis-dialog').forEach(d=>d.addEventListener('click',ev=>{
   const r=d.getBoundingClientRect();if(ev.target===d&&(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom))d.close();
 }));
})();
"""


def consumer_html(dashboard, entries, flights=None):
    """Pure renderer; caller must obtain entries under the approval ledger lock."""
    payload = deepcopy(dashboard)

    # Legacy deterministic narratives are not approved analyses.
    def clean(value):
        if isinstance(value, dict):
            for key in list(value):
                if key in {"narrative", "narrative_text", "executive_reading"}:
                    del value[key]
                else:
                    clean(value[key])
        elif isinstance(value, list):
            for item in value:
                clean(item)

    clean(payload)
    page = render_executive_html(payload)
    blocks = []
    dialogs = []
    manifest = []
    seen = set()
    for record, authorized, package, calculations, checks in entries:
        period = authorized["period_id"]
        if period in seen:
            raise ValueError("Multiple versions for one period")
        seen.add(period)
        prefix = "analysis-" + period + "-"
        label = f"{period[-1]}T{period[2:4]}"
        items = []
        for item in authorized["summary_items"]:
            lead = item.get("lead") or ""
            text = item["text"]
            content = emphasized(text, lead, item.get("emphasis", []))
            items.append("<li>" + content + "</li>")
        blocks.append(
            f'<div data-analysis-period="{label}" hidden><h3>{escape(authorized["thesis"])}</h3><ul class="analysis-summary">'
            + "".join(items)
            + f'</ul><div class="analysis-actions"><button data-analysis-open="{prefix}full">▸ Leer análisis completo</button><button data-analysis-open="{prefix}evidence">▸ Ver evidencia</button></div></div>'
        )
        support = BeautifulSoup(render_review(record, checks, package, calculations), "html.parser")
        context = "".join(
            '<aside class="analysis-context">' + escape(t) + "</aside>" for t in authorized.get("context", [])
        )
        blocks[-1] = blocks[-1].replace(
            '<div class="analysis-actions">', context + '<div class="analysis-actions">'
        )
        for name in ("full", "evidence"):
            dialog = support.find("dialog", id=name)
            dialog["class"] = ["analysis-dialog"]
            dialog["data-prefix"] = prefix
            for el in [dialog, *dialog.find_all(id=True)]:
                el["id"] = prefix + el["id"]
            dialog["aria-labelledby"] = prefix + dialog["aria-labelledby"]
            if name == "full":
                dialog.select_one(
                    ".modal-content > .muted"
                ).string = "Análisis aprobado · cifras del expediente al corte"
            dialogs.append(str(dialog))
        manifest.append(
            {
                k: authorized[k]
                for k in (
                    "period_id",
                    "version",
                    "content_hash",
                    "evidence_fingerprint",
                    "approval_event",
                    "audit_hash",
                )
            }
        )
    old = '<p class="analysis-placeholder" id="narrative-copy">Contenido por definir. Aquí irá el output del agente de análisis por trimestre.</p>'
    if page.count(old) != 1:
        raise ValueError("Dashboard integration anchor changed")
    page = page.replace(
        old,
        '<div id="narrative-copy">'
        + "".join(blocks)
        + '<p id="analysis-empty">Análisis pendiente de aprobación para este trimestre.</p></div>',
    )
    page = page.replace("</head>", "<style>" + STYLE + "</style></head>")
    encoded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    from .reader_ui import refine

    flights = integration_flight_payload(build_flight_payload() if flights is None else flights)
    return refine(
        page.replace(
            "</body>",
            "".join(dialogs)
            + '<script type="application/json" id="analysis-manifest">'
            + encoded
            + "</script><script>"
            + SCRIPT
            + "</script></body>",
        ),
        entries,
        flights,
    )


def publish(records, output, dashboard=None, root=flow.ROOT):
    """Validate every record and atomically replace the entire offline dashboard.

    Immutable intent precedes replacement. Retrying after an interruption verifies
    approval again and produces the same content-addressed receipt.
    """
    output = Path(output).resolve()
    root = Path(root)
    dashboard = build_executive_payload() if dashboard is None else dashboard
    with flow.writer(root):
        entries = []
        for record in records:
            authorized = flow.consumer_payload(record, root)
            package, calculations, checks = flow.verified_inputs(record)
            entries.append((record, authorized, package, calculations, checks))
        content = consumer_html(dashboard, entries).encode("utf-8")
        fingerprint = hashlib.sha256(content).hexdigest()
        receipt = {
            "html_sha256": fingerprint,
            "output": str(output),
            "versions": [r["version"] for r in records],
            "approval_events": [e[1]["approval_event"] for e in entries],
        }
        key = flow.digest(receipt)
        store = root / "publications"
        store.mkdir(parents=True, exist_ok=True)
        intent = store / (key + ".intent.json")
        done = store / (key + ".published.json")
        if not intent.exists():
            flow.atomic_json(intent, receipt)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=output.parent, suffix=".html.tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, output)
        finally:
            Path(name).unlink(missing_ok=True)
        if hashlib.sha256(output.read_bytes()).hexdigest() != fingerprint:
            raise ValueError("Published file hash mismatch")
        if not done.exists():
            flow.atomic_json(done, {**receipt, "published_at": datetime.now(timezone.utc).isoformat()})
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish([json.loads(p.read_bytes()) for p in args.record], args.output)))


if __name__ == "__main__":
    main()
