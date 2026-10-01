"""Deterministic, evidence-only V1.5 positioning states.

States describe a balance/price configuration.  They do not attribute a price
move to a specific market participant and are intentionally not a score.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

PRICE_DIRECTION_5D = 0.02
BALANCE_CHANGE_5D = 0.05
VOLUME_EXPANSION = 1.20
REQUIRED_OBSERVATIONS = 21

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
    volume_ratio: float | None
    source: str | None
    generated_at: str | None


def calculate(rows: list[dict], price_return_5d: float | None, volume_ratio: float | None,
              metadata: dict | None = None) -> PositioningSnapshot:
    rows = sorted(rows, key=lambda row: row.get("date", ""))
    missing = []
    margins = [row.get("margin_balance") for row in rows]
    shorts = [row.get("short_balance") for row in rows]
    if len(rows) < REQUIRED_OBSERVATIONS:
        missing.append("至少需21個交易日的融資與融券餘額")
    if any(value is None for value in margins):
        missing.append("margin_balance")
    if any(value is None for value in shorts):
        missing.append("short_balance")
    if price_return_5d is None:
        missing.append("5日價格變化")
    if volume_ratio is None:
        missing.append("成交量比")
    # Securities lending is intentionally not inferred from the transaction
    # dataset: FinMind's public response has transactions, not a stable balance.
    missing.append("securities_lending（公開餘額欄位尚未驗證）")
    margin_1d, margin_5d = _change(margins, 1), _change(margins, 5)
    margin_20d = _change(margins, 20)
    short_1d, short_5d = _change(shorts, 1), _change(shorts, 5)
    short_20d = _change(shorts, 20)
    material_missing = any(item in missing for item in ("至少需21個交易日的融資與融券餘額", "margin_balance", "short_balance", "5日價格變化", "成交量比"))
    evidence = []
    if not material_missing:
        evidence = [f"5日股價變化 {_fmt(price_return_5d)}", f"量比 {volume_ratio:.2f}倍",
                    f"5日融資餘額 {_fmt(margin_5d[1])}", f"5日融券餘額 {_fmt(short_5d[1])}"]
        expanded_volume = volume_ratio >= VOLUME_EXPANSION
        if price_return_5d >= PRICE_DIRECTION_5D and expanded_volume and short_5d[1] <= -BALANCE_CHANGE_5D:
            state = "SHORT_COVERING_COMPATIBLE"
        elif price_return_5d <= -PRICE_DIRECTION_5D and expanded_volume and margin_5d[1] <= -BALANCE_CHANGE_5D:
            state = "LONG_DELEVERAGING_COMPATIBLE"
        elif abs(price_return_5d) >= PRICE_DIRECTION_5D and margin_5d[1] >= BALANCE_CHANGE_5D and short_5d[1] >= BALANCE_CHANGE_5D:
            state = "TWO_SIDED_CROWDING"
        elif price_return_5d >= PRICE_DIRECTION_5D and margin_5d[1] >= BALANCE_CHANGE_5D:
            state = "LONG_CROWDING_BUILDING"
        elif price_return_5d <= -PRICE_DIRECTION_5D and short_5d[1] >= BALANCE_CHANGE_5D:
            state = "SHORT_PRESSURE_BUILDING"
        elif (margin_5d[1] is not None and short_5d[1] is not None
              and margin_5d[1] <= -BALANCE_CHANGE_5D and short_5d[1] <= -BALANCE_CHANGE_5D):
            state = "PRESSURE_RELEASING"
        else:
            state = "NEUTRAL"
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
        price_return_5d, volume_ratio, meta.get("source"), meta.get("generated_at"),
    )
