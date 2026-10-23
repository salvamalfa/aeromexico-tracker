"""Reviewed Viva report semantics. Units and repeated labels are scoped to ordered tables."""

GRAIN = [
    "edition",
    "statement",
    "period_type",
    "period_start_date",
    "period_end_date",
    "metric_key",
    "segment",
]
TABLE = "fact_viva_retained_financial_source_metrics"
NATIVE = "viva_financial_native"
VERSION = "viva_2026q2_reported_financial_dossier_v1"
# (literal label, metric, source unit, multiplier to explicit base unit, segment)


def money(label, key):
    return (label, key, "USD", 1000, "consolidated")


INDICATORS = [
    money("Total operating revenue", "total_revenue"),
    money("EBITDAR", "ebitdar_non_ifrs"),
    ("EBITDAR margin", "ebitdar_margin", "fraction", 0.01, "consolidated"),
    money("EBITDA", "ebitda_non_ifrs"),
    ("EBITDA margin", "ebitda_margin", "fraction", 0.01, "consolidated"),
]
for label, key, unit, scale in [
    ("ASMs (millions)", "asm", "seat_miles", 1000000),
    ("RPMs (millions)", "rpm", "revenue_passenger_miles", 1000000),
    ("Load Factor (scheduled, RPM/ASM)", "scheduled_load_factor", "fraction", 0.01),
    ("Booked Passengers (thousands)", "booked_passengers", "booked_passengers", 1000),
]:
    INDICATORS.extend(
        [
            (label, key, unit, scale, "total"),
            ("Domestic", key, unit, scale, "domestic"),
            ("International", key, unit, scale, "international"),
        ]
    )
for label, key in [
    ("TRASM", "trasm"),
    ("CASM", "casm"),
    ("CASM ex-fuel", "casm_ex_fuel"),
    ("CASM fuel", "casm_fuel"),
]:
    INDICATORS.append((label + " (US cents)", key, "USD_cents_per_seat_mile", 1, "total"))
for label, key in [
    ("Fare per Passenger", "fare_per_booked_passenger"),
    ("Ancillary per Passenger", "ancillary_per_booked_passenger"),
    ("Total Revenue per Passenger", "revenue_per_booked_passenger"),
    ("Total Revenue per Seat", "revenue_per_seat"),
    ("Total Cost per Seat", "cost_per_seat"),
    ("Total Cost ex-fuel per Seat", "cost_ex_fuel_per_seat"),
]:
    INDICATORS.append(
        (
            label + " (US$)",
            key,
            "USD_per_booked_passenger" if "Passenger" in label else "USD_per_seat",
            1,
            "total",
        )
    )
