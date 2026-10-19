from src.source_updates.catalog import plan, product_map


def test_combined_is_union_of_monthly_and_quarterly_work_with_unique_plan_item_ids():
    as_of = "2026-11-17T12:00:00-06:00"
    monthly = plan("monthly", as_of)["products"]
    quarterly = plan("quarterly", as_of, "2026Q3")["products"]
    combined = plan("combined", as_of, "2026Q3")
    pairs = lambda rows: {(row["id"], row["target_period"]) for row in rows}
    assert pairs(combined["products"]) == pairs(monthly) | pairs(quarterly)
    assert len({row["plan_item_id"] for row in combined["products"]}) == len(combined["products"])
    for key, product in product_map().items():
        if product["cadence"] == "both":
            assert {row["target_period"] for row in combined["products"] if row["id"] == key} == {
                "2026M10",
                "2026Q3",
            }
    assert {row["target_period"] for row in combined["products"] if row["id"] == "rss"} == {"2026M10"}
    assert {row["target_period"] for row in combined["products"] if row["id"] == "bmv_xbrl"} == {"2026Q3"}
    assert combined["writes"] == [] and combined["network_requests"] == 0
