import { financialKpiSources } from "../../lib/financial-sources";
import { bindSourceInfo } from "../market/source-info";
import type { EntityKey } from "../shell/carriers";

type EconomyChart = "unit" | "volume" | "load";
const DETAILS: Record<EconomyChart,string> = {
  unit:"Ingreso y costo por asiento-kilómetro; margen = RASK − CASK.",
  volume:"Pasajeros reportados en millones y RASK. Industria suma pasajeros y pondera RASK por capacidad.",
  load:"Ocupación (%) frente a RASK. Industria pondera ambas cifras por capacidad.",
};

export function renderEconomyChartSource(chart: EconomyChart, entities: EntityKey[]): void {
  const card = document.getElementById(`${chart}-chart`)?.closest<HTMLElement>(".chart-card");
  const title = card?.querySelector<HTMLElement>(".chart-title");
  if (!card || !title) return;
  let button = title.querySelector<HTMLButtonElement>(".market-source-info");
  let panel = card.querySelector<HTMLElement>(".economy-chart-source");
  if (!panel) {
    panel = document.createElement("div"); panel.id = `economy-${chart}-source`; panel.className = "economy-chart-source";
    card.append(panel);
  }
  if (!button) {
    button = document.createElement("button"); button.type = "button"; button.className = "market-source-info";
    button.textContent = "ⓘ"; button.setAttribute("aria-label","Fuente y cálculo de la gráfica");
    title.append(button); bindSourceInfo(button,panel);
  }
  const source = document.createElement("b"); source.textContent = "Fuente: reportes financieros. ";
  const metric = (document.getElementById("unit-metric") as HTMLSelectElement | null)?.value;
  const detail = chart === "unit" && entities.length > 1 && metric === "cask_ex_fuel_cents_per_km"
    ? "Costo sin combustible por asiento-kilómetro. Industria pondera por capacidad."
    : DETAILS[chart] + (chart === "unit" && entities.includes("INDUSTRY") ? " Industria pondera por capacidad." : "");
  panel.replaceChildren(source,document.createTextNode(detail+" "));
  // These charts show historical series: link official archives, not a single
  // quarter's report presented as the source of the entire history.
  const links = new Map(entities.flatMap(entity=>financialKpiSources(entity,"history")).map(link=>[link.href,link]));
  [...links.values()].forEach((link,index)=>{
    if(index) panel!.append(document.createTextNode(" · "));
    const anchor = document.createElement("a"); anchor.href=link.href; anchor.textContent=link.label;
    anchor.target="_blank"; anchor.rel="noopener noreferrer"; panel!.append(anchor);
  });
}
