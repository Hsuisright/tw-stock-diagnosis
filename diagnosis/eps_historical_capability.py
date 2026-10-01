"""TTM and historical growth statistics built only from a normalized EPS sequence."""
from __future__ import annotations
from math import isfinite

HORIZONS = (1, 2, 3)


def period_index(row):
    return row["fiscal_year"] * 4 + row["quarter"] - 1


def _quantile(values, p):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * p
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (pos - low)


def ttm_series(rows):
    """Each TTM has exact four consecutive periods with one identical EPS basis."""
    indexed = {period_index(row): row for row in rows}
    output = []
    for index, latest in sorted(indexed.items()):
        parents = [indexed.get(index - offset) for offset in range(4)]
        if any(parent is None for parent in parents):
            continue
        bases = {parent["eps_basis"] for parent in parents}
        if len(bases) != 1:
            continue
        if not all(isinstance(parent["eps"], (int, float)) and isfinite(parent["eps"]) for parent in parents):
            continue
        output.append(dict(
            ticker=latest["ticker"], period_end=latest["period_end"], fiscal_year=latest["fiscal_year"],
            quarter=latest["quarter"], ttm_eps=sum(parent["eps"] for parent in parents),
            eps_basis=latest["eps_basis"], consolidated=latest["consolidated"],
            qualification=latest["qualification"], source_lineage=parents,
        ))
    return output


def observations(rows):
    ttms = ttm_series(rows)
    indexed = {period_index(item): item for item in ttms}
    output = []
    for years in HORIZONS:
        for start_index, start in sorted(indexed.items()):
            end = indexed.get(start_index + years * 4)
            if end is None or end["eps_basis"] != start["eps_basis"]:
                continue
            if start["ttm_eps"] <= 0 or end["ttm_eps"] <= 0:
                output.append(dict(years=years, start_period=start["period_end"], end_period=end["period_end"],
                    start_eps=start["ttm_eps"], end_eps=end["ttm_eps"], growth=None,
                    reason="nonpositive_start_or_end_ttm", source_lineage=[start["source_lineage"], end["source_lineage"]]))
                continue
            output.append(dict(years=years, start_period=start["period_end"], end_period=end["period_end"],
                start_eps=start["ttm_eps"], end_eps=end["ttm_eps"], growth=(end["ttm_eps"] / start["ttm_eps"]) ** (1 / years) - 1,
                reason=None, source_lineage=[start["source_lineage"], end["source_lineage"]]))
    return output


def summaries(rows):
    results = []
    all_observations = observations(rows)
    for years in HORIZONS:
        values = [item["growth"] for item in all_observations if item["years"] == years and item["growth"] is not None]
        results.append(dict(years=years, n=len(values), median=_quantile(values, .5), p25=_quantile(values, .25),
                            p75=_quantile(values, .75), maximum=max(values) if values else None,
                            minimum=min(values) if values else None))
    return results, all_observations


def base_eps(rows, current_period_end):
    candidates = [row for row in rows if row["period_end"] < current_period_end]
    if not candidates:
        return dict(value=None, components=[], reason="no_prior_quarters")
    latest_index = max(period_index(row) for row in candidates)
    indexed = {period_index(row): row for row in candidates}
    components = [indexed.get(latest_index - offset) for offset in range(4)]
    if any(item is None for item in components):
        return dict(value=None, components=[item for item in components if item], reason="missing_quarter")
    if len({item["eps_basis"] for item in components}) != 1:
        return dict(value=None, components=components, reason="mixed_eps_basis")
    return dict(value=sum(item["eps"] for item in components), components=components, reason=None)


def required_growths(required_eps, actual_ttm_eps):
    """Return the market requirement relative to reported, four-quarter EPS only.

    Deliberately accepts no price or PE inputs: callers must first obtain
    ``required_eps`` from their valuation reference and an actual, comparable
    TTM from ``base_eps``.  This prevents price/PE-implied EPS entering the
    V1.5 requirement denominator by accident.
    """
    if not isinstance(required_eps, (int, float)) or not isfinite(required_eps):
        return dict(one_year=None, two_year=None, three_year=None, reason="required_eps_missing")
    if not isinstance(actual_ttm_eps, (int, float)) or not isfinite(actual_ttm_eps) or actual_ttm_eps <= 0:
        return dict(one_year=None, two_year=None, three_year=None, reason="actual_ttm_eps_missing_or_nonpositive")
    ratio = required_eps / actual_ttm_eps
    if ratio < 0:
        return dict(one_year=None, two_year=None, three_year=None, reason="invalid_required_eps_ratio")
    return dict(
        one_year=ratio - 1,
        two_year=ratio ** .5 - 1,
        three_year=ratio ** (1 / 3) - 1,
        reason=None,
    )
