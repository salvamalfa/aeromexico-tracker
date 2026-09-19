"""Build the first standalone Vuelos review increment and candidate evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis_agent.flight_evidence import build_flight_evidence, write_flight_evidence
from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import DEFAULT_OUTPUT, write_flights_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_flight_payload()
    html_path = write_flights_html(payload, args.output)
    evidence_path = write_flight_evidence(build_flight_evidence(payload))
    print(f"Vuelos review written to {html_path}")
    print(f"Candidate flight evidence written to {evidence_path}")


if __name__ == "__main__":
    main()
