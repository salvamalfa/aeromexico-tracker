(() => {
  "use strict";

  const payloadNode = document.getElementById("dashboard-data");
  if (!payloadNode || typeof Plotly === "undefined") {
    throw new Error("El prototipo no pudo inicializar su payload o motor gráfico local.");
  }

  const payload = JSON.parse(payloadNode.textContent);
  const records = payload.records;
  const views = payload.views;
  const periods = records.map((record) => record.period_id);
  const labels = records.map((record) => record.period_label);
  const periodIndex = new Map(records.map((record, index) => [record.period_id, index]));
  const colors = {
    blue: "#003087",
    blueDark: "#001f5b",
    red: "#e31c23",
    gold: "#c99400",
    amber: "#b96700",
    violet: "#6d3cc7",
    green: "#087f65",
    grid: "#e8edf4",
    muted: "#657188",
    ink: "#182233",
  };
  const plotConfig = {
    displayModeBar: false,
    responsive: true,
    scrollZoom: false,
    staticPlot: false,
  };

  const setText = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  };

  const comparisonText = (comparison) => comparison.available ? comparison.display : "No disponible";

  function commonLayout(height) {
    return {
      height,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {family: 'Inter, "Segoe UI", system-ui, sans-serif', color: colors.ink, size: 10},
      hoverlabel: {bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: {color: colors.ink, size: 11}},
      legend: {orientation: "h", x: 0, y: 1.08, font: {size: 10}},
      margin: {l: 52, r: 24, t: 30, b: 42},
      hovermode: "x unified",
    };
  }

  function selectedShape(periodId) {
    const label = records[periodIndex.get(periodId)].period_label;
    return {
      type: "line",
      xref: "x",
      yref: "paper",
      x0: label,
      x1: label,
      y0: 0,
      y1: 1,
      line: {color: colors.violet, width: 1.4, dash: "dot"},
    };
  }

  function renderUnitEconomics(periodId) {
    const marginColors = records.map((record) =>
      record.unit_margin_cents_per_km >= 0 ? "rgba(0,48,135,0.46)" : "rgba(227,28,35,0.48)"
    );
    const traces = [
      {
        x: labels,
        y: records.map((record) => record.rask_cents_per_km),
        name: "RASK",
        type: "scatter",
        mode: "lines+markers",
        xaxis: "x",
        yaxis: "y",
        line: {color: colors.blue, width: 3},
        marker: {color: "#ffffff", line: {color: colors.blue, width: 2}, size: 7},
        hovertemplate: "%{x}<br>RASK %{y:.2f} ¢<extra></extra>",
      },
      {
        x: labels,
        y: records.map((record) => record.cask_cents_per_km),
        name: "CASK",
        type: "scatter",
        mode: "lines+markers",
        xaxis: "x",
        yaxis: "y",
        line: {color: colors.red, width: 2.4, dash: "dash"},
        marker: {color: "#ffffff", line: {color: colors.red, width: 2}, size: 6},
        hovertemplate: "%{x}<br>CASK %{y:.2f} ¢<extra></extra>",
      },
      {
        x: labels,
        y: records.map((record) => record.unit_margin_cents_per_km),
        name: "Margen unitario",
        type: "bar",
        xaxis: "x2",
        yaxis: "y2",
        marker: {color: marginColors, line: {color: colors.blue, width: 1}},
        hovertemplate: "%{x}<br>Margen %{y:+.2f} ¢<extra></extra>",
      },
    ];
    const layout = commonLayout(390);
    Object.assign(layout, {
      hovermode: "closest",
      bargap: 0.38,
      shapes: [selectedShape(periodId)],
      xaxis: {
        domain: [0, 1],
        anchor: "y",
        categoryorder: "array",
        categoryarray: labels,
        showticklabels: false,
        showgrid: false,
      },
      yaxis: {
        domain: [0.38, 1],
        title: {text: "¢ por ASK-km", font: {size: 10}},
        gridcolor: colors.grid,
        zeroline: false,
        tickformat: ".1f",
      },
      xaxis2: {
        domain: [0, 1],
        anchor: "y2",
        matches: "x",
        categoryorder: "array",
        categoryarray: labels,
        tickfont: {size: 9},
        showgrid: false,
      },
      yaxis2: {
        domain: [0, 0.23],
        title: {text: "Margen ¢", font: {size: 10}},
        gridcolor: colors.grid,
        zeroline: true,
        zerolinecolor: colors.ink,
        zerolinewidth: 1,
        tickformat: "+.1f",
      },
    });
    Plotly.react("unit-chart", traces, layout, plotConfig);
  }

  function renderVolumeMonetization(periodId) {
    const selected = records[periodIndex.get(periodId)].period_label;
    const traces = [
      {
        x: labels,
        y: records.map((record) => record.passengers / 1_000_000),
        name: "Pasajeros",
        type: "bar",
        marker: {color: "rgba(185,103,0,0.34)", line: {color: colors.amber, width: 1}},
        hovertemplate: "%{x}<br>%{y:.2f} M pasajeros<extra></extra>",
      },
      {
        x: labels,
        y: records.map((record) => record.rask_cents_per_km),
        name: "RASK",
        type: "scatter",
        mode: "lines+markers",
        yaxis: "y2",
        line: {color: colors.blue, width: 2.6},
        marker: {color: "#ffffff", line: {color: colors.blue, width: 2}, size: 6},
        hovertemplate: "%{x}<br>RASK %{y:.2f} ¢<extra></extra>",
      },
    ];
    const layout = commonLayout(315);
    Object.assign(layout, {
      shapes: [{
        type: "line", xref: "x", yref: "paper", x0: selected, x1: selected, y0: 0, y1: 1,
        line: {color: colors.violet, width: 1.3, dash: "dot"},
      }],
      bargap: 0.42,
      xaxis: {categoryorder: "array", categoryarray: labels, tickfont: {size: 9}, showgrid: false},
      yaxis: {
        title: {text: "Pasajeros (M)", font: {size: 10}},
        rangemode: "tozero",
        gridcolor: colors.grid,
        tickformat: ".1f",
      },
      yaxis2: {
        title: {text: "RASK ¢", font: {size: 10}},
        overlaying: "y",
        side: "right",
        showgrid: false,
        tickformat: ".1f",
      },
    });
    Plotly.react("volume-chart", traces, layout, plotConfig);
  }

  function renderLoadMonetization(periodId) {
    const current = records[periodIndex.get(periodId)];
    const sizes = records.map((record) => 14 + (record.ask_km / 1_000_000_000 - 13) * 4.5);
    const trace = {
      x: records.map((record) => record.load_factor_reported * 100),
      y: records.map((record) => record.rask_cents_per_km),
      text: records.map((record) => record.period_label),
      customdata: records.map((record) => [
        record.ask_km / 1_000_000_000,
        record.unit_margin_cents_per_km,
        record.passengers / 1_000_000,
      ]),
      name: "Trimestres",
      type: "scatter",
      mode: "markers+text",
      textposition: "top center",
      textfont: {size: 9, color: colors.muted},
      marker: {
        size: sizes,
        sizemode: "diameter",
        color: records.map((record) => record.unit_margin_cents_per_km),
        colorscale: [[0, "#dbe7f8"], [0.55, "#4f7fbe"], [1, colors.blueDark]],
        line: {color: "#ffffff", width: 1.4},
        colorbar: {title: {text: "Margen ¢", font: {size: 9}}, thickness: 8, len: 0.58, tickfont: {size: 8}},
      },
      hovertemplate:
        "%{text}<br>Ocupación %{x:.1f}%<br>RASK %{y:.2f} ¢<br>ASK %{customdata[0]:.2f} mil M<br>Margen %{customdata[1]:.2f} ¢<br>Pasajeros %{customdata[2]:.2f} M<extra></extra>",
    };
    const selectedTrace = {
      x: [current.load_factor_reported * 100],
      y: [current.rask_cents_per_km],
      name: `Seleccionado: ${current.period_label}`,
      type: "scatter",
      mode: "markers",
      marker: {symbol: "circle-open", size: 27, color: colors.red, line: {color: colors.red, width: 3}},
      hoverinfo: "skip",
    };
    const layout = commonLayout(315);
    Object.assign(layout, {
      hovermode: "closest",
      showlegend: false,
      xaxis: {
        title: {text: "Factor de ocupación (%)", font: {size: 10}},
        gridcolor: colors.grid,
        ticksuffix: "%",
      },
      yaxis: {
        title: {text: "RASK (¢ por ASK-km)", font: {size: 10}},
        gridcolor: colors.grid,
        tickformat: ".1f",
      },
    });
    Plotly.react("load-chart", [trace, selectedTrace], layout, plotConfig);
  }

  function updateNarrative(view) {
    setText("narrative-period", view.period_label);
    setText("narrative-headline", view.narrative.headline);
    const container = document.getElementById("narrative-copy");
    container.replaceChildren();
    view.narrative.paragraphs.forEach((paragraph) => {
      const node = document.createElement("p");
      node.textContent = paragraph;
      container.appendChild(node);
    });
  }

  function updateConclusions(view) {
    setText("insight-period", view.period_label);
    const list = document.getElementById("insight-list");
    list.replaceChildren();
    view.conclusions.forEach((conclusion) => {
      const item = document.createElement("li");
      item.textContent = conclusion;
      list.appendChild(item);
    });
  }

  function updateKpis(view) {
    view.kpis.forEach((kpi) => {
      setText(`kpi-${kpi.key}-value`, kpi.display_value);
      setText(`kpi-${kpi.key}-qoq`, comparisonText(kpi.qoq));
      setText(`kpi-${kpi.key}-yoy`, comparisonText(kpi.yoy));
      const card = document.querySelector(`[data-kpi='${kpi.key}']`);
      if (card) card.setAttribute("aria-label", `${kpi.label}: ${kpi.display_value}`);
    });
  }

  function render(periodId) {
    const view = views[periodId];
    if (!view) return;
    updateConclusions(view);
    updateKpis(view);
    updateNarrative(view);
    renderUnitEconomics(periodId);
    renderVolumeMonetization(periodId);
    renderLoadMonetization(periodId);
    document.getElementById("live-status").textContent = `Vista actualizada a ${view.period_label}.`;
  }

  const selector = document.getElementById("period-selector");
  selector.addEventListener("change", (event) => render(event.target.value));
  render(payload.metadata.default_period);
})();
