import { beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { buildChatContext, describeChatContext } from "./context";
import { mountPicker } from "../shell/carriers";
import { state as flightState } from "../flights/state";
import { initPeriods } from "../../state/period";
import { officialState } from "../flights/official-routes";
import type { OfficialRoutesDocument } from "../../types/official-routes";
beforeEach(() => { Object.assign(officialState, { scope:"national", region:null, carriers:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"], document:null, network:null }); });

describe("chat dashboard context", () => {
  it("uses the global reading quarter and Industry even with obsolete selectors", () => {
    initPeriods(["2026Q1", "2026Q2"], "2026Q2");
    document.body.innerHTML = '<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-reading"></button></div><select id="reading-period"><option value="2026Q3">3T26</option></select>';
    const context = buildChatContext();
    expect(context.period).toBe("2026Q2");
    expect(context.entity).toBe("INDUSTRY");
    expect(describeChatContext(context)).toContain("2T26");
    initPeriods(["2026Q1", "2026Q2"], "2026Q1");
    expect(buildChatContext().period).toBe("2026Q1");
    document.querySelector("[role=tab]")!.setAttribute("aria-controls", "panel-economy");
    expect(buildChatContext().period).toBe("2026Q1");
    document.querySelector("[role=tab]")!.setAttribute("aria-controls", "panel-reading");
    (document.querySelector("#reading-period") as HTMLSelectElement).disabled = true;
    expect(buildChatContext().period).toBe("2026Q1");
    (document.querySelector("#reading-period") as HTMLSelectElement).disabled = false;
    (document.querySelector("#reading-period") as HTMLSelectElement).innerHTML = '<option value="../../escape">Invalid</option>';
    expect(buildChatContext().period).toBe("2026Q1");
    document.querySelector("#reading-period")!.remove();
    expect(buildChatContext().period).toBe("2026Q1");
  });
  it("drops a card from an inactive tab instead of mixing its filters with the active tab", () => {
    initPeriods(["2026Q2"], "2026Q2");
    document.body.innerHTML = `
      <div class="reader-tabs">
        <button role="tab" aria-selected="false" aria-controls="panel-reading"></button>
        <button role="tab" aria-selected="true" aria-controls="panel-economy"></button>
      </div>
      <section id="panel-reading" role="tabpanel" hidden>
        <select id="reading-period"><option value="2026Q3">3T26</option></select>
        <section class="narrative-card"><div class="chart" id="reading-card"></div></section>
      </section>
      <section id="panel-economy" role="tabpanel">
        <section class="chart-card"><div class="chart" id="unit-chart"></div></section>
      </section>`;
    const inactiveCard = document.querySelector<HTMLElement>("#panel-reading .narrative-card")!;

    const context = buildChatContext(inactiveCard);

    expect(context.tab).toBe("economy");
    expect(context.period).toBe("2026Q2");
    expect(context.card_id).toBeUndefined();
    expect(context.filters).toBeUndefined();
  });
});


it("keeps the global quarter and AFAC segment while withholding unsupported airport card context",()=>{
 initPeriods(["2026Q1", "2026Q2"], "2026Q2");
 document.body.innerHTML=`<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-market"></button></div><section id="panel-market" role="tabpanel"><select id="market-segment"><option selected>international</option></select><article class="chart-card" id="airport-demand-card" data-chat-unavailable><button id="airport-source">Source</button></article></section>`;
 const context=buildChatContext(document.getElementById("airport-source"));
 expect(context.tab).toBe("market");expect(context.period).toBe("2026Q2");expect(context.filters?.segment).toBe("international");expect(context.card_id).toBeUndefined();
});

it("keeps the exact global quarter for questions despite a stale market comparison marker", () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  document.body.innerHTML = '<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-market"></button></div><section id="panel-market" role="tabpanel"><article class="chart-card" id="market-card" data-comparison-period="2026Q2"><div class="chart" id="market-chart"></div><button id="ask-market">Preguntar</button></article></section>';
  expect(buildChatContext(document.getElementById("ask-market")).period).toBe("2026Q3");
  expect(buildChatContext(document.getElementById("market-chart")).period).toBe("2026Q3");
  expect(buildChatContext().period).toBe("2026Q3");
});

it("passes the selected global quarter into News context along with other views", () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  for (const tab of ["reading", "economy", "flights", "market", "news"]) {
    document.body.innerHTML = `<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-${tab}"></button></div><section id="panel-${tab}" role="tabpanel"></section>`;
    const context = buildChatContext(undefined, true);
    expect(context.tab).toBe(tab === "flights" ? "market" : tab);
    expect(context.period).toBe("2026Q3");
  }
});

it("omits unsupported Connect context rather than substituting Industry or its parent",()=>{
 initPeriods(["2026Q2", "2026Q3"], "2026Q3");
 document.body.innerHTML='<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-news"></button></div><select id="news-company"><option>Aeroméxico Connect</option></select><select id="news-month"><option>2026-07</option></select>';
 const context=buildChatContext();expect(context.tab).toBe("news");expect(context.period).toBe("2026Q3");expect(context).not.toHaveProperty("entity");expect(describeChatContext(context)).toContain("3T26");expect(describeChatContext(context)).toContain("Sin aerolínea preseleccionada");
 (document.getElementById("news-company") as HTMLSelectElement).innerHTML='<option value="">Todas</option>';
 expect(buildChatContext().entity).toBe("INDUSTRY");
});

it("attaches each flight graph with its own airlines and the global quarter", () => {
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  document.body.innerHTML = `<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-flights"></button></div>
  <section id="panel-flights" role="tabpanel"><div class="flights-view"><div class="flights-shell">
    <div id="pick-map"></div><div id="pick-mix"></div>
    <article class="panel flow-map-panel" id="map-panel"><div class="chart" id="route-flow-map"></div><button id="ask-map">Pregunta</button></article>
    <article class="panel chart-panel"><div class="chart" id="mix-chart"></div><button id="ask-mix">Pregunta</button></article>
  </div></div></section>`;
  mountPicker(document.getElementById("pick-map")!, {card:"map", multi:true, defaults:["AEROMEXICO", "VOLARIS"]}, () => {});
  mountPicker(document.getElementById("pick-mix")!, {card:"mix", multi:true, defaults:["VIVA_AEROBUS"]}, () => {});
  flightState.networkMode = "international"; flightState.selectedRegion = "europa"; flightState.passengerPeriod = "month";
  flightState.periodIndex = 0; flightState.mapPeriodId = "2015M01";
  officialState.scope = "us"; officialState.carriers = ["AEROMEXICO", "VOLARIS"];
  const map = buildChatContext(document.getElementById("ask-map"), true);
  expect(map.card_id).toBe("route-flow-map"); expect(map.entity).toEqual(["AEROMEXICO", "VOLARIS"]);
  expect(map.period).toBe("2026Q3"); expect(map.filters?.map_carriers).toEqual(["AEROMEXICO", "VOLARIS"]);
  expect(map.filters?.map_scope).toBe("us"); expect(map.filters?.map_grain).toBe("airport_pair");
  expect(map.filters?.network_mode).toBeUndefined(); expect(map.filters?.entities).toBeUndefined();
  const mix = buildChatContext(document.getElementById("ask-mix"));
  expect(mix.card_id).toBe("mix-chart"); expect(mix.entity).toEqual(["VIVA_AEROBUS"]);
  expect(mix.filters).toMatchObject({start:"2026M07", end:"2026M09", entities:["VIVA_AEROBUS"]});
});

it("snapshots official map filters without attributing AFAC cities to the tracker airlines or leaking map filters",()=>{
  initPeriods(["2026Q3"],"2026Q3");
  document.body.innerHTML='<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-flights"></button></div><section id="panel-flights" role="tabpanel"><article class="panel flow-map-panel"><div class="chart" id="route-flow-map"></div></article><article class="panel chart-panel"><div class="chart" id="mix-chart"></div></article><article class="flight-kpi"><p id="flight-kpi-passengers">Pass</p></article></section>';
  officialState.scope="us"; officialState.carriers=["AEROMEXICO","VOLARIS","VIVA_AEROBUS"];
  const map=document.getElementById("route-flow-map")!;
  const snapshot=structuredClone(buildChatContext(map, true));
  expect(snapshot.filters?.map_scope).toBe("us");
  expect(describeChatContext(snapshot)).toContain("EE. UU.");
  officialState.scope="international";
  for(const region of ["europe","south_america","asia"] as const) {
    officialState.region=region;
    const context=buildChatContext(map, true);
    expect(context.entity).toBeUndefined(); expect(context.filters?.map_carriers).toBeUndefined();
    expect(context.filters?.map_region).toBe(region); expect(describeChatContext(context)).toContain("Todas las aerolíneas");
  }
  expect(buildChatContext(document.getElementById("mix-chart"), true).filters?.map_scope).toBeUndefined();
  expect(buildChatContext(document.getElementById("flight-kpi-passengers"), true).filters?.map_scope).toBeUndefined();
  document.querySelector('[role="tab"]')!.setAttribute("aria-controls","panel-market");
  document.querySelector('section')!.id="panel-market";
  expect(buildChatContext(map, true).entity).toBeUndefined(); expect(buildChatContext(map, true).filters?.map_scope).toBe("international");
  officialState.scope="national"; officialState.region=null;
  expect(snapshot.filters?.map_scope).toBe("us");
});

it("carries the same exact official dataset and visible month window for general and attached Mercado questions", () => {
  const doc = JSON.parse(readFileSync("../tests/fixtures/web/official_routes_sample.json", "utf8")) as OfficialRoutesDocument;
  initPeriods(["2026Q2", "2026Q3"], "2026Q2");
  document.body.innerHTML='<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-flights"></button></div><section id="panel-flights" role="tabpanel"><article class="panel flow-map-panel"><div class="chart" id="route-flow-map"></div></article></section>';
  officialState.document = doc;
  for (const scope of ["national", "us", "international"] as const) {
    officialState.scope = scope;
    officialState.network = doc.networks.find(n => n.scope === scope && (scope !== "us" || n.carrier_keys.length === 3))!;
    for (const attached of [false, true]) {
      const snapshot = buildChatContext(attached ? document.getElementById("route-flow-map") : null, true);
      expect(snapshot).toMatchObject({ tab:"market", period:"2026Q2", filters:{ map_scope:scope, map_dataset_version:doc.dataset_version, map_months:officialState.network.observed_months } });
      expect(snapshot.card_id).toBe(attached ? "route-flow-map" : undefined);
      if (scope !== "us") { expect(snapshot.entity).toBeUndefined(); expect(snapshot.filters?.map_carriers).toBeUndefined(); }
      else expect(snapshot.filters?.map_carriers).toEqual(["AEROMEXICO","VOLARIS","VIVA_AEROBUS"]);
      const months = [...snapshot.filters!.map_months!];
      officialState.network = { ...officialState.network, observed_months:[...officialState.network.observed_months] };
      expect(snapshot.filters!.map_months).toEqual(months);
      expect(snapshot.filters!.map_months).not.toBe(officialState.network.observed_months);
    }
  }
});
