"""Keep retained monthly domestic frequency admission additive across grains."""

from __future__ import annotations

import pandas as pd


def retained_monthly_frequencies(lookup: pd.DataFrame) -> pd.Series:
    """Freeze the existing monthly route's frequency basis before aggregation.

    This preserves the retained monthly admission, including its unresolved
    aircraft-model limitations; capacity completeness is not new evidence of
    carrier identity. A complete monthly market previously used its retained
    departures, while an incomplete one used same-month seed frequencies.
    Choose that basis once for the whole market/month, then add its directional
    values at every grain. Rechoosing it per direction or quarter both changes
    the accepted total and makes a route disagree with its own breakdown.
    """

    retained_basis = lookup.groupby(["market_key", "period_id"])["complete"].transform("all")
    return lookup["departures_estimated"].where(retained_basis, lookup["frequency_estimated"])
