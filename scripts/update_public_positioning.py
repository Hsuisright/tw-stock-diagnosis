"""Incrementally build the one authoritative public TWSE/TPEx positioning CSV."""
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from diagnosis.public_positioning import fetch_day, load, required_dates, save, validate  # noqa:E402

OUT = ROOT / "public_data" / "public_positioning.csv"

def main():
    existing = load(OUT); fetched = []; complete = True
    with ThreadPoolExecutor(max_workers=6) as pool:
        for rows, twse_ok, tpex_ok in pool.map(fetch_day, required_dates(existing, 60)):
            fetched.extend(rows); complete = complete and twse_ok and tpex_ok
    merged = validate([*existing, *fetched])
    save(OUT, merged)
    print(f"rows={len(merged)} fetched={len(fetched)} official_complete={complete}")

if __name__ == "__main__": main()
