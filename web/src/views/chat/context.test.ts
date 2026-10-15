import { describe, expect, it } from "vitest";
import { buildChatContext } from "./context";

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


it("keeps the AFAC month and segment while withholding unsupported airport card context",()=>{
 document.body.innerHTML=`<div class="reader-tabs"><button role="tab" aria-selected="true" aria-controls="panel-market"></button></div><section id="panel-market" role="tabpanel"><select id="market-period"><option selected>2026M06</option></select><select id="market-segment"><option selected>international</option></select><article class="chart-card" id="airport-demand-card" data-chat-unavailable><button id="airport-source">Source</button></article></section>`;
 const context=buildChatContext(document.getElementById("airport-source"));
 expect(context.tab).toBe("market");expect(context.period).toBe("2026M06");expect(context.filters?.segment).toBe("international");expect(context.card_id).toBeUndefined();
});
