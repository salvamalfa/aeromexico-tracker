import { beforeEach, expect, it } from "vitest";
import { attachChatCard } from "./attachment";
import { initPeriods } from "../../state/period";
import { officialState } from "../flights/official-routes";

beforeEach(() => {
  initPeriods(["2026Q3"], "2026Q3");
  document.body.innerHTML = '<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-flights"></button></div><section id="panel-flights" role="tabpanel"><article id="map-panel" class="panel flow-map-panel"><div class="chart" id="route-flow-map"></div></article></section><aside id="chat"><div data-chat-attachment hidden><span data-chat-attachment-label></span></div></aside>';
  Object.assign(officialState, { scope:"international", region:"europe", document:null, network:null, carriers:["AEROMEXICO","VOLARIS"] });
});
it("shows AFAC geography and all-airline scope in the visible chip, and freezes the attached selection", () => {
  const context = attachChatCard(document.getElementById("chat")!, document.getElementById("map-panel")!, true);
  const chip = document.querySelector("[data-chat-attachment-label]")!.textContent!;
  expect(chip).toContain("Europa"); expect(chip).toContain("Todas las aerolíneas"); expect(chip).toContain("3T26");
  expect(chip).not.toContain("Grupo Aeroméxico"); expect(context?.entity).toBeUndefined();
  officialState.region = "asia"; officialState.scope = "us";
  expect(context?.filters?.map_scope).toBe("international"); expect(context?.filters?.map_region).toBe("europe");
  expect(document.querySelector("[data-chat-attachment-label]")!.textContent).toBe(chip);
});
it("names the selected BTS groups in the visible chip without interpreting a city code as an airline", () => {
  officialState.scope = "us";
  const context = attachChatCard(document.getElementById("chat")!, document.getElementById("map-panel")!, true);
  const chip = document.querySelector("[data-chat-attachment-label]")!.textContent!;
  expect(chip).toContain("EE. UU."); expect(chip).toContain("Grupo Aeroméxico, Volaris");
  expect(context?.filters?.map_carriers).toEqual(["AEROMEXICO","VOLARIS"]);
});
