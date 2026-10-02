from pathlib import Path
import hmac
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from diagnosis.quick_analysis import analyze_stock
from diagnosis.reversal_view import render_reversal
from diagnosis.interpretation import build_interpretation, build_opportunity_risk
from diagnosis.sources import search_stock_directory, update_finmind_history, update_stock_directory
from diagnosis.eps_history_store import hydrate_from_seed, refresh as refresh_eps_history
from diagnosis.technical import price_position_label, trend_label
from diagnosis.valuation_requirement_view import fingerprint
from diagnosis.valuation_v15_view import current_actual_ttm
from diagnosis.public_positioning import read_for_streamlit
from diagnosis.positioning_rules import calculate as calculate_positioning
from diagnosis.positioning_view import render as render_positioning


ROOT=Path(__file__).resolve().parent
DB=ROOT/"data"/"quick_analysis.db"
EPS_DB=ROOT/"data"/"eps_history.sqlite3"
EPS_SEED=ROOT/"public_data"/"eps_seed_v1.json"
POSITIONING_DATA=ROOT/"public_data"/"public_positioning.csv"

st.set_page_config(page_title="台股快速溫度分析",page_icon="🌡️",layout="wide")
st.markdown('''<style>
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {background:#F7F2EA;color:#403A36}
[data-testid="stSidebar"] {background:#EAE1D7}
[data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2,[data-testid="stAppViewContainer"] h3 {color:#403A36}
.stButton button[kind="primary"] {background:#875C50;border-color:#875C50;color:#FFFFFF}
.stButton button:hover {border-color:#875C50;color:#875C50}
.stButton button[kind="primary"]:hover {background:#75655E;color:#FFFFFF}
[data-baseweb="input"], [data-baseweb="select"] {background:#EAE1D7}
</style>''',unsafe_allow_html=True)


def require_test_password():
    """公開測試站的簡易密碼門禁；密碼只存放於 Streamlit Secrets。"""
    if "--local-no-password" in sys.argv[1:]:
        if st.get_option("server.address") != "127.0.0.1":
            st.error("本機免密碼模式只允許綁定 127.0.0.1；已停止啟動。")
            st.stop()
        st.caption("本機私人模式 · 僅限這台電腦 · 免密碼")
        return
    try:
        expected = str(st.secrets.get("APP_PASSWORD", ""))
    except Exception:
        expected = ""
    if not expected:
        st.error("網站尚未設定測試密碼，請聯絡管理者。")
        st.stop()
    if st.session_state.get("password_authenticated"):
        return

    st.title("台股快速溫度分析")
    st.caption("此網站目前為邀請測試版，請輸入測試密碼。")
    supplied = st.text_input("測試密碼", type="password")
    if st.button("進入網站", type="primary"):
        if hmac.compare_digest(supplied, expected):
            st.session_state["password_authenticated"] = True
            st.rerun()
        else:
            st.error("密碼不正確")
    st.stop()


require_test_password()
st.caption("Product Version: V1.5 · 本機候選版")
if st.query_params.get('view') == 'valuation_help':
    from diagnosis.valuation_v15_view import render_help
    render_help()
    st.stop()
# V1 hides the historical-trend and readiness preview entrances.
# Their underlying modules remain unchanged and available separately.
st.markdown("""<style>.block-container{max-width:1050px;padding-top:1.5rem}.hero{padding:1.2rem 1.5rem;border-radius:18px;color:white;background:linear-gradient(125deg,#75655E,#875C50);margin-bottom:1rem}.bar{height:20px;background:#EAE1D7;border-radius:12px;overflow:hidden}.bar div{height:100%;background:linear-gradient(90deg,#7F9692,#A4ADA0,#D3BDA2,#B08070,#875C50)}.stage-track{display:grid;grid-template-columns:repeat(6,1fr);gap:.35rem;margin:.4rem 0 1rem}.stage{padding:.55rem .25rem;text-align:center;background:#EAE1D7;border-radius:.45rem;font-size:.85rem}.stage.active{background:#875C50;color:white;font-weight:700}@media(max-width:700px){.stage-track{grid-template-columns:repeat(3,1fr)}}</style>""",unsafe_allow_html=True)
st.markdown("""<div class="hero"><h1 style="margin:0">台股快速溫度分析</h1><div>輸入股票代號或名稱，自動分析估值、成長要求、趨勢、動能與價格型態</div></div>""",unsafe_allow_html=True)

