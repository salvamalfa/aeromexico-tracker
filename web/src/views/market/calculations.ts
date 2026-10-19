import type { MarketDocument, MarketSegmentKey } from "../../types/domain";

type Period = MarketDocument["months"][number];
const labels: Record<string,string> = { AEROMEXICO: "Grupo Aeroméxico", VOLARIS: "Volaris", VIVA_AEROBUS: "Viva" };
export function growth(current: number | null | undefined, prior: number | null | undefined): number | null {
  return current == null || prior == null || prior <= 0 ? null : (current / prior - 1) * 100;
}
export function marketSnapshot(periods: Period[], id: string, segment: MarketSegmentKey) {
  const current = periods.find(p => p.period_id === id)?.segments[segment];
  const priorId = `${Number(id.slice(0,4))-1}${id.slice(4)}`;
  const prior = periods.find(p => p.period_id === priorId)?.segments[segment];
  const total = current?.mexican_carriers_passengers ?? null;
  const base = prior?.mexican_carriers_passengers ?? null;
  const rows = Object.entries(labels).map(([key,label]) => {
    const value = current?.carriers[key]; const previous = prior?.carriers[key];
    return { label, passengers: value?.passengers ?? null, growth: growth(value?.passengers,previous?.passengers), share: value?.share == null ? null : value.share*100,
      shareChange: value?.share == null || previous?.share == null ? null : (value.share-previous.share)*100,
      contribution: total == null || base == null || base <= 0 || value?.passengers == null || previous?.passengers == null ? null : (value.passengers-previous.passengers)/base*100 };
  });
  const rest = total == null || current?.industry.passengers == null ? null : total-current.industry.passengers;
  const previousRest = base == null || prior?.industry.passengers == null ? null : base-prior.industry.passengers;
  rows.push({ label:"Resto de aerolíneas mexicanas", passengers:rest, growth:growth(rest,previousRest), share:rest == null || total == null || total<=0 ? null : rest/total*100,
    shareChange: rest==null || total==null || total<=0 || previousRest==null || base==null || base<=0 ? null : (rest/total-previousRest/base)*100,
    contribution:rest==null || previousRest==null || base==null || base<=0 ? null : (rest-previousRest)/base*100 });
  return { total, growth:growth(total,base), delta:total==null||base==null?null:total-base, rows };
}
export function formatMarketNumber(value: number | null | undefined, suffix=""): string {
  return value == null ? "N/D" : new Intl.NumberFormat("es-MX",{maximumFractionDigits:suffix ? 2 : 0}).format(value)+suffix;
}
