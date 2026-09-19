"""Standalone local editorial review. Never a consumer dashboard export."""
from html import escape
from urllib.parse import urlparse

from .analyst import formatted, lineage, emphasized


def render(record, checks, package, calculations):
    e = lambda value: escape(str(value), quote=True)
    draft = record["draft"]
    claims = {c["claim_id"]: c for c in draft["claims"]}
    nodes = {n["calculation_id"]: n for n in calculations["nodes"]}
    excerpts = {x["excerpt_id"]: x for x in package["excerpts"]}
    sources = {s["artifact_id"]: s for s in package["sources"]}
    labels = {"observed_fact": "Hecho observado", "accounting_decomposition": "Descomposición contable",
              "company_attribution": "Explicación de la compañía", "hypothesis": "Hipótesis / límite"}
    def paragraph(cid):
        text=checks['rendered'][cid];lead=claims[cid].get('lead','')
        body=emphasized(text,lead,claims[cid].get('emphasis',[]))
        return f'<p>{body} <button class="reference" data-evidence="{e(cid)}" aria-label="Ver evidencia de {e(cid)}">Ver evidencia</button></p>'
    summary_html=''.join(paragraph(cid) for cid in draft['summary_claim_ids'])
    if draft.get('summary_format')=='business_bullets_v1':
        summary_html='<ul class="business-summary">'+''.join('<li>'+paragraph(cid)+'</li>' for cid in draft['summary_claim_ids'])+'</ul>'
    summary_html+=''.join('<aside class="analysis-context">'+paragraph(cid)+'</aside>' for cid in draft.get('context_claim_ids',[]))
    def source_block(excerpt_id, span=None):
        x = excerpts[excerpt_id]; s = sources[x["artifact_id"]]
        url = s["source_url"]
        link = f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">Documento oficial ↗</a>' if urlparse(url).scheme == "https" and urlparse(url).hostname in {"www.sec.gov", "sec.gov", "ir.aeromexico.com"} else "Documento archivado"
        return f'<details><summary>{e(x["locator"])} · {e(s["period_id"])} · {link}</summary><p>Disponible: {e(s["version_available_at"])} · {e(s["publication_basis"])}</p><blockquote>{e(span or x["text"])}</blockquote><p class="hash">Artefacto: {e(x["artifact_id"])}<br>SHA-256: {e(s["artifact_sha256"])}<br>Evidencia: {e(excerpt_id)}</p></details>'
    evidence_cards = []
    for cid, claim in claims.items():
        rows, used, source_html = [], set(), []
        bindings = list(claim.get("bindings", {}).values()) + [{"calculation_id": key} for key in claim.get("support_calculation_ids", [])]
        for binding in bindings:
            node = nodes[binding["calculation_id"]]
            if node["calculation_id"] in used:
                continue
            used.add(node["calculation_id"])
            leaves = lineage(node["calculation_id"], package, calculations)
            rows.append(f'<li><strong>{e(node["key"])} · {e(node["period_id"])}</strong>: {e(formatted(node))}<br><span class="hash">{e(node["calculation_id"])}</span><br>Fórmula: {e(node["formula"])}<details><summary>Insumos originales y documentos</summary>' + ''.join(f'<p>{e(m["metric_key"])} · {e(m["period_id"])}: {e(m["formatted_value"])}<br><span class="hash">Registro: {e(m["record_id"])}</span></p>' + source_block(m["excerpt_id"]) for m in leaves) + '</details></li>')
        for xid in claim.get("evidence_ids", []):
            spans = [s["text"] for s in claim.get("support_spans", []) if s["excerpt_id"] == xid]
            source_html.extend(source_block(xid, span) for span in (spans or [None]))
        evidence_cards.append(f'<article class="evidence-card" id="evidence-{e(cid)}"><small>{e(cid)} · {e(labels[claim["type"]])}</small><p>{e(checks["rendered"][cid])}</p><p class="muted">{e(claim["confidence_reason"])}</p><ul>{"".join(rows)}</ul>{"".join(source_html)}</article>')
    detail = ''.join(f'<section><h3>{e(s["title"])}</h3>{"".join(paragraph(cid) for cid in s["claim_ids"])}</section>' for s in draft["sections"])
    period = f'{package["period_id"][-1]}T{package["period_id"][2:4]}'
    html = '''<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lectura trimestral · revisión editorial</title>
<style>
:root{color-scheme:light;font-family:Segoe UI,Arial,sans-serif;color:#092654;background:#f3f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1100px;margin:auto;padding:28px 22px}header{background:#072453;color:white;padding:28px;border-radius:20px;margin-bottom:22px}h1{font-size:27px;margin:8px 0}h2{font-size:27px;line-height:1.3;margin:20px 0}h3{font-size:20px;margin:24px 0 8px}p{line-height:1.75}small,.eyebrow{font-size:12px;letter-spacing:.08em}a{color:#0756ad}.muted{color:#53657c;font-size:13px}.executive{background:#eaf3ff;border:1px solid #b9d6f8;padding:30px;border-radius:18px}.badge{display:inline-block;background:#fff2d9;color:#784a02;border-radius:20px;padding:7px 12px;font-size:12px}.label{display:flex;justify-content:space-between;gap:15px;align-items:center;flex-wrap:wrap}.prose{max-width:870px}.actions{display:flex;gap:24px;flex-wrap:wrap;padding-top:18px;border-top:1px solid #bbd3ef;margin-top:25px}button{font:inherit;cursor:pointer;color:#084c9a}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #e4a300;outline-offset:4px}.opener{border:0;background:transparent;padding:8px 0;font-weight:650}.reference{font-size:12px;border:0;background:transparent;text-decoration:underline;padding:2px 4px}.review{background:white;border:1px solid #d8dfe9;border-radius:16px;padding:24px;margin-top:24px}.review h2{font-size:20px;margin:8px 0}.chips{display:flex;gap:12px;flex-wrap:wrap}.chips span{background:#f0f3f8;padding:8px 12px;border-radius:8px;font-size:13px}dialog{border:1px solid #b6cbe5;border-radius:16px;padding:0;width:min(940px,calc(100% - 24px));max-height:88dvh;color:#092654;background:white}dialog::backdrop{background:#062046aa}dialog .bar{position:sticky;top:0;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#eaf3ff;padding:16px 24px;border-bottom:1px solid #c7dbf4;z-index:1}.bar h2{font-size:20px;margin:0}.close{border:1px solid #b4cae5;border-radius:8px;background:white;padding:8px 14px}.modal-content{padding:10px 28px 28px}.evidence-card{border-bottom:2px solid #dee7f1;padding:22px 0;scroll-margin-top:90px}.evidence-card small{color:#4a6281}details{margin:12px 0;padding:10px;background:#f4f7fb;border-radius:8px}summary{cursor:pointer;line-height:1.6}blockquote{margin:12px 0;padding-left:14px;border-left:3px solid #99b8df;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}.hash{font-size:11px;overflow-wrap:anywhere;color:#64758a}li{line-height:1.7;margin-bottom:12px}footer{padding:22px 0;font-size:12px;color:#60728b}@media(max-width:500px){main{padding:14px 12px}header,.executive,.review{padding:20px}h1{font-size:23px}h2{font-size:22px}.modal-content{padding:10px 18px 22px}dialog .bar{padding:14px}.actions{gap:10px;flex-direction:column;align-items:flex-start}}
</style></head><body><main>'''
    html += f'<header><div class="eyebrow">AEROMÉXICO TRACKER · ETAPA 16</div><h1>Primera lectura para tu revisión</h1><p>Del dato validado a una interpretación del negocio.</p></header><section class="executive" id="executive"><div class="label"><small>PROPUESTA PARA EL DASHBOARD · LECTURA EJECUTIVA</small><span class="badge">Borrador · sin auditoría ni aprobación</span></div><p class="muted">{e(period)} · Corte: {e(package["cutoff_date"])} · Versión: {e(record["version"][:12])} · Cobertura acotada</p><div class="prose"><h2>{e(checks["rendered"][draft["thesis_claim_id"]])}</h2><button class="reference" data-evidence="{e(draft["thesis_claim_id"])}">Evidencia de la tesis</button>{summary_html}</div><div class="actions"><button class="opener" data-open="full">▸ Leer análisis completo</button><button class="opener" data-open="evidence">▸ Ver evidencia</button></div></section>'
    html += f'<aside class="review"><small>SOLO REVISIÓN DEL AGENTE · NO VA AL DASHBOARD</small><h2>Qué revisar en esta versión</h2><p>El fondo azul identifica el bloque propuesto para el dashboard y sus ventanas de análisis y evidencia. Esta área blanca pertenece al proceso de construcción.</p><p>Comenta en Codex si la tesis representa bien el trimestre, qué explicación cambiarías y cuánto detalle te resulta útil. Aceptar esta etapa permite desarrollar el auditor; todavía no aprueba este análisis para incorporarlo al dashboard.</p><div class="chips"><span>{checks["summary_words"]} palabras de resumen</span><span>{checks["detail_words"]} palabras de detalle</span><span>{checks["claims"]} afirmaciones con referencias</span><span>Controles mecánicos: correctos</span></div><p class="muted">La revisión automática comprueba referencias y cifras. La auditoría independiente del respaldo semántico y la causalidad corresponde a la siguiente etapa. Las diferencias de conciliación y de redondeo siguen visibles en metodología.</p><p class="hash">Versión íntegra: {e(record["version"])}<br>Paquete: {e(package["package_id"])}<br>Cálculos: {e(calculations["calculation_fingerprint"])}<br>Modelo: identificador no disponible en el entorno. Estado: draft.</p></aside>'
    html += f'<dialog id="full" aria-labelledby="full-title"><div class="bar"><h2 id="full-title">Análisis completo · {e(period)}</h2><button class="close" data-close>Cerrar ✕</button></div><div class="modal-content"><p class="muted">Borrador para revisión · cifras calculadas desde el expediente al corte</p>{detail}</div></dialog><dialog id="evidence" aria-labelledby="evidence-title"><div class="bar"><h2 id="evidence-title">Evidencia por afirmación</h2><button class="close" data-close>Cerrar ✕</button></div><div class="modal-content"><p class="muted">Documentos y datos incluidos en el paquete temporal. Los enlaces oficiales son opcionales; los fragmentos se pueden consultar sin conexión.</p>{"".join(evidence_cards)}</div></dialog>'
    html += '''<footer>Expediente local de revisión · Ningún contenido incorporado al dashboard.</footer></main><script>
document.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.open).showModal()));
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
document.querySelectorAll('[data-evidence]').forEach(b=>b.addEventListener('click',()=>{const d=document.getElementById('evidence');d.showModal();document.getElementById('evidence-'+b.dataset.evidence).scrollIntoView({block:'start'});}));
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',ev=>{if(ev.target===d){const r=d.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)d.close();}}));
</script></body></html>'''
    return html
