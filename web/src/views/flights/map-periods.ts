// The map follows the single global quarter selector.
import { DOMESTIC_MONTH_NAMES, state } from "./state";
import { selectedFlightQuarter } from "./selected-period";

export function mapPeriodLabel(period: string): string {
  if (period.includes("M")) return `${DOMESTIC_MONTH_NAMES[Number(period.slice(5)) - 1]} ${period.slice(0, 4)}`;
  return `${period.at(-1)}T${period.slice(2, 4)}`;
}

export function currentMapPeriod(): string {
  state.mapPeriodId = null;
  return selectedFlightQuarter().period_id;
}

export function renderMapPeriodControl(): void {
  const layer = document.querySelector<HTMLSelectElement>("#map-domestic-layer");
  if (layer) {
    layer.parentElement!.hidden = state.networkMode !== "domestic" || state.mapEntity !== "AEROMEXICO";
    layer.value = state.domesticLayer;
  }
}

// The source layer is independent of the global period, and remains available.
export function mountMapPeriodControl(onChange: () => void): void {
  const controls = document.querySelector(".map-network-controls");
  if (!controls || document.querySelector("#map-domestic-layer")) return;
  const layer = document.createElement("label");
  layer.className = "map-layer-control";
  layer.innerHTML = '<span class="sr-only">Cifra nacional</span><select id="map-domestic-layer" aria-label="Cifra nacional"><option value="estimated">Frecuencias estimadas</option><option value="official">Programación y atribuciones</option></select>';
  controls.append(layer);
  layer.querySelector("select")!.addEventListener("change", (event) => {
    state.domesticLayer = (event.target as HTMLSelectElement).value as typeof state.domesticLayer;
    onChange();
  });
  renderMapPeriodControl();
}
