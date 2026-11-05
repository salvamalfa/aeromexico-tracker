"""Exact BTS query exception used by validated public presentation sources."""

from __future__ import annotations

import re
from urllib.parse import SplitResult, parse_qs

BTS_SOURCE_HOSTS = frozenset({"www.transtats.bts.gov", "transtats.bts.gov"})


def approved_bts_query(parsed: SplitResult) -> bool:
    """Keep the existing four-parameter Mexico T-100 reference policy unchanged."""
    if parsed.hostname not in BTS_SOURCE_HOSTS:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    return (
        parsed.path == "/DL_SelectFields.aspx"
        and set(query) == {"gnoyr_VQ", "QO_fu146_anzr", "requested_geography", "requested_year"}
        and query["gnoyr_VQ"] == ["FJE"]
        and query["QO_fu146_anzr"] == ["Nv4 Pn44vr45"]
        and query["requested_geography"] == ["Mexico"]
        and len(query["requested_year"]) == 1
        and re.fullmatch(r"20\d{2}", query["requested_year"][0]) is not None
    )
