"""Reconcile reported tables at their printed precision, without solving missing cells."""

from __future__ import annotations

from decimal import Decimal

from src.source_updates.carrier_source_contract import amount


def reconcile(frame):
    by = {
        (int(r.source_table), r.source_row_number, r.source_column): r for r in frame.itertuples(index=False)
    }
    passed, incomplete = [], []

    def val(table, row, col):
        return amount(by[table, row, col].source_value)

    def interval(table, row, col):
        r = by[table, row, col]
        v = amount(r.source_value)
        if v is None:
            return None
        token = r.source_value.strip("()%x").replace(",", "")
        places = len(token.split(".")[1]) if "." in token else 0
        half = Decimal(0) if r.unit in {"aircraft", "departures", "shares"} else Decimal(10) ** -places / 2
        return v - half, v + half

    def equation(table, col, total, parts):
        label = f"table={table},column={col},total_row={total}"
        target = interval(table, total, col)
        ranges = [interval(table, r, col) for r, _ in parts]
        if target is None or any(v is None for v in ranges):
            incomplete.append(label + ":unresolved_source_dash_not_zero")
            return
        low = high = Decimal(0)
        for (a, b), (_, sign) in zip(ranges, parts, strict=True):
            low += a if sign > 0 else -b
            high += b if sign > 0 else -a
        if target[1] < low or target[0] > high:
            raise ValueError(f"Volaris source statement identity failed: {label}")
        passed.append(label)

    def equal(a, b, label):
        left, right = interval(*a), interval(*b)
        if left is None or right is None or left[1] < right[0] or left[0] > right[1]:
            raise ValueError("Volaris required repeated metric mismatch/missing: " + label)
        passed.append(label)

    def ratio(num, den, result, multiplier, label):
        n, d, result = interval(*num), interval(*den), interval(*result)
        if n is None or d is None or result is None or d[0] <= 0:
            raise ValueError("Volaris required ratio inputs missing/nonpositive: " + label)
        possibilities = [x / y * Decimal(str(multiplier)) for x in n for y in d]
        if result[1] < min(possibilities) or result[0] > max(possibilities):
            raise ValueError("Volaris reported ratio and printed precision disagree: " + label)
        passed.append(label)

    for col in [1, 2]:
        for table in [303, 306]:
            for total, parts in [
                (2, [(3, 1), (4, 1)]),
                (6, [(7, 1), (8, 1)]),
                (10, [(2, 1), (6, 1)]),
                (22, [(r, 1) for r in range(12, 22)]),
                (24, [(10, 1), (22, -1)]),
                (29, [(26, 1), (27, 1), (28, 1)]),
                (31, [(24, 1), (29, 1)]),
                (33, [(31, 1), (32, 1)]),
            ]:
                equation(table, col, total, parts)
        for op, income, ancillary in [(297, 303, 309), (300, 306, 310)]:
            for a, b in [(1, 10), (2, 22), (3, 24), (6, 14), (7, 33)]:
                equal((op, a, col), (income, b, col), f"{op}/{income} repeated row {a}, col {col}")
            for total, parts in [
                (26, [(27, 1), (28, 1)]),
                (29, [(30, 1), (31, 1)]),
                (35, [(36, 1), (37, 1)]),
            ]:
                equation(op, col, total, parts)
            # LF is scheduled only; ASM/RPM above include charter. No invented LF identity.
            for metric, numerator, denominator, factor in [
                (19, 1, 26, 100),
                (23, 2, 26, 100),
                (22, 1, 35, 1000),
                (4, 3, 1, 100),
                (8, 7, 1, 100),
            ]:
                ratio(
                    (op, numerator, col),
                    (op, denominator, col),
                    (op, metric, col),
                    factor,
                    f"table {op}, row {metric}, column {col}",
                )
            for eps, shares, ads in [(10, 16, 13), (11, 17, 14)]:
                ratio(
                    (op, 7, col),
                    (op, shares, col),
                    (op, eps, col),
                    1000000,
                    f"IAS33 EPS table {op}, row {eps}, column {col}",
                )
                ratio(
                    (op, 7, col),
                    (op, shares, col),
                    (op, ads, col),
                    10000000,
                    f"ADS=10CPO table {op}, row {ads}, column {col}",
                )
            for a, b, table in [(2, 4, income), (3, 6, income), (6, 35, op), (8, 21, op)]:
                equal((ancillary, a, col), (table, b, col), f"ancillary {ancillary}/{a}, col {col}")
            equation(ancillary, col, 4, [(2, 1), (3, 1)])
            ratio(
                (ancillary, 4, col),
                (ancillary, 6, col),
                (ancillary, 8, col),
                1000,
                f"ancillary per booked passenger {ancillary}, col {col}",
            )
        for total, parts in [
            (4, [(2, 1), (3, 1)]),
            (9, [(r, 1) for r in [2, 3, 5, 6, 7, 8]]),
            (16, [(r, 1) for r in range(10, 16)]),
            (17, [(9, 1), (16, 1)]),
            (27, [(r, 1) for r in range(19, 27)]),
            (34, [(r, 1) for r in range(28, 34)]),
            (35, [(27, 1), (34, 1)]),
            (44, [(r, 1) for r in range(37, 44)]),
            (45, [(35, 1), (44, 1)]),
        ]:
            equation(313, col, total, parts)
        equal((313, 17, col), (313, 45, col), f"assets=liabilities+equity col {col}")
        for table in [316, 317]:
            equation(table, col, 5, [(2, 1), (3, 1), (4, 1)])
            equation(table, col, 8, [(7, 1), (5, 1), (6, 1)])
        equal((316, 8, col), (317, 8, col), f"Q2/H1 cash same June closing, col {col}")
        for r, definition in [
            (2, 1),
            (3, 19),
            (4, 26),
            (5, 32),
            (6, 35),
            (7, 40),
            (8, 2),
            (9, 23),
            (10, 24),
            (11, 3),
            (12, 4),
            (13, 7),
            (14, 8),
        ]:
            equal((276, r, col), (297, definition, col), f"highlight {r}/operating {definition}, col {col}")
        # EBITDAR is reported non-IFRS; compare the provided components, not a new thesis metric.
        values = [interval(297, r, col) for r in [3, 5, 6]]
        ebitdar = interval(276, 15, col)
        if (
            ebitdar is None
            or any(v is None for v in values)
            or (ebitdar[1] < sum(v[0] for v in values) or ebitdar[0] > sum(v[1] for v in values))
        ):
            raise ValueError("Volaris reported EBITDAR reconciliation failed")
        passed.append(f"reported EBITDAR components, col {col}")
        ratio((276, 15, col), (276, 2, col), (276, 16, col), 100, f"EBITDAR margin col {col}")
        equal((289, 9, col), (297, 40, col), f"fleet total/operating col {col}")
    for col in [1, 2, 4]:
        equation(289, col, 9, [(r, 1) for r in [3, 4, 5, 7, 8]])
    equal((313, 2, 1), (316, 8, 1), "current balance/cash-flow closing")
    equal((313, 2, 2), (317, 7, 1), "2025 closing/current H1 beginning")
    for table, row in [(297, r) for r in [19, 23, 24, 26, 29, 32, 35]] + [
        (303, 10),
        (303, 22),
        (303, 24),
        (303, 33),
        (313, 2),
        (313, 17),
        (313, 24),
        (313, 28),
        (313, 25),
        (313, 32),
        (313, 35),
        (313, 44),
        (289, 9),
        (276, 15),
    ]:
        if val(table, row, 1) is None:
            raise ValueError("Volaris required current metric is unavailable")
    return dict(
        reconciliations_passed=len(passed),
        reconciliation_details=passed,
        unresolved_source_identity_checks=incomplete,
        unresolved_dash_observations=int(frame.source_value.eq("-").sum()),
        no_dash_imputed_as_zero=True,
        issuer_fx_context_not_projected=True,
        source_precision_basis="overlap_of_reported_decimal_rounding_intervals",
    )
