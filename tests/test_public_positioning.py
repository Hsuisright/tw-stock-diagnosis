import tempfile
import unittest
from pathlib import Path
from diagnosis.public_positioning import FIELDS, normalize_tpex, normalize_twse, read_for_streamlit, save, status, validate

class PublicPositioningTests(unittest.TestCase):
 def test_twse_normalization(self):
  p={"tables":[{}, {"data":[["2330","x","1,000","2","3","4","x","x","5","6","7","8","x","x"]]}]}
  self.assertEqual(normalize_twse(p,"2026-01-01")[0]["margin_balance"],4.0)
 def test_tpex_normalization(self):
  row=b'"3163","x","1","2","3","4","x","x","x","x","5","6","7","8","9"\n'
  self.assertEqual(normalize_tpex(row,"2026-01-01")[0]["short_balance"],9.0)
 def test_validation_deduplicates_and_streamlit_adapter(self):
  r={key:None for key in FIELDS}; r.update(ticker="2330",date="2026-01-01",market="TWSE",source="TWSE",margin_balance=4,short_balance=2,short_stock_repayment=1)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.csv"; save(p,[r,r]); self.assertEqual(len(read_for_streamlit(p,"2330")),1); self.assertEqual(read_for_streamlit(p,"2330")[0]["short_cash_repayment"],1)
 def test_status(self):
  self.assertEqual(status([],"2330",True),"NOT_MARGIN_ELIGIBLE"); self.assertEqual(status([],"2330",False),"DATA_GAP")

if __name__ == '__main__': unittest.main()
