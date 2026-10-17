"""Keep dated AICM programming separate from observed international routes."""

AICM_LABEL = "AICM · vuelos AM programados"


def add_aicm_schedules(network, scheduled, months, endpoint):
    """Add missing scheduled markets and annotate observations without summing."""
    if not scheduled.empty:
        current_slots = scheduled[scheduled.period_id.isin(months)].copy()
        if not current_slots.empty:
            current_slots["market_key"] = current_slots.apply(
                lambda r: "<>".join(sorted((r.origin_iata, r.dest_iata))), axis=1
            )
            for market, group in current_slots.groupby("market_key"):
                scheduled_count = int(group.scheduled_movements.sum())
                scheduled_months = sorted(group.period_id.unique())
                scheduled_month_label = ", ".join(month[5:] for month in scheduled_months)
                matching = next((r for r in network["routes"] if r["market_key"] == market), None)
                if matching is not None:
                    matching["scheduled_movements_q2"] = scheduled_count
                    matching["scheduled_source_label"] = AICM_LABEL
                    matching["coverage_note"] += (
                        f" · AICM meses {scheduled_month_label}: {scheduled_count:,} programados"
                    )
                    continue
                a, b = market.split("<>")
                directions = [
                    dict(
                        origin_iata=origin,
                        destination_iata=dest,
                        passengers=None,
                        seats=None,
                        departures=int(part.scheduled_movements.sum()),
                    )
                    for (origin, dest), part in group.groupby(["origin_iata", "dest_iata"])
                ]
                network["routes"].append(
                    dict(
                        market_key=market,
                        origin=endpoint(a),
                        destination=endpoint(b),
                        passengers=None,
                        seats=None,
                        departures=scheduled_count,
                        load_factor=None,
                        previous={k: None for k in ("passengers", "seats", "departures")},
                        directions=directions,
                        source_label=AICM_LABEL,
                        observed_months=[],
                        scheduled_months=scheduled_months,
                        coverage_note=(
                            f"Meses: {scheduled_month_label} · AICM · programado, ejecución sin verificar"
                        ),
                        source_hashes=sorted(group.source_hash.unique()),
                        record_ids=sorted(group.record_id.unique()),
                        operation_status="assigned_slot_not_flown",
                        carrier_role="AM_flight_number_slot_holder",
                        marketing_carrier=None,
                        agent_eligible=False,
                    )
                )
