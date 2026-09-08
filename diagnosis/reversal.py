from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import fmean


@dataclass(frozen=True)
class ReversalSnapshot:
    date: str
    score: int | None
    stage: str
    trend_score: int
    momentum_score: int
    volume_score: int | None
    relative_score: int | None
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
    coverage: int = 100
    warnings: tuple[str, ...] = ()
    pivots: tuple = ()
    setup_id: str | None = None
    setup_started: str | None = None
    confirmed: bool = False
    model_version: str = "TRS-2.0"
    retired_setup_id: str | None = None


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
    out[period] = (50 if avg_gain == 0 else 100) if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = (50 if avg_gain == 0 else 100) if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
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
        if values[i] == min(window) and window.count(values[i]) == 1: lows.append(i)
        if values[i] == max(window) and window.count(values[i]) == 1: highs.append(i)
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
        if not row.get("date"):
            continue
        clean.append({"date": str(row["date"]), "open": float(row.get("open") or close),
                      "high": float(row.get("high") or close), "low": float(row.get("low") or close),
                      "close": close, "volume": float(row.get("volume") or 0)})
    clean = sorted({x['date']: x for x in clean}.values(), key=lambda x: x['date'])
    if len(clean) < 65:
        return []
    benchmark = {}
    for row in benchmark_bars or []:
        try:
            value = float(row['close'])
            if row.get('date') and isfinite(value) and value > 0:
                benchmark[str(row['date'])] = value
        except (KeyError, ValueError, TypeError):
            continue
    start = max(64, len(clean) - lookback)
    history = []
    previous = None
    # Replay from warmup, so changing display length cannot change active setup.
    for i in range(64, len(clean)):
        previous = _snapshot(clean[:i + 1], benchmark, previous)
        if i >= start:
            history.append(previous)
    return history


