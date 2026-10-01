import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from diagnosis.eps_history_store import normalize_finmind_eps, comparable_rows, _connect
from diagnosis.eps_historical_capability import base_eps, required_growths, ttm_series, summaries


def row(year, quarter, eps=1.0, basis='basic'):
    month = quarter * 3
    day = 31 if month in (3, 12) else 30
    return dict(ticker='X', fiscal_year=year, quarter=quarter, period_end=f'{year}-{month:02}-{day:02}',
                eps=eps, eps_basis=basis, consolidated='scope', source='test', qualification='test',
                original_field='EPS', source_reference='test://', source_fact_id=f'{year}{quarter}',
                fetched_at='2026-09-30T00:00:00Z', version='test')


class CapabilityTests(unittest.TestCase):
    def test_exactly_four_and_no_older_fallback(self):
        rows = [row(2020 + i//4, i%4+1, 1) for i in range(8)]
        self.assertEqual([x['ttm_eps'] for x in ttm_series(rows)], [4, 4, 4, 4, 4])
        rows.pop(4)
        self.assertEqual(len(ttm_series(rows)), 1)
        self.assertEqual(base_eps(rows, '2022-01-01')['reason'], 'missing_quarter')

    def test_no_basis_mix_or_half_year_substitution(self):
        rows = [row(2020 + i//4, i%4+1, 1, 'basic' if i != 3 else 'diluted') for i in range(8)]
        self.assertEqual([x['period_end'] for x in ttm_series(rows)], ['2021-12-31'])
        api = [dict(stock_id='X', type='EPS', date='2020-06-29', value=1, origin_name='EPS')]
        with self.assertRaises(ValueError): normalize_finmind_eps(api, 'X', 'now', 'v')

    def test_growth_formulae_and_lineage(self):
        rows = [row(2020 + i//4, i%4+1, 1 if i < 4 else 2 if i < 8 else 4 if i < 12 else 8) for i in range(16)]
        stats, obs = summaries(rows)
        self.assertAlmostEqual(next(x for x in obs if x['years']==1)['growth'], 1)
        self.assertAlmostEqual(next(x for x in obs if x['years']==2)['growth'], 1)
        self.assertAlmostEqual(next(x for x in obs if x['years']==3)['growth'], 1)
        self.assertTrue(next(x for x in obs if x['years']==1)['source_lineage'])
        self.assertEqual([x['n'] for x in stats], [9, 5, 1])

    def test_nonpositive_safe(self):
        rows = [row(2020 + i//4, i%4+1, -1 if i < 4 else 1) for i in range(8)]
        _, obs = summaries(rows)
        self.assertTrue(any(x['reason']=='nonpositive_start_or_end_ttm' and x['growth'] is None for x in obs))

    def test_store_preserves_source_metadata(self):
        payload = [dict(stock_id='X',type='EPS',date='2020-03-31',value=1,origin_name='基本每股盈餘', price=999, PER=.01)]
        normalized=normalize_finmind_eps(payload,'X','now','hash')
        self.assertEqual(normalized[0]['eps_basis'],'basic')
        self.assertEqual(normalized[0]['eps'],1)
        self.assertEqual(normalized[0]['source_fact_id'],'X:EPS:2020-03-31:hash')

    def test_known_share_event_excludes_earlier_periods_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'eps.sqlite3'
            with closing(_connect(path)) as con:
                with con:
                    for item in [row(2020 + i//4, i%4+1) for i in range(8)]:
                        con.execute("""INSERT INTO eps_quarters VALUES
                            (:ticker,:fiscal_year,:quarter,:period_end,:eps,:eps_basis,:consolidated,:source,:qualification,
                             :original_field,:source_reference,:source_fact_id,:fetched_at,:version)""",item)
                    con.execute("INSERT INTO eps_basis_events VALUES (?,?,?,?,?,?)",
                        ('X','2020-08-01','stock_distribution','test','test://','now'))
            records, events=comparable_rows(path,'X')
            self.assertEqual(len(events),1)
            self.assertEqual(records[0]['period_end'],'2020-12-31')

    def test_required_growths_uses_only_actual_ttm_input(self):
        # 2454 example: this function has no Price/PE parameter, so an implied
        # EPS cannot enter the V1.5 denominator through this calculation path.
        growth = required_growths(4920 / 19.64, 60.69)
        self.assertAlmostEqual(growth['one_year'], (4920 / 19.64) / 60.69 - 1)
        self.assertAlmostEqual(growth['two_year'], ((4920 / 19.64) / 60.69) ** .5 - 1)
        self.assertAlmostEqual(growth['three_year'], ((4920 / 19.64) / 60.69) ** (1 / 3) - 1)
        self.assertIsNone(growth['reason'])

    def test_missing_actual_ttm_cannot_fallback_to_implied_eps(self):
        growth = required_growths(250.51, None)
        self.assertIsNone(growth['one_year'])
        self.assertIsNone(growth['two_year'])
        self.assertIsNone(growth['three_year'])
        self.assertEqual(growth['reason'], 'actual_ttm_eps_missing_or_nonpositive')


if __name__ == '__main__':
    unittest.main()
