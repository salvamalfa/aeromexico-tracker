import { describe, expect, it } from "vitest";
import type { Route } from "../../types/domain";
import { coverageIndicator, coverageMonths } from "./coverage";
import { flightScheduleNote, flightSource } from "./flight-measure";

function component(month: string, origin = "LAX", destination = "MEX", kind = "observed", carrier = "AEROMEXICO", departures = 10) {
  return { carrier_key: carrier, origin_iata: origin, destination_iata: destination,
    period_id: month, kind, departures, source_label: kind === "scheduled" ? "AICM · vuelos AM programados" : "Estados Unidos · BTS T-100", source_hashes: [] };
}
function route(components: ReturnType<typeof component>[]): Route {
  return { departures: 630, source_label: "Estados Unidos · BTS T-100", flight_components: components } as unknown as Route;
}

describe("operator/direction coverage and programming provenance", () => {
  it("keeps a missing June direction partial despite a three-month union", () => {
    const r = route([
      ...["2026M04", "2026M05", "2026M06"].map(m => component(m)),
      ...["2026M04", "2026M05"].map(m => component(m, "MEX", "LAX")),
      component("2026M06", "MEX", "LAX", "scheduled", "AEROMEXICO_GROUP"),
    ]);
    expect(coverageMonths(r)).toBe(2);
    expect(coverageIndicator(r, 3)?.variant).toBe("is-partial");
  });
  it("checks each operator as well as each direction", () => {
    const r = route([
      ...["2026M04", "2026M05", "2026M06"].map(m => component(m)),
      component("2026M06", "LAX", "MEX", "estimated", "AEROMEXICO_CONNECT"),
    ]);
    expect(coverageMonths(r)).toBe(1);
    expect(coverageIndicator(r, 3)?.variant).toBe("is-thin");
  });
  it("applies the same scope rule to scheduled-only routes", () => {
    const r = route([
      ...["2026M04", "2026M05", "2026M06"].map(m => component(m, "LAX", "MEX", "scheduled", "AEROMEXICO_GROUP")),
      component("2026M04", "MEX", "LAX", "scheduled", "AEROMEXICO_GROUP"),
    ]);
    expect(coverageMonths(r)).toBe(1);
  });
  it("names the schedule source in the separate count and source footer", () => {
    const r = route([component("2026M06"), component("2026M06", "MEX", "LAX", "scheduled", "AEROMEXICO_GROUP", 296)]);
    expect(flightScheduleNote(r)).toContain("296 programados");
    expect(flightScheduleNote(r)).toContain("AICM");
    expect(flightScheduleNote(r)).toContain("MEX → LAX");
    expect(flightSource(r)).toContain("AICM");
    expect(flightSource(r)).toContain("BTS T-100");
  });
  it("distinguishes a two-direction schedule from a one-direction operative headline", () => {
    const r = route([component("2026M06", "LAX", "MEX", "observed", "AEROMEXICO", 143),
      component("2026M06", "LAX", "MEX", "scheduled", "AEROMEXICO_GROUP", 149),
      component("2026M06", "MEX", "LAX", "scheduled", "AEROMEXICO_GROUP", 147)]);
    expect(flightScheduleNote(r)).toBe("296 programados · AICM · ambos sentidos (fuera del total)");
  });
  it("counts an explicit observed zero as reported scope coverage", () => {
    const r = route([component("2026M06", "LAX", "MEX", "observed", "AEROMEXICO", 0)]);
    expect(coverageMonths(r)).toBe(1);
    expect(coverageIndicator(r, 1)?.variant).toBe("is-full");
  });
});
