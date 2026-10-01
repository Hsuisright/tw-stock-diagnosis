"""Optional valuation supplement; read-only data access and bounded history cache."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import pandas as pd
import streamlit as st
from .valuation_requirement import requirement, episodes, summary_table

def fingerprint(path):
    return (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None

@st.cache_data(ttl=3600, max_entries=64)
def load(root, db, ticker, cutoff, signatures):
    root, db = Path(root), Path(db)
    facts = json.loads((root / 'data/interpretation_sources/bundle.json').read_text(encoding='utf-8'))['eps']
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as con:
        prices = [dict(date=d, close=c) for d, c in con.execute(
            'SELECT price_date,close FROM prices WHERE stock_id=? AND price_date<=? ORDER BY price_date', (ticker, cutoff))]
    return facts, episodes(facts, ticker, prices, cutoff)

def render(result, root, db):
    st.markdown('[如何解讀估值溫度計？](?view=valuation_help)')
    st.markdown('#### 現價需要多少獲利支持？（Market Requirement）')
    st.write('以歷史參考本益比換算：目前股價需要公司每股賺多少錢？再與前四個已完成季度的實際 EPS 比較，看看差距多大。這是價格要求，不是獲利預測。')
    try:
        facts, rows = load(str(root), str(db), result['stock_id'], result['price_date'],
            (fingerprint(root / 'data/interpretation_sources/bundle.json'), fingerprint(db), fingerprint(Path(str(db) + '-wal'))))
        r = requirement(facts, result['stock_id'], result['price_date'], result['price'], result.get('normal_pe'))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        st.info('N/A · 本機來源缺失或格式無法驗證；未補值。')
        return
    for col, title, value, fmt in zip(st.columns(4),
            ('前四季實際 EPS（元）', '歷史參考本益比（倍）', '現價要求 EPS（元）', '相對基準所需成長'),
            (r['base_eps'], r['reference_pe'], r['required_eps'], r['required_growth']),
            ('.2f', '.2f', '.2f', '.1%')):
        col.metric(title, format(value, fmt) if value is not None else 'N/A')
    if r['reason']:
        st.info('DATA GAP / N/A · ' + r['reason'])
    st.caption('現價要求 EPS＝股價 ÷ 歷史參考本益比；所需成長＝現價要求 EPS ÷ 前四季實際 EPS − 1。正值表示仍需增加獲利；零或負值表示基準獲利已達要求，不代表預測衰退。')
    st.caption('固定前四個已完成季度，缺季不回填。Reference PE 沿用本頁歷史月末 PE 中位數；不是合理 PE。')
    st.markdown('#### 歷史上，獲利花多久追上價格要求？（Historical Market Lead Time）')
    st.write('回看這家公司每個完整季度的最高收盤價，換算當時的 EPS 要求，再追蹤後續實際四季 EPS 何時達成。每一列依「當時需要成長多少」分組，每一格是歷史件數，不是未來達成機率。')
    table = pd.DataFrame(summary_table(rows, r['bucket']))
    for col in ('≤6M', '6–12M', '1–2Y', '>2Y', 'Not Fulfilled'):
        table[col] = table[col].astype(str)
    table['Status'] = table['Status'].replace({'OK': '樣本數達最低要求', 'INSUFFICIENT SAMPLE': '樣本不足（少於5筆）'})
    table = table.rename(columns={'EPS Requirement': '所需 EPS 成長', '≤6M': '6個月內', '6–12M': '超過6個月～1年',
        '1–2Y': '超過1年～2年', '>2Y': '超過2年', 'Not Fulfilled': '截至追蹤末日尚未達成', 'N': '樣本數', 'Status': '資料狀態'})
    st.dataframe(table, hide_index=True, width='stretch')
    st.caption('→ 表示目前需求所在區間。N < 5 不呈現時間分布。表內為件數，不是預測機率。')
    st.caption('起點已達要求者以0個月計入「6個月內」。尚未達成是「右設限」：只表示觀察期間尚未看到結果，不代表失敗，也不表示永遠無法達成。N/A 表示資料或樣本不足。')
    st.warning('回溯探索：未還原收盤價／目前版本財報；以 EPS 所屬季末計時，不是公告日、Strict PIT 或交易回測。股本／拆股跨期可比性尚未全面驗證。')
    st.caption('歷史 Reference PE：僅用起點之前已完成季度的 Peak Close / 前四季實際 EPS，中位數至少 4 季。與上方現價使用的月末 PE 參考樣本不同。Future EPS 只判定達成；資料缺季即停止追蹤。Not Fulfilled 是右設限，不是失敗。')
    with st.expander('查看季度來源與歷史 episode'):
        st.json(r['base_eps_components'])
        st.dataframe(pd.DataFrame([{k: x.get(k) for k in ('quarter_end', 'peak_date', 'peak_close', 'base_eps', 'reference_pe', 'required_eps', 'required_growth', 'status', 'completion_date', 'censor_date', 'reason')} for x in rows]), hide_index=True)

def render_help():
    st.title('如何解讀估值溫度計？')
    st.markdown('[返回個股分析](?)')
    st.code('Base EPS\n↓\nMarket Price ÷ Reference PE\n↓\nRequired EPS\n↓\nFuture Actual EPS\n↓\nFulfillment\n↓\nMarket Lead Time', language=None)
    for title, content in (
        ('PE', '價格相對每股盈餘的倍數。原溫度計、PE 歷史位階與既有隱含 EPS 計算保留；隱含 EPS 不作新模組的財報來源。'),
        ('Base EPS', '觀察季度 Qn 之前 Qn−1 至 Qn−4 的合併稀釋單季 EPS 合計。不含 Qn；任何一季缺失便 N/A，不換更舊窗口。'),
        ('Reference PE', '歷史估值參考，不代表合理價。現價 Requirement 沿用既有五年月末 PE 中位數；歷史 episode 沿用至少四個先前完整季度 Peak PE 的擴展中位數，兩者樣本不同。'),
        ('Required EPS', '目前價格 ÷ Reference PE，回答這個價格在參考倍數下需要多少 EPS，不是預測值。'),
        ('Required EPS Growth', 'Required EPS / Base EPS − 1。負值表示基準 EPS 已高於要求，不是預測衰退。'),
        ('Historical Market Lead Time', '完整季度最高收盤價（同價取最早日）到後續實際 rolling 四季 EPS 首次達標的歷史時間。已達標為零；不設四年上限。以經濟季度結束日計時，並非市場得知日。'),
        ('Right-censored', '截至最後可連續驗證的 EPS 季度尚未觀察達成。缺季停止，不跨缺口宣稱首次達成；零追蹤也可能被設限。不是 FAIL。'),
        ('Data Qualification', '只沿用合併稀釋實際季度 EPS，不從 Price / PE 倒算。未知公告日期不補造，也不升級 PIT 資格。現在版本／未還原價格只是探索，股本變動可比性仍有限制。'),
        ('常見誤讀', '歷史件數不是未來機率；N < 5 顯示 INSUFFICIENT SAMPLE。不同 EPS Requirement 對應不同樣本，右設限使觀察比例不等於最終完成率。不能把別家公司的時間套用到本公司。'),
        ('本指標在 V1 的角色', '補充價格要求與歷史實際獲利的距離；不參與 TRS、Fundamental、Repricing。不是 EPS forecast、target price、fair value、買賣訊號、報酬預測或擇時訊號。'),
    ):
        st.subheader(title)
        st.write(content)
