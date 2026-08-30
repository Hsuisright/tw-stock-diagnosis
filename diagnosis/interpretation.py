from __future__ import annotations


def build_interpretation(result):
    """用可追溯的固定規則，產生短、中、長期綜合判讀。"""
    technical = result.get("technical")
    bollinger = result.get("bollinger")
    valuation_available = bool(result.get("valuation_available"))

    if technical:
        bullish = len(technical.bullish_evidence)
        bearish = len(technical.bearish_evidence)
        if bullish >= bearish + 2:
            technical_tone = "技術結構偏多"
        elif bearish >= bullish + 2:
            technical_tone = "技術結構偏弱"
        else:
            technical_tone = "技術訊號多空交錯"
    else:
        technical_tone = "技術資料尚不足"

    if valuation_available:
        temperature = float(result.get("valuation_temperature", 50))
        if temperature >= 80:
            valuation_tone = "估值位於歷史偏高區"
        elif temperature <= 20:
            valuation_tone = "估值位於歷史偏低區"
        else:
            valuation_tone = "估值位於歷史中間區間"
    else:
        valuation_tone = "目前缺少足夠的有效P/E資料"

    overall = f"{valuation_tone}，{technical_tone}。"

    short_parts = []
    if technical:
        short_parts.append(f"目前為{technical.short_state}、{technical.pattern_state}")
        if technical.momentum20 is not None:
            short_parts.append(f"20日動能{technical.momentum20:+.1%}")
        if technical.volume_ratio is not None:
            short_parts.append(f"量比{technical.volume_ratio:.2f}倍")
        if technical.volatility60 is not None and technical.volatility60 >= 0.5:
            short_parts.append("波動偏高，需控制追價與停損風險")
    if bollinger and bollinger.percent_b >= 80:
        short_parts.append("價格接近或突破布林上軌，留意過熱回檔")
    elif bollinger and bollinger.percent_b <= 20:
        short_parts.append("價格接近或跌破布林下軌，先確認是否止跌")
    short_term = "；".join(short_parts) + "。" if short_parts else "短期資料不足，暫不形成方向判斷。"

    medium_parts = []
    if technical:
        medium_parts.append(f"60日結構為{technical.medium_state}")
        if technical.momentum60 is not None:
            medium_parts.append(f"60日動能{technical.momentum60:+.1%}")
    if valuation_available:
        growth = result.get("growth")
        if growth and growth.required_growth_1y > 0:
            medium_parts.append(f"需觀察EPS能否達到1年{growth.required_growth_1y:.1%}的隱含成長要求")
        elif growth:
            medium_parts.append("現有EPS對正常P/E參考價仍具估值緩衝，但不代表未來獲利不會下降")
    medium_term = "；".join(medium_parts) + "。" if medium_parts else "中期應等待趨勢與獲利資料更完整後再判斷。"

    long_parts = []
    if technical:
        long_parts.append(f"長期價格結構為{technical.long_state}")
    if valuation_available:
        growth = result.get("growth")
        if growth and growth.required_cagr_3y > 0:
            long_parts.append(f"目前股價隱含3年年化EPS成長約{growth.required_cagr_3y:.1%}")
        long_parts.append("需持續核對EPS、ROE、現金流與產業循環是否支持目前估值")
    else:
        long_parts.append("因P/E資料不足，應改以獲利、現金流與適用的替代估值交叉確認")
    long_term = "；".join(long_parts) + "。"

    return {"overall": overall, "short_term": short_term,
            "medium_term": medium_term, "long_term": long_term}
