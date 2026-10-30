import { formatMarketNumber as fmt } from "./calculations";
interface Row { key:string; group:string; period_id:string; passengers:number|null; yoy_pct:number|null; previous_period:string; previous_passengers:number|null; source_url?:string|null; source_hash?:string; captured_at?:string; }
interface Demand { months:string[]; airports:Row[]; afac_airports?:Row[]; groups:Row[]; quality_notes:string[]; }
let data: Demand | null = null;
let loading: Promise<void> | null = null;
function table(id:string, rows:Row[], period:string) {
  const host=document.getElementById(id); if(!host) return;
  const selected=rows.filter(row=>row.period_id===period).sort((a,b)=>(b.passengers??-1)-(a.passengers??-1));
  host.replaceChildren(...selected.map(row=>{const tr=document.createElement("tr");
    const texts=id==="airport-groups"?[row.key,fmt(row.passengers),fmt(row.yoy_pct,"%"),`${row.previous_period}: ${fmt(row.previous_passengers)}`]:[row.key,row.group,fmt(row.passengers),fmt(row.yoy_pct,"%"),`${row.previous_period}: ${fmt(row.previous_passengers)}`];
    for(const [index,text] of texts.entries()){ const td=document.createElement("td");td.textContent=text;
      if(index===0 && row.source_url){try{const url=new URL(row.source_url);if(url.protocol==="https:"&&!url.username&&!url.password){const a=document.createElement("a");a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";a.textContent=text;a.title=`Fuente · captura: ${row.captured_at ?? "N/D"} · SHA-256: ${row.source_hash ?? "N/D"}`;td.replaceChildren(a);}}catch{ /* Unknown provenance stays plain text. */ }}
      tr.append(td); } return tr; }));
  if(!selected.length){const tr=document.createElement("tr");const td=document.createElement("td");td.colSpan=id==="airport-groups"?4:5;td.textContent="Sin observaciones en este mes.";tr.append(td);host.append(tr);}
}
export function mountDemand(root:string): Promise<void> {
  if(loading) return loading;
  loading=(async()=>{try{
    const response=await fetch(`${root}/market-demand.json`); if(!response.ok) throw new Error("unavailable");data=await response.json() as Demand;
    const picker=document.getElementById("airport-period") as HTMLSelectElement;
    picker.replaceChildren(...data.months.map(id=>new Option(id.replace("M","-"),id)));picker.value=data.months.at(-1)??"";
    let sourcePicker:HTMLSelectElement|null=null;
    if(data.afac_airports?.length){
      sourcePicker=document.createElement("select");sourcePicker.id="airport-source";
      sourcePicker.setAttribute("aria-label","Base de cifras aeroportuarias");
      sourcePicker.append(new Option("Reportes directos de aeropuertos y grupos","direct"),new Option("Estadísticas AFAC · mismos aeropuertos","afac"));
      const basis=document.createElement("label");basis.className="chart-range-control";
      basis.htmlFor="airport-source";basis.textContent="Base aeroportuaria";basis.append(sourcePicker);
      (picker.closest("label")??picker).insertAdjacentElement("afterend",basis);
    }
    function render(){ if(!data)return;const afac=sourcePicker?.value==="afac";
      table("airport-demand",afac?(data.afac_airports??[]):data.airports,picker.value);table("airport-groups",data.groups,picker.value);
      const basis=afac?"Base de aeropuertos: estadísticas AFAC, separadas de los reportes directos. Los grupos conservan sus reportes directos.":"Base de aeropuertos y grupos: sus reportes directos.";
      document.getElementById("airport-note")!.textContent=`Corte aeroportuario: ${picker.value}. ${basis} Las bases interanuales se comparan dentro de cada aeropuerto/grupo; N/D indica base ausente. No representa todo México ni viajeros únicos; no se atribuye a Aeroméxico.`;
      document.getElementById("airport-quality")!.textContent=data.quality_notes.join(" "); }
    picker.addEventListener("change",render);sourcePicker?.addEventListener("change",render);render();
  }catch{document.getElementById("airport-note")!.textContent="Demanda aeroportuaria no disponible en este build.";loading=null;}})();return loading;
}
