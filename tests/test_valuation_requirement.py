import unittest
from diagnosis.valuation_requirement import *

def facts(q=8000, n=16):
    return [dict(ticker='X', report_period=quarter_end(k), period_type='Quarter', eps_basis='diluted',
        consolidation_scope='consolidated', unit='TWD/common_share', value=1., estimated=False) for k in range(q, q+n)]

class RequirementTests(unittest.TestCase):
    def test_exact_prior_four(self):
        fs=facts(); fs[4]['value']=999
        self.assertEqual(base_eps(fs,'X',8004)['value'],4)
    def test_no_backfill(self):
        fs=facts(); del fs[3]
        self.assertIsNone(base_eps(fs,'X',8005)['value'])
    def test_timing_not_gate(self):
        self.assertEqual(base_eps(facts(),'X',8004)['value'],4)
    def test_basis(self):
        fs=facts(); fs[1]['eps_basis']='basic'
        self.assertIsNone(base_eps(fs,'X',8004)['value'])
    def test_current(self):
        r=requirement(facts(),'X',quarter_end(8004),60,10)
        self.assertEqual(r['required_growth'],.5)
        self.assertEqual(r['bucket'],'40–60%')
    def test_buckets(self):
        self.assertEqual([growth_bucket(g) for g in (0,.2,.4,.6,1,2)],list(BUCKETS))
    def test_history(self):
        ps=[dict(date=quarter_end(q),close=40 if q<8009 else 80) for q in range(8000,8014)]
        rs=episodes(facts(),'X',ps,quarter_end(8013))
        r=rs[8]; self.assertEqual(r['status'],'ALREADY_MET')
        self.assertTrue(all(d<r['peak_date'] for d in r['reference_quarters']))
        self.assertEqual(rs[-1]['status'],'RIGHT_CENSORED')
    def test_missing_company(self):
        self.assertIsNone(requirement(facts(),'Y','2002-01-01',40,10)['base_eps'])
    def test_insufficient_highlight(self):
        table=summary_table([], '0–20%')
        self.assertEqual(table[1]['EPS Requirement'],'→ 0–20%')
        self.assertEqual(table[1]['≤6M'],'N/A')
    def test_no_future_leak(self):
        ps=[dict(date=quarter_end(q),close=40) for q in range(8000,8014)]
        fs=facts(); a=episodes(fs,'X',ps,quarter_end(8013))[8]
        fs[9]['value']=1000
        b=episodes(fs,'X',ps,quarter_end(8013))[8]
        self.assertEqual(a['required_eps'],b['required_eps'])
    def test_tie_first_close_not_high(self):
        ps=[dict(date=quarter_end(q),close=40) for q in range(8000,8014)]
        ps.append(dict(date='2002-01-02',close=40,high=999))
        r=episodes(facts(),'X',ps,quarter_end(8013))[8]
        self.assertEqual(r['peak_date'],'2002-01-02')
    def test_fulfillment_and_gap(self):
        ps=[dict(date=quarter_end(q),close=40 if q<8008 else 80) for q in range(8000,8014)]
        fs=facts(); fs[9]['value']=10
        r=episodes(fs,'X',ps,quarter_end(8013))[8]
        self.assertEqual(r['completion_date'],quarter_end(8009))
        fs.pop(8)
        r=episodes(fs,'X',ps,quarter_end(8013))[8]
        self.assertEqual(r['status'],'RIGHT_CENSORED')
        self.assertEqual(r['censor_date'],r['peak_date'])
    def test_help_and_view(self):
        from streamlit.testing.v1 import AppTest
        help_app=AppTest.from_string('from diagnosis.valuation_requirement_view import render_help\nrender_help()').run()
        self.assertFalse(help_app.exception)
        app=AppTest.from_string("from pathlib import Path\nfrom diagnosis.valuation_requirement_view import render\nrender(dict(stock_id='2345',price_date='2026-08-28',price=100,normal_pe=20),Path.cwd(),Path.cwd()/'data/quick_analysis.db')").run()
        self.assertFalse(app.exception)
        self.assertTrue(any('DATA GAP' in x.value for x in app.info))

if __name__=='__main__': unittest.main()
