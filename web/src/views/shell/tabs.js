// Reader tab shell: switches .reader-tabs [role=tab] buttons and their
// [role=tabpanel]. Ported from the inline <script> src/analysis_agent/
// reader_ui.py::refine appends to the published page — same activation
// logic (click + arrow/Home/End keys), same 'reader-tab-visible'
// CustomEvent dispatched after resizing any Plotly graph the panel holds,
// so each view's own listener (see views/economy/charts.js and
// views/flights/network.js) can re-hover/re-align once visible.

export function mountTabs(root = document) {
  const tabs = [...root.querySelectorAll(".reader-tabs [role=tab]")];

  function activate(tab) {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    }
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (!panel) return;
    window.requestAnimationFrame(() => {
      const graphs = [...panel.querySelectorAll(".js-plotly-plot")];
      Promise.all(graphs.map((graph) => window.Plotly?.Plots.resize(graph))).then(() => {
        window.dispatchEvent(new CustomEvent("reader-tab-visible", { detail: { panelId: panel.id } }));
      });
    });
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let target;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target === undefined) return;
      event.preventDefault();
      activate(tabs[target]);
      tabs[target].focus();
    });
  });

  return { activate };
}
