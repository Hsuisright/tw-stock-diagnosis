import unittest
from datetime import date, timedelta

from diagnosis.reversal import reversal_history, explain_change
from diagnosis.interpretation import build_opportunity_risk


def bars(values, volume=1000):
    return [dict(date=(date(2025, 1, 1)+timedelta(days=i)).isoformat(),
                 close=v, open=v, high=v+1, low=v-1, volume=volume)
            for i, v in enumerate(values)]


class ReversalTests(unittest.TestCase):
    def test_flat_is_not_oversold(self):
        data = bars([100]*100)
        last = reversal_history(data, data)[-1]
        self.assertEqual(last.rsi14, 50)
        self.assertEqual(last.stage, '盤整觀察')
        self.assertIsNone(last.confirmation_price)

    def test_missing_is_not_bearish_or_zero(self):
        data = bars([100+i*.1 for i in range(100)], None)
        last = reversal_history(data)[-1]
        self.assertIsNone(last.score)
        self.assertIsNone(last.volume_score)
        self.assertIsNone(last.relative_score)
        self.assertIsNone(last.obv_above_ma10)
        self.assertEqual(last.stage, '資料待補')
        self.assertNotIn('OBV尚未站上10日均線', last.pending)

    def test_stale_benchmark_not_aligned(self):
        data = bars([100+i*.1 for i in range(100)])
        last = reversal_history(data, data[:-1])[-1]
        self.assertIsNone(last.score)
        self.assertIsNone(last.relative_20d)

    def test_split_like_jump_suspends(self):
        data = bars([100]*80+[50]*20)
        last = reversal_history(data, bars([100]*100))[-1]
        self.assertEqual(last.stage, '價格待核對')
        self.assertIsNone(last.score)
        self.assertIsNone(last.failure_price)

    def test_asof_and_window_invariance(self):
        data = bars([130-i*.5 for i in range(65)]+[98+i*.3 for i in range(40)])
        benchmark = bars([100]*len(data))
        full = reversal_history(data, benchmark)
        self.assertEqual(full[-5:], reversal_history(data, benchmark, 5))
        for end in (75, 85, 95):
            self.assertEqual(full[end-65], reversal_history(data[:end], benchmark)[-1])
        for row in full:
            self.assertEqual(row.score, sum((row.trend_score,row.momentum_score,row.volume_score,
                                            row.relative_score,row.structure_score,row.pattern_score)))
            self.assertTrue(0 <= row.score <= 100)
            self.assertTrue(all(p[3] <= row.date for p in row.pivots))
        changes, _ = explain_change(full)
        self.assertEqual(sum(x['變化'] for x in changes), full[-1].score-full[-6].score)

    def test_w_structure_fixed_levels_and_no_resurrection(self):
        values = [130-i*.5 for i in range(60)]
        values += [99,98,97,96,95,97,99,101,103,105,103,101,99,98,97,98,99,101]
        values += [103,106,108,110,104,96,98,100,102,104]
        data = bars(values)
        for row in data[79:]: row['volume'] = 5000
        history = reversal_history(data, bars([100]*len(data)))
        setups = [x for x in history if x.setup_id]
        self.assertTrue(setups)
        first = setups[0]
        self.assertEqual(first.confirmation_price, 105)
        self.assertEqual(first.failure_price, 97)
        same = [x for x in setups if x.setup_id == first.setup_id]
        self.assertTrue(any(x.confirmed for x in same))
        self.assertTrue(any(x.stage == '回測中' for x in same))
        self.assertEqual(same[-1].stage, '反折失敗')
        self.assertTrue(all(x.confirmation_price == 105 and x.failure_price == 97 for x in same))
        failed = same[-1]
        self.assertTrue(all(x.setup_id != failed.setup_id for x in history if x.date > failed.date))

    def test_missing_pe_is_not_upside(self):
        result = build_opportunity_risk({'valuation_available': False})
        self.assertEqual(result['elasticity'], '待驗證')
        self.assertEqual(result['valuation_risk'], '無法評估')
        self.assertEqual(result['category'], '估值待補資料')


if __name__ == '__main__':
    unittest.main()
