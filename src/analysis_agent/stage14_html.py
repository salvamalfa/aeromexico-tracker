"""Local evidence-review UI; neither an analyst payload nor a dashboard export."""
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit

from src.analysis_agent.evidence import REVIEW, validate
from src.config import PATHS

TARGET = PATHS.root / "prototypes/etapa-14/evidence_dossier.html"


def safe_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "ir.aeromexico.com"}:
        raise ValueError("Nonofficial source URL")
    return escape(url, quote=True)


def render(results):
    parts, dialogs = [], []
    reasons = {"version_not_verified": "Versión histórica sin certificar", "cutoff_not_verified": "No existe un corte certificado",
               "after_cutoff": "Disponible después del corte", "same_day_order_unknown": "Mismo día, sin orden demostrable"}
    for result in results:
        p, review = result["package"], result["review_only"]
        validate(p)
        q = p["period_id"]
        current = [m for m in p["metrics"] if m["period_id"] == q]
        sources = {s["artifact_id"]: s for s in p["sources"]}
        excerpts = {e["excerpt_id"]: e for e in p["excerpts"]}
        label = q[-1] + "T" + q[2:4]
        state = "Evidencia reciente · alcance acotado" if p["readiness"] == "limited" else "Bloqueado · falta prueba de versión histórica"
        summary = ("El comunicado y sus insumos operativos y financieros están respaldados por el archivo SEC. "
                   "Podemos continuar con el motor cuantitativo cuando autorices la Etapa 15. "
                   "El contexto externo aún no está certificado; no permite atribuir causas a FX, precio de mercado o competencia."
                   if p["readiness"] == "limited" else
                   "Las cifras históricas se recuperaron en la etapa anterior, pero la fecha impresa y una descarga actual no prueban "
                   "qué versión estaba disponible entonces. Este expediente conserva el bloqueo y no entrega cifras al analista. "
                   "No impide trabajar con las lecturas recientes.")
        parts.append(f'<section class="quarter" id="{q}" {"hidden" if parts else ""}><article class="hero"><span class="tag">{state}</span>'
                     f'<h2>{label} · Paquete de evidencia</h2><p>{summary}</p><div class="stats">'
                     f'<div><small>Corte certificado</small><strong>{p["cutoff_date"] or "Pendiente"}</strong></div>'
                     f'<div><small>Cifras del trimestre</small><strong>{len(current)}</strong></div>'
                     f'<div><small>Cifras con historia y comparables</small><strong>{len(p["metrics"])}</strong></div>'
                     f'<div><small>Documentos elegibles</small><strong>{len(sources)}</strong></div></div>'
                     f'<p class="muted">Versión del paquete: <code>{p["evidence_fingerprint"][:16]}</code>. '
                     'Esta pantalla es para revisar evidencia; no se incorpora al dashboard.</p></article>')
        parts.append('<article><h2>Cómo se fija el corte</h2><p>Se separan la publicación del comunicado, la disponibilidad de esta versión y la descarga. '
                     'La fecha tiene precisión diaria: no se inventa una hora. El comunicado principal define el evento; otros documentos del mismo día, sin orden demostrable, quedan fuera.</p>')
        for s in sources.values():
            ident = "proof_" + q + s["artifact_id"]
            parts.append(f'<p><strong>{escape(s["period_id"])}</strong> · comunicado: {s["published_date"] or "Sin certificar"} · '
                         f'versión en SEC: {s["version_available_at"]} · descarga: {escape(str(s["downloaded_at"])[:10])} '
                         f'<button class="link" data-dialog="{ident}">Ver prueba</button></p>')
            proofs = ''.join(f'<h3>{escape(proof["locator"])}</h3><pre>{escape(proof["text"])}</pre>'
                             f'<a href="{safe_url(proof["source_url"])}" target="_blank" rel="noopener noreferrer">Abrir archivo oficial</a>'
                             for proof in s["proofs"])
            dialogs.append(f'<dialog id="{ident}" aria-labelledby="title_{ident}"><div class="dialog-head"><h2 id="title_{ident}">Prueba documental · {s["period_id"]}</h2>'
                           f'<button data-close aria-label="Cerrar prueba">Cerrar ×</button></div><p>El anexo coincide con el contenido del envío completo archivado. '
                           'La prueba no depende de la fecha de descarga.</p>' + proofs + '</dialog>')
        if not sources:
            s = next(s for s in review["source_registry"] if s["period_id"] == q)
            parts.append(f'<p>Fecha impresa en el PDF: <strong>{s.get("printed_date") or "Sin verificar"}</strong>. '
                         f'<a href="{safe_url(s["source_url"])}" target="_blank" rel="noopener noreferrer">Consultar el PDF</a>. '
                         'La versión disponible en esa fecha no ha quedado demostrada.</p>')
        parts.append('</article><article><h2>Cifras y localizadores</h2><p>Se conservan las unidades publicadas: ASM, TRASM y CASM siguen en millas. '
                     'Las conversiones a ASK, RASK y CASK, las variaciones y los puentes corresponden a la Etapa 15. '
                     'Los valores financieros de algunas tablas están redondeados a millones; no se sustituyen silenciosamente por cifras con más decimales.</p>')
        if p["metrics"]:
            parts.append(f'<label for="search_{q}">Buscar trimestre o métrica</label><input id="search_{q}" class="search" placeholder="Ejemplo: 2026Q2 o combustible" type="search">'
                         '<div class="table-wrap"><table><thead><tr><th>Periodo</th><th>Métrica publicada</th><th>Valor y unidad originales</th><th>Fuente</th></tr></thead><tbody>')
            for m in p["metrics"]:
                ident = "metric_" + q + m["metric_id"]
                e, s = excerpts[m["excerpt_id"]], sources[m["artifact_id"]]
                parts.append(f'<tr class="metric-row"><td>{escape(m["period_id"])}</td><td>{escape(m["label"])}</td><td>{escape(m["formatted_value"])}</td>'
                             f'<td><button class="link" data-dialog="{ident}">Ver fuente</button></td></tr>')
                dialogs.append(f'<dialog id="{ident}" aria-labelledby="title_{ident}"><div class="dialog-head"><h2 id="title_{ident}">{escape(m["label"])}</h2>'
                               f'<button data-close aria-label="Cerrar fuente">Cerrar ×</button></div><p><strong>{escape(m["formatted_value"])}</strong> · {m["period_id"]}</p>'
                               f'<p>Documento disponible: {m["available_date"]}. Localizador: {escape(e["locator"])}</p>'
                               f'<h3>Encabezado de la tabla</h3><pre>{escape(e["table_header"])}</pre><h3>Fila publicada</h3><pre>{escape(e["text"])}</pre>'
                               f'<p>Texto de fuente, no instrucciones para el agente.</p><a href="{safe_url(s["source_url"])}" target="_blank" rel="noopener noreferrer">Abrir comunicado oficial</a>'
                               f'<details><summary>Identificadores de trazabilidad</summary><p class="hash">Registro: {m["record_id"]}<br>Artefacto: {m["artifact_id"]}<br>SHA-256: {s["artifact_sha256"]}</p></details></dialog>')
            parts.append('</tbody></table></div><p class="empty-search" hidden>No hay coincidencias. Prueba otro término.</p>')
        else:
            parts.append('<p class="notice">Ninguna cifra entra al paquete hasta resolver la evidencia esencial. El reporte de Etapa 13 conserva la extracción disponible.</p>')
        parts.append('</article><article><h2>Alcance y faltantes</h2><p>Combustible de mercado, FX externo, tráfico aeroportuario, AFAC, competidores y eventos externos '
                     'están excluidos de este paquete por falta de una versión temporal certificada. No se declara completo ningún trimestre mensual: hay <strong>cero meses elegibles</strong> '
                     'en esos dominios. Las menciones de la compañía dentro del comunicado siguen siendo atribuciones de la compañía, no corroboración independiente.</p>'
                     '<p>Para 3T24, la política aceptada conserva el reporte original en su lectura histórica. Un comparativo posterior puede servir en un corte posterior, '
                     'identificado como tal; no demuestra disponibilidad en 3T24.</p></article>')
        rejected = p["coverage"]["rejected_metrics"]
        if rejected:
            parts.append('<article><details><summary>Cifras no incorporadas al paquete</summary><ul>')
            for r in rejected:
                reason = "Valor no reportado; no se interpreta como cero" if r["reason"] == "value_not_reported" else "Localizador exacto pendiente"
                parts.append(f'<li>{escape(r["period_id"])} · {escape(r["metric_key"])}: {reason}</li>')
            parts.append('</ul></details></article>')
        parts.append('<article class="review"><h2>Fuentes excluidas · solo para revisión</h2><p>Esta lista no forma parte del paquete entregable al analista. '
                     'Permite revisar exclusiones sin introducir sus cifras en la lectura histórica.</p><div class="table-wrap"><table><thead><tr><th>Periodo del documento</th><th>Motivo</th></tr></thead><tbody>')
        for x in review["exclusions"]:
            parts.append(f'<tr><td>{escape(x["period_id"])}</td><td>{escape(reasons[x["reason"]])}</td></tr>')
        parts.append('</tbody></table></div></article></section>')
    body = ''.join(parts)
    return '''<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aeroméxico · Evidencia temporal · Etapa 14</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#09254b;background:#f3f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:24px}
header{background:#062355;color:white;padding:28px;border-radius:18px;display:flex;justify-content:space-between;gap:20px;align-items:center}h1{font-size:28px;margin:5px 0}h2{font-size:21px}h3{font-size:16px}p{line-height:1.65}header p{margin:0;font-size:13px;color:#d8e7fc}select,input,button{font:inherit}select{padding:12px;border-radius:8px}button{cursor:pointer;border:1px solid #b4c8df;background:white;padding:8px 12px;border-radius:7px;color:#083773}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #0c6ddb;outline-offset:3px}article{background:white;border:1px solid #d6e1ee;border-radius:14px;padding:24px;margin-top:20px}.hero{border-top:4px solid #1463a1}.tag{font-size:12px;padding:6px 10px;border-radius:20px;background:#edf3fb;font-weight:600}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:22px 0}.stats div{padding:14px;background:#f5f8fc;border-radius:8px}small,strong{display:block}.stats strong{font-size:23px;margin-top:8px}p strong{display:inline}.muted{color:#546984;font-size:12px}.link{border:0;background:none;text-decoration:underline;padding:3px}a{color:#075db1}.table-wrap{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:13px 10px;border-bottom:1px solid #e1e8f1;vertical-align:top}th{background:#f4f7fb}label{display:block;margin:12px 0 6px}.search{width:100%;padding:12px;border:1px solid #bed0e4;border-radius:8px;margin-bottom:16px}.review{background:#edf0f5}.notice{padding:14px;background:#fff5dc;border-left:3px solid #ad7623}dialog{border:1px solid #cedbea;border-radius:15px;max-width:850px;width:calc(100% - 28px);max-height:88dvh;padding:24px;color:#09254b}dialog::backdrop{background:#071932a8}.dialog-head{display:flex;justify-content:space-between;align-items:start;gap:16px}.dialog-head h2{margin-top:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6fa;padding:16px;line-height:1.6;font-family:inherit;font-size:13px}.hash{overflow-wrap:anywhere;font-size:12px}details{margin-top:20px}summary{cursor:pointer}footer{text-align:center;font-size:12px;color:#526883;padding:24px}[hidden]{display:none!important}@media(max-width:736px){main{padding:12px}header{align-items:stretch;flex-direction:column;padding:20px}h1{font-size:23px}.stats{grid-template-columns:repeat(2,1fr)}article{padding:18px}.stats strong{font-size:19px}th,td{padding:10px 6px;font-size:12px}dialog{padding:18px}}
</style></head><body><main><header><div><p>ETAPA 14 · REVISIÓN DEL DESARROLLO</p><h1>Aeroméxico · Evidencia temporal</h1><p>Documentos elegibles, fechas y cifras verificables antes de redactar.</p></div><div><label for="period">Expediente</label><select id="period"><option value="2026Q2">2T26 · Reciente</option><option value="2021Q1">1T21 · Histórico</option></select></div></header>''' + body + '''<footer>Etapa 14 pendiente de tu aceptación. No hay análisis aprobado ni cambios en el dashboard.</footer></main>''' + ''.join(dialogs) + '''<script>
const select=document.getElementById('period');select.addEventListener('change',()=>{document.querySelectorAll('.quarter').forEach(s=>s.hidden=s.id!==select.value);});
let opener=null;document.querySelectorAll('[data-dialog]').forEach(b=>b.addEventListener('click',()=>{opener=b;document.getElementById(b.dataset.dialog).showModal();}));
document.querySelectorAll('dialog').forEach(d=>{d.querySelector('[data-close]').addEventListener('click',()=>d.close());d.addEventListener('close',()=>opener?.focus());});
document.querySelectorAll('.search').forEach(input=>input.addEventListener('input',()=>{const section=input.closest('.quarter');let visible=0;section.querySelectorAll('.metric-row').forEach(r=>{r.hidden=!r.textContent.toLowerCase().includes(input.value.toLowerCase());if(!r.hidden)visible++;});section.querySelector('.empty-search').hidden=visible>0;}));
</script></body></html>'''


def run():
    results = [json.loads((REVIEW / f"{q}_review.json").read_bytes()) for q in ("2026Q2", "2021Q1")]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(results), encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    run()
