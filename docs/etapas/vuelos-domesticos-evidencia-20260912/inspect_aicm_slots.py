"""Inspect the preserved AICM Aeromexico summer 2026 slot PDF.

This is research-only. Slot assignments are scheduled movements, not flown
segments or transported passengers. Run from the repository root with:

    .venv/Scripts/python.exe docs/etapas/vuelos-domesticos-evidencia-20260912/inspect_aicm_slots.py
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
import glob
import json
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[3]
PDF = next(
    Path(path)
    for path in glob.glob(
        str(ROOT / "data/bronze/domestic_routes_research/aicm_aeromexico_summer_slots_*.pdf")
    )
)
QUARTER_START = date(2026, 4, 1)
QUARTER_END = date(2026, 6, 30)
TARGETS = {"MTY", "GDL", "CUN"}


def active_dates(start: date, end: date, frequency: str):
    day = start
    while day <= end:
        if frequency[day.weekday()] == str(day.weekday() + 1):
            yield day
        day += timedelta(days=1)


def main() -> None:
    rows = []
    invalid = []
    with pdfplumber.open(PDF) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for record in table:
                    if record[0] not in {"A", "D"}:
                        continue
                    try:
                        movement = record[0]
                        airport = record[7] if movement == "A" else record[9]
                        start = datetime.strptime(record[10], "%d/%m/%Y").date()
                        end = datetime.strptime(record[11], "%d/%m/%Y").date()
                        frequency = record[12]
                        reported = int(record[13])
                        if not airport or len(frequency) != 7:
                            raise ValueError("missing airport or bad frequency")
                        scheduled = list(active_dates(start, end, frequency))
                        if len(scheduled) != reported:
                            invalid.append(
                                {"page": page_number, "flight": record[1],
                                 "reported": reported, "reconstructed": len(scheduled)}
                            )
                        rows.append(
                            {"page": page_number, "movement": movement,
                             "flight": record[1], "airport": airport,
                             "equipment": record[4],
                             "start": str(start), "end": str(end),
                             "frequency": frequency, "reported": reported,
                             "quarter_dates": [
                                 str(day) for day in scheduled
                                 if QUARTER_START <= day <= QUARTER_END
                             ]}
                        )
                    except (ValueError, TypeError) as exc:
                        invalid.append({"page": page_number, "flight": record[1], "error": str(exc)})

    summary = {
        "source": str(PDF.relative_to(ROOT)).replace("\\", "/"),
        "scope": "AICM scheduled slot assignments; Aeromexico AM flight numbers",
        "quarter": "2026-04-01/2026-06-30",
        "pages": page_number,
        "rows": len(rows),
        "row_reconciliation_failures": invalid,
        "pilot_routes": {},
    }
    for airport in sorted(TARGETS):
        subset = [row for row in rows if row["airport"] == airport]
        movements = Counter(
            row["movement"]
            for row in subset for _ in row["quarter_dates"]
        )
        page_examples = sorted({row["page"] for row in subset if row["quarter_dates"]})[:10]
        occurrences = Counter(
            (row["movement"], row["flight"], day)
            for row in subset for day in row["quarter_dates"]
        )
        unique_by_movement = Counter(key[0] for key in occurrences)
        summary["pilot_routes"][airport] = {
            "A_to_MEX": movements["A"], "D_from_MEX": movements["D"],
            "total_AICM_movements": sum(movements.values()),
            "unique_flight_day_A_to_MEX": unique_by_movement["A"],
            "unique_flight_day_D_from_MEX": unique_by_movement["D"],
            "duplicate_flight_day_keys": sum(n - 1 for n in occurrences.values() if n > 1),
            "duplicate_examples": [
                {"movement": key[0], "flight": key[1], "day": key[2], "occurrences": n}
                for key, n in occurrences.items() if n > 1
            ][:10],
            "equipment": dict(Counter(
                row["equipment"] for row in subset for _ in row["quarter_dates"]
            )),
            "source_pages_first_10": page_examples,
        }

    output = Path(__file__).with_name("aicm_slots_inspection.json")
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
