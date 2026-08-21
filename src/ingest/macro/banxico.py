"""Banxico macro ingestion with an explicit Federal Reserve H.10 fallback."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from src.common.http import SourceHttpClient
from src.common.quality import log_issue_once
from src.common.storage import save_bronze
from src.config import PATHS
from src.ingest.stage4_common import (
    bronze_period,
    fetch_bronze,
    latest_bronze,
    lineage,
    write_parquet_atomic,
)


START_DATE = "2015-01-01"
BANXICO_SERIES = {
    "SF43718": "usd_mxn_fix",
    "SP1": "inpc",
    "SF61745": "policy_rate",
}
FED_H10_SERIES_ID = "H10/H10/RXI_N.B.MX"
FED_H10_PACKAGE = "60f32914ab61dfab590e0e470153e3ae"


def _parse_sie_file(
    path: Path, series_id: str, end_date: str | None = None
) -> list[dict[str, object]]:
    decoded = path.read_bytes().decode("latin1")
    lines = decoded.splitlines()
    header_index = next(
        index for index, line in enumerate(lines) if line == f'"Fecha","{series_id}"'
    )
    data = pd.read_csv(
        BytesIO(("\n".join(lines[header_index:]) + "\n").encode("latin1")),
        encoding="latin1",
    )
    data.columns = ["date", "value"]
    data["date"] = pd.to_datetime(data["date"], dayfirst=True)
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["date", "value"])
    cutoff = end_date or bronze_period(path).rsplit("_", maxsplit=1)[-1]
    data = data.loc[data["date"] <= pd.Timestamp(cutoff)]
    return [
        {
            "date": observation["date"],
            "series_id": series_id,
            "indicator_key": BANXICO_SERIES[series_id],
            "value": observation["value"],
            "source": "banxico_sie",
            **lineage(path),
        }
        for observation in data.to_dict(orient="records")
    ]


def _try_banxico(end_date: str) -> tuple[list[dict[str, object]], Path | None, str | None]:
    url = (
        "https://www.banxico.org.mx/SieInternet/"
        "consultarDirectorioInternetAction.do?accion=consultarSeries"
    )
    base_form = {
        "idCuadro": "CF373", "sector": "6", "version": "3", "locale": "es",
        "anoInicial": "2015", "anoFinal": str(pd.Timestamp(end_date).year),
        "tipoInformacion": "4,1", "formatoHorizontal": "false",
        "metadatosWeb": "true", "formatoCSV.x": "1", "formatoCSV.y": "1",
    }
    rows: list[dict[str, object]] = []
    first_path: Path | None = None
    try:
        with SourceHttpClient("banxico") as client:
            for series_id in BANXICO_SERIES:
                response = client.request("POST", url, data={**base_form, "series": series_id})
                content_type = response.headers.get("content-type", "")
                if "csv" not in content_type.lower():
                    raise ValueError(f"Banxico export for {series_id} did not return CSV")
                path = save_bronze(
                    response.content,
                    "banxico_sie",
                    series_id,
                    f"{START_DATE}_{end_date}",
                    "csv",
                    str(response.url),
                    "httpx",
                    "Official SIE public CSV export; no API token required.",
                    http_status=response.status_code,
                    content_type=content_type,
                    relative_dir="banxico",
                )
                first_path = first_path or path
                rows.extend(_parse_sie_file(path, series_id, end_date))
        return rows, first_path, None
    except Exception as exc:
        return [], first_path, f"Banxico public CSV export failed: {type(exc).__name__}"


def _fed_h10_fx(end_date: str) -> tuple[pd.DataFrame, Path]:
    url = "https://www.federalreserve.gov/datadownload/Output.aspx"
    params = {
        "rel": "H10", "series": FED_H10_PACKAGE, "lastobs": "",
        "from": pd.Timestamp(START_DATE).strftime("%m/%d/%Y"),
        "to": pd.Timestamp(end_date).strftime("%m/%d/%Y"),
        "filetype": "csv", "label": "include", "layout": "seriescolumn",
        "type": "package",
    }
    with SourceHttpClient("fred") as client:
        path = fetch_bronze(
            client,
            url,
            source_system="federal_reserve_h10",
            entity="usd_mxn",
            period=f"{START_DATE}_{end_date}",
            ext="csv",
            relative_dir="banxico/fred_fallback",
            params=params,
            notes="Federal Reserve H.10 Mexican-peso series; explicit fallback for unavailable Banxico FIX.",
        )
    raw = pd.read_csv(BytesIO(path.read_bytes()), header=None)
    header_index = raw.index[raw.iloc[:, 0].eq("Time Period")]
    if len(header_index) != 1:
        raise ValueError("Federal Reserve H.10 Time Period header not found")
    header_row = int(header_index[0])
    identifiers = raw.iloc[header_row].astype(str).tolist()
    mxn_column = identifiers.index("RXI_N.B.MX")
    frame = raw.iloc[header_row + 1 :, [0, mxn_column]].copy()
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"])
    frame["value"] = pd.to_numeric(frame["value"].replace("ND", pd.NA), errors="coerce")
    frame = frame.dropna(subset=["value"])
    frame["series_id"] = FED_H10_SERIES_ID
    frame["indicator_key"] = "usd_mxn"
    frame["source"] = "federal_reserve_h10"
    for key, value in lineage(path).items():
        frame[key] = value
    return frame, path


def _publish(macro: pd.DataFrame) -> dict[str, object]:
    macro = macro.sort_values(["series_id", "date"]).reset_index(drop=True)
    macro["value"] = macro["value"].astype("float64")
    macro["source_system"] = macro["source"]
    write_parquet_atomic(macro, PATHS.silver / "macro_indicators.parquet")

    fx = macro.loc[macro["indicator_key"].isin(["usd_mxn_fix", "usd_mxn"])].copy()
    fx = fx.rename(columns={"value": "rate_close"})
    fx["currency_pair"] = "USD/MXN"
    fx = fx[
        [
            "date", "currency_pair", "rate_close", "source", "series_id", "source_system",
            "source_file", "source_hash", "ingested_at", "parser_version",
        ]
    ]
    write_parquet_atomic(fx, PATHS.silver / "fx_rates.parquet")
    return {"rows": len(macro), "fx_rows": len(fx)}


def build_from_bronze(end_date: str | None = None) -> dict[str, object]:
    """Rebuild macro silver tables solely from immutable bronze artifacts."""

    rows: list[dict[str, object]] = []
    for series_id in BANXICO_SERIES:
        path = latest_bronze("banxico_sie", series_id)
        if path is None:
            raise FileNotFoundError(f"Missing Banxico bronze artifact for {series_id}")
        rows.extend(_parse_sie_file(path, series_id, end_date))
    return _publish(pd.DataFrame(rows))


def run(end_date: str | None = None) -> dict[str, object]:
    end = end_date or pd.Timestamp.now(tz="America/Mexico_City").date().isoformat()
    banxico_rows, _, banxico_error = _try_banxico(end)
    if banxico_rows:
        macro = pd.DataFrame(banxico_rows)
    else:
        macro = _fed_h10_fx(end)[0]
        log_issue_once(
            "silver",
            "fx_rates",
            "",
            "warning",
            "source_conflict",
            f"Banxico FIX was unavailable ({banxico_error}); Federal Reserve H.10 MXN/USD is used as an explicitly labelled fallback.",
            0,
        )
    result = _publish(macro)
    result["banxico_error"] = banxico_error
    return result


def main() -> int:
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
