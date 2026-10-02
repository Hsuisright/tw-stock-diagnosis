import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from diagnosis.positioning import SEED_SCHEMA_VERSION, load_seed, normalize_finmind_positioning
from diagnosis.positioning_rules import calculate


def rows(margin=100.0, short=100.0, latest_margin=None, latest_short=None):
    result = []
    for day in range(21):
        result.append({"ticker": "X", "date": f"2026-01-{day + 1:02d}",
                       "margin_balance": margin, "short_balance": short})
    result[-1]["margin_balance"] = margin if latest_margin is None else latest_margin
    result[-1]["short_balance"] = short if latest_short is None else latest_short
    return result


class PositioningTests(unittest.TestCase):
    def test_change_windows_and_percentages(self):
        item = calculate(rows(latest_margin=80, latest_short=120), .03, 1.3)
        self.assertEqual(item.margin_change_5d, -20)
        self.assertEqual(item.margin_change_20d, -20)
        self.assertAlmostEqual(item.margin_change_5d_pct, -.2)
        self.assertEqual(item.short_change_1d, 20)

    def test_percentage_denominator_zero_is_safe(self):
        data = rows(margin=0, short=100, latest_margin=0)
        item = calculate(data, .01, 1.0)
        self.assertIsNone(item.margin_change_5d_pct)

    def test_missing_margin_short_or_short_history_is_insufficient(self):
        data = rows()
        data[-1]["margin_balance"] = None
        self.assertEqual(calculate(data, .03, 1.3).state, "INSUFFICIENT_DATA")
        self.assertEqual(calculate(rows()[:5], .03, 1.3).state, "INSUFFICIENT_DATA")

    def test_old_missing_observation_does_not_block_current_5d_state(self):
        data = rows(latest_short=90)
        data[0]["short_balance"] = None
        self.assertEqual(calculate(data, .04, 1.3).state, "SHORT_COVERING_COMPATIBLE")

    def test_short_covering_rule(self):
        item = calculate(rows(latest_short=90), .04, 1.3)
        self.assertEqual(item.state, "SHORT_COVERING_COMPATIBLE")
        self.assertTrue(any("融券" in line for line in item.evidence))
        self.assertTrue(any("相符" in line for line in item.evidence))

    def test_long_deleveraging_rule(self):
        item = calculate(rows(latest_margin=90), -.04, 1.3)
        self.assertEqual(item.state, "LONG_DELEVERAGING_COMPATIBLE")

    def test_two_sided_crowding_rule(self):
        item = calculate(rows(latest_margin=110, latest_short=110), .04, 1.0)
        self.assertEqual(item.state, "TWO_SIDED_CROWDING")

    def test_short_pressure_building_rule(self):
        self.assertEqual(calculate(rows(latest_short=110), -.04, 1.3).state,
                         "SHORT_PRESSURE_BUILDING")

    def test_long_crowding_building_rule(self):
        self.assertEqual(calculate(rows(latest_margin=110), .04, 1.0).state,
                         "LONG_CROWDING_BUILDING")

    def test_pressure_releasing_rule(self):
        self.assertEqual(calculate(rows(latest_margin=90, latest_short=90), .0, 1.0).state,
                         "PRESSURE_RELEASING")

    def test_price_20d_is_retained(self):
        item = calculate(rows(), .01, 1.0, price_return_20d=.12)
        self.assertAlmostEqual(item.price_return_20d, .12)

    def test_neutral_and_deterministic(self):
        first = calculate(rows(), .01, 1.0)
        second = calculate(rows(), .01, 1.0)
        self.assertEqual(first.state, "NEUTRAL")
        self.assertEqual(first, second)

    def test_no_forward_fill_in_normalization(self):
        normalized = normalize_finmind_positioning([
            {"stock_id":"X", "date":"2026-01-01", "MarginPurchaseTodayBalance":100, "ShortSaleTodayBalance":10},
            {"stock_id":"X", "date":"2026-01-02", "MarginPurchaseTodayBalance":None, "ShortSaleTodayBalance":11},
        ], "X")
        self.assertIsNone(normalized[-1]["margin_balance"])

    def test_seed_loader_rejects_wrong_schema_and_preserves_valid_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "positioning.json"
            path.write_text(json.dumps({"schema_version": SEED_SCHEMA_VERSION, "dataset":"TaiwanStockMarginPurchaseShortSale",
                "tickers":{"X":[{"stock_id":"X","date":"2026-01-01","MarginPurchaseTodayBalance":100,"ShortSaleTodayBalance":10}]}}), encoding="utf-8")
            loaded, meta = load_seed(path, "X")
            self.assertEqual(loaded[0]["margin_balance"], 100)
            self.assertEqual(meta["dataset"], "TaiwanStockMarginPurchaseShortSale")
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(load_seed(path, "X"), ([], None))


if __name__ == "__main__":
    unittest.main()
