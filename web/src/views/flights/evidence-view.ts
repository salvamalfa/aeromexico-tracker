import type { Route, RouteDirection } from "../../types/domain";
import { finite } from "./dom";
import { flightKind, flightTotals } from "./flight-measure";
import { routeRegion } from "./regions";

export type EvidenceView = "all" | "north_america_observed";
export interface ExcludedNorthAmericaFlights {
  estimated:number; scheduled:number; attributed:number; movements:number; routes:number;
}
export const emptyExcludedFlights = ():ExcludedNorthAmericaFlights => ({estimated:0,scheduled:0,attributed:0,movements:0,routes:0});

function observedOnly(route:Route):Route | null {
  if (!route.flight_components?.length) return flightKind(route) === "observed" ? {...route,recorded_movements:undefined} : null;
  const components = route.flight_components.filter(component => component.kind === "observed");
  if (!components.length) return null;
  const directions = new Map<string,RouteDirection>();
  for (const component of components) {
    const key = `${component.origin_iata}/${component.destination_iata}`;
    const direction = directions.get(key) ?? {origin_iata:component.origin_iata,destination_iata:component.destination_iata,departures:0};
    direction.departures! += component.departures; directions.set(key,direction);
  }
  const changed = components.length !== route.flight_components.length;
  return {...route,flight_components:components,departures:components.reduce((sum,component)=>sum+component.departures,0),
    directions:[...directions.values()],source_label:[...new Set(components.map(component=>component.source_label))].join(" · "),
    operation_status:"operated_observed",recorded_movements:undefined,
    // A mixed route does not provide passengers/capacity or prior values by
    // evidence kind; do not carry an estimated value into an observed view.
    ...(changed ? {passengers:null,seats:null,load_factor:null,previous:undefined,monthly:[],capacity_estimated:false} : {})};
}

export function routeEvidenceView(routes:Route[], mode:"domestic"|"international", region:string|null) {
  const hasNorthAmericaObservations = mode === "international" && routes.some(route => routeRegion(route) === "norteamerica" && finite(flightTotals(route).observed));
  const active = mode === "international" && (!region || region === "norteamerica") && hasNorthAmericaObservations;
  const excluded = emptyExcludedFlights();
  const observedMonths = new Set<string>();
  if (!active) return {routes:[...routes],evidenceView:"all" as EvidenceView,excluded,observedMonths:[],hasNorthAmericaObservations};
  const filtered = routes.flatMap(route => {
    if (routeRegion(route) !== "norteamerica") return [route];
    const totals = flightTotals(route);
    for (const kind of ["estimated","scheduled","attributed"] as const) excluded[kind] += totals[kind] ?? 0;
    excluded.movements += route.recorded_movements?.count ?? 0;
    const observed = observedOnly(route);
    if (!observed) { excluded.routes++; return []; }
    for (const component of observed.flight_components ?? []) observedMonths.add(component.period_id);
    if (!observed.flight_components?.length) for (const row of observed.monthly ?? []) if (row.period_id) observedMonths.add(row.period_id);
    return [observed];
  });
  return {routes:filtered,evidenceView:"north_america_observed" as EvidenceView,excluded,
    observedMonths:[...observedMonths].sort(),hasNorthAmericaObservations};
}


// Period coverage is derived from the routes in this view, not the union of
// dates in another region (for example Brazil's September versus US July).
export function routeDataMonths(routes:Route[],sourceCoverage:Record<string,string[]>={}):string[]{
 const months=new Set<string>();
 for(const route of routes){
  const componentMonths=(route.flight_components??[]).map(component=>component.period_id);
  const monthly=(route.monthly??[]).filter(row=>finite(row.departures)).map(row=>row.period_id).filter((id):id is string=>!!id);
  const recorded=route.recorded_movements?.observed_months??[];
  let dates=[...componentMonths,...monthly,...recorded];
  if(!dates.length){
   const label=route.source_label??"";
   dates=Object.entries(sourceCoverage).filter(([source])=>source===label||["AeroDataBox","T-100","ANAC","Aerocivil","CAA"].some(name=>source.includes(name)&&label.includes(name))).flatMap(([,values])=>values);
  }
  for(const date of dates)months.add(date);
 }
 return [...months].sort();
}
