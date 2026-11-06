"""Read-only queries of the exact official map dataset, separate from legacy routes."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

from src.conversational_analytics.semantic.context import (
    OFFICIAL_CARRIERS,
    OFFICIAL_REGIONS,
    OFFICIAL_SCOPES,
    validate_context,
)
from src.conversational_analytics.semantic.plan import PlanValidationError
from src.dashboard.official_routes_contract import PUBLIC_PATH, VERSION, validate

OFFICIAL_SOURCE_HOSTS = frozenset(
    {
        "www.gob.mx",
        "gob.mx",
        "www.sct.gob.mx",
        "www.transtats.bts.gov",
        "transtats.bts.gov",
        "www.bts.gov",
        "bts.gov",
        "data.transportation.gov",
    }
)
PUBLISHED_URL = "https://salvamalfa.github.io/aeromexico-tracker/" + PUBLIC_PATH


def official_route_tool_spec(dataset_version: str) -> dict[str, Any]:
    return {
        "type": "function",
        "name": "query_official_routes",
        "description": (
            "Consulta el mismo mapa oficial de Mercado. Usa esta función con map_scope, "
            "con o sin tarjeta adjunta: query_routes/find_shared_routes conservan otra evidencia. "
            "AFAC national/international: ciudad-ciudad, todas las aerolíneas, sin celdas por operador; "
            "international excluye EEUU geográfico. us: aeropuerto-aeropuerto BTS F+G, sólo "
            "Grupo Aeroméxico (Aerovías y Connect separados), Viva y Volaris, multiselección por "
            "carrier_keys; omisión=las tres. Vuelos regulares realizados de pasajeros y carga, "
            "sin charter L/P. Periodo trimestral exacto, sin fallback; devuelve meses observados, "
            "cobertura parcial, comparación publicada y fuentes exactas. No mide pasajeros, "
            "programación, ingresos ni rentabilidad. Los argumentos explícitos prevalecen sobre "
            f"el chip. Dataset fijado: {dataset_version}."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {
                "period": {"type": "string", "pattern": "^20[0-9]{2}Q[1-4]$"},
                "scope": {"type": "string", "enum": sorted(OFFICIAL_SCOPES)},
                "region": {
                    "type": "string",
                    "enum": ["all", *sorted(OFFICIAL_REGIONS)],
                    "description": "Sólo international: all elimina el filtro; null u omisión heredan "
                    "la región del contexto. Otra región explícita la reemplaza.",
                },
                "carrier_keys": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(OFFICIAL_CARRIERS)},
                    "minItems": 0,
                    "maxItems": 3,
                    "uniqueItems": True,
                },
                "dataset_version": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "route_key": {"type": "string", "minLength": 1, "maxLength": 180},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 20},
            },
        },
    }


def configured_official_routes(snapshot: Any, config: Any | None) -> OfficialRouteTools | None:
    """Construct the optional reader only when explicitly enabled and pinned."""
    if not bool(getattr(config, "enable_official_route_tools", False)):
        return None
    pin = getattr(config, "official_route_dataset_sha256", None)
    if not isinstance(pin, str) or len(pin) != 64:
        raise PlanValidationError("La herramienta oficial requiere un pin explícito del dataset")
    return OfficialRouteTools(snapshot, expected_version=pin)


def reject_legacy_context(filters: dict[str, Any]) -> None:
    """An official-map selection cannot silently read a different route dataset."""
    if "map_scope" in filters:
        raise PlanValidationError(
            "La tarjeta del mapa oficial requiere query_official_routes; esta consulta usa otra evidencia"
        )


class OfficialRouteTools:
    """Never loads warehouse data or reconstructs unsupported route/carrier cells."""

    def __init__(self, snapshot: Any, *, expected_version: str | None = None):
        self.snapshot = snapshot
        self.document = snapshot.payload(PUBLIC_PATH)
        try:
            validate(self.document)
        except Exception as exc:
            raise PlanValidationError("El dataset oficial no cumple su contrato e identidad") from exc
        self.version = self.document["dataset_version"]
        if expected_version is not None and expected_version != self.version:
            raise PlanValidationError("El pin del dataset oficial no coincide con el publicado")

    def tool_spec(self) -> dict[str, Any]:
        return official_route_tool_spec(self.version)

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": VERSION,
            "dataset_version": self.version,
            "periods": list(self.document["periods"]),
            "scopes": sorted(OFFICIAL_SCOPES),
            "regions": sorted(OFFICIAL_REGIONS),
            "carriers_us_only": list(OFFICIAL_CARRIERS),
            "afac_entity": "ALL",
            "universe": self.document["metadata"]["universe"],
            "note": "Presencia de periodo no acredita cobertura completa; consultar los meses observados.",
        }

    def query(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(arguments, dict) or set(arguments) - {
            "period",
            "scope",
            "region",
            "carrier_keys",
            "dataset_version",
            "route_key",
            "top_n",
        }:
            raise PlanValidationError("Argumentos query_official_routes no válidos")
        arguments = {key: value for key, value in arguments.items() if value is not None}
        clean = validate_context(context)
        filters = clean.get("filters", {})
        official_context = "map_scope" in filters
        for version in (arguments.get("dataset_version"), filters.get("map_dataset_version")):
            if version is not None and version != self.version:
                raise PlanValidationError("El mapa adjunto o consulta pertenece a otra versión oficial")
        period = arguments.get("period", clean.get("period"))
        scope = arguments.get("scope", filters.get("map_scope"))
        if not isinstance(period, str) or not re.fullmatch(r"20\d{2}Q[1-4]", period):
            raise PlanValidationError("Se requiere un trimestre oficial exacto")
        if not isinstance(scope, str) or scope not in OFFICIAL_SCOPES:
            raise PlanValidationError("Se requiere scope oficial: national, us o international")
        same_scope = official_context and scope == filters["map_scope"]
        carriers = arguments.get("carrier_keys", filters.get("map_carriers") if same_scope else None)
        if carriers is None:
            carriers = list(OFFICIAL_CARRIERS) if scope == "us" else []
        if (
            not isinstance(carriers, list)
            or any(not isinstance(carrier, str) or carrier not in OFFICIAL_CARRIERS for carrier in carriers)
            or len(set(carriers)) != len(carriers)
            or (scope == "us" and not 1 <= len(carriers) <= 3)
            or (scope != "us" and carriers)
        ):
            raise PlanValidationError("AFAC no admite filtro de aerolínea; EEUU requiere una a tres")
        carriers = [carrier for carrier in OFFICIAL_CARRIERS if carrier in carriers]
        region = arguments.get("region", filters.get("map_region") if same_scope else None)
        if region is not None and (
            scope != "international"
            or not isinstance(region, str)
            or region not in OFFICIAL_REGIONS | {"all"}
        ):
            raise PlanValidationError("region sólo corresponde a international y debe ser oficial")
        if region == "all":
            region = None
        top_n = arguments.get("top_n", 10)
        if not isinstance(top_n, int) or isinstance(top_n, bool) or not 1 <= top_n <= 20:
            raise PlanValidationError("top_n debe estar entre 1 y 20")
        route_key = arguments.get("route_key")
        if route_key is not None and (not isinstance(route_key, str) or not 1 <= len(route_key) <= 180):
            raise PlanValidationError("route_key debe ser un ID oficial")
        query = {
            "period": period,
            "scope": scope,
            "region": region,
            "carrier_keys": carriers,
            "dataset_version": self.version,
            "route_key": route_key,
            "top_n": top_n,
        }
        networks = [
            network
            for network in self.document["networks"]
            if network["period_id"] == period
            and network["scope"] == scope
            and network["carrier_keys"] == carriers
        ]
        if len(networks) > 1:
            raise PlanValidationError("Identidad de red oficial duplicada")
        network = networks[0] if networks else None
        # A chip describes the exact displayed coverage, never permission to silently change it.
        context_carriers = [
            carrier for carrier in OFFICIAL_CARRIERS if carrier in filters.get("map_carriers", [])
        ]
        observed_months = network["observed_months"] if network is not None else []
        if (
            same_scope
            and period == clean.get("period")
            and carriers == context_carriers
            and sorted(filters["map_months"]) != sorted(observed_months)
        ):
            raise PlanValidationError("Los meses del mapa adjunto no coinciden con la cobertura publicada")
        refs = [{"label": f"Mapa oficial publicado · {period} · {scope}", "url": PUBLISHED_URL}]
        if network is not None:
            ids = set(network["source_ids"])
            for source in self.document["sources"]:
                if source["id"] not in ids:
                    continue
                parsed = urlparse(source["url"])
                if (
                    parsed.scheme != "https"
                    or parsed.hostname not in OFFICIAL_SOURCE_HOSTS
                    or parsed.username
                    or parsed.password
                    or parsed.port not in (None, 443)
                ):
                    raise PlanValidationError("Fuente oficial fuera de la lista pública permitida")
                refs.append({"label": f"{source['label']} · {source['source_period']}", "url": source["url"]})
        routes = (
            []
            if network is None
            else [
                copy.deepcopy(route)
                for route in network["routes"]
                if (region is None or route["region"] == region)
                and (route_key is None or route["route_key"] == route_key)
            ]
        )
        routes.sort(key=lambda row: (-row["departures"], row["route_key"]))
        missing = network is None or network["availability"] == "unavailable" or not routes
        rows = routes[:top_n] if not missing else []
        result = {
            "data_version": self.snapshot.version,
            "semantic_version": self.snapshot.semantic_version,
            "schema_version": VERSION,
            "dataset_version": self.version,
            "query": query,
            "grain": "airport_pair" if scope == "us" else "city_pair",
            "entity": "ALL" if scope != "us" else ("THREE" if len(carriers) == 3 else carriers),
            "metric": "departures",
            "unit": "flights",
            "value_kind": "reported",
            "universe": self.document["metadata"]["universe"],
            "availability": "missing" if missing else network["availability"],
            "reason": (
                "No hay observaciones publicadas para la selección exacta; no equivale a cero."
                if missing
                else None
            ),
            "expected_months": list(network["expected_months"]) if network else self._quarter_months(period),
            "observed_months": list(network["observed_months"]) if network else [],
            "comparison_calendar": {
                "current_period": period,
                "previous_period": str(int(period[:4]) - 1) + period[4:],
                "current_months": list(network["observed_months"]) if network else [],
                "previous_months": [
                    str(int(month[:4]) - 1) + month[4:] for month in network["observed_months"]
                ]
                if network
                else [],
                "row_months_reference": "comparison.comparison_months contiene soporte del año actual; "
                "la base YoY usa esos mismos meses del año anterior.",
            },
            "total_departures": sum(route["departures"] for route in routes) if not missing else None,
            "total_routes": len(routes) if not missing else None,
            "rows": rows,
            "truncated": len(routes) > len(rows),
            "references": refs,
            "notes": (network["notes"] if network else [])
            + [
                "AFAC no observa celdas ciudad × aerolínea. BTS conserva Aerovías y Connect separados.",
                "La comparación conserva los meses y el motivo publicados; no completa faltantes.",
            ],
        }
        # Preserve coverage and totals while bounding route detail for the worker's transport budget.
        result["display"] = self._display(query, rows, refs)
        while (
            rows
            and len(json.dumps({**result, "displays": [result["display"]]}, ensure_ascii=False).encode())
            > 15_000
        ):
            rows.pop()
            result["truncated"] = True
            result["display"] = self._display(query, rows, refs)
        result["returned_routes"] = len(rows)
        return result

    @staticmethod
    def _quarter_months(period: str) -> list[str]:
        start = (int(period[-1]) - 1) * 3 + 1
        return [f"{period[:4]}M{month:02}" for month in range(start, start + 3)]

    @staticmethod
    def _display(query: dict, rows: list[dict], refs: list[dict]) -> dict[str, Any]:
        identity = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[:16]
        return {
            "display_id": f"tabla:oficial_{identity}",
            "kind": "table",
            "title": f"Vuelos regulares · {query['period']} · {query['scope']}",
            "columns": [
                {"key": "route", "label": "Ruta"},
                {"key": "departures", "label": "Vuelos regulares", "unit": "flights"},
            ],
            "rows": [
                {
                    "route": f"{row['origin']['label']} – {row['destination']['label']}",
                    "departures": row["departures"],
                }
                for row in rows
            ],
            "value_kind": "reported",
            "source": refs[0],
            "sources": refs,
            "source_references": refs,
        }
