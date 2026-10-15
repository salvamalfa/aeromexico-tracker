// Map dates are independent of financial cards and approved analysis dates.
import { DOMESTIC_MONTH_NAMES, state } from "./state";
import { esc } from "./dom";

export function mapPeriodLabel(period: string): string {
  if (period.includes("M")) return `${DOMESTIC_MONTH_NAMES[Number(period.slice(5)) - 1]} ${period.slice(0, 4)}`;
  return `${period.at(-1)}T${period.slice(2, 4)}`;
}

export function mapPeriodOptions(): string[] {
  if (state.networkMode === "international") return [...state.availablePeriods.international].sort();
  const months = state.availablePeriods.domestic_monthly;
  return [...new Set([...months, ...state.availablePeriods.domestic,
    ...months.map((id) => `${id.slice(0, 4)}Q${Math.floor((Number(id.slice(5)) - 1) / 3) + 1}`)])].sort();
}

export function currentMapPeriod(): string {
  return state.mapPeriodId ?? state.quarters[state.periodIndex]?.period_id ?? "";
}

export function renderMapPeriodControl(): void {
  const select = document.querySelector<HTMLSelectElement>("#map-period");
  if (!select) return;
  const ids = mapPeriodOptions();
  if (state.mapPeriodId && !ids.includes(state.mapPeriodId)) ids.push(state.mapPeriodId);
  const option = (id: string) => `<option value="${esc(id)}">${esc(mapPeriodLabel(id))}</option>`;
  select.innerHTML = `<option value="">Trimestre general (${esc(mapPeriodLabel(state.quarters[state.periodIndex]!.period_id))})</option>`
    + `<optgroup label="Trimestres del mapa">${ids.filter((id) => id.includes("Q")).map(option).join("")}</optgroup>`
    + `<optgroup label="Meses del mapa">${ids.filter((id) => id.includes("M")).map(option).join("")}</optgroup>`;
  select.value = state.mapPeriodId ?? "";
  const layer = document.querySelector<HTMLSelectElement>("#map-domestic-layer");
  if (layer) {
    layer.parentElement!.hidden = state.networkMode !== "domestic" || state.mapEntity !== "AEROMEXICO";
    layer.value = state.domesticLayer;
  }
}

export function mountMapPeriodControl(onChange: () => void): void {
  const switcher = document.querySelector(".network-mode-switch");
  if (!switcher || document.querySelector("#map-period")) return;
  const label = document.createElement("label");
  label.className = "map-period-control";
  label.innerHTML = 'Periodo del mapa <select id="map-period" aria-label="Periodo del mapa"></select><span>Las tarjetas y tesis conservan el trimestre general.</span>';
  switcher.insertAdjacentElement("afterend", label);
  const layer = document.createElement("label");
  layer.className = "map-period-control";
  layer.innerHTML = 'Cifra nacional <select id="map-domestic-layer" aria-label="Cifra nacional"><option value="estimated">Frecuencias estimadas</option><option value="official">Programación y atribuciones</option></select>';
  label.insertAdjacentElement("afterend", layer);
  layer.querySelector("select")!.addEventListener("change", (event) => {
    state.domesticLayer = (event.target as HTMLSelectElement).value as typeof state.domesticLayer;
    onChange();
  });
  label.querySelector("select")!.addEventListener("change", (event) => {
    state.mapPeriodId = (event.target as HTMLSelectElement).value || null;
    state.pinnedAirport = null;
    state.selectedMarket = null;
    onChange();
  });
  renderMapPeriodControl();
}
