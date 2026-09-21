(() => {
  "use strict";

  const payload = JSON.parse(document.getElementById("flight-dashboard-data").textContent);
  const quarters = payload.quarters;
  const byPeriod = new Map(quarters.map((item) => [item.period_id, item]));
  let periodIndex = Math.max(0, quarters.findIndex((item) => item.period_id === payload.metadata.default_period));
  const importance = "passengers";
  const networkPeriods = payload.international_networks || payload.route_networks;
  const domesticPeriods = payload.domestic_networks || {};
  const domesticMonthlyPeriods = payload.domestic_monthly_networks || {};
  const domesticMonthIds = Object.keys(domesticMonthlyPeriods).sort();
  // Los meses nacionales siguen al selector global de trimestre: cada
  // trimestre solo ofrece los meses que le pertenecen por calendario, nunca
  // meses de otro trimestre.
  function monthsInQuarter(quarterId) {
    return domesticMonthIds.filter((periodId) =>
      `${periodId.slice(0, 4)}Q${Math.floor((Number(periodId.slice(5, 7)) - 1) / 3) + 1}` === quarterId
    );
  }
  function domesticAvailableForQuarter(quarterId) {
    return monthsInQuarter(quarterId).length > 0 || Boolean(domesticPeriods[quarterId]);
  }
  // Selección múltiple de meses nacionales para el trimestre actualmente
  // mostrado por el selector global. Se reinicia solo cuando ese trimestre
  // cambia (ver renderQuarter); una selección manual dentro del mismo
  // trimestre nunca se sobrescribe.
  let selectedDomesticMonths = new Set(monthsInQuarter(quarters[periodIndex].period_id));
  let domesticMonthsQuarterId = quarters[periodIndex].period_id;
  let networkMode = domesticAvailableForQuarter(quarters[periodIndex].period_id) ? "domestic" : "international";
  const DOMESTIC_MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];
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
    if (record.period_id !== domesticMonthsQuarterId) {
      // Cambio de trimestre global: descarta cualquier selección manual de
      // meses y vuelve a seleccionar automáticamente los meses del nuevo
      // trimestre (puede ser un subconjunto si el trimestre está incompleto).
      selectedDomesticMonths = new Set(monthsInQuarter(record.period_id));
      domesticMonthsQuarterId = record.period_id;
    }
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
  let network = { ...(networkMode === "domestic" ? (aggregateDomesticMonths([...selectedDomesticMonths]) || domesticPeriods[quarters[periodIndex].period_id]) : networkPeriods?.[quarters[periodIndex].period_id]) || payload.route_network, world_geometry: worldGeometry };
  let routes = network.routes;
  function routeValue(route) {
    const key = network.mode === "scheduled_domestic" ? "departures" : importance;
    return finite(route[key]) ? route[key] : 0;
  }
  function orderedRoutes() { return [...routes].sort((a, b) => routeValue(b) - routeValue(a) || a.market_key.localeCompare(b.market_key)); }
  function routeTitle(route) { return `${route.origin.iata} ↔ ${route.destination.iata}`; }

  function renderNetworkPeriod(periodId) {
    const domesticAvailable = domesticAvailableForQuarter(periodId);
    if (networkMode === "domestic" && !domesticAvailable) networkMode = "international";
    const periodNetwork = networkMode === "domestic"
      ? (aggregateDomesticMonths([...selectedDomesticMonths]) || domesticPeriods[periodId])
      : (networkPeriods?.[periodId] || payload.route_network);
    network = { ...periodNetwork, world_geometry: worldGeometry };
    if (networkMode !== "international") selectedRegion = null;
    // Sin vuelos propios no hay registro que mostrar: son rutas donde la fuente
    // solo confirma presencia de Aeromexico, sin volumen atribuible.
    const quantified = (network.routes || []).filter((route) =>
      network.mode === "estimated_domestic" ? finite(route.passengers) : finite(route.departures)
    );
    network.routes = quantified;
    routes = regionRoutes(quantified);
    if (selectedRegion) {
      const shownAirports = new Set(routes.flatMap((route) => [route.origin.iata, route.destination.iata]));
      network.airports = (network.airports || []).filter((airport) => shownAirports.has(airport.iata));
    }
    // Nacional/Internacional es una elección mutuamente excluyente (role="radio"):
    // siempre hay exactamente una vista activa y ambos botones permanecen
    // clicables para poder alternar en cualquier sentido, cuantas veces sea.
    $("network-mode-domestic").disabled = !domesticAvailable;
    $("network-mode-domestic").setAttribute("aria-pressed", String(networkMode === "domestic"));
    $("network-mode-domestic").setAttribute("aria-checked", String(networkMode === "domestic"));
    $("network-mode-international").setAttribute("aria-pressed", String(networkMode === "international"));
    $("network-mode-international").setAttribute("aria-checked", String(networkMode === "international"));
    $("network-title").textContent = networkMode === "domestic" ? "Rutas nacionales" : "Rutas internacionales";
    const scopeNote = $("network-scope-note");
    if (scopeNote) {
      // La etiqueta de alcance nunca dice "Grupo Aeroméxico" salvo cuando el
      // dato realmente combina Aerovías de México y Aeroméxico Connect
      // (nacional). Internacional solo tiene evidencia retenida de Aerovías
      // de México como operador; decirlo explícitamente evita presentar una
      // cifra más angosta como si fuera consolidada.
      scopeNote.textContent = networkMode === "domestic"
        ? "Grupo Aeroméxico · combina Aerovías de México y Aeroméxico Connect"
        : "Aerovías de México (operador reportante) · no incluye Aeroméxico Connect";
    }
    renderMonthSwitch();
    renderRegionSwitch();
    renderNetworkVolume();
    // Con una region elegida, MEX puede quedar fuera del recorte: se abre el
    // aeropuerto de la region con mas rutas para que el detalle nunca salga vacio.
    const regionFallback = () => {
      const counts = new Map();
      routes.forEach((route) => [route.origin.iata, route.destination.iata]
        .filter((iata) => (network.airports || []).some((airport) => airport.iata === iata))
        .forEach((iata) => counts.set(iata, (counts.get(iata) || 0) + 1)));
      return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] || null;
    };
    let focusAirportIata = defaultAirport;
    let defaultIncident = routesForAirport(focusAirportIata);
    if (!defaultIncident.length) {
      focusAirportIata = regionFallback();
      defaultIncident = focusAirportIata ? routesForAirport(focusAirportIata) : [];
    }
    pinnedAirport = defaultIncident.length ? focusAirportIata : null;
    hoveredAirport = pinnedAirport;
    hoveredAirportAt = 0;
    selectedMarket = defaultIncident[0]?.market_key || null;
    if (pinnedAirport) renderAirportTooltip(pinnedAirport, defaultIncident, true);
    else renderRouteDetailPlaceholder();
    if (flowMapRendered) renderFlowMap();
  }

  function renderMonthSwitch() {
    const host = $("network-month-switch");
    if (!host) return;
    const monthsHere = monthsInQuarter(domesticMonthsQuarterId);
    host.hidden = networkMode !== "domestic" || monthsHere.length === 0;
    if (host.hidden) { host.innerHTML = ""; return; }
    host.innerHTML = monthsHere.map((periodId) => {
      const label = domesticMonthlyPeriods[periodId]?.period_label || periodId;
      return `<button type="button" data-domestic-month="${esc(periodId)}" aria-pressed="${String(selectedDomesticMonths.has(periodId))}">${esc(label)}</button>`;
    }).join("");
    host.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
      const id = button.dataset.domesticMonth;
      if (selectedDomesticMonths.has(id)) {
        if (selectedDomesticMonths.size === 1) return; // conserva al menos un mes seleccionado
        selectedDomesticMonths.delete(id);
      } else {
        selectedDomesticMonths.add(id);
      }
      renderNetworkPeriod(quarters[periodIndex].period_id);
    }));
  }

  // Describe el periodo nacional mostrado, p. ej. "abril–junio 2026 ·
  // 3 meses seleccionados" o, si el trimestre solo tiene datos para parte de
  // sus meses de calendario, agrega "· cobertura parcial: 2 de 3 meses".
  function domesticPeriodLabel(monthIds, quarterId) {
    const sorted = [...monthIds].sort();
    const n = sorted.length;
    const monthName = (id) => DOMESTIC_MONTH_NAMES[Number(id.slice(5, 7)) - 1];
    let base;
    if (n === 0) base = "Sin meses con datos";
    else if (n === 1) base = `${monthName(sorted[0])} ${sorted[0].slice(0, 4)}`;
    else base = `${monthName(sorted[0])}–${monthName(sorted[n - 1])} ${sorted[0].slice(0, 4)}`;
    const noun = n === 1 ? "mes seleccionado" : "meses seleccionados";
    let label = `${base} · ${n} ${noun}`;
    const available = monthsInQuarter(quarterId).length;
    if (available > 0 && available < 3) label += ` · cobertura parcial: ${available} de 3 meses`;
    return label;
  }

  // Combina los meses nacionales seleccionados en un agregado de Grupo
  // Aeroméxico: pasajeros, vuelos y asientos suman; la ocupación se calcula
  // con los totales (nunca promediando porcentajes mensuales); una ruta sin
  // datos en alguno de los meses conserva los que sí tiene sin rellenar con
  // cero, y su ocupación solo se muestra cuando la cobertura de pasajeros y
  // de capacidad coincide exactamente en los mismos meses.
  function aggregateDomesticMonths(monthIds) {
    const sorted = [...monthIds].sort();
    const monthNetworks = sorted.map((id) => domesticMonthlyPeriods[id]).filter(Boolean);
    if (!monthNetworks.length) return null;
    const byMarket = new Map();
    const airportsByIata = new Map();
    for (const monthNetwork of monthNetworks) {
      for (const airport of monthNetwork.airports || []) airportsByIata.set(airport.iata, airport);
      for (const route of monthNetwork.routes || []) {
        if (!finite(route.passengers)) continue;
        let agg = byMarket.get(route.market_key);
        if (!agg) {
          agg = {
            market_key: route.market_key, origin: route.origin, destination: route.destination,
            passengers: 0, passengers_low: 0, passengers_high: 0, monthsCovered: 0,
            seats: 0, departures: 0, capacityMonthsCovered: 0,
            source_label: route.source_label, monthly: [], repaired: false,
          };
          byMarket.set(route.market_key, agg);
        }
        agg.passengers += route.passengers;
        agg.passengers_low += finite(route.passengers_low) ? route.passengers_low : route.passengers;
        agg.passengers_high += finite(route.passengers_high) ? route.passengers_high : route.passengers;
        agg.monthsCovered += 1;
        agg.repaired = agg.repaired || Boolean(route.support_repair_applied);
        if (route.capacity_estimated && finite(route.seats) && finite(route.departures)) {
          agg.seats += route.seats;
          agg.departures += route.departures;
          agg.capacityMonthsCovered += 1;
        }
        agg.monthly.push(...(route.monthly || []));
      }
    }
    const monthsSelected = sorted.length;
    const routes = [...byMarket.values()].map((agg) => {
      const capacityComplete = agg.capacityMonthsCovered > 0 && agg.capacityMonthsCovered === agg.monthsCovered;
      const loadFactor = capacityComplete && agg.seats > 0 ? agg.passengers / agg.seats : null;
      const plausible = finite(loadFactor) && loadFactor <= 1;
      agg.monthly.sort((a, b) => a.period_id.localeCompare(b.period_id) || a.origin_iata.localeCompare(b.origin_iata));
      return {
        market_key: agg.market_key, origin: agg.origin, destination: agg.destination,
        passengers: agg.passengers, passengers_low: agg.passengers_low, passengers_high: agg.passengers_high,
        passengers_estimated: true,
        seats: capacityComplete ? agg.seats : null,
        departures: capacityComplete ? agg.departures : null,
        capacity_estimated: capacityComplete,
        load_factor: plausible ? loadFactor : null,
        load_factor_status: !capacityComplete ? "capacity_incomplete" : (plausible ? "estimated" : "inconsistent_inputs"),
        months_covered: agg.monthsCovered, months_selected: monthsSelected,
        capacity_months_covered: agg.capacityMonthsCovered,
        support_repair_applied: agg.repaired,
        source_label: agg.source_label,
        monthly: agg.monthly,
        previous: { passengers: null, seats: null, departures: null },
        directions: [],
      };
    }).sort((a, b) => b.passengers - a.passengers || a.market_key.localeCompare(b.market_key));
    return {
      mode: "estimated_domestic",
      period_label: domesticPeriodLabel(sorted, domesticMonthsQuarterId),
      expected_months: sorted,
      observed_months: sorted,
      routes,
      airports: [...airportsByIata.values()].sort((a, b) => a.iata.localeCompare(b.iata)),
      agent_eligible: false,
    };
  }

  function regionRoutes(allRoutes) {
    if (networkMode !== "international" || !selectedRegion) return allRoutes;
    return allRoutes.filter((route) => routeRegion(route) === selectedRegion);
  }

  function renderRegionSwitch() {
    const host = $("network-region-switch");
    if (!host) return;
    host.hidden = networkMode !== "international";
    if (host.hidden) { host.innerHTML = ""; return; }
    const available = REGIONS.filter((region) => (network.routes || []).some((route) => routeRegion(route) === region.id));
    host.innerHTML = available.map((region) => `<button type="button" data-region="${region.id}" aria-pressed="${String(selectedRegion === region.id)}">${esc(region.label)}</button>`).join("");
    host.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
      const id = button.dataset.region;
      selectedRegion = selectedRegion === id ? null : id;
      renderNetworkPeriod(quarters[periodIndex].period_id);
    }));
  }

  function renderNetworkVolume() {
    const host = $("network-volume");
    if (!host) return;
    const shown = routes || [];
    const flights = shown.reduce((sum, route) => sum + (finite(route.departures) ? route.departures : 0), 0);
    const passengers = shown.reduce((sum, route) => sum + (finite(route.passengers) ? route.passengers : 0), 0);
    const passengersLow = shown.reduce((sum, route) => sum + (finite(route.passengers_low) ? route.passengers_low : 0), 0);
    const passengersHigh = shown.reduce((sum, route) => sum + (finite(route.passengers_high) ? route.passengers_high : 0), 0);
    const noBreakdown = shown.filter((route) => !finite(route.departures)).length;
    host.hidden = shown.length === 0;
    if (host.hidden) { host.innerHTML = ""; return; }
    const scope = networkMode === "domestic"
      ? "en la red nacional"
      : selectedRegion
        ? `hacia ${REGIONS.find((region) => region.id === selectedRegion)?.label || ""}`
        : "en la red internacional";
    if (network.mode === "estimated_domestic") {
      const repaired = shown.some((route) => route.support_repair_applied);
      host.innerHTML = `<strong>≈${integer.format(passengers)}</strong><span>pasajeros estimados de Grupo Aeroméxico ${esc(scope)} · ${esc(network.period_label)} · sensibilidad ${integer.format(passengersLow)}–${integer.format(passengersHigh)}${repaired ? " · soporte de rutas completado con meses cercanos" : ""}</span>`;
      return;
    }
    // Las fuentes internacionales (BTS T-100, ANAC, Aerocivil, CAA, Aena)
    // solo reportan al operador Aerovías de México (AMX). Aeroméxico Connect
    // no aparece en ninguna de ellas para estos periodos, así que esta cifra
    // nunca se presenta como Grupo Aeroméxico.
    host.innerHTML = `<strong>${integer.format(flights)}</strong><span>vuelos operados por Aerovías de México (no incluye Aeroméxico Connect) ${esc(scope)} · ${esc(network.period_label)}${noBreakdown ? ` · ${noBreakdown} ${noBreakdown === 1 ? "ruta" : "rutas"} sin desglose propio` : ""}</span>`;
  }

  const REGION_MEMBERS = {
    asia: ["ICN", "NRT"],
    europa: ["AMS", "BCN", "CDG", "FCO", "LHR", "MAD"],
    sudamerica: ["BOG", "CLO", "CTG", "EZE", "GRU", "LIM", "MDE", "UIO"],
  };
  const REGIONS = [
    { id: "norteamerica", label: "Norteam\u00e9rica", lat: [8, 62], lon: [-170, -52], dtick: 15 },
    { id: "sudamerica", label: "Sudam\u00e9rica", lat: [-56, 16], lon: [-84, -33], dtick: 15 },
    { id: "europa", label: "Europa", lat: [34, 60], lon: [-12, 22], dtick: 10 },
    { id: "asia", label: "Asia", lat: [24, 44], lon: [122, 142], dtick: 5 },
  ];
  let selectedRegion = null;

  function airportRegion(iata) {
    for (const [id, members] of Object.entries(REGION_MEMBERS)) if (members.includes(iata)) return id;
    return "norteamerica";
  }
  function isMexican(airport) {
    return airport.lat >= 14 && airport.lat <= 33 && airport.lon >= -118 && airport.lon <= -86;
  }
  function routeRegion(route) {
    if (isMexican(route.origin)) return airportRegion(route.destination.iata);
    if (isMexican(route.destination)) return airportRegion(route.origin.iata);
    return airportRegion(route.destination.iata);
  }

  // Cuenta los meses del trimestre que la fuente report\u00f3 para esta ruta.
  // Solo las notas con desglose mensual ("Meses: 04, 05") lo declaran; las
  // fuentes de programaci\u00f3n trimestral no traen el dato y no llevan punto.
  const MONTH_ABBR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  function coverageMonths(route) {
    const note = route.coverage_note || "";
    const listed = /^Meses:\s*([\d,\s]+)/.exec(note);
    if (listed) return listed[1].split(",").map((part) => part.trim()).filter(Boolean).length || null;
    const lower = note.toLowerCase();
    const span = new RegExp(String.raw`\b(${MONTH_ABBR.join("|")})[\u2013\u2014-](${MONTH_ABBR.join("|")})\b`).exec(lower);
    if (span) return ((MONTH_ABBR.indexOf(span[2]) - MONTH_ABBR.indexOf(span[1])) % 12 + 12) % 12 + 1;
    if (new RegExp(String.raw`\b(${MONTH_NAMES.join("|")})\b`).test(lower)) return 1;
    return null;
  }
  // Los slots del AICM y el anuncio fechado de OMA son programacion: la fuente
  // dice que el vuelo estaba previsto, no que se realizo. El icono los separa
  // de lo observado sin gastar una columna ni una linea de texto.
  const SCHEDULED_STATUSES = ["assigned_slot_not_flown", "scheduled_from_dated_release"];
  function scheduledIconHtml(route) {
    if (!SCHEDULED_STATUSES.includes(route.operation_status)) return "";
    const title = "Vuelos programados: la fuente no confirma que se hayan realizado";
    return `<span class="route-scheduled-mark" title="${title}" aria-label="${title}" role="img"><svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 1.6 15 14H1z"></path><rect x="7.2" y="6" width="1.6" height="4" rx=".8"></rect><circle cx="8" cy="11.6" r=".95"></circle></svg></span>`;
  }

  function coverageDotHtml(route) {
    if (finite(route.months_covered) && finite(route.months_selected)) {
      // Agregado nacional multi-mes: indica cuántos de los meses
      // seleccionados aportaron datos a esta ruta, nunca un promedio.
      if (route.months_covered >= route.months_selected) return "";
      const variant = route.months_covered / route.months_selected >= 0.67 ? "is-partial" : "is-thin";
      const title = `${route.months_covered} de ${route.months_selected} meses seleccionados con datos de esta ruta`;
      return `<span class="route-coverage-dot ${variant}" title="${title}" aria-label="${title}"></span>`;
    }
    if (route.passengers_estimated) return "";
    const months = coverageMonths(route);
    if (!months) return "";
    const variant = months >= 3 ? "is-full" : months === 2 ? "is-partial" : "is-thin";
    const title = `${months} de 3 meses del trimestre con datos de la fuente`;
    return `<span class="route-coverage-dot ${variant}" title="${title}" aria-label="${title}"></span>`;
  }

  const SOURCE_SHORT_LABELS = {
    "Estados Unidos · BTS T-100": "BTS T-100",
    "México · AICM, vuelos AM programados": "AICM",
    "AICM · vuelos AM programados": "AICM",
    "Brasil · ANAC": "ANAC",
    "Colombia · Aerocivil": "Aerocivil",
    "AIFA · ruta de Aeroméxico identificada; volumen propio sin desglose": "AIFA",
    "AFAC · mercado con Aeroméxico como único operador identificado": "AFAC",
    "AFAC + AeroDataBox + flota Aeroméxico · estimaciones": "AFAC + AeroDataBox + flota (estimación)",
    "OMA · rutas documentadas": "OMA",
    "Reino Unido · CAA": "CAA",
  };

  function shortSourceLabel(label) {
    return SOURCE_SHORT_LABELS[label] || label || "";
  }

  function sourceFooterHtml(tableRoutes) {
    const labels = [...new Set((tableRoutes || []).map((route) => shortSourceLabel(route.source_label)).filter(Boolean))].sort();
    if (!labels.length) return "";
    return `<p class="route-source-footer">${labels.length === 1 ? "Fuente" : "Fuentes"}: ${esc(labels.join(" · "))}</p>`;
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
    if (route.passengers_estimated) return "";
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
        <div class="airport-table-wrap"><table class="airport-route-table domestic-route-table"><thead><tr><th>Ruta</th><th>Vuelos</th></tr></thead>
          <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
            <td>${route.directions.length ? `<button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}</button>` : `<strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}`}</td>
            <td class="route-table-value"><strong>${finite(route.departures) ? integer.format(route.departures) : "Sin desglose propio"}</strong></td>
          </tr>${route.directions.length ? `<tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="2"><div class="domestic-direction-list">${route.directions.map((direction) => `<div><span>${esc(direction.origin_iata)} → ${esc(direction.destination_iata)}</span><strong>${integer.format(direction.departures)}</strong></div>`).join("")}</div></td></tr>` : ""}`).join("")}</tbody></table></div>
        ${sourceFooterHtml(tableRoutes)}`;
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
      if (key === "passengers" && route.passengers_estimated) {
        const low = finite(route.passengers_low) ? route.passengers_low : route.passengers;
        const high = finite(route.passengers_high) ? route.passengers_high : route.passengers;
        const title = `Estimación; rango de sensibilidad ${integer.format(low)}–${integer.format(high)} pasajeros`;
        return `<td class="route-table-value"><span class="route-table-total route-estimate-total" title="${esc(title)}"><strong>≈${integer.format(route.passengers)}</strong><small>${integer.format(low)}–${integer.format(high)}</small></span></td>`;
      }
      if (route.capacity_estimated && ["seats", "departures", "load_factor"].includes(key)) {
        if (key === "load_factor" && !finite(route.load_factor)) {
          const title = route.load_factor_status === "inconsistent_inputs"
            ? "No se muestra: pasajeros y capacidad estimados producen una ocupación superior a 100%"
            : "No disponible";
          return `<td class="route-table-value"><span class="route-table-total" title="${esc(title)}"><strong>N/D</strong></span></td>`;
        }
        const low = key === "seats" ? route.seats_low : key === "load_factor" ? route.load_factor_low : null;
        const high = key === "seats" ? route.seats_high : key === "load_factor" ? route.load_factor_high : null;
        const range = finite(low) && finite(high)
          ? `<small>${formatRouteMetric(key, low)}–${formatRouteMetric(key, high)}</small>`
          : "";
        const title = key === "departures"
          ? "Estimación mensual basada en siete días distribuidos y ponderados por día de la semana"
          : key === "seats"
            ? "Capacidad estimada con el modelo de aeronave y la configuración de Aeroméxico"
            : "Pasajeros estimados divididos entre asientos estimados";
        return `<td class="route-table-value"><span class="route-table-total route-estimate-total" title="${esc(title)}"><strong>≈${formatRouteMetric(key, route[key])}</strong>${range}</span></td>`;
      }
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
    const estimateDetails = (route) => {
      const items = route.monthly || [];
      // Con más de un mes agregado, cada línea necesita decir a qué mes
      // pertenece: sin esto, dos o tres meses de un mismo sentido se verían
      // idénticos salvo por la cifra.
      const spansMonths = new Set(items.map((item) => item.period_id)).size > 1;
      return items.map((item) => {
        const low = finite(item.passengers_low) ? item.passengers_low : item.passengers;
        const high = finite(item.passengers_high) ? item.passengers_high : item.passengers;
        const borrowed = item.support_observed_in_period ? "" : `<small class="route-support-borrowed" title="Soporte de ruta observado en ${esc(item.support_source_periods)}; no es un vuelo observado del mes mostrado">soporte ${esc(item.support_source_periods)}</small>`;
        const seats = item.capacity_estimated ? `≈${formatRouteMetric("seats", item.seats)}` : "N/D";
        const departures = item.capacity_estimated ? `≈${formatRouteMetric("departures", item.departures)}` : "N/D";
        const loadFactor = item.capacity_estimated && finite(item.load_factor)
          ? `≈${formatRouteMetric("load_factor", item.load_factor)}`
          : "N/D";
        const monthLabel = spansMonths && item.period_id
          ? ` <small class="route-month-label">${esc(DOMESTIC_MONTH_NAMES[Number(item.period_id.slice(5, 7)) - 1] || item.period_id)}</small>`
          : "";
        return `
      <div class="route-direction-line route-estimate-line">
        <span class="route-direction-name"><strong>${esc(item.carrier_label)}</strong>${monthLabel}<br>${esc(item.origin_iata)} → ${esc(item.destination_iata)}${borrowed}</span>
        <span title="Rango de sensibilidad ${integer.format(low)}–${integer.format(high)}">≈${integer.format(item.passengers)}<small>${integer.format(low)}–${integer.format(high)}</small></span>
        <span>${seats}</span><span>${departures}</span><span>${loadFactor}</span>
      </div>`;
      }).join("");
    };
    const directionDetails = (route) => route.passengers_estimated && (route.monthly || []).length
      ? estimateDetails(route)
      : routeDirections(route).map(({ origin, destination, direction }) => `
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
          <thead><tr><th>Ruta</th><th>${network.mode === "estimated_domestic" ? "Pasajeros estimados" : "Pasajeros"}</th><th>Asientos</th><th>Vuelos</th><th>Ocupación</th></tr></thead>
          <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
            <td><button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}</button></td>
            ${metricCell(route, "passengers")}
            ${metricCell(route, "seats")}
            ${metricCell(route, "departures")}
            ${metricCell(route, "load_factor")}
          </tr><tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="5">${directionDetails(route)}</td></tr>`).join("")}</tbody>
        </table>
      </div>
      ${sourceFooterHtml(tableRoutes)}`;
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
    const routeCount = `${incident.length} ${incident.length === 1 ? "ruta" : "rutas"}`;
    const metaHtml = `${esc(network.period_label)} · ${esc(routeCount)} · Selecciona el destino para ver el detalle.`;
    renderRouteTable(
      `${airport} · ${airportData?.city || "Aeropuerto"}`,
      "",
      incident,
      metaHtml,
    );
  }

  // El alto del panel sigue al contenedor del mapa, no al <g class="geo"> de
  // Plotly: ese grupo es el mundo entero a escala, de modo que al acercarse a
  // una region crecia a miles de pixeles y arrastraba consigo el panel.
  function alignRouteDetailToGeo() {
    const panel = $("airport-tooltip");
    const map = $("route-flow-map");
    if (!panel || !map) return;
    if (window.matchMedia("(max-width: 900px)").matches) {
      panel.style.marginTop = "";
      panel.style.height = "";
      panel.style.maxHeight = "";
      return;
    }
    const height = map.clientHeight || 570;
    panel.style.marginTop = "0px";
    panel.style.height = `${height}px`;
    panel.style.maxHeight = `${height}px`;
  }

  // Estira el recorte al mismo aspecto que el lienzo, de modo que el mapa
  // dibujado ocupe siempre el alto completo: sin esto, cada region cambiaba
  // el alto del mapa y, con el, el del panel de detalle.
  function fitViewToCanvas(lat, lon) {
    const canvas = $("route-flow-map");
    const ratio = (canvas?.clientWidth || 700) / (canvas?.clientHeight || 570);
    let [lat0, lat1] = lat;
    let [lon0, lon1] = lon;
    const spanLat = lat1 - lat0;
    const spanLon = lon1 - lon0;
    if (spanLon / spanLat < ratio) {
      const want = spanLat * ratio;
      const mid = (lon0 + lon1) / 2;
      lon0 = mid - want / 2;
      lon1 = mid + want / 2;
    } else {
      const want = spanLon / ratio;
      const mid = (lat0 + lat1) / 2;
      lat0 = Math.max(-85, mid - want / 2);
      lat1 = Math.min(85, mid + want / 2);
    }
    return { lat: [lat0, lat1], lon: [lon0, lon1] };
  }

  function renderFlowMap() {
    const ordered = orderedRoutes();
    const activeRegion = networkMode === "international" && selectedRegion
      ? REGIONS.find((region) => region.id === selectedRegion)
      : null;
    const mapView = activeRegion
      ? { ...fitViewToCanvas(activeRegion.lat, activeRegion.lon), latDtick: activeRegion.dtick, lonDtick: activeRegion.dtick }
      : network.mode === "scheduled_domestic"
        ? { ...fitViewToCanvas([13, 34], [-119, -86]), latDtick: 5, lonDtick: 5 }
        : { lat: [-60, 85], lon: [-180, 180], latDtick: 30, lonDtick: 45 };
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
        oceancolor: "#f6f9fd", lataxis: { range: mapView.lat, showgrid: true, gridcolor: "#d9e2ee", dtick: mapView.latDtick },
        lonaxis: { range: mapView.lon, showgrid: true, gridcolor: "#d9e2ee", dtick: mapView.lonDtick },
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
    $("route-flow-map").on("plotly_click", (event) => {
      const point = (event.points || []).find((item) => item.curveNumber === ordered.length + 1);
      const iata = String(point?.customdata || "");
      if (!iata) return;
      pinnedAirport = iata;
      hoveredAirport = iata;
      hoveredAirportAt = Date.now();
      focusAirport(iata, true);
    });
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
  $("network-mode-domestic").addEventListener("click", () => {
    if (domesticAvailableForQuarter(quarters[periodIndex].period_id)) { networkMode = "domestic"; renderNetworkPeriod(quarters[periodIndex].period_id); }
  });
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
