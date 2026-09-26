// Reader tab shell: switches .reader-tabs [role=tab] buttons and their
// [role=tabpanel]. Ported from the inline <script> src/analysis_agent/
// reader_ui.py::refine appends to the published page — same activation
// logic (click + arrow/Home/End keys), same 'reader-tab-visible'
// CustomEvent dispatched after resizing any Plotly graph the panel holds,
// so each view's own listener (see views/economy/charts.ts and
// views/flights/network.ts) can re-hover/re-align once visible.

import type { PlotlyHTMLElement } from "../../lib/plotly";

declare global {
  interface Window {
    Plotly?: { Plots: { resize(root: HTMLElement): Promise<PlotlyHTMLElement> } };
    __pageNoAutoMount?: boolean;
  }
}

export function mountTabs(root: Document | Element = document): { activate: (tab: Element) => void } {
  const tabs = [...root.querySelectorAll(".reader-tabs [role=tab]")];

  function activate(tab: Element): void {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      (t as HTMLElement).tabIndex = on ? 0 : -1;
      const controls = t.getAttribute("aria-controls");
      const panel = controls ? document.getElementById(controls) : null;
      if (panel) (panel as HTMLElement).hidden = !on;
    }
    const controls = tab.getAttribute("aria-controls");
    const panel = controls ? document.getElementById(controls) : null;
    if (!panel) return;
    window.requestAnimationFrame(() => {
      const graphs = [...panel.querySelectorAll(".js-plotly-plot")] as HTMLElement[];
      Promise.all(graphs.map((graph) => window.Plotly?.Plots.resize(graph))).then(() => {
        window.dispatchEvent(new CustomEvent("reader-tab-visible", { detail: { panelId: panel.id } }));
      });
    });
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      const keyboardEvent = event as KeyboardEvent;
      let target: number | undefined;
      if (keyboardEvent.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (keyboardEvent.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      if (keyboardEvent.key === "Home") target = 0;
      if (keyboardEvent.key === "End") target = tabs.length - 1;
      if (target === undefined) return;
      keyboardEvent.preventDefault();
      activate(tabs[target]!);
      (tabs[target] as HTMLElement).focus();
    });
  });

  return { activate };
}