c1,c2=st.columns([3,1])
stock_id=c1.text_input("股票代號或名稱",value="2330",placeholder="例如：2330、台積電或台積")
run=c2.button("搜尋並分析",type="primary",width="stretch")
st.caption("只使用公開市場資料，不需要帳戶、股數或持倉成本。")

def render_price_temperature(result):
    st.subheader("短期價格溫度")
    b=result["bollinger"]
    if not b: st.warning("價格資料不足20筆，無法計算布林通道。")
    else:
        st.markdown(f'<div class="bar"><div style="width:{b.temperature:.1f}%"></div></div>',unsafe_allow_html=True)
        p1,p2,p3,p4=st.columns(4)
        p1.metric("價格溫度",f"{b.temperature:.0f}°C")
        p2.metric("布林位階",price_position_label(b.percent_b))
        p3.metric("均線方向",trend_label(b.ma_slope))
        p4.metric("通道寬度",f"{b.bandwidth:.1f}%")

def run_analysis(sid,label=None):
    with st.spinner(f"正在更新 {label or sid} 的歷史價格與PE…"):
        counts,errors=update_finmind_history(DB,sid,"2019-01-01")
        _,benchmark_errors=update_finmind_history(DB,"0050","2019-01-01",include_pe=False)
        errors.extend(benchmark_errors)
        try:
            # Seeded names open immediately from a versioned public cache.
            # Other names retain the existing live public-source path.
            if not hydrate_from_seed(EPS_DB, EPS_SEED, sid):
                refresh_eps_history(EPS_DB,sid)
        except Exception as exc:
            errors.append(f"季度EPS：{exc}")
    if errors: st.warning("；".join(errors))
    try:
        analysis=analyze_stock(DB,sid)
        positioning_rows = read_for_streamlit(POSITIONING_DATA, sid)
        positioning_meta = {"source": "TWSE/TPEx official public data"} if positioning_rows else None
        bars=analysis.get("bars") or []
        price_return_5d = None
        if len(bars) >= 6:
            previous, latest = bars[-6].get("close"), bars[-1].get("close")
            if previous not in (None, 0) and latest is not None:
                price_return_5d = float(latest) / float(previous) - 1
        analysis["positioning"] = calculate_positioning(
            positioning_rows, price_return_5d,
            analysis.get("technical").volume_ratio if analysis.get("technical") else None,
            positioning_meta,
        )
        st.session_state["analysis"]=analysis
        st.session_state.pop("search_matches",None)
    except ValueError as exc: st.error(str(exc))


if run:
    query=stock_id.strip()
    if not query:
        st.error("請輸入股票代號或名稱")
    else:
        with st.spinner("正在更新公司名稱目錄…"):
            _,directory_errors=update_stock_directory(DB)
        if directory_errors: st.warning("；".join(directory_errors))
        matches=search_stock_directory(DB,query)
        if not matches and query.isdigit():
            run_analysis(query.upper())
        elif not matches:
            st.error(f"找不到「{query}」對應的台股公司，請改用完整名稱或股票代號。")
        elif len(matches)==1:
            match=matches[0]
            run_analysis(match["stock_id"],f'{match["stock_name"]}（{match["stock_id"]}）')
        else:
            st.session_state["search_matches"]=matches
            st.session_state.pop("analysis",None)

pending=st.session_state.get("search_matches")
if pending:
    st.info(f"找到 {len(pending)} 個可能結果，請選擇要分析的股票。")
    labels={f'{x["stock_name"]}（{x["stock_id"]}）｜{x.get("market") or "市場未標示"}':x for x in pending}
    selected=st.selectbox("搜尋結果",list(labels))
    if st.button("分析選取股票",type="primary"):
        match=labels[selected]
        run_analysis(match["stock_id"],selected)

