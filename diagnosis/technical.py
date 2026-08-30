from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import fmean, pstdev


@dataclass(frozen=True)
class BollingerSnapshot:
    price: float
    middle: float
    upper: float
    lower: float
    percent_b: float
    temperature: float
    bandwidth: float
    ma_slope: float | None


@dataclass(frozen=True)
class TechnicalDiagnostic:
    price: float
    short_state: str
    medium_state: str
    long_state: str
    pattern_state: str
    volume_state: str
    risk_state: str
    ma20: float | None
    ma60: float | None
    ma120: float | None
    ma240: float | None
    momentum20: float | None
    momentum60: float | None
    momentum120: float | None
    volume_ratio: float | None
    volatility60: float | None
    range20_high: float | None
    range20_low: float | None
    range60_high: float | None
    range60_low: float | None
    bullish_evidence: tuple[str, ...]
    bearish_evidence: tuple[str, ...]
    neutral_evidence: tuple[str, ...]
    summary: str


def bollinger_snapshot(closes, period: int = 20, deviations: float = 2.0):
    values = [float(x) for x in closes if x is not None and isfinite(float(x)) and float(x) > 0]
    if period < 2 or deviations <= 0 or len(values) < period:
        return None
    window = values[-period:]
    middle = fmean(window)
    sigma = pstdev(window)
    upper = middle + deviations * sigma
    lower = middle - deviations * sigma
    span = upper - lower
    percent_b = 50.0 if span == 0 else (values[-1] - lower) / span * 100
    previous_middle = fmean(values[-period-1:-1]) if len(values) >= period + 1 else None
    slope = ((middle / previous_middle) - 1) * 100 if previous_middle else None
    return BollingerSnapshot(
        price=values[-1], middle=middle, upper=upper, lower=lower,
        percent_b=percent_b, temperature=max(0.0, min(100.0, percent_b)),
        bandwidth=(span / middle * 100 if middle else 0.0), ma_slope=slope,
    )


def price_position_label(percent_b: float) -> str:
    if percent_b > 100: return "突破上軌"
    if percent_b >= 80: return "接近上軌"
    if percent_b >= 60: return "偏強"
    if percent_b >= 40: return "中性"
    if percent_b >= 20: return "偏弱"
    if percent_b >= 0: return "接近下軌"
    return "跌破下軌"


def trend_label(slope: float | None) -> str:
    if slope is None: return "趨勢資料不足"
    if slope > 0.15: return "均線上升"
    if slope < -0.15: return "均線下降"
    return "均線走平"


