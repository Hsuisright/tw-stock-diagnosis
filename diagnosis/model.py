from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class ReturnDiagnosis:
    target_price: float
    dividend_contribution: float
    eps_contribution: float
    valuation_contribution: float
    total_return: float
    direct_return: float
    reconciliation_difference: float
    implied_eps_cagr: float | None

def decompose_return(p0: float, eps0: float, epst: float, dividend: float,
                     rt: float, years: float = 1.0) -> ReturnDiagnosis:
    vals = (p0, eps0, epst, dividend, rt, years)
    if not all(isfinite(float(v)) for v in vals):
        raise ValueError("模型輸入必須是有限數值")
    if p0 <= 0 or eps0 <= 0 or rt <= 0 or years <= 0:
        raise ValueError("P0、EPS0、Rt與期間必須大於0")
    r0 = p0 / eps0
    target = epst * rt
    div_c = dividend / p0
    eps_c = (epst - eps0) / eps0
    val_c = epst * (rt - r0) / (eps0 * r0)
    total = div_c + eps_c + val_c
    direct = (dividend + target - p0) / p0
    cagr = (epst / eps0) ** (1 / years) - 1 if epst > 0 else None
    return ReturnDiagnosis(target, div_c, eps_c, val_c, total, direct,
                           total - direct, cagr)

def percentile_rank(values: list[float], current: float) -> float | None:
    valid = sorted(float(x) for x in values if x is not None and float(x) > 0)
    if not valid: return None
    below = sum(x < current for x in valid)
    equal = sum(x == current for x in valid)
    return (below + equal * 0.5) / len(valid)

def range_position(values: list[float], current: float) -> float | None:
    valid = [float(x) for x in values if x is not None and float(x) > 0]
    if len(valid) < 2 or max(valid) == min(valid): return None
    return max(0.0, min(1.0, (current - min(valid)) / (max(valid) - min(valid))))

def labels(weight: float, result: ReturnDiagnosis, pe_percentile: float | None,
           conservative_return: float | None = None) -> list[str]:
    out=[]
    if weight >= .15: out.append("集中部位")
    elif weight >= .10: out.append("核心部位")
    positives=sum(max(x,0) for x in (result.dividend_contribution,result.eps_contribution,result.valuation_contribution))
    if positives:
        if result.eps_contribution > 0 and result.eps_contribution/positives >= .5: out.append("基本面驅動")
        if result.dividend_contribution > 0 and result.dividend_contribution/positives >= .4: out.append("股利收益型")
        if result.valuation_contribution > 0 and result.valuation_contribution/positives >= .4: out.append("估值依賴偏高")
    if result.eps_contribution < 0: out.append("獲利衰退風險")
    if pe_percentile is not None:
        if pe_percentile >= .75: out.append("估值高檔")
        elif pe_percentile <= .25: out.append("估值低檔")
    if conservative_return is not None and conservative_return < -.15: out.append("下檔風險偏高")
    return out or ["一般觀察"]