result=st.session_state.get("analysis")
if result:
    # V1 always renders the original Timing view, regardless of stale view state.
    identity=f'{result.get("stock_name") or ""}（{result["stock_id"]}）' if result.get("stock_name") else result["stock_id"]
    st.subheader(f'{identity}｜資料日 {result["price_date"]}')
    st.metric("目前股價",f'{result["price"]:,.2f} 元')
    st.header("短期市場與技術面")
    st.caption("觀察價格、趨勢、動能、量價、相對強弱與市場結構。")
    # Keep the public deployment compatible with the established reversal view.
    # The optional compact/callback interface is a local candidate enhancement
    # and is not part of the deployed module contract.
    render_price_temperature(result)
    render_positioning(result.get("positioning") or calculate_positioning([], None, None, None))
    render_reversal(result)
    interpretation=build_interpretation(result)
    st.subheader("綜合判讀")
    st.info(interpretation["overall"])
    st.markdown(f'**短期注意：** {interpretation["short_term"]}')
    st.markdown(f'**中期觀察：** {interpretation["medium_term"]}')
    st.markdown(f'**長期考量：** {interpretation["long_term"]}')
    st.caption("以上內容由固定規則依公開數據產生，用於整理觀察重點，不構成買賣建議。")
    matrix=build_opportunity_risk(result)
    st.subheader("機會—風險矩陣")
    m1,m2,m3,m4=st.columns(4)
    m1.metric("估值資料可用程度",matrix["certainty"])
    m2.metric("成長空間",matrix["elasticity"])
    m3.metric("估值風險",matrix["valuation_risk"])
    m4.metric("價格風險",matrix["price_risk"])
    st.info(f'綜合類型：{matrix["category"]}')
    with st.expander("查看矩陣判斷依據"):
        st.markdown(f'- **估值資料可用程度：** {matrix["certainty_reason"]}')
        st.markdown(f'- **成長空間：** {matrix["elasticity_reason"]}')
        st.markdown(f'- **估值風險：** {matrix["valuation_reason"]}')
        st.markdown(f'- **價格風險：** {matrix["price_reason"]}')
    st.header("長期基本面與估值")
    st.caption("觀察實際獲利與目前價格對 EPS 的要求；不是未來獲利預測。")
    if result["valuation_available"]:
        temp=result["valuation_temperature"]
        actual_ttm = current_actual_ttm(str(EPS_DB), result["stock_id"], result["price_date"], fingerprint(EPS_DB))
        actual_eps = actual_ttm["value"]
        actual_reference_price = actual_eps * result["normal_pe"] if actual_eps is not None else None
        actual_premium = result["price"] - actual_reference_price if actual_reference_price is not None else None
        st.subheader("估值溫度")
        st.markdown(f'<div class="bar"><div style="width:{temp:.1f}%"></div></div>',unsafe_allow_html=True)
        v1,v2,v3,v4=st.columns(4)
        v1.metric("估值溫度",f"{temp:.0f}°C")
        v2.metric("目前／歷史參考PE",f'{result["current_pe"]:.1f}／{result["normal_pe"]:.1f}倍')
        v3.metric("近四季實際 EPS（TTM）",f'{actual_eps:.2f}元' if actual_eps is not None else 'N/A')
        v4.metric("實際EPS參考價格",f'{actual_reference_price:.2f}元' if actual_reference_price is not None else 'N/A')
        if actual_premium is None:
            st.info(f'近四季實際 EPS（TTM）資料不足：{actual_ttm["reason"]}。不以股價／本益比反推值替代。')
        elif actual_premium>=0:
            st.info(f'相對實際EPS參考價格溢價 {actual_premium:.2f}元（{actual_premium / actual_reference_price:.1f}%）')
        else:
            st.success(f'相對實際EPS參考價格折價 {-actual_premium:.2f}元（{-actual_premium / actual_reference_price:.1f}%）')
        st.caption('V1.5 主估值計算均使用近四季實際 EPS（TTM）；不使用股價／本益比反推 EPS。')
        with st.expander("舊版隱含成長診斷（股價／本益比反推值，僅供參考）"):
            g=result["growth"]
            is_buffer=g.required_growth_1y < 0
            st.subheader("市場隱含獲利緩衝" if is_buffer else "市場隱含成長壓力")
            g1,g2,g3,g4=st.columns(4)
            st.caption('此區僅保留舊版診斷，不會進入 V1.5 的 TTM EPS、所需成長率或歷史成長能力計算。')
            g1.metric("歷史PE參考所需EPS（舊版）",f"{g.required_eps:.2f}元")
            if is_buffer:
                g2.metric("1年可容許EPS下降",f"{-g.required_growth_1y:.1%}")
                g3.metric("2年年化可容許下降",f"{-g.required_cagr_2y:.1%}")
                g4.metric("3年年化可容許下降",f"{-g.required_cagr_3y:.1%}")
                st.info("目前隱含EPS高於歷史PE基準下支撐現價所需水準；這是估值緩衝，不是EPS衰退預測。")
            else:
                g2.metric("1年所需成長",f"{g.required_growth_1y:.1%}")
                g3.metric("2年年化成長",f"{g.required_cagr_2y:.1%}")
                g4.metric("3年年化成長",f"{g.required_cagr_3y:.1%}")
            if not is_buffer and g.achievement_rate is None: st.warning(f"{g.label}；目前只有{g.sample_count}個有效歷史樣本。")
            elif not is_buffer:
                st.info(f"{g.label}｜歷史EPS成長中位數 {g.historical_median:.1%}｜歷史達成率 {g.achievement_rate:.0%}｜樣本 {g.sample_count}")
    else:
        st.warning(result.get("valuation_note","估值資料不足"))
    from diagnosis.valuation_v15_view import render as render_requirement
    render_requirement(result, ROOT, DB, EPS_DB)
    with st.expander("技術診斷詳細資料"):
        t=result.get("technical")
        if t:
            st.subheader("技術診斷")
            st.info(t.summary)
            t1,t2,t3,t4=st.columns(4)
            t1.metric("短線",t.short_state)
            t2.metric("中期",t.medium_state)
            t3.metric("長期",t.long_state)
            t4.metric("波動風險",t.risk_state)
            st.markdown("#### 趨勢與動能")
            rows=[]
            for label,avg,momentum in (("20日",t.ma20,t.momentum20),("60日",t.ma60,t.momentum60),
                                       ("120日",t.ma120,t.momentum120),("240日",t.ma240,None)):
                rows.append({"週期":label,"均線":f"{avg:.2f}" if avg is not None else "—",
                             "動能":f"{momentum:+.1%}" if momentum is not None else "—"})
            st.table(rows)
            s1,s2,s3=st.columns(3)
            s1.metric("型態",t.pattern_state)
            s2.metric("量價",t.volume_state, f"量比 {t.volume_ratio:.2f}倍" if t.volume_ratio is not None else None)
            s3.metric("60日年化波動",f"{t.volatility60:.1%}" if t.volatility60 is not None else "—")
            if t.range20_high is not None:
                st.caption(f"20日觀察區間：{t.range20_low:.2f}～{t.range20_high:.2f}元｜60日觀察區間：{t.range60_low:.2f}～{t.range60_high:.2f}元。這些是結構觀察線，不是自動買賣價。")
            bull,bear=st.columns(2)
            with bull:
                st.markdown("#### 多方證據")
                if t.bullish_evidence:
                    for item in t.bullish_evidence: st.success(f"＋ {item}")
                else: st.caption("目前沒有明確多方證據")
            with bear:
                st.markdown("#### 空方／風險證據")
                if t.bearish_evidence:
                    for item in t.bearish_evidence: st.warning(f"－ {item}")
                else: st.caption("目前沒有明確空方證據")
            if t.neutral_evidence:
                st.caption("中性／待確認："+"；".join(t.neutral_evidence))
    st.caption("本頁為歷史比較與市場期待診斷，不構成投資建議。")
