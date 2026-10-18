import { describe, expect, it } from "vitest";
import { buildChatContext, describeChatContext } from "./context";
import { initPeriods } from "../../state/period";

describe("chat dashboard context", () => {
  it("drops a card from an inactive tab instead of mixing its filters with the active tab", () => {
    document.body.innerHTML = `
      <div class="reader-tabs">
        <button role="tab" aria-selected="false" aria-controls="panel-reading"></button>
        <button role="tab" aria-selected="true" aria-controls="panel-economy"></button>
      </div>
      <section id="panel-reading" role="tabpanel" hidden>
        <section class="narrative-card"><div class="chart" id="reading-card"></div></section>
      </section>
      <section id="panel-economy" role="tabpanel">
        <section class="chart-card"><div class="chart" id="unit-chart"></div></section>
      </section>`;
    const inactiveCard = document.querySelector<HTMLElement>("#panel-reading .narrative-card")!;

    const context = buildChatContext(inactiveCard);

    expect(context.tab).toBe("economy");
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

it("omits unsupported Connect context rather than substituting Industry or its parent",()=>{
 document.body.innerHTML='<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-news"></button></div><select id="news-company"><option>Aeroméxico Connect</option></select><select id="news-month"><option>2026-07</option></select>';
 const context=buildChatContext();expect(context.tab).toBe("news");expect(context.period).toBe("2026M07");expect(context).not.toHaveProperty("entity");expect(describeChatContext(context)).toContain("Sin aerolínea preseleccionada");
 (document.getElementById("news-company") as HTMLSelectElement).innerHTML='<option value="">Todas</option>';
 expect(buildChatContext().entity).toBe("INDUSTRY");
});
