from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import fmean


@dataclass(frozen=True)
class ReversalSnapshot:
    date: str
    score: int
    stage: str
    trend_score: int
    momentum_score: int
    volume_score: int
    relative_score: int
    structure_score: int
    pattern_score: int
    rsi14: float | None
    macd_histogram: float | None
    volume_ratio: float | None
    obv_above_ma10: bool | None
    relative_20d: float | None
    relative_60d: float | None
    structure: str
    pattern: str
    confirmation_price: float | None
    failure_price: float | None
    evidence: tuple[str, ...]
    pending: tuple[str, ...]


def _ema(values, period):
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1 - alpha) * out[-1])
    return out


def _rsi(values, period=14):
    if len(values) <= period:
        return [None] * len(values)
    out = [None] * len(values)
    gains = [max(values[i] - values[i - 1], 0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0) for i in range(1, len(values))]
    avg_gain, avg_loss = fmean(gains[:period]), fmean(losses[:period])
    out[period] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def _obv(closes, volumes):
    out = [0.0]
    for i in range(1, len(closes)):
        volume = volumes[i] or 0
        direction = 1 if closes[i] > closes[i - 1] else -1 if closes[i] < closes[i - 1] else 0
        out.append(out[-1] + direction * volume)
    return out


def _pivots(values, left=3, right=3):
    lows, highs = [], []
    for i in range(left, len(values) - right):
        window = values[i - left:i + right + 1]
        if values[i] == min(window): lows.append(i)
        if values[i] == max(window): highs.append(i)
    return lows, highs


def reversal_history(bars, benchmark_bars=None, lookback=120):
    clean = []
    for row in bars:
        try:
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if close <= 0 or not isfinite(close):
            continue
        clean.append({"date": str(row["date"]), "open": float(row.get("open") or close),
                      "high": float(row.get("high") or close), "low": float(row.get("low") or close),
                      "close": close, "volume": float(row.get("volume") or 0)})
    if len(clean) < 65:
        return []
    benchmark = {str(x["date"]): float(x["close"]) for x in (benchmark_bars or [])
                 if x.get("close") not in (None, 0)}
    start = max(64, len(clean) - lookback)
    return [_snapshot(clean[:i + 1], benchmark) for i in range(start, len(clean))]


def _snapshot(bars, benchmark):
    closes = [x["close"] for x in bars]
    volumes = [x["volume"] for x in bars]
    price = closes[-1]
    ma = lambda n: fmean(closes[-n:])
    ma5, ma10, ma20, ma60 = (ma(n) for n in (5, 10, 20, 60))
    prev_ma5, prev_ma10, prev_ma20 = (fmean(closes[-n-5:-5]) for n in (5, 10, 20))
    rsi = _rsi(closes)
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(macd, 9)
    hist = [a - b for a, b in zip(macd, signal)]
    obv = _obv(closes, volumes)
    obv_ma10 = fmean(obv[-10:])
    recent_volume = [v for v in volumes[-21:-1] if v > 0]
    volume_ratio = volumes[-1] / fmean(recent_volume) if volumes[-1] > 0 and recent_volume else None

    trend = (5 if ma5 > ma10 else 0) + (5 if ma5 > prev_ma5 and ma10 > prev_ma10 else 0)
    trend += 5 if price > ma20 else 0
    trend += 5 if ma20 > prev_ma20 else 0
    momentum = (4 if rsi[-1] is not None and rsi[-1] >= 40 else 0)
    momentum += 4 if rsi[-1] is not None and rsi[-6] is not None and rsi[-1] > rsi[-6] else 0
    momentum += 4 if rsi[-1] is not None and rsi[-1] >= 50 else 0
    momentum += 4 if hist[-1] > hist[-2] else 0
    momentum += 4 if hist[-1] > 0 else 0
    volume = (5 if volume_ratio is not None and volume_ratio >= 1.2 else 0)
    volume += 5 if obv[-1] > obv_ma10 else 0
    volume += 5 if obv[-1] > obv[-6] else 0

    aligned = [(x["date"], x["close"] / benchmark[x["date"]]) for x in bars if x["date"] in benchmark]
    rs20 = rs60 = None
    relative = 0
    if len(aligned) >= 61:
        ratios = [x[1] for x in aligned]
        rs20, rs60 = ratios[-1] / ratios[-21] - 1, ratios[-1] / ratios[-61] - 1
        relative = (6 if rs20 > 0 else 0) + (5 if rs60 > 0 else 0)
        relative += 4 if ratios[-1] > fmean(ratios[-20:]) else 0

    window = closes[-65:]
    lows, highs = _pivots(window)
    confirmation = max(closes[-21:-1])
    failure = min(closes[-20:])
    structure_label = "尚未形成明確Higher Low"
    pattern_label = "區間觀察"
    structure = 4 if price > min(closes[-20:-1]) else 0
    pattern_score = 0
    higher_low = False
    if len(lows) >= 2:
        first, second = lows[-2], lows[-1]
        first_price, second_price = window[first], window[second]
        if second - first >= 7:
            higher_low = second_price > first_price
            near_double = abs(second_price / first_price - 1) <= .12
            if higher_low:
                structure += 8; structure_label = "Higher Low成立"
            elif near_double:
                structure += 5; structure_label = "雙低接近，第二低點尚未墊高"
            between = window[first:second + 1]
            confirmation = max(between)
            failure = second_price
            if near_double:
                pattern_label = "潛在W底"; pattern_score += 5
    if len(highs) >= 2 and window[highs[-1]] > window[highs[-2]]:
        structure += 8
        structure_label += "、Higher High成立"
    if price > confirmation:
        pattern_score += 5
        pattern_label = pattern_label.replace("潛在", "已突破") if "潛在" in pattern_label else "突破區間前高"
    structure = min(20, structure)
    score = trend + momentum + volume + relative + structure + pattern_score

    if score < 25: stage = "弱勢延續"
    elif score < 40: stage = "超跌觀察"
    elif score < 55: stage = "初步止跌"
    elif price <= confirmation or not higher_low: stage = "反折形成"
    elif score < 85: stage = "反折確認"
    else: stage = "強勢延伸"

    evidence, pending = [], []
    for passed, yes, no in (
        (ma5 > ma10, "MA5站上MA10", "MA5尚未站上MA10"),
        (price > ma20, "收盤站上MA20", "收盤尚未站上MA20"),
        (rsi[-1] is not None and rsi[-1] > rsi[-6], "RSI14上彎", "RSI14尚未上彎"),
        (hist[-1] > hist[-2], "MACD柱體改善", "MACD柱體尚未改善"),
        (obv[-1] > obv_ma10, "OBV站上10日均線", "OBV尚未站上10日均線"),
        (higher_low, "價格形成Higher Low", "尚未形成Higher Low"),
        (price > confirmation, "收盤突破確認價", "尚未突破確認價"),
    ):
        (evidence if passed else pending).append(yes if passed else no)
    if rs20 is None: pending.append("0050相對強弱資料不足")
    elif rs20 > 0: evidence.append("20日相對0050轉強")
    else: pending.append("20日相對0050仍弱")
    return ReversalSnapshot(bars[-1]["date"], score, stage, trend, momentum, volume, relative,
                            structure, pattern_score, rsi[-1], hist[-1], volume_ratio,
                            obv[-1] > obv_ma10, rs20, rs60, structure_label, pattern_label,
                            confirmation, failure, tuple(evidence), tuple(pending))


def serialize_history(history):
    return [asdict(x) for x in history]

