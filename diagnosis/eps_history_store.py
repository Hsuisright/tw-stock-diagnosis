"""Reusable current-vintage quarterly basic-EPS history.

This is deliberately not a PIT store or an earnings forecast. FinMind documents
its EPS field as a single-quarter *basic* EPS; source facts are retained so that
the presentation layer never has to infer EPS from a P/E multiple.
"""
from __future__ import annotations

from calendar import monthrange
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request

URL = "https://api.finmindtrade.com/api/v4/data"
SOURCE = "FinMind:TaiwanStockFinancialStatements"
QUALIFICATION = "CURRENT_VINTAGE_PROVIDER_REPORTED_BASIC_EPS"
SCHEMA = """
CREATE TABLE IF NOT EXISTS eps_quarters (
  ticker TEXT NOT NULL, fiscal_year INTEGER NOT NULL, quarter INTEGER NOT NULL,
  period_end TEXT NOT NULL, eps REAL NOT NULL, eps_basis TEXT NOT NULL,
  consolidated TEXT NOT NULL, source TEXT NOT NULL, qualification TEXT NOT NULL,
  original_field TEXT NOT NULL, source_reference TEXT NOT NULL, source_fact_id TEXT NOT NULL,
  fetched_at TEXT NOT NULL, version TEXT NOT NULL,
  PRIMARY KEY(ticker, period_end, eps_basis, version)
);
CREATE INDEX IF NOT EXISTS eps_quarters_ticker_period ON eps_quarters(ticker, period_end);
CREATE TABLE IF NOT EXISTS eps_basis_events (
  ticker TEXT NOT NULL, event_date TEXT NOT NULL, event_type TEXT NOT NULL,
  source TEXT NOT NULL, source_reference TEXT NOT NULL, fetched_at TEXT NOT NULL,
  PRIMARY KEY(ticker, event_date, event_type, source)
);
"""


def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _quarter(period_end: str) -> tuple[int, int]:
    y, month, day = map(int, period_end.split("-"))
    if month not in (3, 6, 9, 12) or day != monthrange(y, month)[1]:
        raise ValueError("not_a_calendar_quarter_end")
    return y, month // 3


def _numeric(value) -> float | None:
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize_finmind_eps(rows: list[dict], ticker: str, fetched_at: str, version: str) -> list[dict]:
    """Keep only documented basic, single-quarter EPS. Reject ambiguous periods."""
    normalized = []
    seen = set()
    for row in rows:
        if str(row.get("stock_id", "")).strip() != ticker or row.get("type") != "EPS":
            continue
        value = _numeric(row.get("value"))
        if value is None:
            continue
        period = str(row.get("date", ""))
        year, quarter = _quarter(period)
        if period in seen:
            raise ValueError(f"duplicate_eps_period:{period}")
        seen.add(period)
        original = str(row.get("origin_name") or "EPS")
        normalized.append(dict(
            ticker=ticker, fiscal_year=year, quarter=quarter, period_end=period, eps=value,
            eps_basis="basic", consolidated="provider_income_statement_scope_not_explicit",
            source=SOURCE, qualification=QUALIFICATION, original_field=original,
            source_reference=URL, source_fact_id=f"{ticker}:EPS:{period}:{version[:16]}",
            fetched_at=fetched_at, version=version,
        ))
    return sorted(normalized, key=lambda x: x["period_end"])


