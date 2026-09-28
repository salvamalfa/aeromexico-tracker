"""Dashboard v2 · maqueta de revisión del selector de aerolíneas.

Genera ``prototypes/dashboard-v2/maqueta.html``: una página autocontenida con
los datos reales de ``build_executive_payload()['entities']`` y
``build_market_payload()`` para que el dueño apruebe la dinámica de cada card
(selección única o múltiple, Industria por defecto) antes de reescribir
``web/``. No es la página publicada ni la sustituye.

    uv run python -m src.dashboard.v2_mockup
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import PATHS
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.market import build_market_payload

OUT = PATHS.root / "prototypes" / "dashboard-v2" / "maqueta.html"

# Validated with the dataviz skill's validate_palette.js (--pairs all, light):
# worst CVD ΔE 9.5, worst normal-vision ΔE 27.6, all >= 3:1 on white.
COLORS = {
    "INDUSTRY": "#6b7280",
    "AEROMEXICO": "#1d4f9e",
    "VOLARIS": "#d05aa8",
    "VIVA_AEROBUS": "#1a9a5c",
}

TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aerolíneas MX Tracker · maqueta v2</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@3.7.0/plotly.min.js"></script>
<style>
:root{--ink:#182233;--muted:#5e6a7d;--quiet:#8792a4;--paper:#f4f7fb;--card:#fff;--line:#dce3ed;--line-strong:#bdc9d8;--brand:#003087;
--c-INDUSTRY:#6b7280;--c-AEROMEXICO:#1d4f9e;--c-VOLARIS:#d05aa8;--c-VIVA_AEROBUS:#1a9a5c;--good:#087f65;--bad:#c0262d}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{background:var(--brand);color:#fff;padding:18px 16px}header .wrap{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
h1{font-size:22px;margin:0}.sub{opacity:.85;font-size:13px}.wrap{max-width:1180px;margin:0 auto}
main{padding:16px}.grid{display:grid;gap:16px;grid-template-columns:repeat(12,1fr)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;grid-column:span 12;min-width:0}
.half{grid-column:span 6}@media(max-width:860px){.half{grid-column:span 12}}
.card-head{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:flex-start;justify-content:space-between;margin-bottom:8px}
.card-head h2{font-size:16px;margin:0}.kicker{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 2px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1px solid var(--line-strong);background:#fff;color:var(--ink);border-radius:999px;padding:4px 10px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.chip .dot{width:9px;height:9px;border-radius:50%}.chip[aria-pressed="true"]{border-color:var(--ink);background:#eef2f8;font-weight:600}
.chip.mode{font-size:12px;padding:3px 9px}.hint{font-size:12px;color:var(--quiet)}
select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--line-strong);background:#fff}
.note{font-size:13px;color:var(--muted);margin:4px 0 0}.chart{width:100%;height:320px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.kpi{border:1px solid var(--line);border-radius:10px;padding:10px}.kpi .l{font-size:12px;color:var(--muted)}.kpi .v{font-size:22px;font-weight:700;margin:2px 0}
.kpi .c{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:2px}.up{color:var(--good)}.down{color:var(--bad)}
.share-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:8px}
.share-tiles .kpi{border-left:4px solid var(--tile)}.thesis h3{margin:.2em 0;font-size:17px}.thesis ul{margin:.4em 0 0;padding-left:18px}
.pending{background:#f7f9fc;border:1px dashed var(--line-strong);border-radius:10px;padding:12px;color:var(--muted)}
.legend-note{font-size:12px;color:var(--muted)}footer{padding:16px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header><div class="wrap">
  <div><h1>Aerolíneas MX Tracker</h1><div class="sub" id="industry-note"></div></div>
  <label class="sub">Trimestre <select id="quarter"></select></label>
</div></header>
<main class="wrap"><div class="grid">

<section class="card" id="card-market">
  <div class="card-head"><div><p class="kicker">Mercado</p><h2>Participación de pasajeros (AFAC)</h2></div>
    <div><div class="chips" data-card="market" data-mode="multi"></div><div class="hint">Selección múltiple</div></div></div>
  <div class="share-tiles" id="market-tiles"></div>
  <div class="chips" id="segment"></div>
  <div class="chart" id="market-chart"></div>
  <p class="note" id="market-note"></p>
</section>

<section class="card thesis" id="card-thesis">
  <div class="card-head"><div><p class="kicker">Lectura ejecutiva</p><h2 id="thesis-title">Tesis del trimestre</h2></div>
    <div><div class="chips" data-card="thesis" data-mode="single"></div><div class="hint">Una a la vez</div></div></div>
  <div id="thesis-body"></div>
</section>

<section class="card" id="card-kpis">
  <div class="card-head"><div><p class="kicker">Economía unitaria</p><h2 id="kpi-title">Indicadores del trimestre</h2></div>
    <div><div class="chips" data-card="kpis" data-mode="single"></div><div class="hint">Una a la vez</div></div></div>
  <div class="kpis" id="kpi-grid"></div>
</section>

<section class="card" id="card-unit">
  <div class="card-head"><div><p class="kicker">Economía unitaria</p><h2>Ingreso, costo y margen por ASK</h2></div>
    <div><div class="chips" data-card="unit" data-mode="multi"></div><div class="hint">Selección múltiple</div></div></div>
  <div class="chips" id="unit-metric"></div>
  <div class="chart" id="unit-chart"></div>
  <p class="note">¢ USD por ASK-km. Industria ponderada por ASK (ingresos de las tres ÷ ASK de las tres). RASK por km es menor en redes de largo alcance.</p>
</section>

<section class="card half" id="card-pax">
  <div class="card-head"><div><p class="kicker">Volumen</p><h2>Pasajeros por trimestre</h2></div>
    <div><div class="chips" data-card="pax" data-mode="multi"></div><div class="hint">Selección múltiple</div></div></div>
  <div class="chart" id="pax-chart"></div>
  <p class="note" id="pax-note"></p>
</section>

<section class="card half" id="card-scatter">
  <div class="card-head"><div><p class="kicker">Utilización</p><h2>Ocupación y RASK</h2></div>
    <div><div class="chips" data-card="scatter" data-mode="multi"></div><div class="hint">Selección múltiple</div></div></div>
  <div class="chart" id="scatter-chart"></div>
  <p class="note">Cada punto es un trimestre; el trimestre seleccionado va resaltado.</p>
</section>

<section class="card" id="card-mix">
  <div class="card-head"><div><p class="kicker">Vuelos</p><h2>Mezcla nacional e internacional</h2></div>
    <div><div class="chips" data-card="mix" data-mode="multi"></div><div class="hint">Selección múltiple</div></div></div>
  <div class="chart" id="mix-chart"></div>
  <p class="note">Pasajeros AFAC por trimestre: tono oscuro = nacional, claro = internacional. AM = Aeroméxico, Y4 = Volaris, VB = Viva.</p>
  <div class="pending"><strong>Mapa de rutas (fase 3):</strong> selección única. <em>Industria</em> muestra las rutas donde vuela al menos una de las tres, con su volumen combinado estimado y el reparto por aerolínea en el tooltip; una aerolínea muestra solo sus rutas (estimadas con IPF; T-100 observado en México–EE. UU.). El error medido del estimador es mayor para Viva en internacional (~15 % frente a 4–7 %).</div>
</section>

</div></main>
<footer class="wrap">Maqueta de revisión con datos reales (reportes trimestrales de cada aerolínea y AFAC). Generada por <code>src/dashboard/v2_mockup.py</code>; no es el dashboard publicado.</footer>

<script>
const EXEC = __EXEC__;
const MARKET = __MARKET__;
const COLORS = __COLORS__;
const ORDER = ["INDUSTRY","AEROMEXICO","VOLARIS","VIVA_AEROBUS"];
const LABEL = Object.fromEntries(EXEC.entity_list.map(e => [e.key, e.label]));
const qp = new URLSearchParams(location.search);
const state = {
  quarter: qp.get("q") || MARKET.metadata.default_quarter,
  segment: qp.get("seg") || "total",
  unitMetric: qp.get("metric") || "rask_cents_per_km",
  sel: {},
};
const DEFAULTS = {market:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"], thesis:["INDUSTRY"], kpis:["INDUSTRY"], unit:["INDUSTRY"], pax:["INDUSTRY"], scatter:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"], mix:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"]};
for (const card of Object.keys(DEFAULTS)) {
  const raw = qp.get(card);
  state.sel[card] = raw ? raw.split(",").filter(k => ORDER.includes(k)) : [...DEFAULTS[card]];
  if (!state.sel[card].length) state.sel[card] = [...DEFAULTS[card]];
}
function syncUrl(){const p=new URLSearchParams();p.set("q",state.quarter);p.set("seg",state.segment);p.set("metric",state.unitMetric);for(const [k,v] of Object.entries(state.sel))p.set(k,v.join(","));history.replaceState(null,"","?"+p.toString());}

const fmt = {
  cents: v => v==null?"N/D":v.toFixed(2)+" ¢",
  pct: v => v==null?"N/D":(v*100).toFixed(1)+" %",
  pp: v => v==null?"N/D":(v>0?"+":"")+v.toFixed(1)+" pp",
  millions: v => v==null?"N/D":(v/1e6).toFixed(2)+" M",
  billions: v => v==null?"N/D":(v/1e9).toFixed(2)+" mil M",
};
const qLabel = id => id[5]+"T"+id.slice(2,4);
const recordsOf = key => EXEC.entities[key].records;
const recordAt = (key, q) => recordsOf(key).find(r => r.period_id === q);
const base = {font:{family:"system-ui,-apple-system,Segoe UI,Roboto,sans-serif",size:12,color:"#182233"},margin:{l:52,r:12,t:36,b:48},paper_bgcolor:"#fff",plot_bgcolor:"#fff",
  xaxis:{gridcolor:"#eef1f5",linecolor:"#bdc9d8",tickfont:{color:"#5e6a7d"}},yaxis:{gridcolor:"#eef1f5",zeroline:false,tickfont:{color:"#5e6a7d"}},
  legend:{orientation:"h",x:0,y:1.12,yanchor:"bottom"},hoverlabel:{bgcolor:"#fff",bordercolor:"#bdc9d8",font:{color:"#182233"}}};
const cfg = {displayModeBar:false,responsive:true};
const lineStyle = key => key==="INDUSTRY" ? {color:COLORS[key],width:2,dash:"dash"} : {color:COLORS[key],width:2};

function renderChips(container){
  const card = container.dataset.card, multi = container.dataset.mode === "multi";
  container.innerHTML = "";
  for (const key of ORDER) {
    const b = document.createElement("button");
    b.className = "chip"; b.type = "button";
    b.setAttribute("aria-pressed", state.sel[card].includes(key));
    b.innerHTML = `<span class="dot" style="background:${COLORS[key]}"></span>${LABEL[key]}`;
    b.onclick = () => {
      let s = state.sel[card];
      if (!multi) s = [key];
      else if (s.includes(key)) { if (s.length > 1) s = s.filter(k => k !== key); }
      else s = ORDER.filter(k => s.includes(k) || k === key);
      state.sel[card] = s; render();
    };
    container.appendChild(b);
  }
}
function modeChips(el, options, current, onpick){
  el.innerHTML = "";
  for (const [value,label] of options){const b=document.createElement("button");b.className="chip mode";b.type="button";b.textContent=label;b.setAttribute("aria-pressed",value===current);b.onclick=()=>onpick(value);el.appendChild(b);}
}

function renderMarket(){
  const q = MARKET.quarters.find(x => x.period_id === state.quarter) || MARKET.quarters.at(-1);
  const seg = q.segments[state.segment];
  const tiles = document.getElementById("market-tiles"); tiles.innerHTML = "";
  for (const key of ORDER) {
    const item = key==="INDUSTRY" ? seg.industry : seg.carriers[key];
    const yoy = item.share_change_yoy_pp, cls = yoy==null?"":(yoy>0.05?"up":yoy<-0.05?"down":"");
    tiles.insertAdjacentHTML("beforeend", `<div class="kpi" style="--tile:${COLORS[key]}"><div class="l">${LABEL[key]}</div><div class="v">${fmt.pct(item.share)}</div><div class="c"><span class="${cls}">${fmt.pp(yoy)} vs. año anterior</span><span>${fmt.pp(item.share_change_qoq_pp)} vs. trimestre anterior</span></div></div>`);
  }
  modeChips(document.getElementById("segment"), [["total","Total"],["domestic","Nacional"],["international","Internacional"]], state.segment, v => {state.segment=v; render();});
  const months = MARKET.months;
  const traces = state.sel.market.map(key => ({
    x: months.map(m => m.period_id.slice(0,4)+"-"+m.period_id.slice(5,7)+"-01"),
    y: months.map(m => { const s=m.segments[state.segment]; const it = key==="INDUSTRY"?s.industry:s.carriers[key]; return it.share==null?null:it.share*100; }),
    name: LABEL[key], mode:"lines", line: lineStyle(key), connectgaps:false,
    hovertemplate: `${LABEL[key]}: %{y:.1f} %<extra>%{x|%b %Y}</extra>`,
  }));
  Plotly.react("market-chart", traces, {...base, yaxis:{...base.yaxis, ticksuffix:" %", rangemode:"tozero"}, xaxis:{...base.xaxis, type:"date"}}, cfg);
  document.getElementById("market-note").textContent = MARKET.metadata.method_note;
}

function renderThesis(){
  const key = state.sel.thesis[0], ent = EXEC.entities[key], view = ent.views[state.quarter];
  document.getElementById("thesis-title").textContent = `Tesis del trimestre · ${LABEL[key]} · ${qLabel(state.quarter)}`;
  const body = document.getElementById("thesis-body");
  const approved = key==="AEROMEXICO" && state.quarter==="2026Q2"
    ? `<p class="pending">En el dashboard real aquí aparece el <strong>análisis aprobado de Aeroméxico 2T26</strong> (Analysis Agent).</p>`
    : `<p class="pending">Tesis ${key==="INDUSTRY"?"de la industria":"de "+LABEL[key]} pendiente de aprobación (fase 5). Mientras tanto se muestran las conclusiones automáticas calculadas de los datos:</p>`;
  body.innerHTML = approved + (view ? `<h3>${view.narrative.headline}</h3><ul>${view.conclusions.map(c=>`<li>${c}</li>`).join("")}</ul>` : `<p class="pending">Sin trimestre comparable para ${LABEL[key]} en ${qLabel(state.quarter)}.</p>`);
}

function renderKpis(){
  const key = state.sel.kpis[0], view = EXEC.entities[key].views[state.quarter];
  document.getElementById("kpi-title").textContent = `Indicadores · ${LABEL[key]} · ${qLabel(state.quarter)}`;
  const grid = document.getElementById("kpi-grid");
  if (!view) { grid.innerHTML = `<p class="pending">${LABEL[key]} no tiene ${qLabel(state.quarter)} en su serie.</p>`; return; }
  const cards = view.kpis.map(k => ({label:k.label, value:k.display_value, qoq:k.qoq, yoy:k.yoy, vs:k.vs_industry, desc:k.description, costly:k.key==="cask_cents_per_km", neutral:k.key==="passengers"||k.key==="ask_km"}));
  const rec = recordAt(key, state.quarter);
  cards.splice(2,0,{label:"Margen unitario", value:fmt.cents(rec.unit_margin_cents_per_km)+" USD", qoq:view.margin_qoq, yoy:view.margin_yoy, vs:view.margin_vs_industry, desc:"RASK − CASK."});
  // Color = good/bad, not up/down: a rising cost is bad.
  const tone = (c, costly) => { if (!c || c.direction==="flat" || c.direction==="na") return ""; const good = (c.direction==="up") !== costly; return good?"up":"down"; };
  const chip = (c, costly) => c ? `<span class="${tone(c,costly)}">${c.display}</span>` : "";
  grid.innerHTML = cards.map(c => `<div class="kpi" title="${c.desc}"><div class="l">${c.label}</div><div class="v">${c.value}</div><div class="c"><span>vs. trim. anterior: ${chip(c.qoq,c.costly)}</span><span>vs. año anterior: ${chip(c.yoy,c.costly)}</span>${c.vs?`<span>${c.neutral?c.vs.display:chip(c.vs,c.costly)}</span>`:""}</div></div>`).join("");
}

function renderUnit(){
  const sel = state.sel.unit, metricEl = document.getElementById("unit-metric");
  const metrics = [["rask_cents_per_km","RASK"],["cask_cents_per_km","CASK"],["cask_ex_fuel_cents_per_km","CASK ex-fuel"],["unit_margin_cents_per_km","Margen"]];
  let traces;
  if (sel.length === 1) {
    metricEl.innerHTML = `<span class="hint">Una entidad: RASK, CASK y margen juntos. Elige más aerolíneas para comparar una métrica.</span>`;
    const rs = recordsOf(sel[0]), x = rs.map(r => r.period_label);
    traces = [["rask_cents_per_km","RASK","#1d4f9e"],["cask_cents_per_km","CASK","#c0262d"]].map(([k,n,c]) => ({x, y: rs.map(r=>r[k]), name:n, mode:"lines+markers", line:{color:c,width:2}, marker:{size:8}, hovertemplate:`${n}: %{y:.2f} ¢<extra>%{x}</extra>`}));
    traces.push({x, y: rs.map(r=>r.unit_margin_cents_per_km), name:"Margen", type:"bar", marker:{color:"rgba(24,34,51,.18)"}, hovertemplate:"Margen: %{y:.2f} ¢<extra>%{x}</extra>"});
  } else {
    modeChips(metricEl, metrics, state.unitMetric, v => {state.unitMetric=v; render();});
    const label = Object.fromEntries(metrics)[state.unitMetric];
    const periods = [...new Set(sel.flatMap(k => recordsOf(k).map(r=>r.period_id)))].sort();
    traces = sel.map(key => ({ x: periods.map(qLabel), y: periods.map(p => { const r = recordAt(key,p); return r ? r[state.unitMetric] : null; }),
      name: LABEL[key], mode:"lines+markers", line: lineStyle(key), marker:{size:8, color:COLORS[key]}, connectgaps:false,
      hovertemplate: `${LABEL[key]} · ${label}: %{y:.2f} ¢<extra>%{x}</extra>` }));
  }
  Plotly.react("unit-chart", traces, {...base, yaxis:{...base.yaxis, ticksuffix:" ¢"}, barmode:"overlay"}, cfg);
}

function renderPax(){
  const sel = state.sel.pax; let traces, layout = {...base, yaxis:{...base.yaxis, ticksuffix:" M"}};
  const carriers = ["AEROMEXICO","VOLARIS","VIVA_AEROBUS"];
  if (sel.length === 1 && sel[0] === "INDUSTRY") {
    const periods = recordsOf("INDUSTRY").map(r=>r.period_id);
    traces = carriers.map(key => ({x: periods.map(qLabel), y: periods.map(p => (recordAt(key,p)||{}).passengers/1e6), name: LABEL[key], type:"bar", marker:{color:COLORS[key], line:{color:"#fff", width:2}}, hovertemplate:`${LABEL[key]}: %{y:.2f} M<extra>%{x}</extra>`}));
    layout.barmode = "stack";
    document.getElementById("pax-note").textContent = "Industria: barras apiladas, el total y quién lo compone. Pasajeros según el reporte de cada aerolínea (Viva: pasajeros reservados).";
  } else {
    const periods = [...new Set(sel.flatMap(k => recordsOf(k).map(r=>r.period_id)))].sort().slice(-8);
    traces = sel.map(key => ({x: periods.map(qLabel), y: periods.map(p => { const r=recordAt(key,p); return r? r.passengers/1e6 : null; }), name: LABEL[key], type:"bar", marker:{color:COLORS[key], line:{color:"#fff", width:2}, pattern: key==="INDUSTRY"?{shape:"/", fgcolor:"#fff"}:undefined}, hovertemplate:`${LABEL[key]}: %{y:.2f} M<extra>%{x}</extra>`}));
    layout.barmode = "group";
    document.getElementById("pax-note").textContent = "Varias: barras agrupadas lado a lado (últimos 8 trimestres).";
  }
  Plotly.react("pax-chart", traces, layout, cfg);
}

function renderScatter(){
  const traces = [];
  for (const key of state.sel.scatter) {
    const rs = recordsOf(key);
    traces.push({x: rs.map(r=>r.load_factor*100), y: rs.map(r=>r.rask_cents_per_km), text: rs.map(r=>r.period_label), name: LABEL[key], mode:"markers",
      marker:{size: rs.map(r => r.period_id===state.quarter?15:9), color:COLORS[key], symbol: key==="INDUSTRY"?"diamond":"circle", line:{color:"#fff",width:2}, opacity: rs.map(r => r.period_id===state.quarter?1:.55)},
      hovertemplate:`${LABEL[key]} %{text}<br>Ocupación %{x:.1f} %<br>RASK %{y:.2f} ¢<extra></extra>`});
  }
  Plotly.react("scatter-chart", traces, {...base, xaxis:{...base.xaxis, type:"linear", ticksuffix:" %", title:{text:"Factor de ocupación",font:{size:12,color:"#5e6a7d"}}}, yaxis:{...base.yaxis, ticksuffix:" ¢", title:{text:"RASK",font:{size:12,color:"#5e6a7d"}}}}, cfg);
}

function renderMix(){
  const SHORT = {INDUSTRY:"Ind.", AEROMEXICO:"AM", VOLARIS:"Y4", VIVA_AEROBUS:"VB"};
  const periods = MARKET.quarters.slice(-6), sel = state.sel.mix, traces = [];
  const keys = sel;
  for (const key of keys) {
    for (const [seg, name, alpha] of [["domestic","nacional",1],["international","internacional",.55]]) {
      traces.push({x: [periods.map(q=>q.period_label), periods.map(()=>SHORT[key])], y: periods.map(q => { const s=q.segments[seg]; const it = key==="INDUSTRY"?s.industry:s.carriers[key]; return it.passengers==null?null:it.passengers/1e6; }),
        name: `${LABEL[key]} · ${name}`, type:"bar", marker:{color:COLORS[key], opacity:alpha, line:{color:"#fff",width:1}}, hovertemplate:`${LABEL[key]} ${name}: %{y:.2f} M<extra>%{x}</extra>`});
    }
  }
  Plotly.react("mix-chart", traces, {...base, barmode:"relative", yaxis:{...base.yaxis, ticksuffix:" M"}, xaxis:{...base.xaxis, type:"multicategory", tickangle:0}, showlegend:false}, cfg);
}

function render(){
  document.querySelectorAll(".chips[data-card]").forEach(renderChips);
  renderMarket(); renderThesis(); renderKpis(); renderUnit(); renderPax(); renderScatter(); renderMix(); syncUrl();
}
const quarterSel = document.getElementById("quarter");
for (const q of [...MARKET.quarters].reverse()) if (EXEC.entities.INDUSTRY.views[q.period_id]) quarterSel.add(new Option(q.period_label, q.period_id));
quarterSel.value = state.quarter; quarterSel.onchange = () => {state.quarter = quarterSel.value; render();};
document.getElementById("industry-note").textContent = MARKET.metadata.industry_note;
render();
</script>
</body>
</html>
"""


def build(out: Path = OUT) -> Path:
    executive = build_executive_payload()
    entities = {
        key: {"label": block["label"], "records": block["records"], "views": block["views"]}
        for key, block in executive["entities"].items()
    }
    market = build_market_payload()
    html = (
        TEMPLATE.replace("__EXEC__", json.dumps({"entity_list": executive["entity_list"], "entities": entities}, ensure_ascii=False))
        .replace("__MARKET__", json.dumps(market, ensure_ascii=False))
        .replace("__COLORS__", json.dumps(COLORS))
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    print(build())
