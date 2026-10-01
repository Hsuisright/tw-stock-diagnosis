"""Portable, provider-reported margin and short-positioning data for V1.5.

This module never fills a missing date or infers a position from price.  The
public seed is deliberately a compact cache of FinMind's reported balances,
shared by local use and Streamlit Cloud.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import urllib.parse
import urllib.request

URL = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockMarginPurchaseShortSale"
SOURCE = f"FinMind:{DATASET}"
SEED_SCHEMA_VERSION = 1


def _number(value):
    try:
        parsed = float(value)
        return parsed if isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def fetch_finmind_positioning(ticker: str, start_date: str = "2024-01-01") -> list[dict]:
    params = {"dataset": DATASET, "data_id": str(ticker), "start_date": start_date}
    request = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": "StockDiagnosisV15/1.5"})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
        raise ValueError("finmind_positioning_response_invalid")
    return normalize_finmind_positioning(payload["data"], str(ticker))


def normalize_finmind_positioning(rows: list[dict], ticker: str) -> list[dict]:
    """Map only explicitly documented margin/short fields; reject duplicates."""
    normalized, seen = [], set()
    fields = {
        "margin_balance": "MarginPurchaseTodayBalance",
        "short_balance": "ShortSaleTodayBalance",
        "margin_buy": "MarginPurchaseBuy",
        "margin_sell": "MarginPurchaseSell",
        "margin_cash_repayment": "MarginPurchaseCashRepayment",
        "short_sell": "ShortSaleSell",
        "short_buy": "ShortSaleBuy",
        "short_cash_repayment": "ShortSaleCashRepayment",
    }
    for row in rows:
        if str(row.get("stock_id") or row.get("ticker") or "").strip() != ticker:
            continue
        day = str(row.get("date") or "")
        if not day:
            continue
        if day in seen:
            raise ValueError(f"duplicate_positioning_date:{day}")
        seen.add(day)
        item = {"ticker": ticker, "date": day}
        # The updater receives FinMind raw fields; the public seed contains
        # their canonical counterparts.  Both travel through this one
        # validation path without changing reported values.
        item.update({target: _number(row.get(source) if source in row else row.get(target))
                     for target, source in fields.items()})
        # A reported row without either balance cannot support a positioning
        # observation and is intentionally excluded rather than imputed.
        if item["margin_balance"] is None and item["short_balance"] is None:
            continue
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["date"])


def build_seed(tickers: tuple[str, ...], start_date: str = "2024-01-01") -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    by_ticker = {str(ticker): fetch_finmind_positioning(str(ticker), start_date) for ticker in tickers}
    version = sha256(json.dumps(by_ticker, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": SEED_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source": SOURCE,
        "dataset": DATASET,
        "start_date": start_date,
        "version": version,
        "tickers": by_ticker,
    }


def write_seed(path: Path, tickers: tuple[str, ...], start_date: str = "2024-01-01") -> dict:
    payload = build_seed(tickers, start_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if (existing.get("schema_version") == SEED_SCHEMA_VERSION
                and existing.get("version") == payload["version"]):
            return existing
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_seed(path: Path, ticker: str) -> tuple[list[dict], dict | None]:
    """Return validated public data or no data.  There is no live fallback."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SEED_SCHEMA_VERSION or payload.get("dataset") != DATASET:
            return [], None
        raw = payload.get("tickers", {}).get(str(ticker))
        if not isinstance(raw, list):
            return [], None
        rows = normalize_finmind_positioning(raw, str(ticker))
        return rows, {key: payload.get(key) for key in ("generated_at", "source", "dataset", "version")}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return [], None
