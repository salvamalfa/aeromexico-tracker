import type { MarketDocument,MarketSegmentKey } from "../../types/domain";
import { TOOLTIP_DOWN,TOOLTIP_UP,type UnifiedTooltipModel } from "../../lib/unified-tooltip";
import { growth } from "./calculations";

const names={AEROMEXICO:"Aeroméxico",VOLARIS:"Volaris",VIVA_AEROBUS:"Viva"};
const number=new Intl.NumberFormat("es-MX",{maximumFractionDigits:1});
export function marketMonthLabel(id:string):string {
  return new Intl.DateTimeFormat("es-MX",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(`${id.slice(0,4)}-${id.slice(-2)}-01T00:00:00Z`));
}
export function marketPointDetail(market:MarketDocument,segment:MarketSegmentKey,id:string):UnifiedTooltipModel|null {
  const current=market.months.find(row=>row.period_id===id)?.segments[segment];
  if(!current)return null;
  const previousId=`${Number(id.slice(0,4))-1}${id.slice(4)}`;
  const previous=market.months.find(row=>row.period_id===previousId)?.segments[segment];
  return {heading:marketMonthLabel(id),comparisonLabel:`vs. ${marketMonthLabel(previousId)}`,
    rows:Object.entries(names).map(([key,label])=>{
      const value=current.carriers[key],prior=previous?.carriers[key];
      const change=growth(value?.passengers,prior?.passengers);
      const share=value?.share==null?"N/D":`${number.format(value.share*100)}%`;
      const passengers=value?.passengers==null?"N/D":`${number.format(value.passengers/1e6)} millones`;
      return {label,value:`${share} (${passengers})`,change:change==null?"N/D":`${change>0?"+":""}${number.format(change)}%`,
        color:change==null||change===0?undefined:change>0?TOOLTIP_UP:TOOLTIP_DOWN};
    })};
}
