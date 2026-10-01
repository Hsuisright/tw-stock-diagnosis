"""Small V1.5 presentation component for positioning evidence."""
from __future__ import annotations

import streamlit as st


def _change(value, pct):
    if value is None:
        return "N/A"
    suffix = "" if pct is None else f"（{pct:+.1%}）"
    return f"{value:+,.0f}{suffix}"


def render(snapshot):
    st.subheader("籌碼壓力")
    st.caption("市場部位是否呈現壓力累積、回補或去槓桿結構；不是價格因果證明。")
    st.info(snapshot.state_label)
    for item in snapshot.evidence[:4]:
        st.write("• " + item)
    if snapshot.data_quality != "OK":
        st.caption("資料資格：" + ("有限證據；借券餘額尚未驗證。" if snapshot.data_quality == "LIMITED_EVIDENCE" else "資料不足，保留 N/A。"))
    with st.expander("查看籌碼明細"):
        a, b, c = st.columns(3)
        a.metric("融資餘額", "N/A" if snapshot.margin_balance is None else f"{snapshot.margin_balance:,.0f}",
                 _change(snapshot.margin_change_1d, None))
        b.metric("融資5日變化", _change(snapshot.margin_change_5d, snapshot.margin_change_5d_pct))
        c.metric("融資20日變化", _change(snapshot.margin_change_20d, snapshot.margin_change_20d_pct))
        a, b, c = st.columns(3)
        a.metric("融券餘額", "N/A" if snapshot.short_balance is None else f"{snapshot.short_balance:,.0f}",
                 _change(snapshot.short_change_1d, None))
        b.metric("融券5日變化", _change(snapshot.short_change_5d, snapshot.short_change_5d_pct))
        c.metric("融券20日變化", _change(snapshot.short_change_20d, snapshot.short_change_20d_pct))
        st.caption("借券：資料不足（FinMind 公開資料目前驗證為交易紀錄，未建立可比較的每日餘額）。")
        if snapshot.missing:
            st.caption("缺少／限制：" + "；".join(snapshot.missing))
        if snapshot.latest_date:
            st.caption(f"籌碼資料日：{snapshot.latest_date}｜來源：{snapshot.source or 'N/A'}｜資料發布：{snapshot.generated_at or 'N/A'}")
