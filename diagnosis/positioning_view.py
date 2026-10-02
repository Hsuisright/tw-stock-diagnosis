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
        st.caption("資料資格：資料不足，保留 N/A。")
    with st.expander("查看籌碼明細"):
        a, b, c, d = st.columns(4)
        a.metric("融資餘額", "N/A" if snapshot.margin_balance is None else f"{snapshot.margin_balance:,.0f}",
                 None)
        b.metric("融資1日變化", _change(snapshot.margin_change_1d, None))
        c.metric("融資5日變化", _change(snapshot.margin_change_5d, snapshot.margin_change_5d_pct))
        d.metric("融資20日變化", _change(snapshot.margin_change_20d, snapshot.margin_change_20d_pct))
        a, b, c, d = st.columns(4)
        a.metric("融券餘額", "N/A" if snapshot.short_balance is None else f"{snapshot.short_balance:,.0f}",
                 None)
        b.metric("融券1日變化", _change(snapshot.short_change_1d, None))
        c.metric("融券5日變化", _change(snapshot.short_change_5d, snapshot.short_change_5d_pct))
        d.metric("融券20日變化", _change(snapshot.short_change_20d, snapshot.short_change_20d_pct))
        if (snapshot.price_return_5d is not None and snapshot.price_return_20d is not None
                and snapshot.volume_ratio is not None):
            st.caption(f"價格變化：5日 {snapshot.price_return_5d:+.1%}｜20日 {snapshot.price_return_20d:+.1%}｜量比 {snapshot.volume_ratio:.2f}倍")
        if snapshot.missing:
            st.caption("缺少／限制：" + "；".join(snapshot.missing))
        if snapshot.latest_date:
            st.caption(f"籌碼資料日：{snapshot.latest_date}｜來源：{snapshot.source or 'N/A'}｜資料發布：{snapshot.generated_at or 'N/A'}")
