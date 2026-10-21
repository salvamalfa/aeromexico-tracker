"""Bounded public H.10 captures; no credentials, retries or implicit fallback."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from src.common.http import get_rate_limiter
from src.ingest.macro.banxico import H10_EXPORT_URL, h10_export_params
from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end


MAX_BYTES = 2_000_000
URLS = {
    "history": "https://www.federalreserve.gov/releases/h10/hist/dat00_mx.htm",
    "holidays": "https://www.federalreserve.gov/aboutthefed/k8.htm",
    "definition": "https://www.federalreserve.gov/releases/h10/about.htm",
    "release": "https://www.federalreserve.gov/releases/h10/current/default.htm",
    "transition": "https://www.federalreserve.gov/data/data-download-fred-information.htm",
}


def month_bounds(period: str):
    from datetime import date

    if len(period) != 7 or period[4] != "M":
        raise ValueError("H.10 certification accepts one closed YYYY Mmm month (YYYYMmm)")
    end = period_end(period)
    return date(end.year, end.month, 1), end


def selection(period: str, as_of: str) -> dict:
    _, end = month_bounds(period)
    if end >= local_time(as_of).date():
        raise ValueError("H.10 observation month must be closed before the cutoff")
    urls = {"csv": H10_EXPORT_URL + "?" + urlencode(h10_export_params(end.isoformat())), **URLS}
    return {
        "version": 1,
        "items": [
            {
                "id": "h10-" + role,
                "product": "h10",
                "source_system": "federal_reserve_h10",
                "entity": "h10_certification_" + role,
                "period": period,
                "purpose": "data",
                "url": url,
                "extension": "csv" if role == "csv" else "html",
                "mode": "get",
                "relative_dir": "h10/certification/" + period,
            }
            for role, url in urls.items()
        ],
    }


class BoundedFedClient:
    """Collection's redirect gate runs before each streamed, size-limited GET."""

    def __init__(self, source, *, max_attempts=1, transport=None):
        if max_attempts != 1:
            raise ValueError("H.10 capture has no implicit retries")
        self.client = httpx.Client(
            timeout=20,
            follow_redirects=False,
            headers={"User-Agent": "Aeromexico-Tracker/0.1", "Accept": "*/*"},
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def request(self, method, url, **kwargs):
        if method != "GET" or kwargs != {"follow_redirects": False}:
            raise ValueError("H.10 bounded client only accepts explicit public GET")
        get_rate_limiter("fred").acquire()
        with self.client.stream("GET", url) as response:
            declared = response.headers.get("content-length")
            if declared and int(declared) > MAX_BYTES:
                raise ValueError("H.10 response exceeds the declared size limit")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("H.10 decoded response exceeds the size limit")
            headers = dict(response.headers)
            # iter_bytes already decoded transport compression.
            for name in ("content-encoding", "content-length"):
                headers.pop(name, None)
            return httpx.Response(
                response.status_code, headers=headers, content=bytes(body), request=response.request
            )
