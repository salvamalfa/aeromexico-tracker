/** Presentation aliases come from the source-backed, versioned wire contract. */
import type { CarrierKey, Network, OfficialRouteNetwork, Point, Route } from "./generated/official-routes";
export type MapCarrier = CarrierKey;
export type MapScope = Network["scope"];
export type MapRegion = NonNullable<Route["region"]>;
export type OfficialPoint = Point;
export type OfficialRoute = Route;
export type OfficialNetwork = Network;
export type OfficialRoutesDocument = OfficialRouteNetwork;
