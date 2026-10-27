"""Decimal reconciliation within reported precision; no inferred Q1 values become facts."""

from decimal import Decimal

from src.source_updates.viva_financial_spec import BALANCE, INCOME


def numeric(row):
    return Decimal(row.source_value.rstrip("%x").replace(",", "")) * Decimal(str(row.scale))


def half_quantum(row):
    if row.unit in {"aircraft", "sectors"}:
        return Decimal(0)  # Reported whole counts are exact, not rounded financial amounts.
    value = Decimal(row.source_value.rstrip("%x").replace(",", ""))
    return Decimal(10) ** value.as_tuple().exponent * Decimal(str(row.scale)) / 2


def reconcile(native):
    checks = []

    def compare(name, left, right):
        actual = sum(numeric(row) * sign for row, sign in left)
        expected = sum(numeric(row) * sign for row, sign in right)
        tolerance = sum(half_quantum(row) * abs(sign) for row, sign in left + right)
        residual = actual - expected
        if abs(residual) > tolerance:
            raise ValueError(f"Viva reconciliation failed: {name}; residual={residual}, bound={tolerance}")
        checks.append(dict(check=name, residual=str(residual), rounding_bound=str(tolerance)))

    def ratio(name, numerator, denominator, reported, factor=Decimal(1)):
        terms = numerator if isinstance(numerator, list) else [(numerator, 1)]
        n = sum(numeric(row) * sign for row, sign in terms)
        hn = sum(half_quantum(row) * abs(sign) for row, sign in terms)
        d, r = numeric(denominator), numeric(reported)
        hd, hr = half_quantum(denominator), half_quantum(reported)
        if d <= hd:
            raise ValueError("Viva ratio denominator does not have a positive precision interval")
        candidates = [(n + a * hn) / (d + b * hd) * factor for a in (-1, 1) for b in (-1, 1)]
        if r + hr < min(candidates) or r - hr > max(candidates):
            raise ValueError(f"Viva rounded ratio disagrees: {name}")
        checks.append(dict(check=name, interval_overlap=True))

    for edition, frame in native.groupby("edition", sort=True):

        def rows(statement, kind, stop):
            part = frame.loc[
                frame.statement.eq(statement) & frame.period_type.eq(kind) & frame.period_end_date.eq(stop)
            ]
            return {(r.metric_key, r.segment): r for r in part.itertuples(index=False)}

        for (kind, start, stop), group in frame.loc[frame.statement.eq("income")].groupby(
            ["period_type", "period_start_date", "period_end_date"], sort=True
        ):
            prefix = f"{edition}/{kind}/{start}/{stop}"
            income = {r.metric_key: r for r in group.itertuples(index=False)}
            i = income.__getitem__
            indicators = rows("indicators", kind, stop)

            def ind(key, seg="consolidated"):
                return indicators[(key, seg)]

            compare(
                prefix + "/revenue",
                [(i("passenger_revenue"), 1), (i("ancillary_revenue"), 1)],
                [(i("total_revenue"), 1)],
            )
            expense_keys = [row[1] for row in INCOME[3:13]]
            compare(
                prefix + "/expenses",
                [(i(key), 1) for key in expense_keys],
                [(i("total_operating_expenses"), 1)],
            )
            compare(
                prefix + "/EBIT",
                [(i("total_revenue"), 1), (i("total_operating_expenses"), -1)],
                [(i("operating_income"), 1)],
            )
            compare(
                prefix + "/net_finance",
                [(i("financial_income"), 1), (i("financial_costs"), 1)],
                [(i("net_finance_costs"), 1)],
            )
            compare(
                prefix + "/pretax",
                [(i("operating_income"), 1), (i("net_finance_costs"), 1)],
                [(i("income_before_tax"), 1)],
            )
            compare(
                prefix + "/net_income",
                [(i("income_before_tax"), 1), (i("income_tax"), -1)],
                [(i("net_income"), 1)],
            )
            compare(prefix + "/indicator_revenue", [(i("total_revenue"), 1)], [(ind("total_revenue"), 1)])
            compare(
                prefix + "/EBITDA",
                [(i("operating_income"), 1), (i("depreciation_amortization"), 1)],
                [(ind("ebitda_non_ifrs"), 1)],
            )
            compare(
                prefix + "/EBITDAR",
                [(ind("ebitda_non_ifrs"), 1), (i("leases"), 1)],
                [(ind("ebitdar_non_ifrs"), 1)],
            )
            for metric in ["asm", "rpm", "booked_passengers"]:
                compare(
                    prefix + "/segments_" + metric,
                    [(ind(metric, "domestic"), 1), (ind(metric, "international"), 1)],
                    [(ind(metric, "total"), 1)],
                )
            # LF uses SCHEDULED traffic; reported total ASM/RPM are not the same denominator.
            for numerator, key in [
                ("operating_income", "operating_margin"),
                ("income_before_tax", "ebt_margin"),
                ("net_income", "net_margin"),
            ]:
                ratio(prefix + "/" + key, i(numerator), i("total_revenue"), i(key))
            for numerator, key in [
                ("ebitdar_non_ifrs", "ebitdar_margin"),
                ("ebitda_non_ifrs", "ebitda_margin"),
            ]:
                ratio(prefix + "/" + key, ind(numerator), i("total_revenue"), ind(key))
            for numerator, key in [
                ("total_revenue", "trasm"),
                ("total_operating_expenses", "casm"),
                ("fuel", "casm_fuel"),
            ]:
                ratio(prefix + "/" + key, i(numerator), ind("asm", "total"), ind(key, "total"), Decimal(100))
            compare(
                prefix + "/casm_components",
                [(ind("casm_ex_fuel", "total"), 1), (ind("casm_fuel", "total"), 1)],
                [(ind("casm", "total"), 1)],
            )
            for numerator, denominator, metric in [
                ("passenger_revenue", "booked_passengers", "fare_per_booked_passenger"),
                ("ancillary_revenue", "booked_passengers", "ancillary_per_booked_passenger"),
                ("total_revenue", "booked_passengers", "revenue_per_booked_passenger"),
                ("total_revenue", "seats", "revenue_per_seat"),
                ("total_operating_expenses", "seats", "cost_per_seat"),
            ]:
                ratio(prefix + "/" + metric, i(numerator), ind(denominator, "total"), ind(metric, "total"))
            ex_fuel = [(i("total_operating_expenses"), 1), (i("fuel"), -1)]
            ratio(
                prefix + "/cost_ex_fuel_per_seat",
                ex_fuel,
                ind("seats", "total"),
                ind("cost_ex_fuel_per_seat", "total"),
            )
            ratio(
                prefix + "/casm_ex_fuel",
                ex_fuel,
                ind("asm", "total"),
                ind("casm_ex_fuel", "total"),
                Decimal(100),
            )
            cash = rows("cash_flow", kind, stop)

            def c(key):
                return cash[(key, "consolidated")]

            compare(
                prefix + "/cash_flow",
                [(c(k), 1) for k in ("cash_operating", "cash_investing", "cash_financing")],
                [(c("cash_change"), 1)],
            )
            compare(
                prefix + "/cash_movement", [(c("cash_begin"), 1), (c("cash_change"), 1)], [(c("cash_end"), 1)]
            )
            balance = rows("balance", "instant", stop)
            if balance:
                compare(
                    prefix + "/cash_balance", [(c("cash_end"), 1)], [(balance[("cash", "consolidated")], 1)]
                )
        for stop in sorted(frame.loc[frame.statement.eq("balance"), "period_end_date"].unique()):
            balance = rows("balance", "instant", stop)

            def b(key):
                return balance[(key, "consolidated")]

            prefix = f"{edition}/balance/{stop}"
            for name, indices, total in [
                ("current_assets", range(0, 6), "current_assets"),
                ("assets", [6, *range(7, 16)], "assets"),
                ("current_liabilities", range(17, 27), "current_liabilities"),
                ("liabilities", [27, *range(28, 33)], "liabilities"),
                ("equity", range(34, 42), "equity"),
            ]:
                compare(
                    prefix + "/" + name, [(b(BALANCE[index][1]), 1) for index in indices], [(b(total), 1)]
                )
            compare(
                prefix + "/assets_liabilities_equity",
                [(b("liabilities"), 1), (b("equity"), 1)],
                [(b("assets"), 1)],
            )
            compare(prefix + "/printed_total", [(b("liabilities_equity"), 1)], [(b("assets"), 1)])
            debt = rows("debt", "instant", stop)

            def d(key):
                return debt[(key, "consolidated")]

            compare(
                prefix + "/debt",
                [(b("current_loans"), 1), (b("noncurrent_loans"), 1)],
                [(d("financial_debt"), 1)],
            )
            compare(
                prefix + "/leases",
                [(b("current_leases"), 1), (b("noncurrent_leases"), 1)],
                [(d("lease_liabilities"), 1)],
            )
            compare(prefix + "/cash_debt_table", [(b("cash"), 1)], [(d("cash"), 1)])
            compare(
                prefix + "/adjusted_debt",
                [(d("financial_debt"), 1), (d("lease_liabilities"), 1)],
                [(d("adjusted_debt"), 1)],
            )
            compare(
                prefix + "/net_adjusted_debt",
                [(d("adjusted_debt"), 1), (d("cash"), -1)],
                [(d("net_adjusted_debt"), 1)],
            )
        for stop in sorted(frame.loc[frame.statement.eq("fleet"), "period_end_date"].unique()):
            fleet = rows("fleet", "instant", stop)

            def f(key):
                return fleet[(key, "excluding_short_term_ACMI")]

            prefix = f"{edition}/fleet/{stop}"
            compare(
                prefix + "/total",
                [(f(k), 1) for k in ("a320ceo", "a320neo", "a321ceo", "a321neo")],
                [(f("fleet_total"), 1)],
            )
            for keys, metric in [
                (("a321ceo", "a321neo"), "a321_fraction"),
                (("a320neo", "a321neo"), "neo_fraction"),
            ]:
                # Aircraft counts are exact integers, percentages alone are rounded.
                exact = sum(numeric(f(k)) for k in keys) / numeric(f("fleet_total"))
                if abs(exact - numeric(f(metric))) > half_quantum(f(metric)):
                    raise ValueError("Viva fleet composition fraction disagrees")
                checks.append(dict(check=prefix + "/" + metric, exact_counts=True))
    # Audit differences across editions. Never emit H1-Q2 as a new validated Q1 observation.
    diagnostics = []
    selected = native.loc[native.statement.eq("income") & native.unit.eq("USD")]
    for stop in ("2026-03-31", "2025-03-31"):
        year = stop[:4]
        for key in sorted(selected.metric_key.unique()):

            def get(edition, kind, end):
                rows = selected.loc[
                    selected.edition.eq(edition)
                    & selected.period_type.eq(kind)
                    & selected.period_end_date.eq(end)
                    & selected.metric_key.eq(key)
                ]
                if len(rows) != 1:
                    raise ValueError("Viva cross-edition audit grain incomplete")
                return next(rows.itertuples(index=False))

            first, second, half = (
                get("2026Q1", "quarter", stop),
                get("2026Q2", "quarter", year + "-06-30"),
                get("2026Q2", "half_year", year + "-06-30"),
            )
            difference = numeric(half) - numeric(second) - numeric(first)
            bound = sum(half_quantum(r) for r in (half, second, first))
            diagnostics.append(
                dict(
                    metric_key=key,
                    comparison_period=year + "Q1",
                    reported_difference_USD=str(difference),
                    rounding_bound_USD=str(bound),
                    status="reported_difference_requires_review"
                    if abs(difference) > bound
                    else "within_reported_precision",
                    source_observations=[
                        dict(
                            source_file=r.source_file,
                            source_hash=r.source_hash,
                            source_locator=r.source_locator,
                        )
                        for r in (half, second, first)
                    ],
                )
            )
    return dict(
        scope="retained_Viva_2026Q2_reported_dossier_Q1_support_only_no_historical_harmonization",
        report_period="2026Q2",
        quarters_validated=["2026Q2"],
        months_validated=[],
        accounting_and_operating_checks=checks,
        cross_edition_diagnostics=diagnostics,
        historical_harmonization_allowed=False,
        derived_Q1_metrics_emitted=0,
        first_publication_date=None,
        release_lag_days=None,
        printed_report_dates=["2026-04-30", "2026-07-24"],
        booked_passengers_not_transported=True,
        asm_not_ask=True,
        casm_not_cask=True,
        fx_macro_context_excluded_from_gold=True,
        cash_comparability_note="IFRS9 cash in transit classified in receivables; prior periods not adjusted",
        technical_certification_not_publication_approval=True,
    )
