"""Deterministic, evidence-only V1.5 positioning states.

States describe a balance/price configuration.  They do not attribute a price
move to a specific market participant and are intentionally not a score.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

# Rule thresholds are deliberately small, named constants.  They describe a
# repeatable *structure* rather than a forecast or a trading threshold.
PRICE_DIRECTION_5D = 0.02
BALANCE_CHANGE_5D = 0.05
VOLUME_EXPANSION = 1.20
REQUIRED_OBSERVATIONS = 6

# Volume confirmation is part of the published rule specification only for
# these two states.  The remaining states describe position/price structure
# and intentionally do not require expanded volume.
VOLUME_CONFIRMATION_REQUIRED = frozenset({
    "SHORT_COVERING_COMPATIBLE",
    "LONG_DELEVERAGING_COMPATIBLE",
})

# State precedence is intentional, deterministic, and tested.  A snapshot
# meeting more than one condition uses the first compatible state below:
# short covering -> long deleveraging -> two-sided crowding -> long crowding
# -> short pressure -> pressure releasing -> neutral.

STATE_LABELS = {
    "NEUTRAL": "無明確籌碼壓力",
    "SHORT_PRESSURE_BUILDING": "空方壓力累積",
    "SHORT_COVERING_COMPATIBLE": "空方回補結構",
    "LONG_CROWDING_BUILDING": "多方擁擠累積",
    "LONG_DELEVERAGING_COMPATIBLE": "多方去槓桿結構",
    "TWO_SIDED_CROWDING": "多空雙向擁擠",
    "PRESSURE_RELEASING": "籌碼壓力釋放",
    "INSUFFICIENT_DATA": "資料不足",
}


def _change(values, periods):
    if len(values) <= periods or values[-1] is None or values[-periods - 1] is None:
        return None, None
    old, latest = values[-periods - 1], values[-1]
    delta = latest - old
    return delta, (delta / old if old else None)


def _fmt(value):
    return "N/A" if value is None else f"{value:+.1%}"


@dataclass(frozen=True)
class PositioningSnapshot:
    state: str
    state_label: str
    evidence: tuple[str, ...]
    missing: tuple[str, ...]
    data_quality: str
    latest_date: str | None
    margin_balance: float | None
    short_balance: float | None
    margin_change_1d: float | None
    margin_change_5d: float | None
    margin_change_20d: float | None
    margin_change_5d_pct: float | None
    margin_change_20d_pct: float | None
    short_change_1d: float | None
    short_change_5d: float | None
    short_change_20d: float | None
    short_change_5d_pct: float | None
    short_change_20d_pct: float | None
    price_return_5d: float | None
    price_return_20d: float | None
    volume_ratio: float | None
    source: str | None
    generated_at: str | None


def calculate(rows: list[dict], price_return_5d: float | None, volume_ratio: float | None,
              metadata: dict | None = None, price_return_20d: float | None = None) -> PositioningSnapshot:
    rows = sorted(rows, key=lambda row: row.get("date", ""))
    missing = []
    margins = [row.get("margin_balance") for row in rows]
    shorts = [row.get("short_balance") for row in rows]
    if len(rows) < REQUIRED_OBSERVATIONS:
        missing.append("至少需6個交易日的融資與融券餘額")
    if price_return_5d is None:
        missing.append("5日價格變化")
    if volume_ratio is None:
        missing.append("成交量比")
    margin_1d, margin_5d = _change(margins, 1), _change(margins, 5)
    margin_20d = _change(margins, 20)
    short_1d, short_5d = _change(shorts, 1), _change(shorts, 5)
    short_20d = _change(shorts, 20)
    if margin_20d[0] is None or short_20d[0] is None:
        missing.append("20日融資／融券變化")
    material_missing = (margin_5d[0] is None or short_5d[0] is None
                        or any(item in missing for item in ("至少需6個交易日的融資與融券餘額", "5日價格變化", "成交量比")))
    evidence = []
    if not material_missing:
        common_evidence = [
            f"5日股價變化 {_fmt(price_return_5d)}",
            f"量比 {volume_ratio:.2f}倍",
            f"5日融資餘額 {_fmt(margin_5d[1])}",
            f"5日融券餘額 {_fmt(short_5d[1])}",
        ]
        expanded_volume = volume_ratio >= VOLUME_EXPANSION
        # Keep this ordering aligned with the precedence specification above.
        # Only SHORT_COVERING_COMPATIBLE and LONG_DELEVERAGING_COMPATIBLE use
        # expanded_volume as a required confirmation condition.
        if price_return_5d >= PRICE_DIRECTION_5D and expanded_volume and short_5d[1] <= -BALANCE_CHANGE_5D:
            state = "SHORT_COVERING_COMPATIBLE"
            evidence = [common_evidence[0], common_evidence[3], common_evidence[1],
                        "價格走強期間伴隨融券部位下降，結構與空方回補相符。"]
        elif price_return_5d <= -PRICE_DIRECTION_5D and expanded_volume and margin_5d[1] <= -BALANCE_CHANGE_5D:
            state = "LONG_DELEVERAGING_COMPATIBLE"
            evidence = [common_evidence[0], common_evidence[2], common_evidence[1],
                        "價格走弱期間伴隨融資部位下降，結構與多方去槓桿相符。"]
        elif abs(price_return_5d) >= PRICE_DIRECTION_5D and margin_5d[1] >= BALANCE_CHANGE_5D and short_5d[1] >= BALANCE_CHANGE_5D:
            state = "TWO_SIDED_CROWDING"
            evidence = [common_evidence[0], common_evidence[2], common_evidence[3],
                        "融資與融券部位同步增加，呈現多空雙向擁擠結構。"]
        elif price_return_5d >= PRICE_DIRECTION_5D and margin_5d[1] >= BALANCE_CHANGE_5D:
            state = "LONG_CROWDING_BUILDING"
            evidence = [common_evidence[0], common_evidence[2], common_evidence[1],
                        "價格走強期間融資部位增加，結構與多方擁擠累積相符。"]
        elif price_return_5d <= -PRICE_DIRECTION_5D and short_5d[1] >= BALANCE_CHANGE_5D:
            state = "SHORT_PRESSURE_BUILDING"
            evidence = [common_evidence[0], common_evidence[3], common_evidence[1],
                        "價格走弱期間融券部位增加，結構與空方壓力累積相符。"]
        elif (margin_5d[1] is not None and short_5d[1] is not None
              and margin_5d[1] <= -BALANCE_CHANGE_5D and short_5d[1] <= -BALANCE_CHANGE_5D):
            state = "PRESSURE_RELEASING"
            evidence = [common_evidence[2], common_evidence[3], common_evidence[0],
                        "融資與融券部位同步下降，呈現籌碼壓力釋放結構。"]
        else:
            state = "NEUTRAL"
            evidence = [common_evidence[0], common_evidence[1], common_evidence[2],
                        "目前未見符合既定規則的單一籌碼壓力結構。"]
    else:
        state = "INSUFFICIENT_DATA"
        evidence = ["融資／融券、價格或量能資料不足，未推定籌碼狀態。"]
    meta = metadata or {}
    return PositioningSnapshot(
        state, STATE_LABELS[state], tuple(evidence), tuple(missing),
        "LIMITED_EVIDENCE" if state != "INSUFFICIENT_DATA" and missing else "OK" if state != "INSUFFICIENT_DATA" else "INSUFFICIENT",
        rows[-1].get("date") if rows else None,
        margins[-1] if margins else None, shorts[-1] if shorts else None,
        margin_1d[0], margin_5d[0], margin_20d[0], margin_5d[1], margin_20d[1],
        short_1d[0], short_5d[0], short_20d[0], short_5d[1], short_20d[1],
        price_return_5d, price_return_20d, volume_ratio, meta.get("source"), meta.get("generated_at"),
    )
