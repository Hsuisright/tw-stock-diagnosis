from pathlib import Path

import streamlit as st

from diagnosis.quick_analysis import analyze_stock
from diagnosis.sources import update_finmind_history
from diagnosis.technical import price_position_label, trend_label


ROOT=Path(__file__).resolve().parent
DB=ROOT/"data"/"quick_analysis.db"

st.set_page_config(page_title="台股快速溫度分析",page_icon="🌡️",layout="wide")
st.markdown("""<style>.block-container{max-width:1050px;padding-top:1.5rem}.hero{padding:1.2rem 1.5rem;border-radius:18px;color:white;background:linear-gradient(125deg,#0f3d3e,#168aad);margin-bottom:1rem}.bar{height:20px;background:#e7edf0;border-radius:12px;overflow:hidden}.bar div{height:100%;background:linear-gradient(90deg,#2b8cbe,#7bccc4,#fdd49e,#ef6548,#b30000)}</style>""",unsafe_allow_html=True)
st.markdown("""<div class="hero"><h1 style="margin:0">台股快速溫度分析</h1><div>輸入股票代號，自動分析估值、成長要求與短期價格位置</div></div>""",unsafe_allow_html=True)

c1,c2=st.columns([3,1])
stock_id=c1.text_input("股票代號",value="2330",placeholder="例如：2330")
run=c2.button("更新並分析",type="primary",width="stretch")
st.caption("只使用公開市場資料，不需要帳戶、股數或持倉成本。")

if run:
    sid=stock_id.strip().upper()
    if not sid:
        st.error("請輸入股票代號")
    else:
        with st.spinner(f"正在更新 {sid} 的歷史價格與PE…"):
            counts,errors=update_finmind_history(DB,sid,"2019-01-01")
        if errors: st.warning("；".join(errors))
        try: st.session_state["analysis"]=analyze_stock(DB,sid)
        except ValueError as exc: st.error(str(exc))

result=st.session_state.get("analysis")
if result:
    st.subheader(f'{result["stock_id"]}｜資料日 {result["price_date"]}')
    st.metric("目前股價",f'{result["price"]:,.2f} 元')
    if result["valuation_available"]:
        temp=result["valuation_temperature"]
        st.subheader("估值溫度")
        st.markdown(f'<div class="bar"><div style="width:{temp:.1f}%"></div></div>',unsafe_allow_html=True)
        v1,v2,v3,v4=st.columns(4)
        v1.metric("估值溫度",f"{temp:.0f}°C")
        v2.metric("目前／正常PE",f'{result["current_pe"]:.1f}／{result["normal_pe"]:.1f}倍')
        v3.metric("隱含TTM EPS",f'{result["current_eps"]:.2f}元')
        v4.metric("正常PE參考價格",f'{result["support_price"]:.2f}元')
        if result["premium_amount"]>=0: st.info(f'相對正常PE參考價格溢價 {result["premium_amount"]:.2f}元（{result["premium_pct"]:.1f}%）')
        else: st.success(f'相對正常PE參考價格折價 {-result["premium_amount"]:.2f}元（{-result["premium_pct"]:.1f}%）')
        g=result["growth"]
        is_buffer=g.required_growth_1y < 0
        st.subheader("市場隱含獲利緩衝" if is_buffer else "市場隱含成長壓力")
        g1,g2,g3,g4=st.columns(4)
        g1.metric("正常PE參考所需EPS",f"{g.required_eps:.2f}元")
        if is_buffer:
            g2.metric("1年可容許EPS下降",f"{-g.required_growth_1y:.1%}")
            g3.metric("2年年化可容許下降",f"{-g.required_cagr_2y:.1%}")
            g4.metric("3年年化可容許下降",f"{-g.required_cagr_3y:.1%}")
            st.info("目前EPS高於正常PE基準下支撐現價所需水準；這是估值緩衝，不是EPS衰退預測。")
        else:
            g2.metric("1年所需成長",f"{g.required_growth_1y:.1%}")
            g3.metric("2年年化成長",f"{g.required_cagr_2y:.1%}")
            g4.metric("3年年化成長",f"{g.required_cagr_3y:.1%}")
        if not is_buffer and g.achievement_rate is None: st.warning(f"{g.label}；目前只有{g.sample_count}個有效歷史樣本。")
        elif not is_buffer:
            st.info(f"{g.label}｜歷史EPS成長中位數 {g.historical_median:.1%}｜歷史達成率 {g.achievement_rate:.0%}｜樣本 {g.sample_count}")
    else:
        st.warning(result.get("valuation_note","估值資料不足"))
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
    st.caption("本頁為歷史比較與市場期待診斷，不構成投資建議。")
