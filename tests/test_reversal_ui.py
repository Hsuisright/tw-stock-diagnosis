import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
from diagnosis.reversal import reversal_history
from test_reversal_v2 import bars


class ReversalUITests(unittest.TestCase):
    def test_optional_profile_controls_do_not_change_trs(self):
        data = bars([100+i*.1 for i in range(140)])
        history = reversal_history(data, bars([100]*140))
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'quick_app.py'))
        app.secrets['APP_PASSWORD'] = 'test-only'
        app.session_state['password_authenticated'] = True
        app.session_state['analysis'] = dict(stock_id='TEST',price_date=data[-1]['date'],price=data[-1]['close'],
            bars=data,reversal=history[-1],reversal_history=history,valuation_available=False,bollinger=None,technical=None)
        app.run(timeout=30)
        self.assertFalse(app.checkbox(key='layer_profile').value)
        original = next(x.value for x in app.metric if x.label == 'TRS反折分數')
        app.checkbox(key='layer_profile').check().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(x.label == '最大量價帶（估算POC）' for x in app.metric))
        app.selectbox(key='profile_sessions').select(120)
        app.radio(key='profile_display').set_value('完整橫向成交分布').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('120日成交區' in x.value for x in app.caption))
        self.assertEqual(original, next(x.value for x in app.metric if x.label == 'TRS反折分數'))
        app.checkbox(key='layer_ma').uncheck()
        app.checkbox(key='layer_levels').uncheck()
        app.checkbox(key='layer_pivots').check().run()
        self.assertFalse(app.exception)
        app.checkbox(key='layer_profile').uncheck().run()
        self.assertFalse(app.exception)
        self.assertFalse(any(x.label == '最大量價帶（估算POC）' for x in app.metric))

    def test_complete_missing_and_short_history(self):
        for count, missing in ((100, False), (100, True), (20, True)):
            with self.subTest(count=count, missing=missing):
                data = bars([100+i*.1 for i in range(count)], None if missing else 1000)
                if missing:
                    data = [dict(date=x['date'], close=x['close'], volume=None) for x in data]
                history = reversal_history(data, [] if missing else bars([100]*count))
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'quick_app.py'))
                app.secrets['APP_PASSWORD'] = 'test-only'
                app.session_state['password_authenticated'] = True
                app.session_state['analysis'] = dict(stock_id='TEST', price_date=data[-1]['date'],
                    price=data[-1]['close'], bars=data, reversal=history[-1] if history else None,
                    reversal_history=history, valuation_available=False, bollinger=None, technical=None)
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0, str(app.exception))
                if count >= 65:
                    self.assertEqual(len(app.get('plotly_chart')), 2)
                    self.assertTrue(any('TRS-2.0' in x.value for x in app.caption))
                    if missing:
                        self.assertTrue(any(x.value == '暫不評分' for x in app.metric))


if __name__ == '__main__':
    unittest.main()
