import unittest
from diagnosis.volume_profile import estimate_profile
from test_reversal_v2 import bars


class ProfileTests(unittest.TestCase):
    def test_conservation_and_area(self):
        data=bars([100+i*.1 for i in range(150)])
        for n in (60,120):
            p,error=estimate_profile(data,n)
            self.assertIsNone(error)
            self.assertAlmostEqual(sum(p['volumes']), n*1000)
            self.assertTrue(p['lower'] <= p['poc'] <= p['upper'])
            self.assertGreaterEqual(p['area_fraction'],.7)
            self.assertEqual(p['start'],data[-n]['date'])

    def test_reject_missing_short_and_jump(self):
        for data,n in ((bars([100]*60),120),(bars([100]*120,None),60),
                       (bars([100]*70+[50]*50),120)):
            p,error=estimate_profile(data,n)
            self.assertIsNone(p)
            self.assertTrue(error)
        data=bars([100]*60)
        del data[5]['high']
        self.assertIsNone(estimate_profile(data)[0])

    def test_flat_range(self):
        data=bars([100]*60)
        for x in data: x['low']=x['high']=100
        p,error=estimate_profile(data)
        self.assertIsNone(error)
        self.assertEqual(p['volumes'],[60000])
        self.assertEqual(p['poc'],100)

