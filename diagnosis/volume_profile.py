"""Daily-bar approximation only; not actual volume at price or investor inventory."""
from math import isfinite


def estimate_profile(bars, sessions=60, bins=32):
    if sessions not in (60, 120) or bins < 2:
        raise ValueError('Unsupported profile window or bins')
    ordered = sorted(bars, key=lambda x: str(x.get('date', '')))
    if len(ordered) < sessions:
        return None, f'需要完整{sessions}個交易日，目前只有{len(ordered)}筆。'
    selected = ordered[-sessions:]
    if len({x.get('date') for x in selected}) != sessions or any(not x.get('date') for x in selected):
        return None, '日期缺漏或重複，暫不估算成交分布。'
    clean = []
    for row in selected:
        try:
            low, high, close, volume = (float(row[k]) for k in ('low','high','close','volume'))
            if not all(isfinite(x) and x > 0 for x in (low,high,close,volume)) or not low <= close <= high:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            return None, '所選期間高低價或成交量不完整／異常，暫不估算；不以收盤價代填。'
        clean.append((low,high,close,volume))
    closes = [x[2] for x in clean]
    if any(abs(b/a-1) > .25 for a,b in zip(closes, closes[1:])):
        return None, '所選期間有超過25%的單日價格斷點，請先核對分割／除權息，暫不估算。'
    bottom, top = min(x[0] for x in clean), max(x[1] for x in clean)
    if top == bottom:
        edges, amounts = [bottom,top], [sum(x[3] for x in clean)]
    else:
        step = (top-bottom)/bins
        edges = [bottom+i*step for i in range(bins+1)]
        amounts = [0.0]*bins
        for low,high,close,volume in clean:
            if high == low:
                amounts[min(bins-1, int((close-bottom)/step))] += volume
            else:
                for i in range(bins):
                    overlap = max(0, min(high,edges[i+1])-max(low,edges[i]))
                    amounts[i] += volume*overlap/(high-low)
    poc = max(range(len(amounts)), key=lambda i: amounts[i])
    left = right = poc
    total, covered = sum(amounts), amounts[poc]
    # Contiguous area growing from POC, selecting the larger adjacent bucket.
    while covered < total*.70 and (left > 0 or right < len(amounts)-1):
        if left > 0 and (right == len(amounts)-1 or amounts[left-1] >= amounts[right+1]):
            left -= 1
            covered += amounts[left]
        else:
            right += 1
            covered += amounts[right]
    return dict(sessions=sessions, start=selected[0]['date'], end=selected[-1]['date'],
                edges=edges, volumes=amounts, poc_low=edges[poc], poc_high=edges[poc+1],
                poc=(edges[poc]+edges[poc+1])/2, lower=edges[left], upper=edges[right+1],
                area_fraction=covered/total, close=closes[-1]), None
