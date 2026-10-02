"""Official TWSE/TPEx margin-position data adapter; no imputation or live UI fetch."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterable
import urllib.parse

import requests

FIELDS = ("ticker", "date", "market", "margin_buy", "margin_sell", "margin_cash_repayment",
          "margin_balance", "short_sell", "short_buy", "short_stock_repayment", "short_balance", "source")
TWSE_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TPEX_URL = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"


def _num(value):
    text = str(value or "").strip().replace(",", "")
    return float(text) if text else None


def normalize_twse(payload: dict, day: str) -> list[dict]:
    tables = payload.get("tables", [])
    rows = tables[1].get("data", []) if len(tables) > 1 else []
    return [{"ticker": str(r[0]).strip(), "date": day, "market": "TWSE", "margin_buy": _num(r[2]),
             "margin_sell": _num(r[3]), "margin_cash_repayment": _num(r[4]), "margin_balance": _num(r[5]),
             "short_sell": _num(r[8]), "short_buy": _num(r[9]), "short_stock_repayment": _num(r[10]),
             "short_balance": _num(r[11]), "source": "TWSE"}
            for r in rows if len(r) >= 14 and str(r[0]).strip()]


def normalize_tpex(content: bytes, day: str) -> list[dict]:
    rows = csv.reader(StringIO(content.decode("cp950", errors="replace")))
    output = []
    for r in rows:
        if len(r) < 15 or not str(r[0]).strip() or not str(r[0]).strip()[0].isdigit():
            continue
        output.append({"ticker": str(r[0]).strip(), "date": day, "market": "TPEx", "margin_buy": _num(r[2]),
                       "margin_sell": _num(r[3]), "margin_cash_repayment": _num(r[4]), "margin_balance": _num(r[5]),
                       "short_sell": _num(r[11]), "short_buy": _num(r[12]), "short_stock_repayment": _num(r[13]),
                       "short_balance": _num(r[14]), "source": "TPEx"})
    return output


def fetch_day(day: date) -> tuple[list[dict], bool, bool]:
    iso = day.isoformat(); rows = []
    twse_ok = tpex_ok = False
    try:
        q = urllib.parse.urlencode({"date": day.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"})
        response = requests.get(f"{TWSE_URL}?{q}", timeout=30); response.raise_for_status()
        rows.extend(normalize_twse(response.json(), iso)); twse_ok = True
    except requests.RequestException: pass
    try:
        roc = f"{day.year - 1911:03d}/{day.month:02d}/{day.day:02d}"
        q = urllib.parse.urlencode({"l": "zh-tw", "o": "csv", "d": roc})
        response = requests.get(f"{TPEX_URL}?{q}", timeout=30); response.raise_for_status()
        rows.extend(normalize_tpex(response.content, iso)); tpex_ok = True
    except requests.RequestException: pass
    return rows, twse_ok, tpex_ok


def validate(rows: Iterable[dict]) -> list[dict]:
    seen, valid = set(), []
    for row in sorted(rows, key=lambda r: (r["date"], r["market"], r["ticker"])):
        if tuple(row) != FIELDS or not row["ticker"] or not row["date"] or row["market"] not in {"TWSE", "TPEx"}:
            continue
        row = {**row, **{field: _num(row[field]) for field in FIELDS[3:11]}}
        key = (row["ticker"], row["date"], row["market"])
        if key in seen: continue
        seen.add(key); valid.append(row)
    return valid


def load(path: Path) -> list[dict]:
    if not path.exists(): return []
    with path.open(encoding="utf-8", newline="") as f:
        return validate(list(csv.DictReader(f)))


def save(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(validate(rows))


def status(rows: list[dict], ticker: str, complete_markets: bool) -> str:
    if any(r["ticker"] == str(ticker) for r in rows): return "AVAILABLE"
    return "NOT_MARGIN_ELIGIBLE" if complete_markets else "DATA_GAP"


def read_for_streamlit(path: Path, ticker: str) -> list[dict]:
    """Return canonical existing-card names only; no fill or classification."""
    return [{**r, "short_cash_repayment": r["short_stock_repayment"]}
            for r in load(path) if r["ticker"] == str(ticker)]


def required_dates(existing: list[dict], sessions: int = 60) -> list[date]:
    have = {r["date"] for r in existing}; cursor = date.today(); needed = []
    while len(needed) < sessions:
        if cursor.weekday() < 5 and cursor.isoformat() not in have: needed.append(cursor)
        cursor -= timedelta(days=1)
    return needed
