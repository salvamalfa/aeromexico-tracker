// Partial Plotly bundle (P5): plotly.js/lib/core plus only the trace types
// the page actually uses — scatter and bar (economy charts, passenger mix)
// and scattergeo/choropleth (the Vuelos flow map). This replaces the
// vendored web/vendor/plotly-3.7.0.min.js (4.7 MB, full bundle) with a
// tree-shaken import through Vite; see web/README.md "Tamaño del bundle"
// and docs/arquitectura/auditoria-arquitectura-20260926.md Fase 4.
//
// Deliberately excludes MapLibre map traces, which this page does not use.
// Plotly core imports MapLibre CSS; the local build excludes its JavaScript.
import PlotlyCore from "plotly.js/lib/core";
import bar from "plotly.js/lib/bar";
import scatter from "plotly.js/lib/scatter";
import scattergeo from "plotly.js/lib/scattergeo";
import choropleth from "plotly.js/lib/choropleth";
import type { PlotlyHTMLElement } from "plotly.js";

PlotlyCore.register([bar, scatter, scattergeo, choropleth]);

// @types/plotly.js only types the documented top-level API (react,
// restyle, newPlot, register, ...); the Plots.resize/Fx.hover/Fx.unhover
// helpers the ported views call are real runtime APIs without published
// types, so this narrow extension documents exactly the surface used here
// instead of casting to `any` at each call site.
interface PlotlyExtras {
  Plots: { resize(root: HTMLElement): Promise<PlotlyHTMLElement> };
  Fx: {
    hover(root: HTMLElement, data: Array<{ curveNumber: number; pointNumber: number }>): void;
    unhover(root: HTMLElement): void;
  };
}

const Plotly = PlotlyCore as typeof PlotlyCore & PlotlyExtras;

export default Plotly;
export type { PlotlyHTMLElement } from "plotly.js";
