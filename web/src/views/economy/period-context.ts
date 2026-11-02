import type { Layout } from "plotly.js";
import { currentPeriodId } from "../../state/period";
import { entityLabel, entityRecords, entityView } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";

export const quarterLabel = (id: string): string => `${id.slice(-1)}T${id.slice(2, 4)}`;

export function economyPeriodContext(id: string, layout: Partial<Layout>, entities: EntityKey[], categorical: boolean): void {
  const selected = currentPeriodId();
  if (!selected) return;
  const label = quarterLabel(selected);
  const coverage = entities.map(key => {
    const records = entityRecords(key);
    const latest = records.map(row => row.period_id).sort().at(-1);
    if (entityView(key, selected)?.narrative?.headline === "Industria calculada · vista previa para revisión")
      return `${entityLabel(key)}: ${label} calculado · vista previa`;
    return records.some(row => row.period_id === selected)
      ? `${entityLabel(key)}: ${label} disponible`
      : `${entityLabel(key)}: sin dato para ${label}${latest ? `; último publicado ${quarterLabel(latest)}` : ""}`;
  }).join(" · ");
  const host = document.getElementById(id);
  if (host) {
    host.setAttribute("aria-description", `${coverage}. Se conserva la historia disponible.`);
    host.dataset.selectedPeriod = selected;
  }
  // Each render supplies new arrays. Leave Plotly in immutable mode so a
  // metric/entity/range change within the same quarter recalculates them.
  // A quarter-only datarevision makes Plotly treat those arrays as unchanged.
  if (categorical) {
    const labels = [...new Set([...(layout.xaxis?.categoryarray ?? []) as string[], label])].sort((a,b) => {
      const key = (v: string) => v.slice(2) + v.slice(0,1); return key(a).localeCompare(key(b));
    });
    layout.xaxis = { ...layout.xaxis, type: "category", categoryorder: "array", categoryarray: labels, range: [-0.5, labels.length - 0.5] };
    const index = labels.indexOf(label);
    layout.shapes = [{ type: "rect", xref: "x", yref: "paper", x0: index - .45, x1: index + .45,
      y0: 0, y1: 1, fillcolor: "rgba(0,48,135,.08)", line: { color: "#003087", width: 1, dash: "dot" }, layer: "below" }];
    layout.annotations = [{ x: label, y: 1, xref: "x", yref: "paper", text: label, showarrow: false, yanchor: "bottom", font: { size: 10, color: "#003087" } }];
  }
}
