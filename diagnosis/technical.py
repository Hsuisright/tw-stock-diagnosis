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
