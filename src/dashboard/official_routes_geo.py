"""Explicit city and airport identities; country geography differs from BTS reporting geography."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

COUNTRIES = {
    "ALEMANIA": "DE", "ARGENTINA": "AR", "BELGICA": "BE", "BELICE": "BZ", "BRASIL": "BR",
    "COREA DEL SUR": "KR", "CANADA": "CA", "CHILE": "CL", "CHINA": "CN", "COLOMBIA": "CO",
    "COSTA RICA": "CR", "CUBA": "CU", "ECUADOR": "EC", "EL SALVADOR": "SV",
    "EMIRATOS ARABES": "AE", "ESPANA": "ES", "ESTADOS UNIDOS": "US", "FRANCIA": "FR",
    "GUATEMALA": "GT", "HONG KONG": "HK", "HONDURAS": "HN", "IRLANDA": "IE", "ITALIA": "IT",
    "JAPON": "JP", "LUXEMBURGO": "LU", "MEXICO": "MX", "NICARAGUA": "NI", "PAISES BAJOS": "NL",
    "PANAMA": "PA", "PERU": "PE", "PORTUGAL": "PT", "PUERTO RICO": "PR", "QATAR": "QA",
    "REINO UNIDO": "GB", "REPUBLICA DOMINICANA": "DO", "SUIZA": "CH", "TURQUIA": "TR",
    "VENEZUELA": "VE",
}
REGION_COUNTRIES = {
    "canada": {"CA"},
    "central_america_caribbean": {
        "BZ", "CR", "CU", "SV", "GT", "HN", "NI", "PA", "DO", "PR", "VI", "JM", "HT", "BS",
        "BB", "TT", "AW", "CW", "SX", "GP", "MQ", "KY", "TC", "AG", "AI", "DM", "GD", "KN", "LC", "VC",
    },
    "south_america": {"AR", "BR", "CL", "CO", "EC", "PE", "VE", "BO", "PY", "UY", "GY", "SR", "GF"},
    "europe": {"DE", "BE", "ES", "FR", "IE", "IT", "LU", "NL", "PT", "GB", "CH", "TR"},
    "asia": {"KR", "CN", "AE", "HK", "JP", "QA"},
}
TERRITORIES = {"SJU": "PR", "BQN": "PR", "PSE": "PR", "MAZ": "PR", "VQS": "PR", "CPX": "PR",
               "STT": "VI", "STX": "VI"}


def normalize(value: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in value.upper()).split())


def iso(value: str) -> str:
    try:
        return COUNTRIES[normalize(value)]
    except KeyError as exc:
        raise ValueError(f"Unreviewed AFAC country: {value}") from exc


def city_key(name: str, country: str) -> str:
    return "CITY_" + country + "_" + normalize(name).replace(" ", "_")


def region(country: str) -> str | None:
    if country in {"MX", "US"}:
        return None
    found = [key for key, members in REGION_COUNTRIES.items() if country in members]
    if len(found) != 1:
        raise ValueError(f"Unreviewed official route region: {country}")
    return found[0]


def city_points(frame: pd.DataFrame) -> dict:
    import pandas as pd

    required = {"afac_city_key", "label", "country_iso2", "latitude", "longitude", "geonameid"}
    if not required <= set(frame) or frame.afac_city_key.duplicated().any():
        raise ValueError("Explicit unique official city geography required")
    result = {}
    for row in frame.to_dict("records"):
        lat, lon = row["latitude"], row["longitude"]
        if pd.isna(lat) != pd.isna(lon):
            raise ValueError("City geography requires both coordinates or neither")
        result[row["afac_city_key"]] = dict(
            id=row["afac_city_key"], label=row["label"], country_iso2=row["country_iso2"],
            lat=None if pd.isna(lat) else float(lat), lon=None if pd.isna(lon) else float(lon), point_kind="city",
        )
    return result


def airport_points(frame: pd.DataFrame) -> dict:
    import pandas as pd

    result = {}
    for row in frame.to_dict("records"):
        code = row.get("iata_code") or row.get("airport_iata")
        if pd.isna(code) or not code:
            continue
        country = TERRITORIES.get(code, row.get("iso_country", row.get("country")))
        lat, lon = row.get("latitude_deg", row.get("latitude")), row.get("longitude_deg", row.get("longitude"))
        point = dict(id="AIRPORT_" + code, label=row.get("name", code), country_iso2=country,
                     lat=None if pd.isna(lat) else float(lat), lon=None if pd.isna(lon) else float(lon),
                     point_kind="airport", iata=code)
        if code in result and result[code] != point:
            raise ValueError(f"Conflicting airport geographic identity {code}")
        result[code] = point
    return result
