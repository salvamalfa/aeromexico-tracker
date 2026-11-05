import { readFileSync } from "node:fs";
import { expect,it } from "vitest";
import type { MarketDocument,MarketSegmentKey } from "../../types/domain";
import { marketPointDetail } from "./point-detail";
import { TOOLTIP_DOWN,TOOLTIP_UP } from "../../lib/unified-tooltip";
const market=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/afac-official-market-september.json","utf8")) as MarketDocument;
it("uses actual monthly AFAC share, compact passengers and YoY against the same month and segment",()=>{
  const nf=new Intl.NumberFormat("es-MX",{maximumFractionDigits:1}),colors=new Set<string|undefined>();
  for(const month of ["2023M02","2026M07","2026M09"])for(const segment of ["total","domestic","international"] as MarketSegmentKey[]) {
    const model=marketPointDetail(market,segment,month)!;
    const before=`${Number(month.slice(0,4))-1}${month.slice(4)}`;
    expect(model.heading).toContain(month.slice(0,4));expect(model.comparisonLabel).toContain(before.slice(0,4));
    expect(model.rows).toHaveLength(3);
    for(const [index,key] of ["AEROMEXICO","VOLARIS","VIVA_AEROBUS"].entries()) {
      const current=market.months.find(row=>row.period_id===month)!.segments[segment].carriers[key]!;
      const prior=market.months.find(row=>row.period_id===before)!.segments[segment].carriers[key]!;
      const change=(current.passengers!/prior.passengers!-1)*100;
      expect(model.rows[index]!.value).toBe(`${nf.format(current.share!*100)}% (${nf.format(current.passengers!/1e6)} millones)`);
      expect(model.rows[index]!.change).toBe(`${change>0?"+":""}${nf.format(change)}%`);
      expect(model.rows[index]!.color).toBe(change>0?TOOLTIP_UP:change<0?TOOLTIP_DOWN:undefined);
      colors.add(model.rows[index]!.color);
    }
  }
  expect(colors.has(TOOLTIP_UP)).toBe(true);expect(colors.has(TOOLTIP_DOWN)).toBe(true);
  expect(marketPointDetail(market,"total","2023M02")?.heading).toBe("febrero de 2023");
  expect(marketPointDetail(market,"total","2023M02")?.comparisonLabel).toBe("vs. febrero de 2022");
});
it("keeps missing or zero prior bases unavailable without inventing monthly changes",()=>{
  const copy=structuredClone(market);copy.months=copy.months.filter(row=>row.period_id!=="2025M09");
  expect(marketPointDetail(copy,"total","2026M09")!.rows.every(row=>row.change==="N/D")).toBe(true);
  const prior=structuredClone(market);prior.months.find(row=>row.period_id==="2025M09")!.segments.total.carriers.AEROMEXICO!.passengers=0;
  expect(marketPointDetail(prior,"total","2026M09")!.rows[0]!.change).toBe("N/D");
});
