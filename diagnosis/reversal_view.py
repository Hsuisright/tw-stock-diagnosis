from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from .reversal import explain_change
from .volume_profile import estimate_profile


def render_reversal(result):
    current = result.get("reversal")
    if current is None:
        st.info("反折資料不足：至少需65筆有效日價格。")
        return
    history = result.get("reversal_history", [])
    st.subheader("反折診斷")
    st.caption(f"價格日 {result['price_date']}｜反折資料日 {current.date}｜TRS-2.0｜有效構面權重 {current.coverage}/100")
    lag = (date.today()-date.fromisoformat(current.date)).days
    if lag > 4 or current.date != result["price_date"]:
        st.warning("反折資料可能落後現價；以下訊號與距離均以反折資料日為準，請重新更新。")
    st.caption("使用未還原日價格；尚未自動校正除權息／分割。偵測到大幅價格斷點時暫停TRS，較小事件仍需人工核對。")
    for warning in current.warnings:
        st.warning(warning)
    stages = ["弱勢延續","超跌觀察","初步止跌","反折形成","反折確認","強勢延伸"]
    st.markdown(" → ".join(f"**【{s}】**" if s == current.stage else s for s in stages))
    st.caption("階段由結構與條件決定，可跳轉或退回；既有多頭、盤整、回測、失敗和資料不足另行標示。")
    cols = st.columns(4)
    delta = None
    if len(history) >= 6 and current.score is not None and history[-6].score is not None:
        delta = current.score-history[-6].score
    cols[0].metric("TRS反折分數", "暫不評分" if current.score is None else f"{current.score}/100",
                   None if delta is None else f"近5日 {delta:+d}")
    cols[1].metric("目前階段", current.stage)
    price = result["bars"][-1]["close"]
    for col,label,value in ((cols[2],"確認價",current.confirmation_price),(cols[3],"失敗價",current.failure_price)):
        col.metric(label, "尚無有效結構" if value is None else f"{value:.2f}元",
                   None if value is None else f"距反折資料日收盤 {value/price-1:+.1%}")
    if current.setup_id:
        st.caption(f"本次結構自 {current.setup_started} 開始觀察；第二低點日期 {current.setup_id}。價位固定，失敗或60個交易日到期後重新辨識。")
    st.caption("總分須六構面資料完整才提供；缺漏不當作0分，也不重新放大其餘權重。分數不是成功機率。相對強弱基準為0050。")
    components = [("趨勢",current.trend_score,20),("動能",current.momentum_score,20),
                  ("量價",current.volume_score,15),("相對強弱",current.relative_score,15),
                  ("結構",current.structure_score,20),("型態",current.pattern_score,10)]
    for col,(name,value,maximum) in zip(st.columns(6),components):
        col.metric(name,"資料不足" if value is None else f"{value}/{maximum}")
    rows,note = explain_change(history)
    st.markdown("**近5個交易日變化**")
    st.write(note)
    if rows:
        st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
    if len(history) >= 6:
        old = history[-6]
        added = set(current.evidence)-set(old.evidence)
        lost = set(old.evidence)-set(current.evidence)
        st.write("新增證據：" + ("；".join(sorted(added)) or "無"))
        st.write("消失證據：" + ("；".join(sorted(lost)) or "無") + "（資料不足也可能使證據暫停）")
    with st.expander("指標數值與判斷依據"):
        st.write(f"RSI14 {current.rsi14:.2f}｜MACD柱體 {current.macd_histogram:.4f}")
        st.write("量比 " + ("資料不足" if current.volume_ratio is None else f"{current.volume_ratio:.2f}倍"))
        st.write(current.structure+"；"+current.pattern)
        for item in current.evidence: st.success(item)
        for item in current.pending: st.warning(item)
        st.caption("波段高低點以收盤價左右各3日確認，必須等右側3日結束才可使用；圖上標示發生日及可用日期。雙低間隔至少7日、價差≤12%，中間反彈至少3%，且第二低點之前60日曾自高點回落≥10%。確認需突破頸線、量比≥1.2與TRS≥70；跌回頸線為回測，跌破固定低點為失敗。上述門檻為待回測的模型規則。")
    st.markdown("**K線圖層**")
    toggles = st.columns(4)
    show_ma = toggles[0].checkbox("均線", value=True, key="layer_ma")
    show_levels = toggles[1].checkbox("反折確認價／失敗價", value=True, key="layer_levels")
    show_profile = toggles[2].checkbox("成交密集參考區（日線估算）", value=False, key="layer_profile")
    show_pivots = toggles[3].checkbox("波段高低點標記", value=False, key="layer_pivots")
    profile, full_profile = None, False
    if show_profile:
        options = st.columns(2)
        sessions = options[0].selectbox("成交區計算期間", [60,120], format_func=lambda n: f"{n}日", key="profile_sessions")
        display = options[1].radio("成交區顯示內容", ["主要成交區","完整橫向成交分布"], key="profile_display")
        full_profile = display == "完整橫向成交分布"
        profile, error = estimate_profile(result.get('bars') or [], sessions)
        st.caption("日線估算，非實際持倉或主力成本；將每日成交量均勻分配於當日最低至最高價，共32個價帶（全期同價時為1帶）。主要成交區從最大量價帶向相鄰較大量價帶擴展，直到涵蓋至少70%估算量；同量優先較低價帶。選項不影響TRS。")
        st.caption("未自動還原除權息／分割。大幅價格斷點會暫停估算，但較小公司行動仍可能扭曲分布；參考區不是保證支撐或壓力。")
        if error:
            st.warning(error)
        else:
            st.caption(f"{sessions}日成交區｜{profile['start']}～{profile['end']}｜實際涵蓋估算量 {profile['area_fraction']:.1%}｜本次統計不是各歷史日當時已知區間")
            a,b,c = st.columns(3)
            a.metric("最大量價帶（估算POC）", f"{profile['poc_low']:.2f}～{profile['poc_high']:.2f}元")
            b.metric("主要成交區下緣", f"{profile['lower']:.2f}元", f"距資料日收盤 {profile['lower']/profile['close']-1:+.1%}")
            c.metric("主要成交區上緣", f"{profile['upper']:.2f}元", f"距資料日收盤 {profile['upper']/profile['close']-1:+.1%}")
            position = "上方，下方區域可列為回測觀察" if profile['close'] > profile['upper'] else "下方，上方區域可列為反彈觀察" if profile['close'] < profile['lower'] else "內部，仍位於主要交易區"
            st.info(f"{sessions}日成交區：資料日收盤位於區域{position}；不據此推斷主力吸籌或持有人尚未賣出。")
    frame = pd.DataFrame(result.get("bars") or [])
    frame["date"] = pd.to_datetime(frame["date"])
    for period in (5,10,20,60):
        frame[f"MA{period}"] = frame["close"].rolling(period).mean()
    frame["V20"] = frame["volume"].shift(1).rolling(20).mean()
    frame = frame.tail(120)
    if profile and full_profile:
        fig = make_subplots(rows=2,cols=2,specs=[[{},{}],[{},None]],shared_xaxes=True,
                            shared_yaxes=True,column_widths=[.8,.2],row_heights=[.75,.25],
                            vertical_spacing=.05,horizontal_spacing=.025)
        edges = profile['edges']
        fig.add_trace(go.Bar(x=profile['volumes'],y=[(a+b)/2 for a,b in zip(edges,edges[1:])],
                             width=[max(b-a,.01) for a,b in zip(edges,edges[1:])],orientation="h",
                             name=f"{profile['sessions']}日估算量",marker_color="#80cbc4",
                             hovertemplate="價帶中心 %{y:.2f}<br>估算成交量 %{x:,.0f}<extra></extra>"),row=1,col=2)
        fig.update_xaxes(title_text="估算成交量",row=1,col=2)
    else:
        fig = make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.75,.25],vertical_spacing=.05)
    ohlc = all(k in frame and frame[k].notna().all() for k in ("open","high","low"))
    if ohlc:
        fig.add_trace(go.Candlestick(x=frame.date,open=frame.open,high=frame.high,low=frame.low,close=frame.close,name="K線"),row=1,col=1)
    else:
        fig.add_trace(go.Scatter(x=frame.date,y=frame.close,name="收盤價（OHLC不足）"),row=1,col=1)
    for period in ((5,10,20,60) if show_ma else ()):
        fig.add_trace(go.Scatter(x=frame.date,y=frame[f"MA{period}"],name=f"MA{period}",line_width=1),row=1,col=1)
    for label,day,value,known in (current.pivots if show_pivots else ()):
        fig.add_trace(go.Scatter(x=[day],y=[value],mode="markers",name=label,marker_size=11,
                                text=[f"{label}｜發生 {day}｜可用 {known}"],
                                hovertemplate="%{text}<br>收盤 %{y:.2f}<extra></extra>"),row=1,col=1)
    for name,value in (("確認價",current.confirmation_price),("失敗價",current.failure_price)):
        if show_levels and value is not None:
            fig.add_shape(type="line",x0=current.setup_started,x1=current.date,y0=value,y1=value,line_dash="dash",row=1,col=1)
            fig.add_annotation(x=current.date,y=value,text=name,showarrow=False,xanchor="right",row=1,col=1)
    if profile:
        fig.add_shape(type="rect",x0=profile['start'],x1=profile['end'],y0=profile['lower'],y1=profile['upper'],
                      fillcolor="rgba(0,150,136,.12)",line_width=0,layer="below",row=1,col=1)
        for label,value in (("成交區下緣",profile['lower']),("POC中心",profile['poc']),("成交區上緣",profile['upper'])):
            fig.add_shape(type="line",x0=profile['start'],x1=profile['end'],y0=value,y1=value,
                          line=dict(color="#00897b",dash="dot"),row=1,col=1)
            fig.add_annotation(x=profile['start'],y=value,text=label,showarrow=False,xanchor="left",row=1,col=1)
    fig.add_trace(go.Bar(x=frame.date,y=frame.volume,name="成交量"),row=2,col=1)
    fig.add_trace(go.Scatter(x=frame.date,y=frame.V20,name="前20日均量"),row=2,col=1)
    fig.update_layout(height=600,xaxis_rangeslider_visible=False,legend_orientation="h",margin=dict(l=10,r=10,t=40,b=10),title="價格結構：標記可懸停查看確認日期")
    st.plotly_chart(fig,width="stretch")
    graph = go.Figure(go.Scatter(x=[x.date for x in history],y=[x.score for x in history],connectgaps=False,
                                text=[f"{x.stage}｜資料權重 {x.coverage}/100" for x in history],
                                hovertemplate="%{x}<br>TRS %{y}<br>%{text}<extra></extra>"))
    graph.update_layout(height=280,yaxis_range=[0,100],title="TRS歷史：缺資料留白，階段不由分數區間直接決定")
    st.plotly_chart(graph,width="stretch")
    with st.expander("查看歷史階段、價位及每日構面"):
        st.dataframe(pd.DataFrame([dict(日期=x.date,TRS=x.score,階段=x.stage,確認價=x.confirmation_price,
                                       失敗價=x.failure_price,結構起日=x.setup_started,資料權重=x.coverage,
                                       趨勢=x.trend_score,動能=x.momentum_score,量價=x.volume_score,
                                       相對強弱=x.relative_score,結構=x.structure_score,型態=x.pattern_score)
                                  for x in history]),hide_index=True,width="stretch")
        st.caption("依目前下載資料逐日重算；使用各日之前可取得的價格，不是當時保存的實盤紀錄，也不是已驗證勝率。")