def _snapshot(bars, benchmark, previous=None):
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
    volume_ok = all(isfinite(v) and v > 0 for v in volumes[-61:])
    relative_ok = all(x['date'] in benchmark for x in bars[-61:])
    if relative_ok:
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
    pivots = ()
    setup_id = None
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
            if near_double and confirmation >= max(first_price, second_price) * 1.03:
                pattern_label = "潛在W底"; pattern_score += 5
                neck = first + between.index(max(between))
                offset = len(bars) - 65
                pivots = tuple((label, bars[offset+j]['date'], window[j], bars[offset+j+3]['date'])
                               for label, j in (("第一低點", first), ("頸線", neck), ("第二低點", second)))
                setup_id = bars[offset+second]['date']
    if len(highs) >= 2 and window[highs[-1]] > window[highs[-2]]:
        structure += 8
        structure_label += "、Higher High成立"
    if price > confirmation:
        pattern_score += 5
        pattern_label = pattern_label.replace("潛在", "已突破") if "潛在" in pattern_label else "突破區間前高"
    structure = min(20, structure)
    score = trend + momentum + volume + relative + structure + pattern_score

    warnings = []
    if not volume_ok: warnings.append("近61日成交量不完整，量價暫不評分")
    if not relative_ok: warnings.append("0050未完整對齊近61個交易日，相對強弱暫不評分")
    discontinuity = any(abs(closes[j]/closes[j-1]-1) > .25 for j in range(max(1,len(closes)-60),len(closes)))
    if discontinuity: warnings.append("近60日有超過25%的單日價格變動，需核對分割、除權息或異常行情")
    benchmark_jump = relative_ok and any(abs(benchmark[bars[j]['date']]/benchmark[bars[j-1]['date']]-1) > .25 for j in range(len(bars)-60,len(bars)))
    if benchmark_jump:
        relative_ok = False
        warnings.append("0050存在價格斷點，相對強弱暫不評分")
    volume = volume if volume_ok else None
    relative = relative if relative_ok else None
    coverage = 70 + (15 if volume_ok else 0) + (15 if relative_ok else 0)
    if discontinuity: coverage = 0
    score = trend + momentum + (volume or 0) + (relative or 0) + structure + pattern_score if coverage == 100 else None
    # Weakness must precede the second low; an established uptrend is not a reversal.
    weak_background = False
    if pivots:
        second_index = next(j for j,x in enumerate(bars) if x['date'] == setup_id)
        prior = closes[max(0,second_index-60):second_index+1]
        peak = prior[0]
        for value in prior[1:]:
            peak = max(peak, value)
            if value / peak - 1 <= -.10:
                weak_background = True
    retired = previous.retired_setup_id if previous else None
    if setup_id and retired and setup_id <= retired:
        weak_background = False
    active = previous and previous.setup_id and previous.stage not in ("反折失敗", "觀察到期")
    started = bars[-1]['date'] if setup_id and weak_background else None
    confirmed = False
    if active:
        setup_id, pivots = previous.setup_id, previous.pivots
        confirmation, failure = previous.confirmation_price, previous.failure_price
        started, confirmed = previous.setup_started, previous.confirmed
        weak_background = True
    elif not weak_background:
        setup_id, pivots, started = None, (), None
        confirmation = failure = None
    higher_low = bool(pivots and pivots[2][2] > pivots[0][2] and price >= failure)
    structure_label = "Higher Low仍有效" if higher_low else "雙低觀察" if setup_id else "尚無有效底部結構"
    structure = (4 if price > min(closes[-20:-1]) else 0) + (8 if higher_low else 0)
    higher_high = len(highs) >= 2 and window[highs[-1]] > window[highs[-2]]
    if higher_high:
        structure += 8
        structure_label += "、Higher High成立"
    pattern_score = (5 if setup_id and price >= failure else 0) + (5 if confirmation is not None and price > confirmation else 0)
    score = trend + momentum + (volume or 0) + (relative or 0) + structure + pattern_score if coverage == 100 else None
    age = sum(x['date'] >= started for x in bars) if started else 0
    if discontinuity:
        stage = "價格待核對"
        confirmation = failure = None
        setup_id, pivots, started, confirmed = None, (), None, False
    elif setup_id and price < failure:
        stage = "反折失敗"
        retired = setup_id
    elif setup_id and age > 60:
        stage = "觀察到期"
        retired = setup_id
    elif coverage < 100:
        stage = "資料待補"
    elif setup_id:
        if price > confirmation and volume_ratio is not None and volume_ratio >= 1.2 and score >= 70:
            confirmed = True
        if confirmed:
            stage = "回測中" if price <= confirmation else "強勢延伸" if score >= 85 else "反折確認"
        else:
            stage = "反折形成"
    elif rsi[-1] <= 30 and price/ma20-1 <= -.05:
        stage = "超跌觀察"
    elif price < ma60 and min(closes[-5:]) >= min(closes[-20:-5]) and hist[-1] > hist[-2]:
        stage = "初步止跌"
    elif price > ma60 and ma20 > prev_ma20:
        stage = "既有多頭"
    elif price < ma60 and ma20 < prev_ma20:
        stage = "弱勢延續"
    else:
        stage = "盤整觀察"

    evidence, pending = [], []
    for passed, yes, no in (
        (ma5 > ma10, "MA5站上MA10", "MA5尚未站上MA10"),
        (price > ma20, "收盤站上MA20", "收盤尚未站上MA20"),
        (rsi[-1] is not None and rsi[-1] > rsi[-6], "RSI14上彎", "RSI14尚未上彎"),
        (hist[-1] > hist[-2], "MACD柱體改善", "MACD柱體尚未改善"),
        (obv[-1] > obv_ma10, "OBV站上10日均線", "OBV尚未站上10日均線"),
        (higher_low, "價格形成Higher Low", "尚未形成Higher Low"),
        (confirmation is not None and price > confirmation, "收盤突破確認價", "尚未突破有效確認價"),
    ):
        (evidence if passed else pending).append(yes if passed else no)
    if not relative_ok: pending.append("0050相對強弱資料不足或價格待核對")
    elif rs20 > 0: evidence.append("20日相對0050轉強")
    else: pending.append("20日相對0050仍弱")
    if not volume_ok:
        evidence = [x for x in evidence if not x.startswith('OBV')]
        pending = [x for x in pending if not x.startswith('OBV')]
        pending.append("成交量不足，OBV暫不判讀")
    if not setup_id: pending.append("尚無具弱勢背景的有效雙低結構，暫不提供型態價位")
    if confirmed and stage == "回測中": pending.append("已跌回確認價，仍在失敗價上方")
    if stage == "反折失敗": pending.append("收盤跌破本次固定失敗價，結構失效")
    pattern_label = "已確認雙低突破" if confirmed else "雙低結構觀察" if setup_id else "尚無有效底部型態"
    return ReversalSnapshot(bars[-1]["date"], score, stage, trend, momentum, volume, relative,
                            structure, pattern_score, rsi[-1], hist[-1], volume_ratio,
                            obv[-1] > obv_ma10 if volume_ok else None,
                            rs20 if relative_ok else None, rs60 if relative_ok else None, structure_label, pattern_label,
                            confirmation, failure, tuple(evidence), tuple(pending), coverage,
                            tuple(warnings), pivots, setup_id, started, confirmed,
                            retired_setup_id=retired)


def serialize_history(history):
    return [asdict(x) for x in history]


def explain_change(history, days=5):
    if len(history) <= days:
        return [], "歷史不足，尚不能比較"
    old, new = history[-days-1], history[-1]
    rows = []
    for label, key in (("趨勢","trend_score"),("動能","momentum_score"),("量價","volume_score"),
                       ("相對強弱","relative_score"),("結構","structure_score"),("型態","pattern_score")):
        a, b = getattr(old,key), getattr(new,key)
        rows.append({"構面":label,"前值":a,"目前":b,"變化":None if a is None or b is None else b-a})
    note = f"{old.date} → {new.date}；{old.stage} → {new.stage}"
    if old.score is None or new.score is None:
        note += "；資料涵蓋不足，總分變化不可比較"
    else:
        note += f"；總分 {new.score-old.score:+d}"
    if old.setup_id != new.setup_id:
        note += "；觀察結構已更換，關鍵價位請重新核對"
    return rows, note
