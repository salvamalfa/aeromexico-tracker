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
  const signedTwoDecimals = (value) => `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;

  function selectedHover(id) {
    const graph = document.getElementById(id);
    if (!graph || !graph.data || !graph.getBoundingClientRect().width) return;
    const label = records[periodIndex.get(activePeriodId)].period_label;
    const point = graph.data[0].x.indexOf(label);
    if (point < 0) { Plotly.Fx.unhover(graph); return; }
    Plotly.Fx.hover(graph, [{curveNumber: 1, pointNumber: point}]);
  }

  function marginLegend() {
    const graph = document.getElementById('unit-chart');
    const svg = graph.querySelector('svg.main-svg');
    if (!svg) return;
    let gradient = svg.querySelector('#margin-legend-gradient');
    if (!gradient) {
      const ns = 'http://www.w3.org/2000/svg';
      gradient = document.createElementNS(ns, 'linearGradient');
      gradient.id = 'margin-legend-gradient';
      [['0%', colors.green], ['50%', colors.green], ['50%', colors.red], ['100%', colors.red]].forEach(([offset,color]) => {
        const stop = document.createElementNS(ns,'stop'); stop.setAttribute('offset',offset);stop.setAttribute('stop-color',color);gradient.appendChild(stop);
      });
      svg.querySelector('defs').appendChild(gradient);
    }
    graph.querySelectorAll('.legend .traces').forEach(row => {
      if (row.querySelector('.legendtext')?.textContent !== 'Margen unitario') return;
      row.querySelectorAll('.legendpoints path').forEach(path => {path.style.fill='url(#margin-legend-gradient)';path.style.fillOpacity='1';});
    });
  }

  function bindDefaultHover(id) {
    const graph = document.getElementById(id);
    if (graph.dataset.defaultHover) return;
    graph.dataset.defaultHover = 'true';
    graph.addEventListener('mouseleave', () => selectedHover(id));
    if (id === 'unit-chart') graph.on('plotly_afterplot', marginLegend);
  }
  window.addEventListener('reader-tab-visible', () => {
    selectedHover('unit-chart');selectedHover('volume-chart');marginLegend();
  });

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

  function visibleUnitRecords(rangeValue) {
    if (rangeValue === "all") return records;
    return records.slice(-Number(rangeValue));
  }

  function horizontalQuarterTicks(visibleRecords) {
    const compact = window.innerWidth <= 700;
    const stride = compact && visibleRecords.length > 12 ? 4 : compact && visibleRecords.length > 8 ? 2 : 1;
    return visibleRecords.filter((_, index) => index % stride === 0 || index === visibleRecords.length - 1);
  }

  function renderUnitEconomics() {
    const rangeValue = document.getElementById("unit-range").value;
    const visibleRecords = visibleUnitRecords(rangeValue);
    const visibleLabels = visibleRecords.map((record) => record.period_label);
    const tickRecords = horizontalQuarterTicks(visibleRecords);
    const marginColors = visibleRecords.map((record) =>
      record.unit_margin_cents_per_km >= 0 ? "rgba(8,127,101,0.36)" : "rgba(227,28,35,0.28)"
    );
    const traces = [
      {
        x: visibleLabels,
        y: visibleRecords.map((record) => record.unit_margin_cents_per_km),
        text: visibleRecords.map((record) => `${record.period_label}<br>Margen ${signedTwoDecimals(record.unit_margin_cents_per_km)} ¢ USD por ASK-km`),
        name: "Margen unitario",
        type: "bar",
        yaxis: "y2",
        zorder: 0,
        opacity: 0.72,
        textposition: "none",
        marker: {color: marginColors, line: {color: visibleRecords.map((record) => record.unit_margin_cents_per_km >= 0 ? colors.green : colors.red), width: 1}},
        hovertemplate: "%{text}<extra></extra>",
      },
      {
        x: visibleLabels,
        y: visibleRecords.map((record) => record.rask_cents_per_km),
        name: "RASK",
        type: "scatter",
        mode: "lines+markers",
        zorder: 10,
        xaxis: "x",
        yaxis: "y",
        line: {color: colors.blue, width: 3},
        marker: {color: "#ffffff", line: {color: colors.blue, width: 2}, size: 7},
        hovertemplate: "%{x}<br>RASK %{y:.2f} ¢ USD por ASK-km<extra></extra>",
      },
      {
        x: visibleLabels,
        y: visibleRecords.map((record) => record.cask_cents_per_km),
        name: "CASK",
        type: "scatter",
        mode: "lines+markers",
        zorder: 10,
        xaxis: "x",
        yaxis: "y",
        line: {color: colors.red, width: 2.4, dash: "dash"},
        marker: {color: "#ffffff", line: {color: colors.red, width: 2}, size: 6},
        hovertemplate: "%{x}<br>CASK %{y:.2f} ¢ USD por ASK-km<extra></extra>",
      },
    ];
    traces.forEach(trace => {
      trace.customdata=visibleRecords.map(r=>[r.rask_cents_per_km,r.cask_cents_per_km,signedTwoDecimals(r.unit_margin_cents_per_km)]);
      trace.hovertemplate='<b>%{x}</b><br>RASK %{customdata[0]:.2f}<br>CASK %{customdata[1]:.2f}<br>Margen unitario %{customdata[2]}<br>¢ USD por asiento-kilómetro<extra></extra>';
    });
    const layout = commonLayout(365);
    Object.assign(layout, {
      hovermode: "closest",
      bargap: 0.34,
      barmode: "overlay",
      xaxis: {
        categoryorder: "array",
        categoryarray: visibleLabels,
        tickmode: "array",
        tickvals: tickRecords.map((record) => record.period_label),
        ticktext: tickRecords.map((record) => record.period_label),
        tickangle: 0,
        tickfont: {size: 8},
        showgrid: false,
      },
      yaxis: {
        title: {text: "¢ USD por ASK-km", font: {size: 10}},
        gridcolor: colors.grid,
        zeroline: false,
        tickformat: ".1f",
      },
      yaxis2: {
        title: {text: "Margen (¢ USD por ASK-km)", font: {size: 10}},
        overlaying: "y",
        side: "right",
        showgrid: false,
        zeroline: true,
        zerolinecolor: colors.ink,
        zerolinewidth: 1,
        tickformat: "+.1f",
        hoverformat: "+.2f",
      },
    });
    Plotly.react("unit-chart", traces, layout, plotConfig).then(()=>{bindDefaultHover('unit-chart');marginLegend();selectedHover('unit-chart');});
  }

  function renderVolumeMonetization() {
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
        hovertemplate: "%{x}<br>RASK %{y:.2f} ¢ USD por ASK-km<extra></extra>",
      },
    ];
    traces.forEach(trace=>{
      trace.customdata=records.map(r=>[r.passengers/1e6,r.rask_cents_per_km]);
      trace.hovertemplate='<b>%{x}</b><br>Pasajeros %{customdata[0]:.2f} M<br>RASK %{customdata[1]:.2f} ¢ USD por asiento-kilómetro<extra></extra>';
    });
    const layout = commonLayout(315);
    Object.assign(layout, {
      bargap: 0.42,
      hovermode: 'closest',
      xaxis: {categoryorder: "array", categoryarray: labels, tickangle: -45, tickfont: {size: 8}, showgrid: false},
      yaxis: {
        title: {text: "Pasajeros (M)", font: {size: 10}},
        rangemode: "tozero",
        gridcolor: colors.grid,
        tickformat: ".1f",
      },
      yaxis2: {
        title: {text: "RASK (¢ USD)", font: {size: 10}},
        overlaying: "y",
        side: "right",
        showgrid: false,
        tickformat: ".1f",
      },
    });
    Plotly.react("volume-chart", traces, layout, plotConfig).then(()=>{bindDefaultHover('volume-chart');selectedHover('volume-chart');});
  }

  function renderLoadMonetization(periodId) {
    const current = records[periodIndex.get(periodId)];
    const yearColors = {2021: "#e31c23", 2022: "#d66a00", 2023: "#087f65", 2024: "#003087", 2025: "#6d3cc7", 2026: "#2894c7"};
    const traces = [...new Set(records.map((record) => record.period_id.slice(0, 4)))].map((year) => {
      const yearRecords = records.filter((record) => record.period_id.startsWith(year));
      return {
        x: yearRecords.map((record) => record.load_factor_reported * 100),
        y: yearRecords.map((record) => record.rask_cents_per_km),
        text: yearRecords.map((record) => record.period_label),
        customdata: yearRecords.map((record) => [
          (record.ask_km / 1_000_000_000).toFixed(2),
          signedTwoDecimals(record.unit_margin_cents_per_km),
          (record.passengers / 1_000_000).toFixed(2),
        ]),
        name: year,
        type: "scatter",
        mode: "markers+text",
        textposition: "top center",
        textfont: {size: 8, color: colors.muted},
        marker: {size: 13, color: yearColors[year], line: {color: "#ffffff", width: 1.2}},
        hovertemplate: "%{text}<br>Ocupación %{x:.1f}%<br>RASK %{y:.2f} ¢ USD por ASK-km<br>ASK %{customdata[0]} mil M<br>Margen %{customdata[1]} ¢ USD por ASK-km<br>Pasajeros %{customdata[2]} M<extra></extra>",
      };
    });
    const selectedTrace = {
      x: [current.load_factor_reported * 100],
      y: [current.rask_cents_per_km],
      name: `Seleccionado: ${current.period_label}`,
      showlegend: false,
      type: "scatter",
      mode: "markers",
      marker: {symbol: "circle-open", size: 27, color: colors.red, line: {color: colors.red, width: 3}},
      hoverinfo: "skip",
    };
    const layout = commonLayout(315);
    Object.assign(layout, {
      hovermode: "closest",
      legend: {orientation: "h", x: 0, y: 1.12, font: {size: 9}},
      xaxis: {
        title: {text: "Factor de ocupación (%)", font: {size: 10}},
        gridcolor: colors.grid,
        ticksuffix: "%",
      },
      yaxis: {
        title: {text: "RASK (¢ USD por ASK-km)", font: {size: 10}},
        gridcolor: colors.grid,
        tickformat: ".1f",
        hoverformat: ".2f",
      },
    });
    Plotly.react("load-chart", [...traces, selectedTrace], layout, plotConfig);
  }

  function updateNarrative(view) {
    setText("narrative-period", view.period_label);
  }

  function updateKpis(view) {
    view.kpis.forEach((kpi) => {
      setText(`kpi-${kpi.key}-value`, kpi.display_value);
      setText(`kpi-${kpi.key}-qoq`, comparisonText(kpi.qoq));
      setText(`kpi-${kpi.key}-yoy`, comparisonText(kpi.yoy));
      [["qoq", kpi.qoq], ["yoy", kpi.yoy]].forEach(([suffix, comparison]) => {
        const node = document.getElementById(`kpi-${kpi.key}-${suffix}`);
        if (node) node.className = `delta-${comparison.direction}`;
      });
      const card = document.querySelector(`[data-kpi='${kpi.key}']`);
      if (card) card.setAttribute("aria-label", `${kpi.label}: ${kpi.display_value}`);
    });
    const record = records[periodIndex.get(view.period_id)];
    if (record) {
      const value = `${signedTwoDecimals(record.unit_margin_cents_per_km)} ¢ USD`;
      setText("kpi-unit_margin_cents_per_km-value", value);
      setText("kpi-unit_margin_cents_per_km-qoq", comparisonText(view.margin_qoq));
      setText("kpi-unit_margin_cents_per_km-yoy", comparisonText(view.margin_yoy));
      [["qoq", view.margin_qoq], ["yoy", view.margin_yoy]].forEach(([suffix, comparison]) => {
        const node = document.getElementById(`kpi-unit_margin_cents_per_km-${suffix}`);
        if (node) node.className = `delta-${comparison.direction}`;
      });
      const card = document.querySelector("[data-kpi='unit_margin_cents_per_km']");
      if (card) card.setAttribute("aria-label", `Margen unitario: ${value}`);
    }
  }

  function render(periodId) {
    const view = views[periodId];
    if (!view) return;
    updateKpis(view);
    updateNarrative(view);
    const range = document.getElementById('unit-range');
    if (!visibleUnitRecords(range.value).some(r=>r.period_id===periodId)) {range.value='all';renderUnitEconomics();}
    else selectedHover('unit-chart');
    renderVolumeMonetization();
    renderLoadMonetization(periodId);
    setText("period-display", view.period_label);
    const currentIndex = periodIndex.get(periodId);
    document.getElementById("period-prev").disabled = currentIndex === 0;
    document.getElementById("period-next").disabled = currentIndex === records.length - 1;
    document.getElementById("live-status").textContent = `Vista actualizada a ${view.period_label}.`;
  }

  let activePeriodId = payload.metadata.default_period;
  const movePeriod = (offset) => {
    const nextIndex = periodIndex.get(activePeriodId) + offset;
    if (nextIndex < 0 || nextIndex >= records.length) return;
    activePeriodId = records[nextIndex].period_id;
    render(activePeriodId);
  };
  document.getElementById("period-prev").addEventListener("click", () => movePeriod(-1));
  document.getElementById("period-next").addEventListener("click", () => movePeriod(1));
  document.getElementById("unit-range").addEventListener("change", renderUnitEconomics);
  window.addEventListener("resize", renderUnitEconomics);
  renderUnitEconomics();
  render(activePeriodId);
})();
