"""Build the public, portable quarterly-EPS seed used by the Cloud app."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from diagnosis.eps_history_store import (  # noqa: E402
    SEED_SCHEMA_VERSION,
    _basis_events,
    fetch_finmind_eps,
)

TICKERS = ("2330", "2454", "2345", "2412")


def build(tickers=TICKERS):
    generated_at = datetime.now(timezone.utc).isoformat()
    output = {"schema_version": SEED_SCHEMA_VERSION, "generated_at": generated_at,
              "source": "FinMind public datasets", "tickers": {}}
    for ticker in tickers:
        rows = fetch_finmind_eps(ticker)
        output["tickers"][ticker] = {
            "quarters": [
                {"stock_id": ticker, "type": "EPS", "date": row["period_end"], "value": row["eps"],
                 "origin_name": row["original_field"]}
                for row in rows
            ],
            "basis_events": _basis_events(ticker, "2005-01-01", generated_at),
        }
    version_source = json.dumps(output["tickers"], sort_keys=True, ensure_ascii=False).encode()
    output["version"] = sha256(version_source).hexdigest()
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "public_data" / "eps_seed_v1.json")
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} for {len(payload['tickers'])} tickers")


if __name__ == "__main__":
    main()
