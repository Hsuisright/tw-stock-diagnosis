"""Supplemental retrospective requirements; never a forecast or PIT backtest."""
from datetime import date
from calendar import monthrange
from math import isfinite
from statistics import median

BUCKETS = ('≤0%', '0–20%', '20–40%', '40–60%', '60–100%', '>100%')

def quarter(day):
    d = date.fromisoformat(day)
    return d.year * 4 + (d.month - 1) // 3

def quarter_end(q):
    y, k = divmod(q, 4)
    m = (k + 1) * 3
    return date(y, m, monthrange(y, m)[1]).isoformat()

def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)

def growth_bucket(g):
    if not numeric(g):
        return None
    return next((BUCKETS[i] for i, limit in enumerate((0, .2, .4, .6, 1)) if g <= limit), BUCKETS[-1])

def base_eps(facts, ticker, q):
    components = []
    for target in range(q - 1, q - 5, -1):
        matches = [f for f in facts if f.get('ticker') == ticker and f.get('report_period') == quarter_end(target)]
        if len(matches) != 1:
            return dict(value=None, components=components, reason='missing_or_ambiguous_quarter')
        f = matches[0]
        if not (f.get('period_type') == 'Quarter' and f.get('eps_basis') == 'diluted'
                and f.get('consolidation_scope') == 'consolidated'
                and f.get('unit') == 'TWD/common_share' and numeric(f.get('value'))
                and f.get('estimated') is False):
            return dict(value=None, components=components, reason='unqualified_eps_basis')
        components.append(dict(f))
    return dict(value=sum(f['value'] for f in components), components=components, reason=None)

def requirement(facts, ticker, day, price, reference_pe):
    b = base_eps(facts, ticker, quarter(day))
    reason = b['reason']
    if b['value'] is not None and b['value'] <= 0:
        reason = 'PE_NOT_MEANINGFUL'
    if not numeric(reference_pe) or reference_pe <= 0:
        reason = reason or 'reference_pe_unavailable'
    if not numeric(price) or price <= 0:
        reason = reason or 'price_unavailable'
    required = price / reference_pe if numeric(price) and price > 0 and numeric(reference_pe) and reference_pe > 0 else None
    g = required / b['value'] - 1 if not reason else None
    return dict(base_eps=b['value'], base_eps_components=b['components'], reference_pe=reference_pe,
                required_eps=required, required_growth=g, bucket=growth_bucket(g), reason=reason)

def episodes(facts, ticker, prices, cutoff):
    """Median of >=4 prior completed quarter peak PEs; economic quarter-end clock.

    Current-vintage raw-close exploration only. Publication dates are retained in
    parent facts, NOT manufactured. Stop follow-up at first missing EPS quarter.
    """
    groups = {}
    for p in sorted(prices, key=lambda p: p['date']):
        if p['date'] <= cutoff and numeric(p.get('close')) and p['close'] > 0:
            groups.setdefault(quarter(p['date']), []).append(p)
    history, out = [], []
    for q, ps in sorted(groups.items()):
        if quarter_end(q) > cutoff:
            continue
        peak = max(ps, key=lambda p: p['close'])  # stable: earliest equal close
        ref = median([h['pe'] for h in history]) if len(history) >= 4 else None
        r = requirement(facts, ticker, peak['date'], peak['close'], ref)
        row = dict(ticker=ticker, quarter_end=quarter_end(q), peak_date=peak['date'], peak_close=peak['close'],
                   reference_quarters=[h['quarter_end'] for h in history], **r,
                   status='N/A', completion_date=None, censor_date=None, lead_days=None,
                   qualification='CURRENT_VINTAGE_UNADJUSTED_NOT_STRICT_PIT', clock='economic_quarter_end')
        b = r['base_eps']
        if not r['reason']:
            if b >= r['required_eps']:
                row.update(status='ALREADY_MET', completion_date=peak['date'], lead_days=0)
            else:
                last = peak['date']
                for future_q in range(q, quarter(cutoff) + 1):
                    end = quarter_end(future_q)
                    if end > cutoff:
                        break
                    realized = base_eps(facts, ticker, future_q + 1)
                    if realized['reason']:
                        break
                    last = end
                    if realized['value'] >= r['required_eps']:
                        row.update(status='FULFILLED', completion_date=end,
                                   completion_facts=realized['components'],
                                   lead_days=(date.fromisoformat(end) - date.fromisoformat(peak['date'])).days)
                        break
                if row['status'] == 'N/A':
                    row.update(status='RIGHT_CENSORED', censor_date=last)
        out.append(row)
        if b is not None and b > 0 and len(r['base_eps_components']) == 4:
            history.append(dict(quarter_end=quarter_end(q), pe=peak['close'] / b))
    return out

def summary_table(rows, current_bucket):
    result = []
    for bucket in BUCKETS:
        rs = [r for r in rows if r['bucket'] == bucket and r['status'] != 'N/A']
        counts = [0] * 5
        for r in rs:
            if r['status'] == 'RIGHT_CENSORED':
                counts[4] += 1
            else:
                d = r['lead_days']
                counts[0 if d <= 365.25 / 2 else 1 if d <= 365.25 else 2 if d <= 365.25 * 2 else 3] += 1
        result.append(dict(zip(('EPS Requirement', '≤6M', '6–12M', '1–2Y', '>2Y', 'Not Fulfilled', 'N', 'Status'),
            (('→ ' if bucket == current_bucket else '') + bucket,
             *(counts if len(rs) >= 5 else ['N/A'] * 5), len(rs), 'OK' if len(rs) >= 5 else 'INSUFFICIENT SAMPLE'))))
    return result
