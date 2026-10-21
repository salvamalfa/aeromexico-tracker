import type { MapCoverage } from "../../types/domain";
import { ENTITY_LABELS, type EntityKey } from "../shell/carriers";
import { state } from "./state";
import { mapCarriers } from "./map-selection";
import { currentMapPeriod, mapPeriodLabel } from "./map-periods";

export function coverageRatio(data: MapCoverage | null, entities: string[], periods: string[]) {
  const carriers = [...new Set(entities.flatMap(mapCarriers))];
  const selectedPeriods = [...new Set(periods)];
  if (!data || !carriers.length || !selectedPeriods.length) return null;
  const calendar = new Set<string>();
  for (const period of selectedPeriods) {
    const quarter = /^(\d{4})Q([1-4])$/.exec(period);
    const months = quarter ? [0, 1, 2].map((offset) => `${quarter[1]}M${String((Number(quarter[2]) - 1) * 3 + 1 + offset).padStart(2, "0")}`) : [period];
    for (const month of months) {
      if (calendar.has(month)) return null;
      calendar.add(month);
    }
  }
  let observed = 0, estimated = 0, official = 0;
  for (const entity of carriers) for (const period_id of selectedPeriods) for (const scope of ["domestic", "international"]) {
    const rows = data.rows.filter((r) => r.entity === entity && r.period_id === period_id && r.scope === scope);
    if (rows.length !== 1) return null;
    const row = rows[0]!;
    if (row.official_regular == null || !Number.isFinite(row.official_regular) || row.official_regular < 0 ||
        !Number.isFinite(row.observed_regular) || row.observed_regular < 0 || !Number.isFinite(row.estimated) || row.estimated < 0) return null;
    observed += row.observed_regular; estimated += row.estimated; official += row.official_regular;
  }
  if (official <= 0) return null;
  return { observed, estimated, official, represented: observed + estimated, percent: 100 * (observed + estimated) / official };
}

export function renderMapCoverage(): void {
  const value = document.getElementById("flight-map-coverage");
  const explanation = document.getElementById("flight-map-coverage-info");
  if (!value || !explanation) return;
  const period = currentMapPeriod();
  const months = state.networkMode === "domestic" && period?.includes("Q") ? [...state.selectedDomesticMonths].sort() : [];
  const periods = months.length ? months : period ? [period] : [];
  const programming = state.networkMode === "domestic" && state.domesticLayer === "official" && state.mapEntity === "AEROMEXICO";
  const result = programming ? null : coverageRatio(state.mapCoverage, [state.mapEntity], periods);
  const label = months.length && months.length !== 3 ? months.map(mapPeriodLabel).join(", ") : period ? mapPeriodLabel(period) : "Periodo sin datos";
  const carriers = mapCarriers(state.mapEntity).map((key) => key === "VOLARIS" ? "Volaris México" : ENTITY_LABELS[key as EntityKey] ?? key).join(", ");
  value.textContent = result ? `${new Intl.NumberFormat("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(result.percent)} %` : "No disponible";
  value.dataset.represented = result ? String(result.represented) : "";
  value.dataset.official = result ? String(result.official) : "";
  explanation.textContent = result
    ? `${label} · ${carriers}. Nacional + internacional: ${result.represented.toLocaleString("es-MX")} vuelos observados regulares + estimados / ${result.official.toLocaleString("es-MX")} vuelos AFAC VLOSREG. Todas las rutas; los recortes geográficos y las rutas destacadas no cambian esta base.`
    : `${label} · ${carriers}. ${programming ? "Programación: no acredita vuelos realizados ni una cobertura comparable." : "Sin denominador y representación comparables AFAC para toda la selección."}`;
}
