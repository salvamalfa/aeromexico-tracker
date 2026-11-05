import { readFileSync } from "node:fs";
import { afterEach,expect,it,vi } from "vitest";
import type { MarketDocument } from "../../types/domain";
import { initPeriods } from "../../state/period";
import { entityState } from "../executive/entities";
import { renderMarket } from "../executive/market";
import { mountChatCardActions } from "../chat/card-actions";
import { buildChatContext } from "../chat/context";
import { mountTabs } from "../shell/tabs";

vi.mock("../../lib/plotly",()=>({default:{react:vi.fn(),Plots:{resize:vi.fn(async()=>{})}}}));
afterEach(()=>{entityState.market=null;window.history.replaceState(null,"","/");vi.restoreAllMocks();});
it("merges Mercado with exactly four financial flight KPIs and map → rich AFAC participation → mix",async()=>{
  document.body.innerHTML=readFileSync("index.html","utf8");
  document.querySelectorAll('.reader-tabs [role="tab"]').forEach(tab=>tab.setAttribute("aria-selected",String(tab.id==="tab-flights")));
  entityState.market=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/afac-official-market-september.json","utf8")) as MarketDocument;
  const opened:Array<ReturnType<typeof buildChatContext>>=[];
  const dispose=mountChatCardActions(card=>opened.push(structuredClone(buildChatContext(card))));
  expect(document.getElementById("market-details")).toBeNull();
  expect([...document.querySelectorAll('.reader-tabs [role="tab"]')].map(tab=>tab.textContent)).toEqual(["Lectura ejecutiva","Mercado","Economía unitaria","Noticias"]);
  expect(document.getElementById("tab-flights")?.textContent).toBe("Mercado");
  expect(document.getElementById("tab-market")).toBeNull(); expect(document.getElementById("panel-market")).toBeNull();
  expect(document.getElementById("market-kpis")).toBeNull();
  expect(document.querySelectorAll("#panel-flights .flight-kpi")).toHaveLength(4);
  const before=(a:string,b:string)=>expect(document.getElementById(a)!.compareDocumentPosition(document.getElementById(b)!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  before("flight-kpi-load_factor","route-flow-map"); before("route-flow-map","market-chart"); before("market-chart","mix-chart");
  for(const period of ["2026Q2","2026Q3","2026Q2"]) for(const segment of ["total","domestic","international"]) {
    initPeriods(["2026Q2","2026Q3"],period); (document.getElementById("market-segment") as HTMLSelectElement).value=segment;
    renderMarket(undefined); await Promise.resolve();
    expect(document.querySelectorAll("#panel-flights .chat-card-action")).toHaveLength(7);
    for(const card of document.querySelectorAll<HTMLElement>("#panel-flights .flight-kpi")) {
      expect(card.querySelectorAll(":scope > .chat-card-action")).toHaveLength(1);
      expect(buildChatContext(card)).toMatchObject({tab:"flights",period});
    }
    const afac=document.getElementById("market-card")!;
    expect(afac.querySelectorAll(":scope > .chat-card-action")).toHaveLength(1);
    expect(buildChatContext(afac)).toMatchObject({tab:"market",period,filters:{segment}});
    afac.querySelector<HTMLButtonElement>(".chat-card-action")!.click();
    expect(document.querySelectorAll("#market-source")).toHaveLength(1);
  }
  expect(opened).toHaveLength(9); expect(opened[0]).toMatchObject({tab:"market",period:"2026Q2"});
  dispose();
});

it.each(["#market","#flights","#tab-market","#panel-flights","?tab=market","?tab=flights"])("opens the merged Mercado view from historical link %s",async link=>{
  document.body.innerHTML=readFileSync("index.html","utf8");
  window.history.replaceState(null,"",`/${link}`);
  vi.spyOn(window,"requestAnimationFrame").mockImplementation(callback=>{callback(0);return 1;});
  mountTabs(); await Promise.resolve();
  expect(document.getElementById("tab-flights")?.getAttribute("aria-selected")).toBe("true");
  expect(document.getElementById("panel-flights")?.hidden).toBe(false);
  expect(document.getElementById("panel-economy")?.hidden).toBe(true);
});
