from __future__ import annotations
import json, os, urllib.parse, urllib.request
from datetime import date, datetime
from .db import connect

UA={"User-Agent":"Mozilla/5.0 StockDiagnosisV2"}
def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))
def _num(v):
    try:return float(str(v).replace(",","").strip())
    except:return None
def update_market(db_path):
    feeds=[("TWSE","https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"),
           ("TPEx","https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")]
    con=connect(db_path); updated=0; errors=[]
    with con:
        for market,url in feeds:
            try:
                for x in _get(url):
                    code=(x.get("Code") if market=="TWSE" else x.get("SecuritiesCompanyCode"))
                    px=_num(x.get("ClosingPrice") if market=="TWSE" else x.get("Close"))
                    raw=x.get("Date") or date.today().isoformat()
                    digits="".join(c for c in str(raw) if c.isdigit())
                    if len(digits)==7: d=f"{int(digits[:3])+1911}-{digits[3:5]}-{digits[5:7]}"
                    elif len(digits)>=8: d=f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
                    else:d=date.today().isoformat()
                    if code and px and px>0:
                        con.execute("INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?)",(str(code).strip(),d,px,market,url));updated+=1
                con.execute("INSERT INTO data_sources(dataset,source,url,status,updated_at,note) VALUES(?,?,?,?,?,?)",("市場價格",market,url,"成功",datetime.now().isoformat(timespec="seconds"),f"更新{updated}筆"))
            except Exception as e: errors.append(f"{market}: {e}")
    return updated,errors

def update_finmind_history(db_path, stock_id, start_date="2016-01-01", token=None):
    """更新單一股票歷史價格與P/E；Token可由FINMIND_TOKEN環境變數提供。"""
    token=token or os.getenv("FINMIND_TOKEN","")
    con=connect(db_path); counts={"price":0,"pe":0}; errors=[]
    def query(dataset):
        q={"dataset":dataset,"data_id":stock_id,"start_date":start_date}
        if token:q["token"]=token
        return _get("https://api.finmindtrade.com/api/v4/data?"+urllib.parse.urlencode(q)).get("data",[])
    with con:
        try:
            for x in query("TaiwanStockPrice"):
                px=_num(x.get("close")); d=x.get("date")
                if d and px and px>0:
                    con.execute("INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?)",(stock_id,d,px,"FinMind","https://api.finmindtrade.com/api/v4/data"));counts["price"]+=1
        except Exception as e:errors.append(f"價格：{e}")
        try:
            for x in query("TaiwanStockPER"):
                pe=_num(x.get("PER")); d=x.get("date")
                if d and pe and pe>0:
                    con.execute("INSERT OR REPLACE INTO pe_history VALUES(?,?,?,?)",(stock_id,d,pe,"FinMind"));counts["pe"]+=1
        except Exception as e:errors.append(f"P/E：{e}")
    return counts,errors