INDICATORS += [
    ("Seats (thousands)", "seats", "seats", 1000, "total"),
    ("Average Stage Length (miles)", "average_stage_length", "miles", 1, "total"),
    ("Sectors", "sectors", "sectors", 1, "total"),
    ("Block Hours", "block_hours", "hours", 1, "total"),
    (
        "Average Operating Aircraft Utilization (Block Hours)",
        "operating_aircraft_utilization",
        "block_hours_per_aircraft_day",
        1,
        "operating_fleet",
    ),
    (
        "Average Total Aircraft Utilization (Block Hours)",
        "total_aircraft_utilization",
        "block_hours_per_aircraft_day",
        1,
        "total_fleet",
    ),
    ("Fuel gallons consumed (millions)", "fuel_gallons", "gallons", 1000000, "total"),
    ("Average jet fuel1 (US$/gal)", "context_jet_fuel", "USD_per_gallon", 1, "context_not_gold"),
    (
        "Average exchange rate2 (US$/MX$)",
        "context_average_fx_ambiguous_label",
        "US$/MX$_as_printed",
        1,
        "context_not_gold",
    ),
    (
        "EoP exchange rate2 (US$/MX$)",
        "context_eop_fx_ambiguous_label",
        "US$/MX$_as_printed",
        1,
        "context_not_gold",
    ),
]
INCOME = [
    money(label, key)
    for label, key in [
        ("Passenger revenue", "passenger_revenue"),
        ("Ancillary revenue", "ancillary_revenue"),
        ("Total operating revenue", "total_revenue"),
        ("Other income", "other_income_expense_offset"),
        ("Fuel", "fuel"),
        ("Depreciation and amortization", "depreciation_amortization"),
        ("Landing, takeoff and navigation expenses", "landing_navigation"),
        ("Wages, salaries, and other benefits", "wages"),
        ("Operational support expenses", "operational_support"),
        ("Marketing and distribution expenses", "marketing_distribution"),
        ("Maintenance", "maintenance"),
        ("Leases", "leases"),
        ("Other expenses", "other_expenses"),
        ("Total operating expenses", "total_operating_expenses"),
        ("Operating profit (loss)", "operating_income"),
        ("EBIT Margin", "operating_margin"),
        ("Financial Income", "financial_income"),
        ("Financial costs", "financial_costs"),
        ("Total finance costs, net", "net_finance_costs"),
        ("Income (loss) before income tax", "income_before_tax"),
        ("EBT Margin", "ebt_margin"),
        ("Income tax", "income_tax"),
        ("Net income (loss)", "net_income"),
        ("Net income (loss) margin", "net_margin"),
    ]
]
INCOME = [
    (
        label,
        key,
        "fraction" if key.endswith("margin") else unit,
        0.01 if key.endswith("margin") else scale,
        segment,
    )
    for label, key, unit, scale, segment in INCOME
]
BALANCE = [
    money(label, key)
    for label, key in [
        ("Cash and cash equivalents", "cash"),
        ("Derivative financial instruments", "current_asset_derivatives"),
        ("Accounts receivables and other", "receivables"),
        ("Related parties", "current_asset_related_parties"),
        ("Inventories", "inventory"),
        ("Guarantee deposits and prepaid expenses", "current_deposits_prepaid"),
        ("Total current assets", "current_assets"),
        ("Restricted cash", "restricted_cash"),
        ("Related parties", "noncurrent_asset_related_parties"),
        ("Long-term advance payments for maintenance", "maintenance_advances"),
        ("Operating equipment, furniture and equipment", "property_equipment"),
        ("Right of use assets", "right_of_use_assets"),
        ("Intangible assets", "intangibles"),
        ("Guarantee deposits and prepaid expenses", "noncurrent_deposits_prepaid"),
        ("Deferred income taxes", "deferred_tax_assets"),
        ("Derivative financial instruments", "noncurrent_asset_derivatives"),
        ("Total assets", "assets"),
        ("Loans", "current_loans"),
        ("Derivative financial instruments", "current_liability_derivatives"),
        ("Lease liabilities", "current_leases"),
        ("Trade accounts payable", "trade_payables"),
        ("Accrued liabilities", "accrued_liabilities"),
        ("Provisions", "current_provisions"),
        ("Employee statutory profit sharing", "employee_profit_sharing"),
        ("Related parties", "current_liability_related_parties"),
        ("Air traffic liability", "air_traffic_liability"),
        ("Advances for services", "service_advances"),
        ("Total current liabilities", "current_liabilities"),
        ("Loans", "noncurrent_loans"),
        ("Lease liabilities", "noncurrent_leases"),
        ("Derivative financial instruments", "noncurrent_liability_derivatives"),
        ("Provisions", "noncurrent_provisions"),
        ("Employee benefits", "employee_benefits"),
        ("Total liabilities", "liabilities"),
        ("Capital stock", "capital_stock"),
        ("Legal reserve", "legal_reserve"),
        ("Compound instrument", "compound_instrument"),
        ("Share subscription reserve", "subscription_reserve"),
        ("Additional paid in capital", "paid_in_capital"),
        ("Other equity accounts", "other_equity"),
        ("Retained earnings", "retained_earnings"),
        ("Accumulated comprehensive income", "accumulated_comprehensive_income"),
        ("Total stockholders’ equity", "equity"),
        ("Total liabilities and stockholders’ equity", "liabilities_equity"),
    ]
]
CASH = [
    money(label, key)
    for label, key in [
        ("Net cash flow from operating activities", "cash_operating"),
        ("Net cash flow from (used in) investing activities", "cash_investing"),
        ("Net cash flow from (used in) financing activities", "cash_financing"),
        ("Increase (decrease) in cash and equivalents", "cash_change"),
        ("Cash and cash equivalents at beginning of period", "cash_begin"),
        ("Cash and cash equivalents at end of period", "cash_end"),
    ]
]
DEBT = [
    (label, key, unit, scale, "consolidated")
    for label, key, unit, scale in [
        ("Total Debt", "financial_debt", "USD", 1000000),
        ("Lease liabilities", "lease_liabilities", "USD", 1000000),
        ("Total Adj. Debt", "adjusted_debt", "USD", 1000000),
        ("Cash & cash equivalents1", "cash", "USD", 1000000),
        ("Net Adj. Debt2", "net_adjusted_debt", "USD", 1000000),
        ("Net Adj. Debt / LTM EBITDAR", "net_debt_to_ltm_ebitdar", "times_ltm", 1),
        ("Cash / LTM Total Operating Revenue", "cash_to_ltm_revenue", "fraction", 0.01),
    ]
]
FLEET = [
    (label, key, unit, scale, "excluding_short_term_ACMI")
    for label, key, unit, scale in [
        ("Airbus 320ceo", "a320ceo", "aircraft", 1),
        ("Airbus 320neo", "a320neo", "aircraft", 1),
        ("Airbus 321ceo", "a321ceo", "aircraft", 1),
        ("Airbus 321neo", "a321neo", "aircraft", 1),
        ("EoP Total Fleet", "fleet_total", "aircraft", 1),
        ("A321 %", "a321_fraction", "fraction", 0.01),
        ("Neo %", "neo_fraction", "fraction", 0.01),
    ]
]
