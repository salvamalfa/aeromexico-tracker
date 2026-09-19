"""Local review of calculations and their evidence graph."""
from html import escape
import json
from pathlib import Path

from src.analysis_agent.quantitative import OUTPUT
from src.analysis_agent.stage14_html import safe_url
from src.config import PATHS


def run():
    result = json.loads((OUTPUT / "calculations.json").read_bytes())
    package = json.loads((PATHS.root / "analysis_runs/evidence" / (result["package_id"] + ".json")).read_bytes())
    nodes = {n["calculation_id"]: n for n in result["nodes"]}
    metrics = {m["metric_id"]: m for m in package["metrics"]}
    excerpts = {e["excerpt_id"]: e for e in package["excerpts"]}
    sources = {s["artifact_id"]: s for s in package["sources"]}
    def lineage(id, seen=None):
        seen = set() if seen is None else seen
        if id in seen:
            return ""
        seen.add(id)
        if id in metrics:
            m = metrics[id];e = excerpts[m["excerpt_id"]];s = sources[m["artifact_id"]]
            return f'<li><strong>{escape(m["period_id"] + " · " + m["label"])}</strong>: {escape(m["formatted_value"])}<p>{escape(e["locator"])}</p><pre>{escape(e["text"])}</pre><a href="{safe_url(s["source_url"])}" target="_blank" rel="noopener noreferrer">Documento oficial</a></li>'
        n = nodes[id]
        return f'<li><strong>{escape(n["key"])}</strong> · {escape(n["formatted_value"])}<p>{escape(n["formula"])}</p><ul>' + ''.join(lineage(i, seen) for i in n["input_ids"]) + '</ul></li>'
    dialogs = []
    emitted = set()
    def button(n):
        id = n["calculation_id"]
        if id in emitted:
            return f'<button data-dialog="{id}">Ver cálculo</button>'
        emitted.add(id)
        dialogs.append(f'<dialog id="{id}" aria-label="Fórmula y fuentes"><button class="close">Cerrar ×</button><h2>Fórmula e insumos</h2><ul>{lineage(id)}</ul></dialog>')
        return f'<button data-dialog="{id}">Ver cálculo</button>'
    body = '<header><small>ETAPA 15 · REVISIÓN DEL DESARROLLO</small><h1>2T26 · Motor cuantitativo</h1><p>Cálculos precomputados sobre la versión de evidencia aceptada. No es una lectura redactada ni contenido publicado en el dashboard.</p></header>'
    body += '<article><h2>Qué puedes revisar</h2><p>Conversiones de millas a kilómetros, cambios QoQ/YoY contra periodos calendario exactos y un puente de variación del spread. Cada cálculo abre su fórmula y llega hasta el documento.</p><p><strong>El spread RASK−CASK no es el margen operativo ni el margen EBITDAR.</strong> El costo efectivo del combustible no es un precio de mercado, y el resto del costo unitario es un residual sin explicación causal identificada.</p></article>'
    for b in result["bridges"]:
        body += f'<article><h2>Cambio del spread · {b["comparison"]}</h2><p>Comparación con {b["base_period"]}. Contribuciones en centavos USD por ASK.</p><table><tr><th>Componente</th><th>Contribución al cambio</th><th>Detalle</th></tr>'
        labels = ['Cambio de RASK', 'Cambio del costo de combustible por ASK (signo invertido)', 'Cambio del resto del CASK (signo invertido; residual)']
        for label, id in zip(labels,b["contribution_ids"]):
            n = nodes[id];body += f'<tr><td>{label}</td><td>{n["value"]:+.3f}</td><td>{button(n)}</td></tr>'
        total = nodes[b["total_id"]]
        body += f'<tr><td><strong>Cambio total del spread</strong></td><td><strong>{total["value"]:+.3f}</strong></td><td>{button(total)}</td></tr></table><p>La suma reconcilia numéricamente. Este puente no aísla contribuciones de FX, coberturas, rutas o eficiencia.</p></article>'
    for b in result["identity_bridges"]:
        title = 'Ingresos: capacidad y monetización por ASK' if b['name']=='revenue' else 'Combustible: consumo y costo efectivo'
        labels = ['Capacidad', 'Monetización por ASK'] if b['name']=='revenue' else ['Litros consumidos', 'Costo efectivo por litro']
        body += f'<article><h2>{title} · {b["comparison"]}</h2><p>Asignación simétrica: cambio de un componente × promedio del otro. Millones USD; identidad contable, sin atribución causal.</p><table><tr><th>Componente</th><th>Contribución · millones USD</th><th>Detalle</th></tr>'
        for label, id in zip(labels,b['contribution_ids']):
            n=nodes[id];body+=f'<tr><td>{label}</td><td>{n["value"]/1e6:+.3f}</td><td>{button(n)}</td></tr>'
        n=nodes[b['total_id']];body+=f'<tr><td><strong>Cambio total</strong></td><td><strong>{n["value"]/1e6:+.3f}</strong></td><td>{button(n)}</td></tr></table></article>'
    differences = [c for c in result["checks"] if c["status"] == "not_reconciled"]
    body += '<article class="warning"><h2>Diferencias pendientes entre costo unitario y gasto financiero</h2><p>En estos periodos, CASK publicado y gasto operativo/ASK no coinciden dentro del redondeo. No se ha demostrado que tengan el mismo alcance. Se conserva la diferencia y queda prohibido presentar el puente del spread como una explicación del margen financiero.</p><table><tr><th>Periodo</th><th>Diferencia · centavos USD/ASK</th></tr>'
    for c in differences:body += f'<tr><td>{c["period_id"]}</td><td>{c["difference"]:+.4f}</td></tr>'
    body += '</table></article><article><h2>Cálculos del trimestre y comparaciones</h2><label for="filter">Buscar métrica o QoQ/YoY</label><input id="filter" type="search" placeholder="Ejemplo: rask, operating_margin, YoY"><div class="table-wrap"><table><thead><tr><th>Métrica/cálculo</th><th>Resultado</th><th>Detalle</th></tr></thead><tbody>'
    used = set(n['calculation_id'] for n in result['nodes'] if n['period_id'] != result['period_id'])
    # Dialogs already emitted for bridges are reused rather than duplicated.
    existing = {id for b in result['bridges'] for id in b['contribution_ids']+[b['total_id']]}
    for n in result['nodes']:
        if n['period_id'] != result['period_id']:continue
        id=n['calculation_id']
        action=f'<button data-dialog="{id}">Ver cálculo</button>' if id in existing else button(n)
        existing.add(id)
        body+=f'<tr class="row"><td>{escape(n["key"])}</td><td>{escape(n["formatted_value"])}</td><td>{action}</td></tr>'
    body+='</tbody></table></div><p id="empty" hidden>Sin coincidencias.</p></article><article><h2>Validación y precisión</h2><p>Los controles financieros y de ingreso unitario se verifican con intervalos de redondeo. Los cinco contrastes de costo/ASK señalados arriba permanecen sin reconciliar. Los puentes QoQ y YoY cierran con error numérico inferior a 10⁻¹⁰.</p><p>La precisión se trata de forma conservadora: media unidad del último decimal conservado por cada insumo, propagada por las operaciones. Cuando la base es cero, negativa o falta el periodo exacto, no se presenta un porcentaje de crecimiento.</p><p>La evidencia original permanece intacta. Los resultados tienen su propia versión y huella. Esta etapa requiere revisión humana antes de desarrollar al analista.</p></article>'
    css='''*{box-sizing:border-box}body{font:15px Segoe UI,Arial,sans-serif;color:#09254b;background:#f3f6fa;margin:0}main{max-width:1150px;margin:auto;padding:24px}header{background:#062355;color:white;padding:28px;border-radius:16px}h1{font-size:28px}h2{font-size:21px}p{line-height:1.65}article{padding:24px;margin-top:20px;border:1px solid #d6e1ee;border-radius:14px;background:white}.warning{background:#fff8e9;border-left:4px solid #b88129}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:12px 8px;text-align:left;border-bottom:1px solid #dce5ef;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}button{cursor:pointer;white-space:nowrap;font:inherit;color:#065ba0;background:white;border:1px solid #b7c9de;border-radius:7px;padding:7px 10px}button:focus-visible,input:focus-visible{outline:3px solid #1976d2}input{width:100%;padding:12px;margin:12px 0;border:1px solid #b7c9de;border-radius:7px}dialog{width:calc(100% - 28px);max-width:850px;max-height:88dvh;overflow:auto;border:1px solid #bbcddd;border-radius:14px;color:#09254b;padding:22px}dialog::backdrop{background:#001d4488}dialog li{margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:12px;font:13px Segoe UI}.close{float:right}a{color:#065ba0}[hidden]{display:none!important}@media(max-width:736px){main{padding:12px}header,article{padding:17px}h1{font-size:23px}table{font-size:12px}td,th{padding:9px 5px;overflow-wrap:normal}button{font-size:12px;padding:7px 8px}.row td:first-child{overflow-wrap:anywhere}dialog ul{padding-left:16px}}'''
    js='''let opener;document.querySelectorAll('[data-dialog]').forEach(b=>b.onclick=()=>{opener=b;document.getElementById(b.dataset.dialog).showModal()});document.querySelectorAll('dialog').forEach(d=>{d.querySelector('.close').onclick=()=>d.close();d.onclose=()=>opener?.focus()});document.getElementById('filter').oninput=e=>{let n=0;document.querySelectorAll('.row').forEach(r=>{r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase());if(!r.hidden)n++});document.getElementById('empty').hidden=n>0};'''
    target=PATHS.root/'prototypes/etapa-15/quantitative_review.html';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Etapa 15 · Cálculos trimestrales</title><style>'+css+'</style></head><body><main>'+body+'</main>'+''.join(dialogs)+'<script>'+js+'</script></body></html>',encoding='utf-8')
    print(target)


if __name__ == '__main__':run()
