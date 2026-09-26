// Airport search box inside the route detail panel. Ported from
// src/dashboard/assets/flights.js.

import { $, esc } from "./dom.js";
import { state } from "./state.js";
import { routesForAirport } from "./map.js";

function normalizedSearch(value) {
  return String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("es-MX");
}

function airportSearchMatches(query) {
  const needle = normalizedSearch(query.trim());
  if (!needle) return [];
  return state.network.airports.map((airport) => ({
    airport,
    incident: routesForAirport(airport.iata),
    exact: normalizedSearch(airport.iata) === needle,
    haystack: normalizedSearch(`${airport.iata} ${airport.city} ${airport.name}`),
  })).filter((item) => item.haystack.includes(needle))
    .sort((a, b) => Number(b.exact) - Number(a.exact) || b.incident.length - a.incident.length || a.airport.iata.localeCompare(b.airport.iata))
    .slice(0, 8);
}

export function bindAirportSearchControls() {
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
      if (state.selectAirportFromSearch) state.selectAirportFromSearch(node.dataset.airportResult);
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
