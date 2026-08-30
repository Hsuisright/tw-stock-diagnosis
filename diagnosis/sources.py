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
                    con.execute("""INSERT OR REPLACE INTO daily_bars
                        (stock_id,price_date,open,high,low,close,volume,source)
                        VALUES(?,?,?,?,?,?,?,?)""",(
                            stock_id,d,_num(x.get("open")),_num(x.get("max")),
                            _num(x.get("min")),px,_num(x.get("Trading_Volume")),"FinMind"))
        except Exception as e:errors.append(f"價格：{e}")
        try:
            for x in query("TaiwanStockPER"):
                pe=_num(x.get("PER")); d=x.get("date")
                if d and pe and pe>0:
                    con.execute("INSERT OR REPLACE INTO pe_history VALUES(?,?,?,?)",(stock_id,d,pe,"FinMind"));counts["pe"]+=1
        except Exception as e:errors.append(f"P/E：{e}")
    return counts,errors


def update_stock_directory(db_path, token=None):
    """更新台股代號與公司名稱目錄，供代號、全名及部分名稱搜尋。"""
    token=token or os.getenv("FINMIND_TOKEN","")
    q={"dataset":"TaiwanStockInfo"}
    if token:q["token"]=token
    url="https://api.finmindtrade.com/api/v4/data?"+urllib.parse.urlencode(q)
    con=connect(db_path); updated=0
    try:
        rows=_get(url).get("data",[])
        latest={}
        for x in rows:
            stock_id=str(x.get("stock_id") or "").strip()
            stock_name=str(x.get("stock_name") or "").strip()
            if not stock_id or not stock_name:continue
            previous=latest.get(stock_id)
            if previous is None or str(x.get("date") or "")>=str(previous.get("date") or ""):
                latest[stock_id]=x
        now=datetime.now().isoformat(timespec="seconds")
        with con:
            for stock_id,x in latest.items():
                con.execute("""INSERT OR REPLACE INTO stock_directory
                    (stock_id,stock_name,market,industry,source_date,updated_at)
                    VALUES(?,?,?,?,?,?)""",(stock_id,str(x.get("stock_name") or "").strip(),
                        x.get("type"),x.get("industry_category"),x.get("date"),now))
                updated+=1
        return updated,[]
    except Exception as exc:
        return 0,[f"公司名稱目錄：{exc}"]
    finally:
        con.close()


def search_stock_directory(db_path, query, limit=20):
    text=str(query or "").strip()
    if not text:return []
    con=connect(db_path)
    exact=con.execute("""SELECT stock_id,stock_name,market,industry FROM stock_directory
        WHERE stock_id=? OR stock_name=? ORDER BY stock_id LIMIT ?""",(text,text,limit)).fetchall()
    rows=exact or con.execute("""SELECT stock_id,stock_name,market,industry FROM stock_directory
        WHERE stock_id LIKE ? OR stock_name LIKE ?
        ORDER BY CASE WHEN stock_name LIKE ? THEN 0 ELSE 1 END, LENGTH(stock_name),stock_id LIMIT ?""",
        (text+"%","%"+text+"%",text+"%",limit)).fetchall()
    result=[dict(row) for row in rows]
    con.close();return result
