// Route coverage indicators (rank colors, scheduled-flight icon) and source
// footers. Ported from src/dashboard/assets/flights.js.

import { esc, finite } from "./dom";
import type { Route } from "../../types/domain";

// Cuenta los meses del trimestre que la fuente reportó para esta ruta.
// Solo las notas con desglose mensual ("Meses: 04, 05") lo declaran; las
// fuentes de programación trimestral no traen el dato y no llevan punto.
const MONTH_ABBR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function coverageMonths(route: Route): number | null {
  if (route.flight_components?.length) {
    const operative = route.flight_components.filter((c) => c.kind !== "scheduled");
    const scopes = new Map<string, Set<string>>();
    for (const c of operative.length ? operative : route.flight_components) {
      const key = `${c.carrier_key}|${c.origin_iata}|${c.destination_iata}`;
      const months = scopes.get(key) ?? new Set<string>();
      months.add(c.period_id);
      scopes.set(key, months);
    }
    return Math.min(...[...scopes.values()].map((months) => months.size));
  }
  const note = route.coverage_note || "";
  const listed = /^Meses:\s*([\d,\s]+)/.exec(note);
  if (listed) return listed[1]!.split(",").map((part) => part.trim()).filter(Boolean).length || null;
  const lower = note.toLowerCase();
  const span = new RegExp(String.raw`\b(${MONTH_ABBR.join("|")})[–—-](${MONTH_ABBR.join("|")})\b`).exec(lower);
  if (span) return (((MONTH_ABBR.indexOf(span[2]!) - MONTH_ABBR.indexOf(span[1]!)) % 12 + 12) % 12) + 1;
  if (new RegExp(String.raw`\b(${MONTH_NAMES.join("|")})\b`).test(lower)) return 1;
  return null;
}

// Los slots del AICM y el anuncio fechado de OMA son programación: la fuente
// dice que el vuelo estaba previsto, no que se realizó. El icono los separa
// de lo observado sin gastar una columna ni una línea de texto.
export const SCHEDULED_STATUSES = ["assigned_slot_not_flown", "scheduled_from_dated_release"];

export function scheduledIconHtml(route: Route): string {
  if (!route.operation_status || !(route.operation_status === "assigned_slot_not_flown" || route.operation_status.startsWith("scheduled_"))) return "";
  const title = "Vuelos programados: la fuente no confirma que se hayan realizado";
  return `<span class="route-scheduled-mark" title="${title}" aria-label="${title}" role="img"><svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 1.6 15 14H1z"></path><rect x="7.2" y="6" width="1.6" height="4" rx=".8"></rect><circle cx="8" cy="11.6" r=".95"></circle></svg></span>`;
}

export function coverageIndicator(route: Route, selectedMonthCount = 3): { variant: string; title: string } | null {
  if ((route.operation_status ?? "").includes("partial_frequencies")) return {
    variant: "is-partial", title: "Frecuencias conocidas; hay operadores o sentidos sin conteo, sin completar con cero",
  };
  if (route.flight_components?.length) {
    const months = coverageMonths(route)!;
    const ratio = months / selectedMonthCount;
    return { variant: ratio >= 1 ? "is-full" : ratio >= 0.5 ? "is-partial" : "is-thin",
      title: `${months} de ${selectedMonthCount} ${selectedMonthCount === 1 ? "mes" : "meses"} como mínimo por operador y sentido con cifras; no acredita cobertura completa de vuelos` };
  }
  if (finite(route.months_covered) && finite(route.months_selected) && route.months_selected > 0) {
    // Agregado nacional multi-mes: mismo criterio que Internacional
    // (verde/amarillo/rojo según cuántos meses de calendario del
    // trimestre completo tienen datos de esta ruta), no un promedio.
    const ratio = route.months_covered / route.months_selected;
    const variant = ratio >= 1 ? "is-full" : ratio >= 0.5 ? "is-partial" : "is-thin";
    const title = `${route.months_covered} de ${route.months_selected} ${route.months_selected === 1 ? "mes" : "meses"} del periodo seleccionado con datos de esta ruta`;
    return { variant, title };
  }
  if (route.passengers_estimated) return null;
  const months = coverageMonths(route);
  if (!months) return null;
  const ratio = months / selectedMonthCount;
  const variant = ratio >= 1 ? "is-full" : ratio >= 0.5 ? "is-partial" : "is-thin";
  const title = `${months} de ${selectedMonthCount} ${selectedMonthCount === 1 ? "mes" : "meses"} del periodo seleccionado con datos de la fuente`;
  return { variant, title };
}

const SOURCE_SHORT_LABELS: Record<string, string> = {
  "Estados Unidos · BTS T-100": "BTS T-100",
  "México · AICM, vuelos AM programados": "AICM",
  "AICM · vuelos AM programados": "AICM",
  "Brasil · ANAC": "ANAC",
  "Colombia · Aerocivil": "Aerocivil",
  "AIFA · ruta de Aeroméxico identificada; volumen propio sin desglose": "AIFA",
  "AFAC · mercado con Aeroméxico como único operador identificado": "AFAC",
  "AFAC + AeroDataBox + flota Aeroméxico · estimaciones": "AFAC + AeroDataBox + flota (estimación)",
  "OMA · rutas documentadas": "OMA",
  "AFAC + AeroDataBox · Grupo Aeroméxico estimado": "AFAC + AeroDataBox (estimación)",
  "Reino Unido · CAA": "CAA",
};

export function shortSourceLabel(label?: string): string {
  return (label && SOURCE_SHORT_LABELS[label]) || label || "";
}

export function sourceFooterHtml(tableRoutes: Route[]): string {
  const labels = [...new Set((tableRoutes || []).map((route) => shortSourceLabel(route.source_label)).filter(Boolean))].sort();
  if (!labels.length) return "";
  return `<p class="route-source-footer">${labels.length === 1 ? "Fuente" : "Fuentes"}: ${esc(labels.join(" · "))}</p>`;
}
