"""Build the current Vuelos payload and its candidate flight evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis_agent.flight_evidence import DEFAULT_OUTPUT_DIR, build_flight_evidence, write_flight_evidence
from src.dashboard.flights import build_flight_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    payload = build_flight_payload()
    evidence_path = write_flight_evidence(build_flight_evidence(payload), args.output)
    print(f"Vuelos payload rebuilt ({len(payload['quarters'])} quarters)")
    print(f"Candidate flight evidence written to {evidence_path}")


if __name__ == "__main__":
    main()
