from __future__ import annotations

from datetime import datetime
from statistics import median

from .db import connect
from .growth import implied_growth_diagnostic, yoy_growths
from .model import percentile_rank
from .technical import bollinger_snapshot, price_position_label, trend_label


def analyze_stock(db_path, stock_id):
    stock_id=str(stock_id).strip().upper()
    if not stock_id:
        raise ValueError("請輸入股票代號")
    con=connect(db_path)
    latest=con.execute("SELECT price_date,close FROM prices WHERE stock_id=? AND close>0 ORDER BY price_date DESC LIMIT 1",(stock_id,)).fetchone()
    if not latest:
        con.close(); raise ValueError("尚無價格資料，請先執行更新")
    latest_pe=con.execute("SELECT pe FROM pe_history WHERE stock_id=? AND value_date=? AND pe>0",(stock_id,latest["price_date"])).fetchone()
    prices=con.execute("SELECT close FROM prices WHERE stock_id=? AND close>0 ORDER BY price_date DESC LIMIT 60",(stock_id,)).fetchall()
    boll=bollinger_snapshot([r["close"] for r in reversed(prices)])
    result={"stock_id":stock_id,"price_date":latest["price_date"],"price":float(latest["close"]),
        "bollinger":boll,"price_label":price_position_label(boll.percent_b) if boll else None,
        "trend_label":trend_label(boll.ma_slope) if boll else None,"valuation_available":False}
    if not latest_pe:
        result["valuation_note"]="最新交易日沒有有效PE，可能是最近四季EPS非正數或資料來源未提供。"
        con.close(); return result
    latest_date=datetime.fromisoformat(latest["price_date"])
    cutoff5=latest_date.replace(year=latest_date.year-5).date().isoformat()
    pe_rows=con.execute("SELECT value_date,pe FROM pe_history WHERE stock_id=? AND value_date>=? AND value_date<=? AND pe>0 ORDER BY value_date",(stock_id,cutoff5,latest["price_date"])).fetchall()
    by_month={}
    for row in pe_rows: by_month[row["value_date"][:7]]=float(row["pe"])
    pe_values=list(by_month.values())
    if len(pe_values)<24:
        result["valuation_note"]=f"PE歷史只有{len(pe_values)}個月，至少需要24個月。"
        con.close(); return result
    current_pe=float(latest_pe["pe"]); current_eps=float(latest["close"])/current_pe
    normal_pe=median(pe_values); support=current_eps*normal_pe
    cutoff6=latest_date.replace(year=latest_date.year-6).date().isoformat()
    rows=con.execute("""SELECT p.price_date,p.close,h.pe FROM prices p JOIN pe_history h
        ON h.stock_id=p.stock_id AND h.value_date=p.price_date
        WHERE p.stock_id=? AND p.price_date>=? AND p.price_date<=? AND p.close>0 AND h.pe>0
        ORDER BY p.price_date""",(stock_id,cutoff6,latest["price_date"])).fetchall()
    monthly_eps={}
    for row in rows:
        y,m=map(int,row["price_date"].split("-")[:2]); monthly_eps[(y,m)]=float(row["close"])/float(row["pe"])
    growth=implied_growth_diagnostic(float(latest["close"]),current_eps,normal_pe,yoy_growths(monthly_eps))
    result.update({"valuation_available":True,"current_pe":current_pe,"current_eps":current_eps,
        "normal_pe":normal_pe,"valuation_temperature":percentile_rank(pe_values,current_pe)*100,
        "support_price":support,"premium_amount":float(latest["close"])-support,
        "premium_pct":((float(latest["close"])-support)/support*100),
        "growth":growth,"pe_months":len(pe_values)})
    con.close(); return result