def technical_diagnostic(bars):
    clean=[]
    for row in bars:
        try:
            close=float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isfinite(close) or close <= 0:
            continue
        volume=row.get("volume") if isinstance(row,dict) else row["volume"]
        clean.append({"close":close,"volume":float(volume) if volume not in (None,"") else None})
    if len(clean) < 20:
        return None

    closes=[x["close"] for x in clean]
    price=closes[-1]
    def ma(n): return fmean(closes[-n:]) if len(closes)>=n else None
    def momentum(n): return price/closes[-n-1]-1 if len(closes)>n else None
    def slope(n,lag=5):
        if len(closes)<n+lag:return None
        return ma(n)/fmean(closes[-n-lag:-lag])-1
    def prior_range(n):
        if len(closes)<=n:return None,None
        prior=closes[-n-1:-1]
        return max(prior),min(prior)

    ma20,ma60,ma120,ma240=(ma(n) for n in (20,60,120,240))
    m20,m60,m120=(momentum(n) for n in (20,60,120))
    h20,l20=prior_range(20); h60,l60=prior_range(60)
    s20,s60,s120,s240=(slope(n) for n in (20,60,120,240))

    def state_for(avg,slp,positive="偏多",negative="偏空"):
        if avg is None or slp is None:return "資料不足"
        if price>avg and slp>0:return positive
        if price<avg and slp<0:return negative
        return "整理／轉折"
    short_state=state_for(ma20,s20,"短線偏多","短線偏空")
    medium_state=state_for(ma60,s60,"中期偏多","中期偏空")
    long_avg=ma240 if ma240 is not None else ma120
    long_slope=s240 if ma240 is not None else s120
    long_state=state_for(long_avg,long_slope,"長期偏多","長期偏空")

    recent_volumes=[x["volume"] for x in clean[-21:-1] if x["volume"] is not None and x["volume"]>0]
    latest_volume=clean[-1]["volume"]
    volume_ratio=(latest_volume/fmean(recent_volumes)) if latest_volume and recent_volumes else None
    if volume_ratio is None: volume_state="成交量資料不足"
    elif volume_ratio>=1.5: volume_state="明顯放量"
    elif volume_ratio>=1.2: volume_state="溫和放量"
    elif volume_ratio<0.7: volume_state="量能偏低"
    else: volume_state="量能一般"

    daily_returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    volatility60=pstdev(daily_returns[-60:])*(252**0.5) if len(daily_returns)>=60 else None
    if volatility60 is None:risk_state="風險資料不足"
    elif volatility60>=0.5:risk_state="波動風險高"
    elif volatility60>=0.3:risk_state="波動風險中等"
    else:risk_state="波動風險較低"

    boll=bollinger_snapshot(closes)
    if h60 is not None and price>h60:
        pattern_state="放量突破60日區間" if volume_ratio is not None and volume_ratio>=1.2 else "突破60日區間，量能待確認"
    elif l60 is not None and price<l60:
        pattern_state="跌破60日區間"
    elif boll and boll.bandwidth<10:
        pattern_state="波動收斂整理"
    elif h20 is not None and l20 is not None:
        location=(price-l20)/(h20-l20) if h20>l20 else .5
        pattern_state="區間上緣整理" if location>=.75 else "區間下緣整理" if location<=.25 else "區間整理"
    else:pattern_state="型態資料不足"

    bullish=[];bearish=[];neutral=[]
    if ma20 is not None:
        (bullish if price>ma20 else bearish).append(f"股價{'站上' if price>ma20 else '低於'}20日均線")
    if ma60 is not None:
        (bullish if price>ma60 else bearish).append(f"股價{'站上' if price>ma60 else '低於'}60日均線")
    if ma240 is not None:
        (bullish if price>ma240 else bearish).append(f"股價{'站上' if price>ma240 else '低於'}240日均線")
    if m20 is not None:
        (bullish if m20>0 else bearish).append(f"20日動能{'轉正' if m20>0 else '為負'}（{m20:+.1%}）")
    if m60 is not None:
        (bullish if m60>0 else bearish).append(f"60日動能{'為正' if m60>0 else '為負'}（{m60:+.1%}）")
    if "突破" in pattern_state and "待確認" not in pattern_state:bullish.append(pattern_state)
    elif "跌破" in pattern_state:bearish.append(pattern_state)
    else:neutral.append(pattern_state)
    if volume_ratio is None:neutral.append("成交量資料不足")
    elif volume_ratio<.7:bearish.append(f"量比僅{volume_ratio:.2f}倍，量能尚未確認")
    elif volume_ratio>=1.2:bullish.append(f"量比{volume_ratio:.2f}倍，成交量支持")
    else:neutral.append(f"量比{volume_ratio:.2f}倍，量能一般")
    if volatility60 is not None and volatility60>=.5:bearish.append(f"60日年化波動率{volatility60:.1%}，風險偏高")

    summary=f"{medium_state}，{short_state}；目前為{pattern_state}，{volume_state}。"
    return TechnicalDiagnostic(price,short_state,medium_state,long_state,pattern_state,volume_state,risk_state,
        ma20,ma60,ma120,ma240,m20,m60,m120,volume_ratio,volatility60,h20,l20,h60,l60,
        tuple(bullish),tuple(bearish),tuple(neutral),summary)
