from pathlib import Path
import hmac

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from diagnosis.quick_analysis import analyze_stock
from diagnosis.interpretation import build_interpretation, build_opportunity_risk
from diagnosis.sources import search_stock_directory, update_finmind_history, update_stock_directory
from diagnosis.technical import price_position_label, trend_label


ROOT=Path(__file__).resolve().parent
DB=ROOT/"data"/"quick_analysis.db"

st.set_page_config(page_title="台股快速溫度分析",page_icon="🌡️",layout="wide")


def require_test_password():
    """公開測試站的簡易密碼門禁；密碼只存放於 Streamlit Secrets。"""
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
st.markdown("""<style>.block-container{max-width:1050px;padding-top:1.5rem}.hero{padding:1.2rem 1.5rem;border-radius:18px;color:white;background:linear-gradient(125deg,#0f3d3e,#168aad);margin-bottom:1rem}.bar{height:20px;background:#e7edf0;border-radius:12px;overflow:hidden}.bar div{height:100%;background:linear-gradient(90deg,#2b8cbe,#7bccc4,#fdd49e,#ef6548,#b30000)}.stage-track{display:grid;grid-template-columns:repeat(6,1fr);gap:.35rem;margin:.4rem 0 1rem}.stage{padding:.55rem .25rem;text-align:center;background:#e7edf0;border-radius:.45rem;font-size:.85rem}.stage.active{background:#168aad;color:white;font-weight:700}@media(max-width:700px){.stage-track{grid-template-columns:repeat(3,1fr)}}</style>""",unsafe_allow_html=True)
st.markdown("""<div class="hero"><h1 style="margin:0">台股快速溫度分析</h1><div>輸入股票代號或名稱，自動分析估值、成長要求、趨勢、動能與價格型態</div></div>""",unsafe_allow_html=True)

c1,c2=st.columns([3,1])
stock_id=c1.text_input("股票代號或名稱",value="2330",placeholder="例如：2330、台積電或台積")
run=c2.button("搜尋並分析",type="primary",width="stretch")
st.caption("只使用公開市場資料，不需要帳戶、股數或持倉成本。")

def run_analysis(sid,label=None):
    with st.spinner(f"正在更新 {label or sid} 的歷史價格與PE…"):
        counts,errors=update_finmind_history(DB,sid,"2019-01-01")
        _,benchmark_errors=update_finmind_history(DB,"0050","2019-01-01",include_pe=False)
        errors.extend(benchmark_errors)
    if errors: st.warning("；".join(errors))
    try:
        st.session_state["analysis"]=analyze_stock(DB,sid)
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
    identity=f'{result.get("stock_name") or ""}（{result["stock_id"]}）' if result.get("stock_name") else result["stock_id"]
    st.subheader(f'{identity}｜資料日 {result["price_date"]}')
    st.metric("目前股價",f'{result["price"]:,.2f} 元')
    reversal=result.get("reversal")
    if reversal:
        stages=["弱勢延續","超跌觀察","初步止跌","反折形成","反折確認","強勢延伸"]
        active=stages.index(reversal.stage) if reversal.stage in stages else 0
        stage_html="".join(f'<div class="stage {"active" if i==active else ""}">{name}</div>' for i,name in enumerate(stages))
        st.subheader("反折診斷")
        st.markdown(f'<div class="stage-track">{stage_html}</div>',unsafe_allow_html=True)
        r1,r2,r3,r4=st.columns(4)
        history=result.get("reversal_history") or []
        delta=reversal.score-history[-6].score if len(history)>=6 else None
        r1.metric("TRS反折分數",f"{reversal.score}/100",f"近5日 {delta:+d}" if delta is not None else None)
        r2.metric("目前階段",reversal.stage)
        r3.metric("確認價",f"{reversal.confirmation_price:.2f}元" if reversal.confirmation_price else "—",
                  f"距離 {(reversal.confirmation_price/result['price']-1):+.1%}" if reversal.confirmation_price else None)
        r4.metric("失敗價",f"{reversal.failure_price:.2f}元" if reversal.failure_price else "—",
                  f"距離 {(reversal.failure_price/result['price']-1):+.1%}" if reversal.failure_price else None)
        st.caption("TRS衡量由弱轉強的證據完整度；高分不等於適合追價。相對強弱以0050作為大盤代理。")
        score_cols=st.columns(6)
        score_items=(("趨勢",reversal.trend_score,20),("動能",reversal.momentum_score,20),
                     ("量價",reversal.volume_score,15),("相對強弱",reversal.relative_score,15),
                     ("結構",reversal.structure_score,20),("型態",reversal.pattern_score,10))
        for col,(label,value,total) in zip(score_cols,score_items): col.metric(label,f"{value}/{total}")
        with st.expander("查看反折證據與未確認條件"):
            e1,e2=st.columns(2)
            with e1:
                st.markdown("**已成立證據**")
                for item in reversal.evidence: st.success(f"＋ {item}")
            with e2:
                st.markdown("**尚未確認**")
                for item in reversal.pending: st.warning(f"－ {item}")
        bars=pd.DataFrame(result.get("bars") or []).tail(120)
        if not bars.empty:
            bars["date"]=pd.to_datetime(bars["date"])
            fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.04,row_heights=[.75,.25])
            fig.add_trace(go.Candlestick(x=bars["date"],open=bars["open"],high=bars["high"],low=bars["low"],close=bars["close"],name="K線"),row=1,col=1)
            for period in (5,10,20,60):
                fig.add_trace(go.Scatter(x=bars["date"],y=bars["close"].rolling(period).mean(),name=f"MA{period}",line={"width":1.4}),row=1,col=1)
            if reversal.confirmation_price: fig.add_hline(y=reversal.confirmation_price,line_dash="dash",annotation_text="確認價",row=1,col=1)
            if reversal.failure_price: fig.add_hline(y=reversal.failure_price,line_dash="dot",annotation_text="失敗價",row=1,col=1)
            fig.add_trace(go.Bar(x=bars["date"],y=bars["volume"],name="成交量",marker_color="#7f8c8d"),row=2,col=1)
            fig.update_layout(height=610,margin={"l":10,"r":10,"t":35,"b":10},xaxis_rangeslider_visible=False,hovermode="x unified",legend_orientation="h",title="價格結構、均線與關鍵價位")
            st.plotly_chart(fig,width="stretch")
        if history:
            trs=pd.DataFrame({"日期":[x.date for x in history],"TRS":[x.score for x in history]})
            trs_fig=go.Figure(go.Scatter(x=trs["日期"],y=trs["TRS"],mode="lines",name="TRS",line={"width":3}))
            for y in (25,40,55,70,85): trs_fig.add_hline(y=y,line_width=1,line_dash="dot")
            trs_fig.update_layout(height=300,margin={"l":10,"r":10,"t":35,"b":10},yaxis={"range":[0,100],"title":"TRS"},title="TRS歷史變化")
            st.plotly_chart(trs_fig,width="stretch")

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
    m1.metric("基本面確定性",matrix["certainty"])
    m2.metric("潛在成長彈性",matrix["elasticity"])
    m3.metric("估值風險",matrix["valuation_risk"])
    m4.metric("價格風險",matrix["price_risk"])
    st.info(f'綜合類型：{matrix["category"]}')
    with st.expander("查看矩陣判斷依據"):
        st.markdown(f'- **基本面確定性：** {matrix["certainty_reason"]}')
        st.markdown(f'- **成長彈性：** {matrix["elasticity_reason"]}')
        st.markdown(f'- **估值風險：** {matrix["valuation_reason"]}')
        st.markdown(f'- **價格風險：** {matrix["price_reason"]}')
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
