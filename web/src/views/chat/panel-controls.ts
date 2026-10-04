import Plotly from "../../lib/plotly";

export function resizeDashboardCharts(): void {
  window.requestAnimationFrame(() => {
    const graphs = [...document.querySelectorAll<HTMLElement>(".js-plotly-plot")];
    void Promise.all(graphs.map((graph) => Plotly.Plots.resize(graph)));
  });
}

export function mountPanelControls(
  panel: HTMLElement,
  resizer: HTMLElement,
  onClose: () => void,
): () => void {
  const onKeydown = (event: KeyboardEvent) => {
    if (panel.hidden) return;
    const key = event;
    if (key.key === "Escape") { key.preventDefault(); onClose(); return; }
    if (key.key === "Tab" && window.matchMedia("(max-width: 760px)").matches) {
      const focusables = [...panel.querySelectorAll<HTMLElement>(
        'button:not([hidden]):not(:disabled),input:not([type="hidden"]):not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]'
      )].filter((item) => item !== resizer && !item.closest("[hidden]") && getComputedStyle(item).visibility !== "hidden" && getComputedStyle(item).display !== "none");
      if (!focusables.length) return;
      if (key.shiftKey && document.activeElement === focusables[0]) { key.preventDefault(); focusables.at(-1)!.focus(); }
      else if (!key.shiftKey && document.activeElement === focusables.at(-1)) { key.preventDefault(); focusables[0]!.focus(); }
    }
  };
  document.addEventListener("keydown", onKeydown);

  let resizeStart = 0;
  let widthStart = 420;
  const setWidth = (width: number) => {
    const normalized = Math.max(340, Math.min(620, width, window.innerWidth - 360));
    document.documentElement.style.setProperty("--chat-width", `${normalized}px`);
    resizer.setAttribute("aria-valuenow", String(Math.round(normalized)));
    resizeDashboardCharts();
  };
  resizer.setAttribute("aria-valuenow", "420");
  resizer.addEventListener("pointerdown", (event) => {
    resizeStart = event.clientX; widthStart = panel.getBoundingClientRect().width;
    resizer.setPointerCapture(event.pointerId); panel.classList.add("is-resizing");
  });
  resizer.addEventListener("pointermove", (event) => {
    if (!resizer.hasPointerCapture(event.pointerId)) return;
    setWidth(widthStart + resizeStart - event.clientX);
  });
  const stopResize = () => panel.classList.remove("is-resizing");
  resizer.addEventListener("pointerup", stopResize); resizer.addEventListener("pointercancel", stopResize);
  resizer.addEventListener("keydown", (event) => {
    const key = event as KeyboardEvent;
    if (key.key === "ArrowLeft" || key.key === "ArrowRight") {
      key.preventDefault();
      setWidth((panel.getBoundingClientRect().width || 420) + (key.key === "ArrowLeft" ? 24 : -24));
    }
  });
  window.addEventListener("resize", resizeDashboardCharts);
  return () => {
    document.removeEventListener("keydown", onKeydown);
    window.removeEventListener("resize", resizeDashboardCharts);
  };
}
