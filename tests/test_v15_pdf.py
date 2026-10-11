import copy
from dataclasses import replace
from io import BytesIO
import unittest
from unittest.mock import patch
import plotly.graph_objects as go
from pypdf import PdfReader
from diagnosis.v15_pdf import page_payload, export_pdf
from diagnosis.reversal import ReversalSnapshot


class PresentationTests(unittest.TestCase):
    def test_private_fields_not_copied(self):
        result=dict(stock_id='TEST',price_date='2026-10-08',price=None,
                    shares=12345,cost='PRIVATE_CANARY',profit='PRIVATE_CANARY')
        original=copy.deepcopy(result)
        report=page_payload(result,{},None)
        text=PdfReader(BytesIO(export_pdf(report))).pages[0].extract_text()
        self.assertEqual(result,original)
        self.assertNotIn('PRIVATE_CANARY',text)
        self.assertIn('N/A',text)

    def test_exact_page_trace_and_content_id(self):
        fig=go.Figure(go.Scatter(x=['2026-10-07','2026-10-08'],y=[38.123456,36.6],name='MA5'))
        source={'stock_id':'2409','price_date':'2026-10-08','price':36.6}
        a=page_payload(source,{'overall':'原判讀'},[fig])
        self.assertEqual(a['figures'][0]['data'][0]['y'],[38.123456,36.6])
        self.assertEqual(a['content_id'],page_payload(source,{'overall':'原判讀'},[fig])['content_id'])
        fig.data[0].y=[38.1,36.6]
        self.assertNotEqual(a['content_id'],page_payload(source,{'overall':'原判讀'},[fig])['content_id'])

    def test_future_chart_rejected(self):
        fig=go.Figure(go.Scatter(x=['2026-10-09'],y=[100]))
        with self.assertRaisesRegex(ValueError,'截止日'):
            page_payload({'price_date':'2026-10-08'}, {}, [fig])

    def test_font_failure_explicit(self):
        from pathlib import Path
        with patch('diagnosis.v15_pdf.FONT_ROOT',Path('missing-font-fixture')):
            with self.assertRaises(FileNotFoundError):
                export_pdf(page_payload({'stock_id':'X'}, {}, None))

    def test_long_warning_and_judgment_preserved(self):
        p=page_payload({'stock_id':'X','price_date':'2026-10-08'}, {}, None)
        p['reversal']['warnings']=['來源警示'*120]
        p['interpretation']['overall']='判讀文字'*120
        reader=PdfReader(BytesIO(export_pdf(p)))
        self.assertGreater(len(reader.pages),1)
        all_text=''.join(page.extract_text() for page in reader.pages)
        self.assertIn('完整內容請見續頁',all_text)
        self.assertIn('資料警示：',all_text)
        self.assertIn('判讀文字',all_text)

if __name__=='__main__':unittest.main()
