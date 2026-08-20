"""Project-wide constants, paths, source identities, and rate limits."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)

CIK_AEROMEXICO: Final[str] = "0001561861"
TICKER_AEROMEXICO: Final[str] = "AERO"

# Peer CIKs marked None must be resolved against SEC company_tickers during
# Stage 5. The two populated values are revalidated by the Stage 0/1 network
# checks before being treated as current source metadata.
CARRIERS: Final[dict[str, dict[str, str | None]]] = {
    "AEROMEXICO": {
        "iata": "AM",
        "icao": "AMX",
        "cik": CIK_AEROMEXICO,
        "ticker": TICKER_AEROMEXICO,
    },
    "VOLARIS": {
        "iata": "Y4",
        "icao": "VOI",
        "cik": "0001520504",
        "ticker": "VLRS",
    },
    "VIVA_AEROBUS": {"iata": "VB", "icao": "VIV", "cik": None, "ticker": None},
    "RYANAIR": {"iata": "FR", "icao": "RYR", "cik": None, "ticker": "RYAAY"},
    "DELTA": {"iata": "DL", "icao": "DAL", "cik": None, "ticker": "DAL"},
    "IAG": {"iata": None, "icao": None, "cik": None, "ticker": "ICAGY"},
}

# Requests per second. Capacity is one token, so these rates are strict rather
# than bursty. Conservative values are intentional for public sources.
RATE_LIMITS: Final[dict[str, float]] = {
    "sec": 5.0,
    "bmv": 0.5,
    "afac": 1.0 / 3.0,
    "bts": 0.5,
    "aeromexico_ir": 0.5,
    "banxico": 2.0,
    "eia": 2.0,
    "fred": 2.0,
    "market": 1.0,
    "default": 1.0,
}

SOURCE_URLS: Final[dict[str, str]] = {
    "sec_submissions": f"https://data.sec.gov/submissions/CIK{CIK_AEROMEXICO}.json",
    "sec_companyfacts": (
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK_AEROMEXICO}.json"
    ),
    "aeromexico_ir": "https://ir.aeromexico.com/financial-information/quarterly-results",
    "bmv_xbrl": "https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl",
    "afac_statistics": (
        "https://www.gob.mx/afac/acciones-y-programas/"
        "estadistica-mensual-por-aerolinea-monthly-airline-statistics"
    ),
    "bts_transtats": "https://transtats.bts.gov/",
    "banxico_sie": "https://www.banxico.org.mx/SieAPIRest/service/v1/",
    "eia_api": "https://api.eia.gov/v2/",
}


class MissingSecUserAgentError(RuntimeError):
    """Raised before any SEC request when no identifiable contact is configured."""


def get_sec_user_agent() -> str:
    """Return the configured SEC identity or fail before network I/O."""

    value = os.getenv("SEC_USER_AGENT", "").strip()
    if not value:
        raise MissingSecUserAgentError(
            "SEC_USER_AGENT is required for SEC requests. Set an identifiable "
            "application name and monitored contact email in .env."
        )
    return value


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Canonical paths derived from a single repository root."""

    root: Path = PROJECT_ROOT

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def bronze(self) -> Path:
        return self.data / "bronze"

    @property
    def silver(self) -> Path:
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        return self.data / "gold"

    @property
    def quality(self) -> Path:
        return self.data / "quality"

    @property
    def warehouse(self) -> Path:
        return self.data / "warehouse.duckdb"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure_runtime_directories(self) -> None:
        for path in (self.bronze, self.silver, self.gold, self.quality, self.logs):
            path.mkdir(parents=True, exist_ok=True)


PATHS: Final[ProjectPaths] = ProjectPaths()
