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


def build_opportunity_risk(result):
    """以現有市場資料產生定性機會—風險矩陣，不假設精確成功率。"""
    technical = result.get("technical")
    growth = result.get("growth")
    valuation_available = bool(result.get("valuation_available"))
    if valuation_available and result.get("current_eps", 0) > 0:
        sample_count = getattr(growth, "sample_count", 0) if growth else 0
        certainty = "中高" if sample_count >= 12 else "中"
        certainty_reason = "目前EPS為正，且具備可比較的歷史P/E與EPS樣本"
    else:
        certainty = "偏低／待驗證"
        certainty_reason = "目前缺少有效P/E，常見原因是近四季EPS非正數或資料不足"
    if growth and growth.required_growth_1y <= 0:
        elasticity = "中"
        elasticity_reason = "現有EPS對正常P/E參考價仍有緩衝，股價未要求額外成長"
    elif growth and growth.historical_median is not None:
        if growth.required_cagr_3y <= growth.historical_median:
            elasticity = "中高"
            elasticity_reason = "三年隱含成長要求未高於歷史EPS成長中位數"
        else:
            elasticity = "高期待／低容錯"
            elasticity_reason = "股價要求的成長高於歷史EPS成長中位數，上行依賴持續超預期"
    else:
        elasticity = "高但未驗證" if technical and "偏多" in technical.medium_state else "待驗證"
        elasticity_reason = "缺少正EPS估值基準，只能確認價格趨勢，無法驗證獲利上行空間"
    if valuation_available:
        temperature = float(result.get("valuation_temperature", 50))
        valuation_risk = "高" if temperature >= 80 else "中高" if temperature >= 60 else "偏低" if temperature <= 20 else "中"
        valuation_reason = f"目前P/E位於近年歷史約第{temperature:.0f}百分位"
    else:
        valuation_risk = "高／不可量化"
        valuation_reason = "負EPS或P/E資料不足，無法用傳統本益比建立估值安全邊際"
    volatility = technical.volatility60 if technical else None
    percent_b = result.get("bollinger").percent_b if result.get("bollinger") else None
    if volatility is None:
        price_risk = "待驗證"; price_reason = "價格樣本不足"
    elif volatility >= .5 or (percent_b is not None and (percent_b >= 90 or percent_b <= 10)):
        price_risk = "高"
        price_reason = f"60日年化波動率約{volatility:.1%}" + ("，且價格接近通道極端" if percent_b is not None and (percent_b >= 90 or percent_b <= 10) else "")
    elif volatility >= .3 or (percent_b is not None and (percent_b >= 80 or percent_b <= 20)):
        price_risk = "中高"; price_reason = f"60日年化波動率約{volatility:.1%}，價格位階亦需留意"
    else:
        price_risk = "中低"; price_reason = f"60日年化波動率約{volatility:.1%}，價格未處通道極端"
    if not valuation_available:
        category = "轉機／選擇權型"
    elif valuation_risk == "高" and certainty in ("中高", "中"):
        category = "高成長、高估值型"
    elif certainty == "中高" and valuation_risk in ("偏低", "中"):
        category = "基本面相對穩健型"
    else:
        category = "等待更多確認"
    return {"certainty": certainty, "certainty_reason": certainty_reason,
            "elasticity": elasticity, "elasticity_reason": elasticity_reason,
            "valuation_risk": valuation_risk, "valuation_reason": valuation_reason,
            "price_risk": price_risk, "price_reason": price_reason, "category": category}
