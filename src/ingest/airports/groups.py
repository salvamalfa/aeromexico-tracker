"""Monthly Mexican airport traffic from official SEC and operator IR releases."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
import re
from difflib import get_close_matches
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader

from src.common.http import SourceHttpClient
from src.common.storage import save_bronze
from src.config import PATHS
from src.ingest.airports.reference import OPERATOR_AIRPORTS
from src.ingest.stage4_common import fetch_bronze, lineage, write_parquet_atomic


SEC_GROUPS = {"ASUR": "0001123452", "GAP": "0001347557"}
OMA_IR_URL = "https://ir.oma.aero/en/traffic-reports/"
AICM_STATS_INDEX = "https://www.aicm.com.mx/estadisticas-del-aicm/17-09-2013"
AIFA_STATS_INDEX = "https://aifa.aero/normateca"
MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
SPANISH_MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
GAP_CODES = {
    "Guadalajara": "GDL", "Tijuana": "TIJ", "Los Cabos": "SJD",
    "Puerto Vallarta": "PVR", "Guanajuato": "BJX", "Hermosillo": "HMO",
    "Morelia": "MLM", "La Paz": "LAP", "Mexicali": "MXL",
    "Aguascalientes": "AGU", "Los Mochis": "LMM", "Manzanillo": "ZLO",
    "Montego Bay": "MBJ", "Kingston": "KIN",
}
OMA_CODES = {
    "Acapulco": "ACA", "Ciudad Juarez": "CJS", "Culiacan": "CUL",
    "Chihuahua": "CUU", "Durango": "DGO", "Mazatlan": "MZT",
    "Monterrey": "MTY", "Reynosa": "REX", "San Luis Potosi": "SLP",
    "Tampico": "TAM", "Torreon": "TRC", "Zacatecas": "ZCL",
    "Zihuatanejo": "ZIH",
}


def _number(value: object, *, scale: float = 1.0) -> int | None:
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan":
        return None
    try:
        return int(round(float(text) * scale))
    except ValueError:
        return None


def _period(year: int, month: int) -> str:
    return f"{year}M{month:02d}"


def _month_number(label: str) -> int | None:
    prefix = label.strip()[:3].casefold()
    names = {**MONTHS, **SPANISH_MONTHS}
    return next((number for name, number in names.items() if name[:3].casefold() == prefix), None)


def _base_row(period_id: str, code: str, name: str, group: str, source: str) -> dict[str, object]:
    return {
        "period_id": period_id,
        "airport_iata": code,
        "airport_name": name,
        "operator_group": group,
        "country": "Mexico" if code not in {"MBJ", "KIN"} else "Jamaica",
        "passengers_domestic": None,
        "passengers_international": None,
        "passengers_total": None,
        "cargo_tons": None,
        "operations": None,
        "source": source,
        "source_system": source,
        "is_group_total": code.startswith("ALL_"),
    }


def _parse_asur(content: bytes, source_path) -> list[dict[str, object]]:
    try:
        tables = pd.read_html(BytesIO(content))
    except ValueError:
        return []
    summary = next((t for t in tables if "Passenger Traffic Summary" in str(t.iloc[0, 0])), None)
    detail = next((t for t in tables if "Mexico Passenger Traffic" in str(t.iloc[0, 0])), None)
    if summary is None or detail is None:
        return []
    month_name = str(summary.iloc[1, 1])
    month = _month_number(month_name)
    if month is None:
        return []
    years = [int(summary.iloc[2, 1]), int(summary.iloc[2, 2])]
    rows: list[dict[str, object]] = []
    mexico = summary.loc[summary.iloc[:, 0].astype(str).eq("Mexico")].iloc[0]
    domestic = summary.iloc[summary.index.get_loc(mexico.name) + 1]
    international = summary.iloc[summary.index.get_loc(mexico.name) + 2]
    for offset, year in enumerate(years, start=1):
        row = _base_row(_period(year, month), "ALL_ASUR", "ASUR Mexico airports", "ASUR", "sec_edgar")
        row.update(
            passengers_domestic=_number(domestic.iloc[offset]),
            passengers_international=_number(international.iloc[offset]),
            passengers_total=_number(mexico.iloc[offset]),
            **lineage(source_path),
        )
        rows.append(row)
    total_start = detail.index[detail.iloc[:, 0].astype(str).eq("Traffic Total Mexico")]
    if len(total_start):
        for _, item in detail.loc[total_start[0] + 1 :].iterrows():
            code = str(item.iloc[0]).strip()
            if not re.fullmatch(r"[A-Z]{3}", code):
                continue
            for offset, year in enumerate(years, start=2):
                row = _base_row(_period(year, month), code, str(item.iloc[1]), "ASUR", "sec_edgar")
                row.update(passengers_total=_number(item.iloc[offset]), **lineage(source_path))
                rows.append(row)
    return rows


def _clean_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("*", " ")).strip()


def _parse_gap(content: bytes, source_path) -> list[dict[str, object]]:
    try:
        tables = pd.read_html(BytesIO(content))
    except ValueError:
        return []
    classified: dict[str, pd.DataFrame] = {}
    airport_tables: list[pd.DataFrame] = []
    for table in tables:
        title = str(table.iloc[0, 0]).lower()
        if str(table.iloc[0, 0]).strip().lower() == "airport":
            airport_tables.append(table)
            continue
        if "terminal passengers" not in title:
            continue
        if "domestic" in title:
            classified["domestic"] = table
        elif "international" in title:
            classified["international"] = table
        elif "total" in title:
            classified["total"] = table
    if len(classified) < 3 and len(airport_tables) >= 3:
        classified = dict(zip(["domestic", "international", "total"], airport_tables[:3]))
    if "total" not in classified:
        return []
    header_positions = classified["total"].index[
        classified["total"].iloc[:, 0].astype(str).str.strip().eq("Airport")
    ]
    if not len(header_positions):
        return []
    header_position = int(header_positions[0])
    header = classified["total"].loc[header_position]
    labels = [str(header.iloc[1]), str(header.iloc[2])]
    parsed = [re.search(r"([A-Za-z]+)-(\d{2})", label) for label in labels]
    if any(match is None for match in parsed):
        return []
    periods = []
    for match in parsed:
        month = _month_number(match.group(1))  # type: ignore[union-attr]
        if month is None:
            return []
        periods.append(_period(2000 + int(match.group(2)), month))  # type: ignore[union-attr]
    values: dict[tuple[str, str], dict[str, int | None]] = defaultdict(dict)
    names: dict[str, str] = {}
    for metric, table in classified.items():
        metric_headers = table.index[table.iloc[:, 0].astype(str).str.strip().eq("Airport")]
        if not len(metric_headers):
            continue
        for _, item in table.loc[int(metric_headers[0]) + 1 :].iterrows():
            name = _clean_name(item.iloc[0])
            if name.lower() == "total":
                continue
            code = GAP_CODES.get(name)
            if not code:
                continue
            names[code] = name
            for index, period_id in enumerate(periods, start=1):
                values[(period_id, code)][metric] = _number(item.iloc[index], scale=1000)
    rows: list[dict[str, object]] = []
    for (period_id, code), metrics in values.items():
        row = _base_row(period_id, code, names[code], "GAP", "sec_edgar")
        row.update(
            passengers_domestic=metrics.get("domestic"),
            passengers_international=metrics.get("international"),
            passengers_total=metrics.get("total"),
            **lineage(source_path),
        )
        rows.append(row)
    for period_id in periods:
        mexican = [r for r in rows if r["period_id"] == period_id and r["country"] == "Mexico"]
        if not mexican:
            continue
        total = _base_row(period_id, "ALL_GAP", "GAP Mexico airports", "GAP", "sec_edgar")
        for column in ["passengers_domestic", "passengers_international", "passengers_total"]:
            total[column] = sum(int(r[column] or 0) for r in mexican)
        total.update(lineage(source_path))
        rows.append(total)
    return rows


def _sec_documents(group: str, cik: str) -> list[tuple[bytes, object]]:
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    with SourceHttpClient("sec") as client:
        submissions_path = fetch_bronze(
            client,
            submissions_url,
            source_system="sec_edgar",
            entity=f"{group}_submissions",
            period="current",
            ext="json",
            relative_dir=f"airports/{group.lower()}",
            notes="SEC submissions used to discover official airport traffic releases.",
        )
        payload = json.loads(submissions_path.read_text(encoding="utf-8"))
        recent = payload["filings"]["recent"]
        candidates = [
            (recent["accessionNumber"][i], recent["primaryDocument"][i])
            for i, form in enumerate(recent["form"])
            if form == "6-K" and str(recent["filingDate"][i]).startswith("2026-")
        ]
        found: list[tuple[bytes, object]] = []
        seen_urls: set[str] = set()
        for accession, primary in candidates:
            compact = accession.replace("-", "")
            folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}"
            index_path = fetch_bronze(
                client,
                f"{folder}/index.json",
                source_system="sec_edgar",
                entity=f"{group}_{accession}_index",
                period=accession,
                ext="json",
                relative_dir=f"airports/{group.lower()}/{accession}",
            )
            index = json.loads(index_path.read_text(encoding="utf-8"))
            filenames = [primary]
            filenames.extend(
                item["name"]
                for item in index.get("directory", {}).get("item", [])
                if str(item.get("name", "")).lower().endswith((".htm", ".html"))
                and 10_000 <= int(item.get("size", 0) or 0) <= 1_000_000
            )
            for filename in dict.fromkeys(filenames):
                url = f"{folder}/{filename}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    path = fetch_bronze(
                        client,
                        url,
                        source_system="sec_edgar",
                        entity=f"{group}_{accession}_{filename}",
                        period=accession,
                        ext="htm",
                        relative_dir=f"airports/{group.lower()}/{accession}",
                    )
                except Exception:
                    continue
                content = path.read_bytes()
                text = BeautifulSoup(content, "lxml").get_text(" ", strip=True).lower()
                if "passenger traffic" not in text:
                    continue
                parser = _parse_asur if group == "ASUR" else _parse_gap
                if parser(content, path):
                    found.append((content, path))
                    break
        return found


def _ascii_words(value: str) -> str:
    value = value.replace("�", " ")
    return re.sub(r"[^a-z ]+", " ", value.lower()).strip()


def _parse_oma_pdf(content: bytes, source_path) -> list[dict[str, object]]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    header = re.search(
        r"([A-Z][a-z]+)-(20\d{2})\s+([A-Z][a-z]+)-(20\d{2})\s+Change",
        text,
    )
    if not header:
        return []
    month = _month_number(header.group(1))
    if month is None:
        return []
    years = [int(header.group(2)), int(header.group(4))]
    rows: list[dict[str, object]] = []
    group_match = re.search(
        r"Domestic\s+([\d,]+)\s+([\d,]+).*?International\s+([\d,]+)\s+([\d,]+).*?OMA Total\s+([\d,]+)\s+([\d,]+)",
        text,
        re.S,
    )
    if group_match:
        numbers = [_number(value) for value in group_match.groups()]
        for index, year in enumerate(years):
            row = _base_row(_period(year, month), "ALL_OMA", "OMA airports", "OMA", "oma_ir")
            row.update(
                passengers_domestic=numbers[index],
                passengers_international=numbers[index + 2],
                passengers_total=numbers[index + 4],
                **lineage(source_path),
            )
            rows.append(row)
    known_names = list(OMA_CODES)
    for line in text.splitlines():
        match = re.match(r"(.+?)\s+([\d,]+)\s+([\d,]+)\s+\(?-?[\d.]+\)?\s+", line.strip())
        if not match:
            continue
        raw_name = match.group(1).strip()
        normalized = _ascii_words(raw_name)
        choices = {_ascii_words(name): name for name in known_names}
        close = get_close_matches(normalized, list(choices), n=1, cutoff=0.62)
        if not close:
            continue
        canonical = choices[close[0]]
        code = OMA_CODES[canonical]
        for index, year in enumerate(years, start=2):
            row = _base_row(_period(year, month), code, canonical, "OMA", "oma_ir")
            row.update(passengers_total=_number(match.group(index)), **lineage(source_path))
            rows.append(row)
    return rows


def _aicm_current_values(
    text: str, *, decimal: bool = False
) -> dict[int, tuple[float, float, float]]:
    number = r"[\d,.]+" if decimal else r"[\d,]+"
    output: dict[int, tuple[float, float, float]] = {}
    for label, month in SPANISH_MONTHS.items():
        match = re.search(
            rf"(?m)^{label}\s+" + r"\s+".join([f"({number})"] * 6) + r"(?:\s+.*)?$",
            text,
        )
        if match:
            output[month] = tuple(
                float(match.group(index).replace(",", "")) for index in (4, 5, 6)
            )
    return output


def _aifa_monthly_block(frame: pd.DataFrame) -> dict[int, tuple[float, float, float]]:
    first = frame.index[frame.iloc[:, 2].astype(str).str.strip().eq("ENERO")]
    if not len(first):
        raise ValueError("Could not locate monthly block in AIFA sheet")
    block = frame.loc[int(first[0]) : int(first[0]) + 11, [2, 3, 4, 5]]
    output: dict[int, tuple[float, float, float]] = {}
    for _, item in block.iterrows():
        month = _month_number(item.iloc[0])
        if month is not None and pd.notna(item.iloc[1]) and pd.notna(item.iloc[2]):
            output[month] = tuple(float(item.iloc[index]) for index in (1, 2, 3))
    return output


def _aifa_publication_year(frame: pd.DataFrame) -> int:
    header_text = " ".join(frame.iloc[:10].astype(str).to_numpy().ravel())
    year_values = re.findall(r"20\d{2}", header_text)
    if not year_values:
        raise ValueError("Could not determine AIFA publication year")
    return int(year_values[0])


def _parse_aicm_pdf(content: bytes, source_path) -> list[dict[str, object]]:
    pages = [page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages]
    if len(pages) < 13:
        raise ValueError("AICM statistics PDF has fewer pages than expected")

    year_match = re.search(r"Enero-[A-Za-z]+\s+(20\d{2})", pages[2])
    if not year_match:
        raise ValueError("Could not determine AICM publication year")
    year = int(year_match.group(1))
    passengers = _aicm_current_values(pages[2])
    operations = _aicm_current_values(pages[7])
    cargo = _aicm_current_values(pages[12], decimal=True)
    if not passengers:
        raise ValueError("No current-year AICM passenger months were found")
    rows: list[dict[str, object]] = []
    for month, (domestic, international, total) in passengers.items():
        row = _base_row(_period(year, month), "MEX", "Mexico City", "GOVERNMENT", "aicm")
        row.update(
            passengers_domestic=int(domestic),
            passengers_international=int(international),
            passengers_total=int(total),
            operations=int(operations[month][2]) if month in operations else None,
            cargo_tons=cargo[month][2] if month in cargo else None,
            **lineage(source_path),
        )
        rows.append(row)
    return rows


def _parse_aifa_xlsx(content: bytes, source_path) -> list[dict[str, object]]:
    def monthly_sheet(sheet_name: str) -> dict[int, tuple[float, float, float]]:
        frame = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=None)
        return _aifa_monthly_block(frame)

    passengers = monthly_sheet("Pasajeros")
    operations = monthly_sheet("Operaciones")
    cargo = monthly_sheet("Carga")
    first_sheet = pd.read_excel(BytesIO(content), sheet_name="Esquema Operativo", header=None)
    year = _aifa_publication_year(first_sheet)
    if not passengers:
        raise ValueError("No current-year AIFA passenger months were found")
    rows: list[dict[str, object]] = []
    for month, (domestic, international, total) in passengers.items():
        row = _base_row(_period(year, month), "NLU", "Felipe Angeles", "GOVERNMENT", "aifa")
        row.update(
            passengers_domestic=int(domestic),
            passengers_international=int(international),
            passengers_total=int(total),
            operations=int(operations[month][2]) if month in operations else None,
            cargo_tons=cargo[month][2] / 1000 if month in cargo else None,
            **lineage(source_path),
        )
        rows.append(row)
    return rows


def _oma_documents() -> list[tuple[bytes, object]]:
    with SourceHttpClient("airports") as client:
        index_path = fetch_bronze(
            client,
            OMA_IR_URL,
            source_system="oma_ir",
            entity="traffic_index",
            period="current",
            ext="html",
            relative_dir="airports/oma",
        )
        soup = BeautifulSoup(index_path.read_bytes(), "lxml")
        links: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            title = " ".join(anchor.stripped_strings)
            match = re.search(r"(20\d{2}) Total Passenger Traffic", title)
            if not match or int(match.group(1)) < 2025:
                continue
            links.append((title, anchor["href"]))
        documents: list[tuple[bytes, object]] = []
        for title, url in dict.fromkeys(links):
            path = fetch_bronze(
                client,
                url,
                source_system="oma_ir",
                entity=re.sub(r"\W+", "_", title).strip("_"),
                period=title,
                ext="pdf",
                relative_dir="airports/oma",
                notes="Official OMA monthly traffic report linked from its IR index.",
            )
            if path.read_bytes().startswith(b"%PDF"):
                documents.append((path.read_bytes(), path))
        return documents


def _government_documents() -> list[object]:
    with SourceHttpClient("airports") as client:
        aicm_index = fetch_bronze(
            client,
            AICM_STATS_INDEX,
            source_system="aicm",
            entity="statistics_index",
            period="current",
            ext="html",
            relative_dir="airports/government",
            notes="Official AICM statistics landing page used for link discovery.",
        )
        aicm_soup = BeautifulSoup(aicm_index.read_bytes(), "lxml")
        aicm_links = [
            urljoin(AICM_STATS_INDEX, anchor["href"])
            for anchor in aicm_soup.find_all("a", href=True)
            if "Estadísticas del AICM a" in " ".join(anchor.stripped_strings)
        ]
        if not aicm_links:
            raise RuntimeError("Current AICM statistics link was not found")
        aicm = fetch_bronze(
            client,
            aicm_links[0],
            source_system="aicm",
            entity="traffic_statistics",
            period="current",
            ext="pdf",
            relative_dir="airports/government",
            notes="Official AICM en Cifras monthly publication.",
        )
        aifa_index = fetch_bronze(
            client,
            AIFA_STATS_INDEX,
            source_system="aifa",
            entity="statistics_index",
            period="current",
            ext="html",
            relative_dir="airports/government",
            notes="Official AIFA statistics landing page used for link discovery.",
        )
        aifa_soup = BeautifulSoup(aifa_index.read_bytes(), "lxml")
        aifa_links = [
            urljoin(AIFA_STATS_INDEX, anchor["href"])
            for anchor in aifa_soup.find_all("a", href=True)
            if "Numeralia Aeroportuaria" in " ".join(anchor.stripped_strings)
            and "Formato XLSX" in " ".join(anchor.stripped_strings)
        ]
        if not aifa_links:
            raise RuntimeError("Current AIFA XLSX statistics link was not found")
        aifa = fetch_bronze(
            client,
            aifa_links[-1],
            source_system="aifa",
            entity="airport_statistics",
            period="current",
            ext="xlsx",
            relative_dir="airports/government",
            notes="Official AIFA monthly airport-statistics workbook.",
        )
    return [aicm, aifa]


def build_from_bronze() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    parsed_files: dict[str, int] = {}
    for group, parser, pattern in [
        ("ASUR", _parse_asur, "*.htm"),
        ("GAP", _parse_gap, "*.htm"),
        ("OMA", _parse_oma_pdf, "*.pdf"),
    ]:
        count = 0
        for path in (PATHS.bronze / "airports" / group.lower()).rglob(pattern):
            try:
                parsed = parser(path.read_bytes(), path)
            except Exception:
                continue
            if parsed:
                count += 1
                rows.extend(parsed)
        parsed_files[group] = count
    government_count = 0
    for parser, pattern in [(_parse_aicm_pdf, "aicm_*.pdf"), (_parse_aifa_xlsx, "aifa_*.xlsx")]:
        for path in (PATHS.bronze / "airports" / "government").glob(pattern):
            parsed = parser(path.read_bytes(), path)
            if parsed:
                government_count += 1
                rows.extend(parsed)
    parsed_files["GOVERNMENT"] = government_count
    if not rows:
        raise RuntimeError("No airport traffic rows parsed")
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["period_id", "operator_group", "airport_iata", "ingested_at"])
    frame = frame.drop_duplicates(["period_id", "operator_group", "airport_iata"], keep="last")
    integer_columns = [
        "passengers_domestic", "passengers_international", "passengers_total",
        "operations",
    ]
    for column in integer_columns:
        frame[column] = pd.array(frame[column], dtype="Int64")
    frame["cargo_tons"] = pd.to_numeric(frame["cargo_tons"], errors="coerce").astype("Float64")
    write_parquet_atomic(frame.reset_index(drop=True), PATHS.silver / "airport_traffic.parquet")
    return {"rows": len(frame), "parsed_files": parsed_files}


def run() -> dict[str, object]:
    source_counts: dict[str, int] = {}
    for group, cik in SEC_GROUPS.items():
        documents = _sec_documents(group, cik)
        source_counts[group] = len(documents)
    oma_documents = _oma_documents()
    source_counts["OMA"] = len(oma_documents)
    source_counts["GOVERNMENT"] = len(_government_documents())
    result = build_from_bronze()
    result["downloaded_documents"] = source_counts
    return result


def main() -> int:
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
