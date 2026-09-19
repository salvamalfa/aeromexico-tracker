(() => {
  "use strict";

  const payload = JSON.parse(document.getElementById("flight-dashboard-data").textContent);
  const quarters = payload.quarters;
  const byPeriod = new Map(quarters.map((item) => [item.period_id, item]));
  let periodIndex = Math.max(0, quarters.findIndex((item) => item.period_id === payload.metadata.default_period));
  const importance = "passengers";
  const networkPeriods = payload.international_networks || payload.route_networks;
  const domesticPeriods = payload.domestic_networks || {};
  let networkMode = domesticPeriods[quarters[periodIndex].period_id] ? "domestic" : "international";
  const defaultAirport = "MEX";
  let passengerPeriod = "quarter";
  let selectedMarket = null;
  let pinnedAirport = null;
  let hoveredAirport = null;
  let hoveredAirportAt = 0;
  let flowMapRendered = false;
  let selectAirportFromSearch = null;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const integer = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
  const decimal = new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const percent = new Intl.NumberFormat("es-MX", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dateLabel = (iso) => new Intl.DateTimeFormat("es-MX", { month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${iso.slice(0, 7)}-01T00:00:00Z`));

  function metricDisplay(key, value) {
    if (!finite(value)) return "No disponible";
    if (key === "load_factor") return percent.format(value);
    if (key === "passengers") return `${(value / 1e6).toFixed(3)} M`;
    return `${(value / 1e9).toFixed(3)} mil M`;
  }

  function priorPeriod(periodId, years = 0) {
    const year = Number(periodId.slice(0, 4));
    const quarter = Number(periodId.slice(-1));
    if (years) return `${year - years}Q${quarter}`;
    return quarter === 1 ? `${year - 1}Q4` : `${year}Q${quarter - 1}`;
  }

  function deltaDisplay(current, previous, points = false) {
    if (!finite(current) || !finite(previous) || (!points && previous === 0)) {
      return { text: "No disponible", className: "delta-na" };
    }
    const delta = points ? (current - previous) * 100 : (current / previous - 1) * 100;
    const text = points ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} pp` : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`;
    return { text, className: delta > 0.005 ? "delta-up" : delta < -0.005 ? "delta-down" : "delta-na" };
  }

  function setDelta(id, change) {
    const node = $(id);
    node.textContent = change.text;
    node.className = change.className;
  }

  function renderQuarter() {
    const record = quarters[periodIndex];
    $("period-display").textContent = record.period_label;
    $("period-prev").disabled = periodIndex === 0;
    $("period-next").disabled = periodIndex === quarters.length - 1;
    const qoq = byPeriod.get(priorPeriod(record.period_id));
    const yoy = byPeriod.get(priorPeriod(record.period_id, 1));
    for (const key of ["passengers", "asm_miles", "rpm_miles", "load_factor"]) {
      const metric = record.metrics[key];
      $( `flight-kpi-${key}` ).textContent = metricDisplay(key, metric.value);
      setDelta(`flight-kpi-${key}-qoq`, deltaDisplay(metric.value, qoq?.metrics[key]?.value, key === "load_factor"));
      setDelta(`flight-kpi-${key}-yoy`, deltaDisplay(metric.value, yoy?.metrics[key]?.value, key === "load_factor"));
    }
    renderMix(record);
    renderNetworkPeriod(record.period_id);
    $("live-status").textContent = $("forecast-chart")
      ? `Trimestre actualizado a ${record.period_label}. La red usa los meses disponibles por fuente del trimestre; el pronóstico conserva su propia ventana.`
      : `Trimestre actualizado a ${record.period_label}. La red usa los meses disponibles por fuente del trimestre.`;
  }

  function renderMix(record) {
    const series = payload.monthly_passengers;
    const monthlyPoints = series.records.map((point) => ({ ...point, period_label: dateLabel(point.date) }));
    const quarterGroups = new Map();
    monthlyPoints.forEach((point) => {
      const periodId = _quarterForDate(point.date);
      if (!quarterGroups.has(periodId)) {
        const startMonth = (Number(periodId.slice(-1)) - 1) * 3 + 1;
        quarterGroups.set(periodId, {
          period_id: periodId,
          period_label: `${periodId.slice(-1)}T${periodId.slice(2, 4)}`,
          date: `${periodId.slice(0, 4)}-${String(startMonth).padStart(2, "0")}-01`,
          domestic: 0, international: 0, total_segment_sum: 0,
        });
      }
      const quarter = quarterGroups.get(periodId);
      quarter.domestic += point.domestic;
      quarter.international += point.international;
      quarter.total_segment_sum += point.total_segment_sum;
    });
    const points = passengerPeriod === "quarter" ? [...quarterGroups.values()] : monthlyPoints;
    const narrow = window.matchMedia("(max-width: 736px)").matches;
    const veryNarrow = window.matchMedia("(max-width: 420px)").matches;
    const rangeStart = new Date(`${points[0].date}T00:00:00Z`);
    const rangeEnd = new Date(`${points[points.length - 1].date}T00:00:00Z`);
    const paddingDays = passengerPeriod === "quarter" ? 45 : 15;
    rangeStart.setUTCDate(rangeStart.getUTCDate() - paddingDays);
    rangeEnd.setUTCDate(rangeEnd.getUTCDate() + paddingDays);
    const hoverData = points.map((point) => {
      const heading = passengerPeriod === "quarter"
        ? point.period_label
        : new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${point.date}T00:00:00Z`));
      const total = point.total_segment_sum;
      return [heading, total, point.domestic, point.international, total ? point.domestic / total : 0, total ? point.international / total : 0];
    });
    const hoverTemplate = [
      "<b>%{customdata[0]}</b>",
      "<span style='color:#182233'>■</span> <b>Total</b> %{customdata[1]:,.0f}",
      "<span style='color:#003087'>■</span> Nacional %{customdata[2]:,.0f} (%{customdata[4]:.1%})",
      "<span style='color:#c99400'>■</span> Internacional %{customdata[3]:,.0f} (%{customdata[5]:.1%})",
      "<extra></extra>",
    ].join("<br>");
    const traces = [
      {
        type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.domestic),
        name: "Nacional", marker: { color: "#003087" },
        customdata: hoverData, hovertemplate: hoverTemplate,
      },
      {
        type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.international),
        name: "Internacional", marker: { color: "#c99400" },
        customdata: hoverData, hovertemplate: hoverTemplate,
      },
      {
        type: "scatter", mode: "lines+markers", x: points.map((point) => point.date),
        y: points.map((point) => point.total_segment_sum), name: "Total",
        connectgaps: false, line: { color: "#182233", width: 2.5 },
        marker: { color: "#fff", line: { color: "#182233", width: 1.5 }, size: 6 },
        customdata: hoverData, hovertemplate: hoverTemplate,
      },
    ];
    Plotly.react("mix-chart", traces, {
      barmode: "stack", bargap: .22, height: $("mix-chart").clientHeight || 430,
      margin: { l: 58, r: 18, t: 46, b: 68 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: 'Inter, "Segoe UI", sans-serif', color: "#182233", size: 10 },
      legend: { orientation: "h", y: 1.17, x: 0 },
      xaxis: {
        showgrid: false, tickformat: passengerPeriod === "quarter" ? "%Y" : "%b %Y",
        dtick: passengerPeriod === "quarter" ? (veryNarrow ? "M24" : "M12") : (veryNarrow ? "M24" : narrow ? "M12" : "M6"), tickangle: 0,
        range: [rangeStart.toISOString(), rangeEnd.toISOString()], tickfont: { size: narrow ? 8 : 10 },
      },
      yaxis: { rangemode: "tozero", gridcolor: "#e7ebf1", tickformat: ".2s", title: "Pasajeros" },
      shapes: [{
        type: "rect", xref: "x", yref: "paper", x0: record.metrics.passengers.period_start,
        x1: record.metrics.passengers.period_end, y0: 0, y1: 1,
        fillcolor: "rgba(0,48,135,.06)", line: { color: "rgba(0,48,135,.32)", width: 1, dash: "dot" }, layer: "below",
      }],
      annotations: [{
        x: record.metrics.passengers.period_start, y: 1, xref: "x", yref: "paper", xanchor: "left", yanchor: "bottom",
        text: record.period_label, showarrow: false, font: { size: 9, color: "#003087" },
      }],
      hovermode: "closest",
      hoverlabel: { align: "left", bgcolor: "#ffffff", bordercolor: "#b9c8d9", font: { color: "#182233", size: 11 } },
    }, { displayModeBar: false, responsive: true });
  }

  function _quarterForDate(iso) {
    const year = iso.slice(0, 4);
    const month = Number(iso.slice(5, 7));
    return `${year}Q${Math.floor((month - 1) / 3) + 1}`;
  }

  const worldGeometry = payload.route_network.world_geometry;
  window.PlotlyGeoAssets = window.PlotlyGeoAssets || { topojson: {} };
  window.PlotlyGeoAssets.topojson.world_110m = worldGeometry.topojson;
  let network = { ...(networkMode === "domestic" ? domesticPeriods[quarters[periodIndex].period_id] : networkPeriods?.[quarters[periodIndex].period_id]) || payload.route_network, world_geometry: worldGeometry };
  let routes = network.routes;
  function routeValue(route) {
    const key = network.mode === "scheduled_domestic" ? "departures" : importance;
    return finite(route[key]) ? route[key] : 0;
  }
  function orderedRoutes() { return [...routes].sort((a, b) => routeValue(b) - routeValue(a) || a.market_key.localeCompare(b.market_key)); }
  function routeTitle(route) { return `${route.origin.iata} ↔ ${route.destination.iata}`; }

  function renderNetworkPeriod(periodId) {
    const domesticAvailable = Boolean(domesticPeriods[periodId]);
    if (networkMode === "domestic" && !domesticAvailable) networkMode = "international";
    const periodNetwork = networkMode === "domestic" ? domesticPeriods[periodId] : (networkPeriods?.[periodId] || payload.route_network);
    network = { ...periodNetwork, world_geometry: worldGeometry };
    routes = network.routes;
    $("network-mode-domestic").disabled = !domesticAvailable;
    $("network-mode-domestic").setAttribute("aria-pressed", String(networkMode === "domestic"));
    $("network-mode-international").setAttribute("aria-pressed", String(networkMode === "international"));
    $("network-title").textContent = networkMode === "domestic" ? "Rutas nacionales" : "Rutas internacionales";
    $("route-network-note").innerHTML = networkMode === "domestic"
      ? `Red nacional identificada para ${esc(network.period_label)}. El AICM aporta slots de vuelos AM; Colima y Durango tienen movimientos atribuidos por inferencia; otras ocho rutas desde AIFA tienen presencia de Aeroméxico identificada en junio, sin desglose de vuelos propios. <a href="${esc(network.source_url)}" target="_blank" rel="noreferrer">Horario AICM</a> · <a href="https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx" target="_blank" rel="noreferrer">AFAC origen–destino</a>.`
      : "Rutas observadas y destinos programados de Aeroméxico. Las filas indican fuente y meses; los slots programados se distinguen de vuelos realizados. Grosor por pasajeros cuando se conoce; N/D indica dato no disponible. Fuentes: <a href='https://www.aicm.com.mx/aicm/negocios/slots/horarios-historicos-para-verano-2026-pdf' target='_blank' rel='noreferrer'>AICM</a> y <a href='https://noticias.oma.aero/news/del-cerro-de-la-silla-a-la-torre-eiffel-y-sin-escalas-inicia-nueva-ruta-directa-monterrey-paris-a6d41-5f19f.html' target='_blank' rel='noreferrer'>OMA</a>.";
    renderAenaAirportActivity();
    const defaultIncident = routesForAirport(defaultAirport);
    pinnedAirport = defaultIncident.length ? defaultAirport : null;
    hoveredAirport = pinnedAirport;
    hoveredAirportAt = 0;
    selectedMarket = defaultIncident[0]?.market_key || null;
    if (pinnedAirport) renderAirportTooltip(pinnedAirport, defaultIncident, true);
    else renderRouteDetailPlaceholder();
    if (flowMapRendered) renderFlowMap();
  }

  function renderAenaAirportActivity() {
    const host = $("aena-airport-activity");
    if (!host) return;
    const items = networkPeriods?.[quarters[periodIndex].period_id]?.aena_airport_activity || [];
    host.hidden = items.length === 0;
    if (!items.length) { host.innerHTML = ""; return; }
    const incomplete = items.some((item) => item.coverage_status !== "complete");
    const cards = items.sort((a, b) => (b.passengers || 0) - (a.passengers || 0)).map((item) => {
      const city = item.airport_iata === "MAD" ? "Madrid" : "Barcelona";
      const months = (item.observed_months || []).map((month) => dateLabel(`${month.slice(0, 4)}-${month.slice(5)}-01`)).join(", ");
      return `<div class="aena-activity-card"><div class="aena-activity-city"><strong>${city}</strong><span>${esc(item.airport_iata)}</span></div>
        <div class="aena-activity-metrics"><div><strong>${formatRouteMetric("passengers", item.passengers)}</strong><span>pasajeros</span></div>
        <div><strong>${formatRouteMetric("operations", item.operations)}</strong><span>operaciones</span></div></div>
        <small class="aena-activity-months">${esc(months)}${item.coverage_status !== "complete" ? " · cobertura parcial" : ""}</small></div>`;
    }).join("");
    host.innerHTML = `<div class="aena-activity-heading"><div><p class="section-kicker">España · Aena</p><h3>Actividad de Aeroméxico en aeropuertos españoles</h3></div>
      <span>${esc(network.period_label)}${incomplete ? " · periodo parcial" : ""}</span></div>
      <div class="aena-activity-grid">${cards}</div>
      <p class="aena-activity-note">Los meses incluidos se indican en cada tarjeta. Aena agrupa a Aerovías de México por aeropuerto español y compañía. Madrid puede incluir servicios desde Ciudad de México, Guadalajara y Monterrey; estas cifras no se asignan a una ruta concreta. Operaciones = aterrizajes + despegues. <a href="https://www.aena.es/es/estadisticas/consultas-personalizadas.html" target="_blank" rel="noreferrer">Fuente: Aena</a>.</p>`;
  }

  function formatRouteMetric(key, value) {
    if (!finite(value)) return "N/D";
    if (key === "load_factor") return percent.format(value);
    return integer.format(value);
  }

  function renderRouteDetailPlaceholder() {
    $("airport-tooltip").innerHTML = `
      <div class="airport-tooltip-empty">
        <strong>Detalle de rutas</strong>
        <span>Selecciona un punto amarillo para comparar pasajeros, asientos, vuelos y ocupación por sentido.</span>
      </div>`;
  }

  function routeMetricChangeChip(route, key) {
    const previous = route.previous || {};
    const previousValue = key === "load_factor"
      ? (finite(previous.passengers) && finite(previous.seats) && previous.seats > 0 ? previous.passengers / previous.seats : null)
      : previous[key];
    const change = deltaDisplay(route[key], previousValue, key === "load_factor");
    const label = change.text === "No disponible" ? "N/D" : change.text;
    const metricNames = { passengers: "Pasajeros", seats: "Asientos", departures: "Vuelos", load_factor: "Ocupación" };
    return `<span class="route-change-chip ${change.className}" title="${metricNames[key]} frente a los mismos meses del año anterior" aria-label="${esc(change.text)} frente a los mismos meses del año anterior">${esc(label)}</span>`;
  }

  function renderRouteTable(title, subtitle, tableRoutes, subtitleHtml = null) {
    if (network.mode === "scheduled_domestic") {
      const quantifiedMovements = tableRoutes.reduce((sum, route) => sum + (finite(route.departures) ? route.departures : 0), 0);
      const presenceOnly = tableRoutes.filter((route) => !finite(route.departures)).length;
      $("airport-tooltip").innerHTML = `
        <div class="airport-title-row">
          <h3>${esc(title)}</h3>
          <button type="button" class="airport-search-toggle" id="airport-search-toggle" aria-label="Buscar aeropuerto por código o ciudad" aria-expanded="false" aria-controls="airport-search-box">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 5 5"></path></svg>
          </button>
        </div>
        <div class="airport-search-box" id="airport-search-box" hidden>
          <label class="sr-only" for="airport-search-input">Código o ciudad</label>
          <input id="airport-search-input" type="search" autocomplete="off" placeholder="Código o ciudad">
          <div class="airport-search-results" id="airport-search-results" role="listbox" aria-label="Aeropuertos encontrados"></div>
        </div>
        <p class="airport-meta">${subtitleHtml || esc(subtitle)}</p>
        <div class="domestic-route-summary"><strong>${integer.format(quantifiedMovements)}</strong><span>movimientos cuantificados · ambos sentidos${presenceOnly ? ` · ${presenceOnly} rutas sin desglose propio` : ""}</span></div>
        <div class="airport-table-wrap"><table class="airport-route-table domestic-route-table"><thead><tr><th>Ruta</th><th>Movimientos</th></tr></thead>
          <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
            <td>${route.directions.length ? `<button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong></button>` : `<strong class="route-table-name">${esc(routeTitle(route))}</strong>`}<small class="route-source-note">${esc(route.coverage_note)}</small></td>
            <td class="route-table-value"><strong>${finite(route.departures) ? integer.format(route.departures) : "Sin desglose propio"}</strong></td>
          </tr>${route.directions.length ? `<tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="2"><div class="domestic-direction-list">${route.directions.map((direction) => `<div><span>${esc(direction.origin_iata)} → ${esc(direction.destination_iata)}</span><strong>${integer.format(direction.departures)}</strong></div>`).join("")}</div></td></tr>` : ""}`).join("")}</tbody></table></div>
        <p class="domestic-scope-note">AICM identifica slots de vuelos AM; AFAC identifica vuelos por par de ciudades. El <a href="https://expansion.mx/empresas/2026/06/08/aerolineas-aifa-vuelos-nacionales-e-internacionales" target="_blank" rel="noreferrer">listado de aerolíneas del 8 de junio de 2026</a> identifica a Aeroméxico en diez destinos desde AIFA. En Colima y Durango, Aeroméxico es el único operador identificado allí, de modo que su atribución es inferida. Las otras ocho rutas comparten aerolíneas; sus totales AFAC no se asignan a Aeroméxico. Los slots AICM se cuentan como realizados solo en el escenario de cobertura solicitado.</p>`;
      $("airport-tooltip").querySelectorAll(".route-expand-toggle").forEach((toggle) => toggle.addEventListener("click", () => {
        const detail = document.getElementById(toggle.getAttribute("aria-controls"));
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!expanded));
        toggle.classList.toggle("is-open", !expanded);
        detail.hidden = expanded;
      }));
      bindAirportSearchControls();
      return;
    }
    const routeDirections = (route) => {
      const endpoints = [route.origin.iata, route.destination.iata];
      return endpoints.map((origin, index) => {
        const destination = endpoints[1 - index];
        const direction = (route.directions || []).find((item) => item.origin_iata === origin && item.destination_iata === destination);
        return { origin, destination, direction };
      });
    };
    const metricCell = (route, key) => {
      const chip = routeMetricChangeChip(route, key);
      return `<td class="route-table-value"><span class="route-table-total"><strong>${formatRouteMetric(key, route[key])}</strong>${chip}</span></td>`;
    };
    const directionValue = (direction, key, route) => {
      if (key === "load_factor" && route.source_label && !route.source_label.includes("BTS")) return "<span>N/D</span>";
      if (!direction) return `<em>No disponible</em>`;
      const value = key === "load_factor" && finite(direction.seats) && direction.seats > 0
        ? direction.passengers / direction.seats
        : direction[key];
      return `<span>${formatRouteMetric(key, value)}</span>`;
    };
    const directionDetails = (route) => routeDirections(route).map(({ origin, destination, direction }) => `
      <div class="route-direction-line">
        <span class="route-direction-name">${esc(origin)} → ${esc(destination)}</span>
        ${directionValue(direction, "passengers", route)}
        ${directionValue(direction, "seats", route)}
        ${directionValue(direction, "departures", route)}
        ${directionValue(direction, "load_factor", route)}
      </div>`).join("");
    $("airport-tooltip").innerHTML = `
      <div class="airport-title-row">
        <h3>${esc(title)}</h3>
        <button type="button" class="airport-search-toggle" id="airport-search-toggle" aria-label="Buscar aeropuerto por código o ciudad" aria-expanded="false" aria-controls="airport-search-box">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 5 5"></path></svg>
        </button>
      </div>
      <div class="airport-search-box" id="airport-search-box" hidden>
        <label class="sr-only" for="airport-search-input">Código de aeropuerto o ciudad</label>
        <input id="airport-search-input" type="search" autocomplete="off" placeholder="Código o ciudad">
        <div class="airport-search-results" id="airport-search-results" role="listbox" aria-label="Aeropuertos encontrados"></div>
      </div>
      <p class="airport-meta">${subtitleHtml || esc(subtitle)}</p>
      <div class="airport-table-wrap">
        <table class="airport-route-table">
          <thead><tr><th>Ruta</th><th>Pasajeros</th><th>Asientos</th><th>Vuelos</th><th>Ocupación</th></tr></thead>
          <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
            <td><button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong></button><small class="route-source-note">${esc(route.coverage_note || "BTS T-100")}</small></td>
            ${metricCell(route, "passengers")}
            ${metricCell(route, "seats")}
            ${metricCell(route, "departures")}
            ${metricCell(route, "load_factor")}
          </tr><tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="5">${directionDetails(route)}</td></tr>`).join("")}</tbody>
        </table>
      </div>`;
    $("airport-tooltip").querySelectorAll(".route-expand-toggle").forEach((toggle) => {
      toggle.addEventListener("click", () => {
        const detail = document.getElementById(toggle.getAttribute("aria-controls"));
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!expanded));
        toggle.classList.toggle("is-open", !expanded);
        detail.hidden = expanded;
      });
    });
    bindAirportSearchControls();
  }

  function normalizedSearch(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es-MX");
  }

  function airportSearchMatches(query) {
    const needle = normalizedSearch(query.trim());
    if (!needle) return [];
    return network.airports.map((airport) => ({
      airport,
      incident: routesForAirport(airport.iata),
      exact: normalizedSearch(airport.iata) === needle,
      haystack: normalizedSearch(`${airport.iata} ${airport.city} ${airport.name}`),
    })).filter((item) => item.haystack.includes(needle))
      .sort((a, b) => Number(b.exact) - Number(a.exact) || b.incident.length - a.incident.length || a.airport.iata.localeCompare(b.airport.iata))
      .slice(0, 8);
  }

  function bindAirportSearchControls() {
    const toggle = $("airport-search-toggle");
    const box = $("airport-search-box");
    const input = $("airport-search-input");
    const results = $("airport-search-results");
    if (!toggle || !box || !input || !results) return;
    const close = () => {
      box.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    };
    const renderResults = () => {
      const matches = airportSearchMatches(input.value);
      results.innerHTML = input.value.trim() && !matches.length
        ? '<div class="airport-search-empty">No se encontraron aeropuertos.</div>'
        : matches.map(({ airport, incident }) => `<button type="button" role="option" data-airport-result="${esc(airport.iata)}"><strong>${esc(airport.iata)}</strong><span>${esc(airport.city)}</span><small>${incident.length} ${incident.length === 1 ? "ruta" : "rutas"}</small></button>`).join("");
      results.querySelectorAll("[data-airport-result]").forEach((node) => node.addEventListener("click", () => {
        if (selectAirportFromSearch) selectAirportFromSearch(node.dataset.airportResult);
      }));
    };
    toggle.addEventListener("click", () => {
      const opening = box.hidden;
      box.hidden = !opening;
      toggle.setAttribute("aria-expanded", String(opening));
      if (opening) input.focus();
    });
    input.addEventListener("input", renderResults);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { close(); toggle.focus(); }
      if (event.key === "Enter") {
        const first = results.querySelector("[data-airport-result]");
        if (first) { event.preventDefault(); first.click(); }
      }
    });
  }

  function xyz(lat, lon, radius = 1) {
    const phi = lat * Math.PI / 180;
    const theta = lon * Math.PI / 180;
    return [radius * Math.cos(phi) * Math.cos(theta), radius * Math.cos(phi) * Math.sin(theta), radius * Math.sin(phi)];
  }

  function arcPoints(route) {
    const a = xyz(route.origin.lat, route.origin.lon);
    const b = xyz(route.destination.lat, route.destination.lon);
    const dot = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
    const omega = Math.acos(dot);
    const sinOmega = Math.sin(omega);
    const lat = [], lon = [];
    for (let index = 0; index <= 20; index += 1) {
      const t = index / 20;
      const first = sinOmega < 1e-8 ? 1 - t : Math.sin((1 - t) * omega) / sinOmega;
      const second = sinOmega < 1e-8 ? t : Math.sin(t * omega) / sinOmega;
      const vector = [first * a[0] + second * b[0], first * a[1] + second * b[1], first * a[2] + second * b[2]];
      const length = Math.hypot(...vector);
      const x = vector[0] / length;
      const y = vector[1] / length;
      const z = vector[2] / length;
      lat.push(Math.asin(z) * 180 / Math.PI);
      lon.push(Math.atan2(y, x) * 180 / Math.PI);
    }
    return { lat, lon };
  }

  function routesForAirport(airport, ordered = orderedRoutes()) {
    return ordered.filter((route) => route.origin.iata === airport || route.destination.iata === airport);
  }

  const routePalette = [
    "#e31c23", "#0066cc", "#00875a", "#8b5cf6", "#d97706", "#0891b2",
    "#c026d3", "#4d7c0f", "#db2777", "#7c3aed", "#0f766e", "#b45309",
  ];

  function airportRouteColor(index) {
    return routePalette[index] || `hsl(${Math.round((index * 137.508 + 18) % 360)} 68% 40%)`;
  }

  function renderAirportTooltip(airport, incident, isPinned) {
    const airportData = network.airports.find((item) => item.iata === airport);
    const routeCount = `${incident.length} ${incident.length === 1 ? "mercado mostrado" : "mercados mostrados"}`;
    const missingMonths = (network.expected_months || []).filter((month) => !(network.observed_months || []).includes(month));
    const monthLabel = (month) => new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric", timeZone: "UTC" })
      .format(new Date(`${month.slice(0, 4)}-${month.slice(5, 7)}-01T00:00:00Z`));
    const incidentSources = new Set(incident.map(route => route.source_label));
    const sourceCoverage = Object.entries(network.coverage_by_source || {}).filter(([label]) => incidentSources.has(label)).map(([label, months]) => `${label}: ${months.map(monthLabel).join(", ")}`).join(" · ");
    const missingLabel = sourceCoverage ? `${esc(sourceCoverage)} · ` : missingMonths.length
      ? `<strong class="coverage-gap">${missingMonths.length === 1 ? "Falta" : "Faltan"} ${missingMonths.map(monthLabel).join(", ")}</strong> · `
      : "";
    const metaHtml = `${esc(network.period_label)} · ${missingLabel}${esc(routeCount)} · Selecciona el destino para ver el detalle.`;
    renderRouteTable(
      `${airport} · ${airportData?.city || "Aeropuerto"}`,
      "",
      incident,
      metaHtml,
    );
  }

  function alignRouteDetailToGeo() {
    const panel = $("airport-tooltip");
    const map = $("route-flow-map");
    const geo = map.querySelector(".geo");
    if (!panel) return;
    if (!geo || window.matchMedia("(max-width: 900px)").matches) {
      panel.style.marginTop = "";
      panel.style.height = "";
      panel.style.maxHeight = "";
      return;
    }
    const mapRect = map.getBoundingClientRect();
    const geoRect = geo.getBoundingClientRect();
    const visibleHeight = Math.round(geoRect.height * 100) / 100;
    panel.style.marginTop = `${Math.max(0, geoRect.top - mapRect.top)}px`;
    panel.style.height = `${visibleHeight}px`;
    panel.style.maxHeight = `${visibleHeight}px`;
  }

  function renderFlowMap() {
    const ordered = orderedRoutes();
    const maxValue = Math.max(...ordered.map(routeValue), 1);
    const contextMarkets = new Set(ordered.slice(0, 12).map((route) => route.market_key));
    const geometry = network.world_geometry.geojson;
    const traces = [{
      type: "choropleth", geojson: geometry, featureidkey: "id",
      locations: geometry.features.map((feature) => feature.id),
      z: geometry.features.map(() => 0), colorscale: [[0, "#e4edf8"], [1, "#e4edf8"]],
      marker: { line: { color: "#b9c8d9", width: .45 } }, showscale: false, hoverinfo: "skip",
    }];
    ordered.forEach((route) => {
      const arc = arcPoints(route);
      const selected = route.market_key === selectedMarket;
      const context = contextMarkets.has(route.market_key);
      traces.push({
        type: "scattergeo", mode: "lines", ...arc, name: route.market_key,
        customdata: arc.lat.map(() => route.market_key),
        line: { color: selected ? "#e31c23" : "#003087", width: selected ? 6 : .8 + 3.8 * Math.sqrt(routeValue(route) / maxValue) },
        opacity: selected ? 1 : (context ? .24 : .025),
        hoverinfo: "skip",
        showlegend: false,
      });
    });
    traces.push({
      type: "scattergeo", mode: "markers", name: "Aeropuertos",
      lat: network.airports.map((airport) => airport.lat), lon: network.airports.map((airport) => airport.lon),
      text: network.airports.map((airport) => `${airport.iata} · ${airport.city}`),
      customdata: network.airports.map((airport) => airport.iata),
      marker: { color: "#c99400", size: 4.5, line: { color: "#001f5b", width: 1 } },
      hovertemplate: "%{text}<extra></extra>", showlegend: false,
    });
    Plotly.react("route-flow-map", traces, {
      height: $("route-flow-map").clientHeight || 570, margin: { l: 0, r: 0, t: 0, b: 0 },
      paper_bgcolor: "rgba(0,0,0,0)", showlegend: false,
      geo: {
        projection: { type: "equirectangular" },
        bgcolor: "rgba(0,0,0,0)", showframe: true, framecolor: "#9fb2c8", framewidth: 1,
        showcoastlines: false, showcountries: false, showland: false, showocean: true,
        oceancolor: "#f6f9fd", lataxis: { range: network.mode === "scheduled_domestic" ? [13, 34] : [-60, 85], showgrid: true, gridcolor: "#d9e2ee", dtick: network.mode === "scheduled_domestic" ? 5 : 30 },
        lonaxis: { range: network.mode === "scheduled_domestic" ? [-119, -86] : [-180, 180], showgrid: true, gridcolor: "#d9e2ee", dtick: network.mode === "scheduled_domestic" ? 5 : 45 },
      },
      dragmode: false,
    }, { displayModeBar: false, responsive: true, scrollZoom: false });
    flowMapRendered = true;
    function focusAirport(airport, isPinned = false) {
      const incident = routesForAirport(airport, ordered);
      const incidentMarkets = new Set(incident.map((route) => route.market_key));
      const colors = new Map(incident.map((route, index) => [route.market_key, airportRouteColor(index)]));
      const traceIndexes = ordered.map((_, index) => index + 1);
      Plotly.restyle("route-flow-map", {
        opacity: ordered.map((route) => incidentMarkets.has(route.market_key) ? 1 : .012),
        "line.color": ordered.map((route) => colors.get(route.market_key) || "#d7dee8"),
        "line.width": ordered.map((route) => incidentMarkets.has(route.market_key) ? 2.2 + 4.8 * Math.sqrt(routeValue(route) / maxValue) : .45),
      }, traceIndexes);
      const airportTrace = ordered.length + 1;
      Plotly.restyle("route-flow-map", {
        "marker.color": [network.airports.map((item) => item.iata === airport ? "#e31c23" : "#c99400")],
        "marker.size": [network.airports.map((item) => item.iata === airport ? 9 : 4.5)],
      }, [airportTrace]);
      renderAirportTooltip(airport, incident, isPinned);
      $("live-status").textContent = `${airport}: ${incident.length} mercados ${isPinned ? "fijados" : "resaltados"} en el mapa.`;
    }
    function restoreRouteContext() {
      const traceIndexes = ordered.map((_, index) => index + 1);
      Plotly.restyle("route-flow-map", {
        opacity: ordered.map((route) => route.market_key === selectedMarket ? 1 : (contextMarkets.has(route.market_key) ? .24 : .025)),
        "line.color": ordered.map((route) => route.market_key === selectedMarket ? "#e31c23" : "#003087"),
        "line.width": ordered.map((route) => route.market_key === selectedMarket ? 6 : .8 + 3.8 * Math.sqrt(routeValue(route) / maxValue)),
      }, traceIndexes);
      Plotly.restyle("route-flow-map", {
        "marker.color": [network.airports.map(() => "#c99400")],
        "marker.size": [network.airports.map(() => 4.5)],
      }, [ordered.length + 1]);
      renderRouteDetailPlaceholder();
    }
    function pinAirportSelection(airport) {
      const incident = routesForAirport(airport, ordered);
      if (!incident.length) return;
      pinnedAirport = airport;
      hoveredAirport = airport;
      hoveredAirportAt = Date.now();
      selectedMarket = incident[0].market_key;
      focusAirport(airport, true);
      $("live-status").textContent = `${airport}: ${incident.length} mercados fijados en la tabla; ${incident[0].market_key} encabeza la métrica disponible.`;
    }
    selectAirportFromSearch = pinAirportSelection;
    const mapElement = $("route-flow-map");
    if (mapElement._airportClickHandler) mapElement.removeEventListener("click", mapElement._airportClickHandler, true);
    mapElement._airportClickHandler = (event) => {
      const markers = [...mapElement.querySelectorAll(".point")];
      let nearest = null;
      markers.forEach((marker, index) => {
        const rect = marker.getBoundingClientRect();
        const distance = Math.hypot(event.clientX - (rect.left + rect.width / 2), event.clientY - (rect.top + rect.height / 2));
        if (!nearest || distance < nearest.distance) nearest = { distance, airport: network.airports[index]?.iata };
      });
      if (nearest?.airport && nearest.distance <= 11) {
        event.preventDefault();
        event.stopImmediatePropagation();
        pinAirportSelection(nearest.airport);
      }
    };
    mapElement.addEventListener("click", mapElement._airportClickHandler, true);
    $("route-flow-map").removeAllListeners?.("plotly_click");
    $("route-flow-map").removeAllListeners?.("plotly_hover");
    $("route-flow-map").removeAllListeners?.("plotly_unhover");
    $("route-flow-map").on("plotly_hover", (event) => {
      const point = (event.points || []).find((item) => item.curveNumber === ordered.length + 1);
      if (point?.curveNumber === ordered.length + 1) {
        hoveredAirport = String(point.customdata || "");
        hoveredAirportAt = Date.now();
        if (!pinnedAirport) focusAirport(hoveredAirport);
      }
    });
    $("route-flow-map").on("plotly_unhover", () => {
      if (pinnedAirport) focusAirport(pinnedAirport, true);
      else {
        restoreRouteContext();
      }
    });
    if (pinnedAirport) focusAirport(pinnedAirport, true);
    window.requestAnimationFrame(alignRouteDetailToGeo);
  }

  function renderForecast() {
    if (!$("forecast-chart") || !$("model-note")) return;
    const forecast = payload.forecast;
    if (!forecast.available) {
      $("forecast-chart").innerHTML = '<div class="unavailable">No hay un pronóstico publicado.</div>';
      return;
    }
    const future = forecast.points.filter((point) => !point.is_backtest);
    const traces = [
      { x: [...future.map((p) => p.date), ...future.map((p) => p.date).reverse()], y: [...future.map((p) => p.upper_95), ...future.map((p) => p.lower_95).reverse()], type: "scatter", mode: "lines", fill: "toself", fillcolor: "rgba(0,48,135,.10)", line: { color: "rgba(0,0,0,0)" }, name: "Intervalo 95%", hoverinfo: "skip" },
      { x: [...future.map((p) => p.date), ...future.map((p) => p.date).reverse()], y: [...future.map((p) => p.upper_80), ...future.map((p) => p.lower_80).reverse()], type: "scatter", mode: "lines", fill: "toself", fillcolor: "rgba(0,48,135,.20)", line: { color: "rgba(0,0,0,0)" }, name: "Intervalo 80%", hoverinfo: "skip" },
      { x: forecast.history.map((p) => p.date), y: forecast.history.map((p) => p.actual), type: "scatter", mode: "lines+markers", name: "Observado AFAC", line: { color: "#182233", width: 2 }, marker: { size: 4 }, hovertemplate: "%{x|%b %Y}<br>%{y:,.0f} pasajeros<extra></extra>" },
      { x: future.map((p) => p.date), y: future.map((p) => p.forecast), type: "scatter", mode: "lines+markers", name: "Pronóstico", line: { color: "#003087", width: 2.5, dash: "dash" }, marker: { size: 5 }, hovertemplate: "%{x|%b %Y}<br>%{y:,.0f} pasajeros<extra></extra>" },
    ];
    Plotly.react("forecast-chart", traces, {
      height: $("forecast-chart").clientHeight || 450, margin: { l: 58, r: 16, t: 28, b: 65 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: 'Inter, "Segoe UI", sans-serif', color: "#182233", size: 10 },
      legend: { orientation: "h", x: 0, y: -0.17 },
      xaxis: { showgrid: false, tickformat: "%b %Y" },
      yaxis: { rangemode: "tozero", gridcolor: "#e7ebf1", tickformat: ".2s", title: "Pasajeros" },
      hovermode: "x unified",
    }, { displayModeBar: false, responsive: true });
    $("model-note").textContent = `${forecast.model_name} · entrenado ${forecast.trained_at.slice(0, 10)} con información hasta ${forecast.trained_through_period} · sMAPE de test ${percent.format(forecast.test_smape)} · bandas 80% y 95%.`;
  }

  function renderSources() {
    if (!$("source-inventory") || !$("eligibility-exclusions")) return;
    $("source-inventory").innerHTML = `<table class="source-table"><thead><tr><th>Fuente</th><th>Uso</th><th>Disponible al corte 2T26</th></tr></thead><tbody>${payload.sources.map((source) => {
      const url = source.source_url || source.source_urls?.[0];
      const title = url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(source.name)}</a>` : esc(source.name);
      return `<tr><td>${title}<br><small>${esc(source.source_system)}</small></td><td>${esc(source.source_id)}</td><td>${source.available_at_cutoff ? "Sí" : "No"}</td></tr>`;
    }).join("")}</tbody></table>`;
    $("eligibility-exclusions").innerHTML = Object.entries(payload.agent_eligibility.excluded).map(([key, value]) => `<li><strong>${esc(key)}</strong>: ${esc(value)}</li>`).join("");
  }

  $("period-prev").addEventListener("click", () => { if (periodIndex > 0) { periodIndex -= 1; renderQuarter(); } });
  $("period-next").addEventListener("click", () => { if (periodIndex < quarters.length - 1) { periodIndex += 1; renderQuarter(); } });
  $("network-mode-domestic").addEventListener("click", () => { if (domesticPeriods[quarters[periodIndex].period_id]) { networkMode = "domestic"; renderNetworkPeriod(quarters[periodIndex].period_id); } });
  $("network-mode-international").addEventListener("click", () => { networkMode = "international"; renderNetworkPeriod(quarters[periodIndex].period_id); });
  $("passenger-period").addEventListener("change", (event) => { passengerPeriod = event.target.value; renderMix(quarters[periodIndex]); });
  window.addEventListener("resize", () => window.requestAnimationFrame(alignRouteDetailToGeo));
  window.addEventListener("reader-tab-visible", () => {
    const panel = $("panel-flights");
    if (!panel || panel.hidden) return;
    window.requestAnimationFrame(() => {
      renderFlowMap();
      ["route-flow-map", "mix-chart"].forEach((id) => {
        const graph = $(id);
        if (graph?.classList.contains("js-plotly-plot")) Plotly.Plots.resize(graph);
      });
      alignRouteDetailToGeo();
    });
  });

  renderQuarter();
  renderForecast();
  renderSources();
  window.requestAnimationFrame(renderFlowMap);
})();