def fetch_finmind_eps(ticker: str, start_date="2005-01-01", end_date=None) -> list[dict]:
    params = {"dataset": "TaiwanStockFinancialStatements", "data_id": ticker, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    request = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "StockDiagnosisV15/1.5"})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
        raise ValueError("finmind_eps_response_invalid")
    now = datetime.now(timezone.utc).isoformat()
    version = sha256(json.dumps(payload["data"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return normalize_finmind_eps(payload["data"], str(ticker), now, version)


def _fetch_dataset(dataset: str, ticker: str, start_date: str) -> list[dict]:
    params = {"dataset": dataset, "data_id": ticker, "start_date": start_date}
    request = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "StockDiagnosisV15/1.5"})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
        raise ValueError(f"{dataset}_response_invalid")
    return payload["data"]


def _basis_events(ticker: str, start_date: str, fetched_at: str) -> list[dict]:
    events = []
    dividend = _fetch_dataset("TaiwanStockDividend", ticker, start_date)
    for item in dividend:
        stock = _numeric(item.get("StockEarningsDistribution")) or 0
        statutory = _numeric(item.get("StockStatutorySurplus")) or 0
        if stock + statutory > 0:
            event_date = str(item.get("StockExDividendTradingDate") or item.get("date") or "")
            if event_date:
                events.append(dict(ticker=ticker, event_date=event_date, event_type="stock_distribution",
                    source="FinMind:TaiwanStockDividend", source_reference=URL, fetched_at=fetched_at))
    for dataset, label in (("TaiwanStockSplitPrice", "stock_split"),
                           ("TaiwanStockCapitalReductionReferencePrice", "capital_reduction")):
        for item in _fetch_dataset(dataset, ticker, start_date):
            event_date = str(item.get("date") or "")
            if event_date:
                events.append(dict(ticker=ticker, event_date=event_date, event_type=label,
                    source="FinMind:"+dataset, source_reference=URL, fetched_at=fetched_at))
    return events


def refresh(path: Path, ticker: str, start_date="2005-01-01") -> dict:
    rows = fetch_finmind_eps(ticker, start_date)
    if not rows:
        raise ValueError("finmind_eps_empty")
    with closing(_connect(path)) as con:
        with con:
            con.execute("DELETE FROM eps_quarters WHERE ticker=?", (ticker,))
            con.executemany("""INSERT INTO eps_quarters
                (ticker,fiscal_year,quarter,period_end,eps,eps_basis,consolidated,source,qualification,
                 original_field,source_reference,source_fact_id,fetched_at,version)
                VALUES (:ticker,:fiscal_year,:quarter,:period_end,:eps,:eps_basis,:consolidated,:source,:qualification,
                        :original_field,:source_reference,:source_fact_id,:fetched_at,:version)""", rows)
            con.execute("DELETE FROM eps_basis_events WHERE ticker=?", (ticker,))
            events = _basis_events(ticker, start_date, rows[0]["fetched_at"])
            con.executemany("""INSERT INTO eps_basis_events
                (ticker,event_date,event_type,source,source_reference,fetched_at)
                VALUES (:ticker,:event_date,:event_type,:source,:source_reference,:fetched_at)""", events)
    return {"ticker": ticker, "count": len(rows), "first_period": rows[0]["period_end"],
            "last_period": rows[-1]["period_end"], "eps_basis": "basic", "qualification": QUALIFICATION,
            "share_basis_event_count": len(events)}


def load(path: Path, ticker: str, cutoff: str | None = None) -> list[dict]:
    if not path.exists():
        return []
    with closing(_connect(path)) as con:
        sql = "SELECT * FROM eps_quarters WHERE ticker=?"
        args = [ticker]
        if cutoff:
            sql += " AND period_end<=?"
            args.append(cutoff)
        sql += " ORDER BY period_end"
        return [dict(row) for row in con.execute(sql, args)]


def comparable_rows(path: Path, ticker: str, cutoff: str | None = None) -> tuple[list[dict], list[dict]]:
    """Return records after the last known share-basis-changing event.

    Raw source rows remain available via ``load``. No re-scaling is invented:
    the first comparison period is the calendar quarter after the latest event.
    """
    rows = load(path, ticker, cutoff)
    if not rows:
        return [], []
    with closing(_connect(path)) as con:
        events = [dict(row) for row in con.execute(
            "SELECT * FROM eps_basis_events WHERE ticker=? ORDER BY event_date", (ticker,))]
    if not events:
        return rows, events
    year, month, _ = map(int, events[-1]["event_date"].split("-"))
    event_index = year * 4 + (month - 1) // 3
    return [row for row in rows if (row["fiscal_year"] * 4 + row["quarter"] - 1) > event_index], events
