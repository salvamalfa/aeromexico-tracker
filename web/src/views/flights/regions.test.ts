import { describe, expect, it } from "vitest";
import { airportRegion, isMexican, routeRegion } from "./regions";
import type { Airport, Route } from "../../types/domain";

const airport = (iata: string, lat: number, lon: number): Airport => ({ iata, city: iata, lat, lon });

describe("isMexican", () => {
  it("classifies an airport inside the Mexican bounding box", () => {
    expect(isMexican(airport("MEX", 19.4, -99.1))).toBe(true);
  });
  it("classifies an airport outside the bounding box as not Mexican", () => {
    expect(isMexican(airport("JFK", 40.6, -73.8))).toBe(false);
  });
});

describe("airportRegion", () => {
  it("maps a listed airport to its region", () => {
    expect(airportRegion("MAD")).toBe("europa");
    expect(airportRegion("GRU")).toBe("sudamerica");
    expect(airportRegion("NRT")).toBe("asia");
  });
  it("defaults unlisted airports to norteamerica", () => {
    expect(airportRegion("JFK")).toBe("norteamerica");
  });
});

describe("routeRegion", () => {
  it("classifies by the non-Mexican endpoint when origin is Mexican", () => {
    const route = { origin: airport("MEX", 19.4, -99.1), destination: airport("MAD", 40.5, -3.6) } as Route;
    expect(routeRegion(route)).toBe("europa");
  });
  it("classifies by the non-Mexican endpoint when destination is Mexican", () => {
    const route = { origin: airport("GRU", -23.4, -46.5), destination: airport("MEX", 19.4, -99.1) } as Route;
    expect(routeRegion(route)).toBe("sudamerica");
  });
});
