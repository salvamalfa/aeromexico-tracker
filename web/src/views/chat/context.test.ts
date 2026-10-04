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
