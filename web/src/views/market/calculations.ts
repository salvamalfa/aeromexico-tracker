import type { MarketDocument, MarketSegmentKey } from "../../types/domain";

type Period = MarketDocument["months"][number];
export function comparisonQuarter(periods: Period[], selected: string, segment: MarketSegmentKey): Period | undefined {
  return periods.find(period => period.period_id === selected && period.segments[segment].mexican_carriers_passengers != null);
}

// A partial quarter uses exactly the available current months and the same
// calendar months one year earlier. It never borrows an older quarter or fills
// an unpublished month with zero.
export function selectedMarketPeriods(market: MarketDocument, selected: string, segment: MarketSegmentKey): { periods: Period[]; months: string[]; partial: boolean } {
  const year = Number(selected.slice(0, 4));
  const start = (Number(selected.slice(-1)) - 1) * 3 + 1;
  const ids = Array.from({length: 3}, (_, i) => `${year}M${String(start+i).padStart(2,"0")}`);
  const months = ids.filter(id => market.months.some(row => row.period_id === id && row.segments[segment].mexican_carriers_passengers != null));
  if (comparisonQuarter(market.quarters, selected, segment)) return { periods: market.quarters, months, partial: false };
  const aggregate = (targetYear: number): Period | undefined => {
    if (!months.length) return undefined;
    const rows = months.map(id => market.months.find(row => row.period_id === `${targetYear}${id.slice(4)}`)?.segments[segment]);
    if (rows.some(row => !row || row.mexican_carriers_passengers == null)) return undefined;
    const total = rows.reduce((sum, row) => sum + row!.mexican_carriers_passengers!, 0);
    const sum = (get: (row: NonNullable<typeof rows[number]>) => number | null | undefined) => {
      const values = rows.map(row => get(row!));
      return values.some(v => v == null) ? null : values.reduce<number>((a, b) => a + b!, 0);
    };
    const carriers = Object.fromEntries(["AEROMEXICO","VOLARIS","VIVA_AEROBUS"].map(key => {
      const passengers = sum(row => row.carriers[key]?.passengers);
      return [key, {passengers, share: passengers == null || total <= 0 ? null : passengers / total}];
    }));
    const passengers = sum(row => row.industry.passengers);
    const block = {mexican_carriers_passengers:total,carriers,industry:{passengers,share:passengers == null || total <= 0 ? null : passengers/total}};
    return {period_id:`${targetYear}${selected.slice(4)}`, period_label:selected, segments:{total:block,domestic:block,international:block}} as Period;
  };
  return {periods:[aggregate(year-1), aggregate(year)].filter((row): row is Period => !!row), months, partial:true};
}
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
