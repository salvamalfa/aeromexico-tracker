import { expect,it } from "vitest";
import { mountChatCardActions } from "./card-actions";
it("does not advertise a chat tool for an unsupported dataset",()=>{
 document.body.innerHTML='<main class="page-shell"><article class="chart-card" id="supported"></article><article class="chart-card" id="airport" data-chat-unavailable></article></main>';
 const dispose=mountChatCardActions(()=>{});
 expect(document.querySelectorAll("#supported .chat-card-action")).toHaveLength(1);
 expect(document.querySelectorAll("#airport .chat-card-action")).toHaveLength(0);
 dispose();
});

it("places information beside a KPI label and keeps its tooltip separate from the attachment title",()=>{
 document.body.innerHTML='<main class="page-shell"><article class="kpi-card"><span class="kpi-info" title="Definición del ingreso">i</span><p class="kpi-label">RASK</p></article></main>';
 const dispose=mountChatCardActions(()=>{});
 expect(document.querySelector(".kpi-label > .kpi-info")?.getAttribute("title")).toBe("Definición del ingreso");
 expect(document.querySelector(".chat-card-action")?.getAttribute("aria-label")).toBe("Preguntar sobre RASK");
 expect(document.querySelector(".chat-card-action")?.textContent).toBe("Pregunta");
 dispose();expect(document.querySelector(".kpi-card > .kpi-info")).not.toBeNull();
});

it("keeps the flight KPI information selector and tooltip beside its label",()=>{
 document.body.innerHTML='<main class="page-shell"><article class="flight-kpi"><span class="info" title="Fuente financiera">i</span><p>Pasajeros</p><p id="flight-kpi-passengers">22 M</p></article></main>';
 const dispose=mountChatCardActions(()=>{});
 expect(document.querySelector(".flight-kpi > p > .info svg")).not.toBeNull();
 expect(document.querySelector(".flight-kpi .info")?.getAttribute("title")).toBe("Fuente financiera");
 expect(document.querySelector(".chat-card-action")?.getAttribute("aria-label")).toBe("Preguntar sobre Pasajeros");
 dispose();expect(document.querySelector(".flight-kpi > .info")).not.toBeNull();
});

it("gives each flight graph its own action, without a shell-level floating button", () => {
  document.body.innerHTML = `<main class="page-shell"><div class="flights-view"><div class="flights-shell">
    <article class="panel flow-map-panel" id="map-panel"><div class="chart" id="route-flow-map"></div></article>
    <article class="panel chart-panel"><div class="panel-heading"><p class="panel-title">Pasajeros por segmento</p></div><div class="chart" id="mix-chart"></div></article>
  </div></div><div id="news-heading"><h2>Noticias y estrategia</h2></div></main>`;
  const opened: string[] = [];
  const dispose = mountChatCardActions((card) => opened.push(card.querySelector(".chart")?.id ?? card.id));
  expect(document.querySelector(".flights-shell > .chat-card-action")).toBeNull();
  expect(document.querySelectorAll(".flights-view .panel > .chat-card-action")).toHaveLength(2);
  expect(document.querySelector("#map-panel > .chat-card-action")?.getAttribute("aria-label")).toBe("Preguntar sobre Mapa de rutas");
  expect(document.querySelector(".chart-panel > .chat-card-action")?.getAttribute("aria-label")).toBe("Preguntar sobre Pasajeros por segmento");
  document.querySelectorAll<HTMLButtonElement>(".chat-card-action").forEach(button => button.click());
  expect(opened).toEqual(["route-flow-map", "mix-chart", "news-heading"]);
  dispose(); expect(document.querySelectorAll(".chat-card-action")).toHaveLength(0);
});

it("refreshes an existing action when its chart title changes without duplicating its listener", async () => {
  document.body.innerHTML = '<main class="page-shell"><article class="chart-card"><p class="chart-title">RASK · Industria<button class="market-source-info">Información de fuente</button></p></article></main>';
  const opened: Element[] = [];
  const dispose = mountChatCardActions(card => opened.push(card));
  const action = document.querySelector<HTMLButtonElement>(".chat-card-action")!;
  expect(action.getAttribute("aria-label")).toBe("Preguntar sobre RASK · Industria");
  document.querySelector(".chart-title")!.innerHTML = 'Margen unitario por aerolínea<button class="market-source-info">Información de fuente</button>';
  await Promise.resolve();
  window.dispatchEvent(new Event("reader-tab-visible"));
  expect(document.querySelectorAll(".chat-card-action")).toHaveLength(1);
  expect(document.querySelector(".chat-card-action")).toBe(action);
  expect(action.getAttribute("aria-label")).toBe("Preguntar sobre Margen unitario por aerolínea");
  action.click();
  expect(opened).toEqual([document.querySelector(".chart-card")]);
  dispose();
});
