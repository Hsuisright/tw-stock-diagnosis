import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from diagnosis.eps_growth_history import historical_growth
from diagnosis.valuation_requirement import quarter_end
from diagnosis.quick_analysis import analyze_stock

def sample():
    return [dict(ticker='X',report_period=quarter_end(q),period_type='Quarter',eps_basis='diluted',
        consolidation_scope='consolidated',unit='TWD/common_share',value=2**((q-8000)/4),estimated=False)
        for q in range(8000,8020)]

class V15Tests(unittest.TestCase):
    def test_growth(self):
        sums, obs=historical_growth(sample(),'X',quarter_end(8019))
        self.assertEqual([x['n'] for x in sums],[13,9,5])
        for s in sums: self.assertAlmostEqual(s['median'],1.)
        self.assertTrue(all(x['start_facts'] and x['end_facts'] for x in obs))
    def test_gap_and_cutoff(self):
        fs=sample();del fs[8]
        _,obs=historical_growth(fs,'X',quarter_end(8015))
        self.assertTrue(all(x['end']<=quarter_end(8015) for x in obs))
        self.assertFalse(any(x['start']<=quarter_end(8008)<=x['end'] for x in obs))
    def test_zero_and_negative_start(self):
        fs=sample()
        for f in fs: f['value']=0
        self.assertFalse(historical_growth(fs,'X',quarter_end(8019))[1])
        for f in fs: f['value']=-1
        self.assertFalse(historical_growth(fs,'X',quarter_end(8019))[1])
    def test_cloud_entrypoint_renders_v15(self):
        a=AppTest.from_file(str(Path.cwd()/'quick_app.py'),default_timeout=30)
        a.secrets['APP_PASSWORD']='test-only';a.session_state['password_authenticated']=True
        a.session_state['analysis']=analyze_stock('data/quick_analysis.db','2330');a.run()
        self.assertFalse(a.exception)
        self.assertTrue(any('Product Version: V1.5' in c.value for c in a.caption))
    def test_full_2330(self):
        r=analyze_stock('data/quick_analysis.db','2330')
        a=AppTest.from_file(str(Path.cwd()/'quick_app_v15.py'),default_timeout=30)
        a.secrets['APP_PASSWORD']='test-only';a.session_state['password_authenticated']=True
        a.session_state['analysis']=r;a.run()
        self.assertFalse(a.exception)
        self.assertTrue(any('Product Version: V1.5' in c.value for c in a.caption))
        self.assertEqual(a.session_state['analysis']['reversal'].score,r['reversal'].score)
        self.assertTrue(any(m.label == '近四季實際 EPS（TTM）' for m in a.metric))
        self.assertFalse(any(m.label == '隱含TTM EPS' for m in a.metric))
        self.assertTrue(any(e.label=='查看歷史市場領先時間' for e in a.expander))
        a.query_params['view']='valuation_help';a.run()
        self.assertFalse(a.exception)
        self.assertEqual(len(a.selectbox[0].options),10)
    def test_other_companies(self):
        for ticker in ('2454','2345','2412'):
            a=AppTest.from_string("from pathlib import Path\nfrom diagnosis.valuation_v15_view import render\nrender(dict(stock_id='"+ticker+"',price_date='2026-08-28',price=100,normal_pe=20),Path.cwd(),Path.cwd()/'data/quick_analysis.db')")
            a.run();self.assertFalse(a.exception)
            self.assertTrue(any('市場要求與歷史觀察對照' in x.value for x in a.info))

if __name__=='__main__': unittest.main()
