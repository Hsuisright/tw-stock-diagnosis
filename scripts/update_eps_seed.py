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
from diagnosis.positioning import write_seed as write_positioning_seed  # noqa: E402

TICKERS = ("2330", "2454", "2345", "2412")


def write_if_changed(path: Path, payload: dict) -> bool:
    """Keep the public data commit stable when reported facts are unchanged."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("schema_version") == payload.get("schema_version") and existing.get("version") == payload.get("version"):
            return False
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


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
            "basis_events": [{key: value for key, value in event.items() if key != "fetched_at"}
                             for event in _basis_events(ticker, "2005-01-01", generated_at)],
        }
    version_source = json.dumps(output["tickers"], sort_keys=True, ensure_ascii=False).encode()
    output["version"] = sha256(version_source).hexdigest()
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "public_data" / "eps_seed_v1.json")
    parser.add_argument("--positioning-output", type=Path,
                        default=ROOT / "public_data" / "positioning_seed_v1.json")
    parser.add_argument("--positioning-start-date", default="2024-01-01")
    args = parser.parse_args()
    payload = build()
    changed = write_if_changed(args.output, payload)
    print(f"{'wrote' if changed else 'unchanged'} {args.output} for {len(payload['tickers'])} tickers")
    positioning = write_positioning_seed(args.positioning_output, TICKERS, args.positioning_start_date)
    print(f"wrote {args.positioning_output} for {len(positioning['tickers'])} tickers")


if __name__ == "__main__":
    main()
