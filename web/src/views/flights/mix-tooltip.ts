import type { MarketDocument, MarketSegmentKey } from "../../types/domain";
import type { EntityKey } from "../shell/carriers";
import { ENTITY_LABELS } from "../shell/carriers";
import { bindUnifiedTooltip, TOOLTIP_UP, TOOLTIP_DOWN, type UnifiedTooltipModel } from "../../lib/unified-tooltip";

let tooltipRequest=0;
export function scheduleMixTooltip(rendered:unknown,keys:string[],provider:(key:string,index:number)=>UnifiedTooltipModel|null):void{
 const request=++tooltipRequest;
 void Promise.resolve(rendered).then(()=>{if(request===tooltipRequest)bindUnifiedTooltip("mix-chart",keys,provider);});
}

type Segment = Extract<MarketSegmentKey,"domestic"|"international">;
const monthName=(month:string)=>new Intl.DateTimeFormat("es-MX",{month:"long",timeZone:"UTC"}).format(new Date(`${month.slice(0,4)}-${month.slice(5,7)}-01T00:00:00Z`));
const prior=(id:string)=>`${Number(id.slice(0,4))-1}${id.slice(4)}`;
const finite=(value:unknown):value is number=>typeof value==="number"&&Number.isFinite(value);
export const mixGrowth=(value:number|null,base:number|null):number|null=>finite(value)&&finite(base)&&base>0?(value/base-1)*100:null;
const compact=(value:number|null)=>finite(value)?`${(value/1e6).toFixed(1)} M`:"N/D";
const periodLabel=(id:string)=>id.includes("Q")?`${id.slice(-1)}T${id.slice(2,4)}`:`${monthName(id)} de ${id.slice(0,4)}`;
function expectedMonths(id:string):string[]{
 if(id.includes("M"))return[id];const start=(Number(id.slice(-1))-1)*3+1;
 return[0,1,2].map(offset=>`${id.slice(0,4)}M${String(start+offset).padStart(2,"0")}`);
}
function comparisonLabel(id:string,months:string[]):string{
 if(id.includes("M")||months.length===3)return `vs. ${periodLabel(prior(id))}`;
 if(!months.length)return `vs. ${periodLabel(prior(id))}`;
 const names=months.map(monthName),numbers=months.map(month=>Number(month.slice(5,7)));
 const consecutive=numbers.every((month,index)=>index===0||month===numbers[index-1]!+1);
 return `vs. ${names.length===1?names[0]:consecutive?`${names[0]}–${names.at(-1)}`:names.join(" y ")} de ${Number(id.slice(0,4))-1}`;
}
function change(value:number|null,base:number|null){
 const growth=mixGrowth(value,base);
 return growth==null?{change:"N/D",color:"#657188"}
  : {change:`${growth>0?"+":""}${growth.toFixed(1)}%`,color:growth>0?TOOLTIP_UP:growth<0?TOOLTIP_DOWN:"#657188"};
}
function valueFor(market:MarketDocument,entity:EntityKey,id:string,segment:Segment):number|null{
 const row=(id.includes("Q")?market.quarters:market.months).find(item=>item.period_id===id);
 const block=row?.segments[segment];return (entity==="INDUSTRY"?block?.industry:block?.carriers[entity])?.passengers??null;
}

export function afacMixTooltip(market:MarketDocument,entities:EntityKey[],id:string):UnifiedTooltipModel{
 const multiple=entities.length>1;
 const rows=entities.flatMap(entity=>(["domestic","international"] as const).map(segment=>{
  const value=valueFor(market,entity,id,segment),months=expectedMonths(id).filter(month=>finite(valueFor(market,entity,month,segment)));
  const currentMonths=months.map(month=>valueFor(market,entity,month,segment));
  const previousMonths=months.map(month=>valueFor(market,entity,prior(month),segment));
  // Compare the same observed months; never substitute a previous partial
  // quarter or compare a full current value with fewer prior months.
  const monthlySum=currentMonths.reduce<number>((sum,item)=>sum+(item??0),0);
  const comparable=months.length>0&&currentMonths.every(finite)&&previousMonths.every(finite)
    &&finite(value)&&Math.abs(monthlySum-value)<.5;
  const base=comparable?previousMonths.reduce<number>((sum,item)=>sum+(item??0),0):null;
  return {label:`${multiple?ENTITY_LABELS[entity]+" · ":""}${segment==="domestic"?"Nacional":"Internacional"}`,value:compact(value),...change(value,base),baseLabel:comparisonLabel(id,months)};
 }));
 const common=[...new Set(rows.map(row=>row.baseLabel))];
 return {heading:periodLabel(id),comparisonLabel:common.length===1?common[0]!:"vs. año anterior",
  rows:rows.map(({baseLabel,...row})=>({...row,change:common.length===1?row.change:`${row.change} · ${baseLabel}`}))};
}

export interface MixPoint {date:string;domestic:number|null;international:number|null;}
export function seriesMixTooltip(points:MixPoint[],id:string,grain:"month"|"quarter",booked=false):UnifiedTooltipModel{
 const key=(point:MixPoint)=>grain==="month"?point.date.slice(0,7).replace("-","M"):`${point.date.slice(0,4)}Q${Math.floor((Number(point.date.slice(5,7))-1)/3)+1}`;
 const current=points.find(point=>key(point)===id),previous=points.find(point=>key(point)===prior(id));
 return {heading:periodLabel(id)+(booked?" · tramos reservados":""),comparisonLabel:`vs. ${periodLabel(prior(id))}`,
  rows:(["domestic","international"] as const).map(segment=>({label:segment==="domestic"?"Nacional":"Internacional",value:compact(current?.[segment]??null),...change(current?.[segment]??null,previous?.[segment]??null)}))};
}
