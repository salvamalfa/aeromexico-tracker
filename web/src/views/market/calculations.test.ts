import { describe, expect, it } from "vitest";
import { comparisonQuarter, growth, marketSnapshot } from "./calculations";
import type { MarketDocument } from "../../types/domain";
function period(id:string, values:number[]) {
 const total=values.reduce((a,b)=>a+b,0);const carriers=Object.fromEntries(["AEROMEXICO","VOLARIS","VIVA_AEROBUS"].map((key,i)=>[key,{passengers:values[i]!,share:values[i]!/total}]));
 const segment={mexican_carriers_passengers:total,carriers,industry:{passengers:total-values[3]!,share:(total-values[3]!)/total}};
 return {period_id:id,period_label:id,segments:{total:segment,domestic:segment,international:segment}};
}
describe("comparable market arithmetic",()=>{
 it("selects the exact global quarter by segment without borrowing another quarter", () => {
  const missing = period("2026Q2", [1, 2, 3, 4]);
  const rows = [period("2026Q3", [1,2,3,4]), missing, period("2026Q1", [1,2,3,4])] as MarketDocument["quarters"];
  rows[1]!.segments.international = { ...rows[1]!.segments.international, mexican_carriers_passengers: null };
  expect(comparisonQuarter(rows, "2026Q2", "total")?.period_id).toBe("2026Q2");
  expect(comparisonQuarter(rows, "2026Q2", "international")).toBeUndefined();
  expect(comparisonQuarter(rows, "2025Q4", "total")).toBeUndefined();
 });
 it("reconciles contributions including the rest and uses same period last year",()=>{
  const rows=[period("2025M06",[20,30,40,10]),period("2026M05",[10,10,10,10]),period("2026M06",[25,35,50,10])];
  const result=marketSnapshot(rows as MarketDocument["months"],"2026M06","total");
  expect(result.total).toBe(120);expect(result.growth).toBeCloseTo(20);
  expect(result.rows.reduce((sum,r)=>sum+r.contribution!,0)).toBeCloseTo(result.growth!);
  expect(result.rows[0]!.shareChange).toBeCloseTo(0.8333333);
 });
 it("preserves absent or zero bases",()=>{expect(growth(12,null)).toBeNull();expect(growth(12,0)).toBeNull();expect(growth(0,10)).toBe(-100);
  expect(marketSnapshot([period("2026Q2",[1,2,3,4])] as MarketDocument["months"],"2026Q2","total").growth).toBeNull();});
});
