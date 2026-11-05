import { coverageText, expectedMonths, periodLabel } from "../../state/coverage";

export function renderPassengerCoverage(period: string, grain: "month" | "quarter", available: string[], basis: string, observedMonths?: string[]): void {
  const host = document.getElementById("mix-chart");
  if (!host) return;
  let note = document.getElementById("mix-coverage");
  if (!note) {
    note = document.createElement("p"); note.id = "mix-coverage"; note.className = "sr-only";
    note.setAttribute("role", "status"); host.before(note);
  }
  const months = observedMonths ?? (grain === "month" ? available : available.flatMap(expectedMonths));
  const latest = [...available].sort().at(-1);
  note.textContent = `${basis} · ${coverageText(period, months)}. `
    + (grain === "quarter" && !available.includes(period) ? "No se calcula un trimestre con meses incompletos. " : "")
    + (latest ? `Historia disponible hasta ${periodLabel(latest)}.` : "Sin serie disponible.");
  host.dataset.selectedPeriod = period;
  host.setAttribute("aria-describedby", note.id);
}
