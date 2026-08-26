from __future__ import annotations

import sqlite3
from pathlib import Path


# 公開版只建立個股診斷所需的市場資料表，不含帳戶、持倉、成本或交易紀錄。
SCHEMA = """
CREATE TABLE IF NOT EXISTS prices(
 stock_id TEXT NOT NULL, price_date TEXT NOT NULL, close REAL NOT NULL,
 market TEXT, source TEXT, PRIMARY KEY(stock_id,price_date));
CREATE TABLE IF NOT EXISTS pe_history(
 stock_id TEXT NOT NULL, value_date TEXT NOT NULL,
 pe REAL, source TEXT, PRIMARY KEY(stock_id,value_date));
CREATE TABLE IF NOT EXISTS data_sources(
 id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, stock_id TEXT, as_of_date TEXT,
 source TEXT NOT NULL, url TEXT, status TEXT NOT NULL, updated_at TEXT NOT NULL, note TEXT);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection
