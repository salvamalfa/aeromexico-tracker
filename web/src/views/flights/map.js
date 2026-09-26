// The Plotly scattergeo flow map: great-circle route arcs, airport
// markers, hover/click focusing and the airport search hookup. Ported
// from src/dashboard/assets/flights.js::renderFlowMap and its helpers.

import { $ } from "./dom.js";
import { state } from "./state.js";
import { REGIONS } from "./regions.js";
import { orderedRoutes, routeValue } from "./network.js";
import { renderAirportTooltip, renderRouteDetailPlaceholder, airportRouteColor } from "./table.js";

export function xyz(lat, lon, radius = 1) {
  const phi = lat * Math.PI / 180;
  const theta = lon * Math.PI / 180;
  return [radius * Math.cos(phi) * Math.cos(theta), radius * Math.cos(phi) * Math.sin(theta), radius * Math.sin(phi)];
}

export function arcPoints(route) {
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

export function routesForAirport(airport, ordered = orderedRoutes()) {
  return ordered.filter((route) => route.origin.iata === airport || route.destination.iata === airport);
}

// El alto del panel sigue al contenedor del mapa, no al <g class="geo"> de
// Plotly: ese grupo es el mundo entero a escala, de modo que al acercarse a
// una region crecia a miles de pixeles y arrastraba consigo el panel.
export function alignRouteDetailToGeo() {
  const panel = $("route-detail-column") || $("airport-tooltip");
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
export function fitViewToCanvas(lat, lon) {
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

export function renderFlowMap() {
  const ordered = orderedRoutes();
  const activeRegion = state.networkMode === "international" && state.selectedRegion
    ? REGIONS.find((region) => region.id === state.selectedRegion)
    : null;
  const mapView = activeRegion
    ? { ...fitViewToCanvas(activeRegion.lat, activeRegion.lon), latDtick: activeRegion.dtick, lonDtick: activeRegion.dtick }
    : state.networkMode === "domestic"
      ? { ...fitViewToCanvas([13, 34], [-119, -86]), latDtick: 5, lonDtick: 5 }
      : { lat: [-60, 85], lon: [-180, 180], latDtick: 30, lonDtick: 45 };
  const maxValue = Math.max(...ordered.map(routeValue), 1);
  const contextMarkets = new Set(ordered.slice(0, 12).map((route) => route.market_key));
  const geometry = state.network.world_geometry.geojson;
  const traces = [{
    type: "choropleth", geojson: geometry, featureidkey: "id",
    locations: geometry.features.map((feature) => feature.id),
    z: geometry.features.map(() => 0), colorscale: [[0, "#e4edf8"], [1, "#e4edf8"]],
    marker: { line: { color: "#b9c8d9", width: .45 } }, showscale: false, hoverinfo: "skip",
  }];
  ordered.forEach((route) => {
    const arc = arcPoints(route);
    const selected = route.market_key === state.selectedMarket;
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
    lat: state.network.airports.map((airport) => airport.lat), lon: state.network.airports.map((airport) => airport.lon),
    text: state.network.airports.map((airport) => `${airport.iata} · ${airport.city}`),
    customdata: state.network.airports.map((airport) => airport.iata),
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
  state.flowMapRendered = true;
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
      "marker.color": [state.network.airports.map((item) => item.iata === airport ? "#e31c23" : "#c99400")],
      "marker.size": [state.network.airports.map((item) => item.iata === airport ? 9 : 4.5)],
    }, [airportTrace]);
    renderAirportTooltip(airport, incident, isPinned);
    $("live-status").textContent = `${airport}: ${incident.length} mercados ${isPinned ? "fijados" : "resaltados"} en el mapa.`;
  }
  function restoreRouteContext() {
    const traceIndexes = ordered.map((_, index) => index + 1);
    Plotly.restyle("route-flow-map", {
      opacity: ordered.map((route) => route.market_key === state.selectedMarket ? 1 : (contextMarkets.has(route.market_key) ? .24 : .025)),
      "line.color": ordered.map((route) => route.market_key === state.selectedMarket ? "#e31c23" : "#003087"),
      "line.width": ordered.map((route) => route.market_key === state.selectedMarket ? 6 : .8 + 3.8 * Math.sqrt(routeValue(route) / maxValue)),
    }, traceIndexes);
    Plotly.restyle("route-flow-map", {
      "marker.color": [state.network.airports.map(() => "#c99400")],
      "marker.size": [state.network.airports.map(() => 4.5)],
    }, [ordered.length + 1]);
    renderRouteDetailPlaceholder();
  }
  function pinAirportSelection(airport) {
    const incident = routesForAirport(airport, ordered);
    if (!incident.length) return;
    state.pinnedAirport = airport;
    state.hoveredAirport = airport;
    state.hoveredAirportAt = Date.now();
    state.selectedMarket = incident[0].market_key;
    focusAirport(airport, true);
    $("live-status").textContent = `${airport}: ${incident.length} mercados fijados en la tabla; ${incident[0].market_key} encabeza la métrica disponible.`;
  }
  state.selectAirportFromSearch = pinAirportSelection;
  const mapElement = $("route-flow-map");
  if (mapElement._airportClickHandler) mapElement.removeEventListener("click", mapElement._airportClickHandler, true);
  mapElement._airportClickHandler = (event) => {
    const markers = [...mapElement.querySelectorAll(".point")];
    let nearest = null;
    markers.forEach((marker, index) => {
      const rect = marker.getBoundingClientRect();
      const distance = Math.hypot(event.clientX - (rect.left + rect.width / 2), event.clientY - (rect.top + rect.height / 2));
      if (!nearest || distance < nearest.distance) nearest = { distance, airport: state.network.airports[index]?.iata };
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
    state.pinnedAirport = iata;
    state.hoveredAirport = iata;
    state.hoveredAirportAt = Date.now();
    focusAirport(iata, true);
  });
  $("route-flow-map").on("plotly_hover", (event) => {
    const point = (event.points || []).find((item) => item.curveNumber === ordered.length + 1);
    if (point?.curveNumber === ordered.length + 1) {
      state.hoveredAirport = String(point.customdata || "");
      state.hoveredAirportAt = Date.now();
      if (!state.pinnedAirport) focusAirport(state.hoveredAirport);
    }
  });
  $("route-flow-map").on("plotly_unhover", () => {
    if (state.pinnedAirport) focusAirport(state.pinnedAirport, true);
    else {
      restoreRouteContext();
    }
  });
  if (state.pinnedAirport) focusAirport(state.pinnedAirport, true);
  window.requestAnimationFrame(alignRouteDetailToGeo);
}
