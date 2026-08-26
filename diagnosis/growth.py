from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class GrowthForecast:
    current_eps: float
    forecast_revenue: float
    forecast_ebitda: float
    forecast_net_income: float
    forecast_eps: float
    eps_growth: float
    forward_static_pe: float | None
    required_eps: float | None
    digestion_ratio: float | None


@dataclass(frozen=True)
class ImpliedGrowthDiagnostic:
    required_eps: float
    required_growth_1y: float
    required_cagr_2y: float
    required_cagr_3y: float
    historical_median: float | None
    pressure_percentile: float | None
    achievement_rate: float | None
    sample_count: int
    label: str


def yoy_growths(monthly_eps):
    """Return point-in-time year-over-year growth from {(year, month): eps}."""
    result=[]
    for (year,month),value in sorted(monthly_eps.items()):
        prior=monthly_eps.get((year-1,month))
        if prior is None or prior <= 0 or value <= 0:
            continue
        growth=float(value)/float(prior)-1
        # Near-zero bases destroy interpretability; retain broad cycles but reject explosions.
        if -0.9 <= growth <= 3.0:
            result.append(growth)
    return result


def implied_growth_diagnostic(current_price, current_eps, normal_pe, historical_growths,
                              min_samples=24):
    if not all(isfinite(float(x)) for x in (current_price,current_eps,normal_pe)):
        raise ValueError("隱含成長輸入必須是有限數值")
    if current_price <= 0 or current_eps <= 0 or normal_pe <= 0:
        raise ValueError("股價、EPS與正常PE必須大於0")
    required_eps=float(current_price)/float(normal_pe)
    ratio=required_eps/float(current_eps)
    g1=ratio-1
    g2=ratio**.5-1
    g3=ratio**(1/3)-1
    history=sorted(float(x) for x in historical_growths if x is not None and isfinite(float(x)))
    if len(history) >= min_samples:
        below=sum(x<g1 for x in history)
        equal=sum(x==g1 for x in history)
        pct=(below+equal*.5)/len(history)
        achievement=sum(x>=g1 for x in history)/len(history)
        med=median(history)
        if g1 <= 0: label="目前EPS已支撐正常估值"
        elif pct < .25: label="成長壓力低"
        elif pct < .60: label="成長壓力合理"
        elif pct < .85: label="成長壓力偏高"
        elif pct < .95: label="成長壓力很高"
        else: label="成長要求極端"
    else:
        pct=achievement=med=None
        label="目前EPS已支撐正常估值" if g1 <= 0 else "歷史成長資料不足"
    return ImpliedGrowthDiagnostic(required_eps,g1,g2,g3,med,pct,achievement,len(history),label)


def forecast_from_ebitda(ttm_revenue, ttm_net_income, diluted_shares,
                         revenue_growth, ebitda_margin, net_income_conversion,
                         current_price=None, normal_pe=None):
    values=(ttm_revenue,ttm_net_income,diluted_shares,revenue_growth,
            ebitda_margin,net_income_conversion)
    if not all(isfinite(float(x)) for x in values):
        raise ValueError("成長預估輸入必須是有限數值")
    if ttm_revenue <= 0 or diluted_shares <= 0 or ttm_net_income <= 0:
        raise ValueError("TTM營收、淨利與稀釋後股數必須大於0")
    if revenue_growth <= -1 or not 0 <= ebitda_margin <= 1 or not 0 <= net_income_conversion <= 1:
        raise ValueError("成長率或轉換率超出合理範圍")
    revenue=float(ttm_revenue)*(1+float(revenue_growth))
    ebitda=revenue*float(ebitda_margin)
    net_income=ebitda*float(net_income_conversion)
    current_eps=float(ttm_net_income)/float(diluted_shares)
    forecast_eps=net_income/float(diluted_shares)
    eps_growth=forecast_eps/current_eps-1
    forward_pe=(float(current_price)/forecast_eps if current_price and current_price>0 and forecast_eps>0 else None)
    required=(float(current_price)/float(normal_pe) if current_price and normal_pe and normal_pe>0 else None)
    digestion=None
    if required is not None and required>current_eps:
        digestion=(forecast_eps-current_eps)/(required-current_eps)
    return GrowthForecast(current_eps,revenue,ebitda,net_income,forecast_eps,
                          eps_growth,forward_pe,required,digestion)
