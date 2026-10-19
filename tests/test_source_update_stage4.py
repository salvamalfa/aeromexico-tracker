from src.transform.validate_stage4 import government_hub_complete


def test_new_aicm_month_does_not_break_accepted_hub_coverage_but_missing_month_does():
    assert government_hub_complete({"rows": 7, "first_period": "2026M01", "last_period": "2026M07"})
    assert government_hub_complete({"rows": 8, "first_period": "2026M01", "last_period": "2026M08"})
    assert not government_hub_complete({"rows": 7, "first_period": "2026M01", "last_period": "2026M08"})
    assert not government_hub_complete({"rows": 6, "first_period": "2026M02", "last_period": "2026M07"})
