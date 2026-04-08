"""
Behavioral Economics Metrics for Robert Shiller Expert Analysis

Long-term valuation and behavioral indicators:
- CAPE ratio (Cyclically-Adjusted P/E)
- Bubble detection indicators
- Narrative momentum scoring

No external dependencies — uses Python stdlib (math, statistics).
"""

from typing import List, Dict, Any, Optional
from statistics import mean, stdev, median
import math

from .metrics_calculator import MetricResult


def cape_ratio(
    earnings_history: List[float],
    current_price: float,
    shares_outstanding: float,
    inflation_adjustment: float = 1.0,
) -> MetricResult:
    """
    Cyclically-Adjusted Price-to-Earnings (CAPE/Shiller P/E).

    Uses up to 10 years of average real earnings to smooth cyclicality.
    Shiller's original research: CAPE is the single best predictor of
    long-term (10-year) stock returns.

    Args:
        earnings_history: Net income values, oldest first (up to 15 years)
        current_price: Current stock price
        shares_outstanding: Current shares outstanding
        inflation_adjustment: CPI adjustment factor (default 1.0 = no adjustment)
    """
    flags = []

    if not earnings_history or current_price <= 0 or shares_outstanding <= 0:
        return MetricResult(
            value=0, interpretation="Cannot calculate CAPE — missing data",
            flags=["Missing earnings history or price data"], data_quality=0.2
        )

    # Use up to 10 years of earnings
    earnings_to_use = earnings_history[-10:] if len(earnings_history) >= 10 else earnings_history
    years_used = len(earnings_to_use)

    # Calculate average real earnings
    avg_earnings = mean(earnings_to_use)
    eps_avg = avg_earnings / shares_outstanding if shares_outstanding > 0 else 0

    # Adjust for inflation if provided
    eps_avg_real = eps_avg / inflation_adjustment

    # CAPE ratio
    cape = current_price / eps_avg_real if eps_avg_real > 0 else 0

    # Excess CAPE yield (inverse of CAPE, as %)
    excess_cape_yield = (1 / cape * 100) if cape > 0 else 0

    # Implied long-term real return (rough approximation from Shiller's research)
    # Historically: 10-year real return ~ 1/CAPE * 100
    implied_10yr_return = excess_cape_yield

    components = {
        "cape_ratio": round(cape, 2),
        "excess_cape_yield": round(excess_cape_yield, 2),
        "implied_10yr_real_return": round(implied_10yr_return, 2),
        "years_of_earnings_used": years_used,
        "avg_eps_real": round(eps_avg_real, 2),
        "current_price": current_price,
    }

    # Interpretation using historical S&P 500 CAPE benchmarks
    # (applying same framework to individual stocks with caveat)
    if cape > 40:
        interpretation = f"Extremely elevated CAPE ({cape:.1f}) — historically associated with poor 10-year returns"
        flags.append(f"CAPE of {cape:.1f} exceeds dot-com peak levels (44) — extreme overvaluation risk")
    elif cape > 30:
        interpretation = f"High CAPE ({cape:.1f}) — above historical average, implies lower future returns"
        flags.append(f"CAPE above 30 — historically rare, expected real returns ~{implied_10yr_return:.1f}%/yr")
    elif cape > 20:
        interpretation = f"Moderate CAPE ({cape:.1f}) — near long-term average"
    elif cape > 12:
        interpretation = f"Below-average CAPE ({cape:.1f}) — historically favorable for long-term returns"
        flags.append(f"Below-average CAPE implies ~{implied_10yr_return:.1f}% real annual returns")
    elif cape > 0:
        interpretation = f"Low CAPE ({cape:.1f}) — historically associated with strong future returns"
        flags.append(f"Very low CAPE — historically best 10-year return periods")
    else:
        interpretation = "Negative or zero CAPE — sustained losses, not meaningful"
        flags.append("CAPE not meaningful with negative average earnings")

    if years_used < 10:
        flags.append(f"Only {years_used} years of earnings data — CAPE less reliable (ideally 10 years)")

    return MetricResult(
        value=round(cape, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
        data_quality=min(1.0, years_used / 10),
    )


def bubble_indicators(
    prices: List[Dict[str, Any]],
    earnings_history: List[float] = None,
) -> MetricResult:
    """
    Bubble detection indicators inspired by Shiller's research.

    Detects:
    - Price-to-trend deviation (is price far above its long-term trend?)
    - Price growth vs earnings growth divergence
    - Valuation percentile vs own history
    - Acceleration in price (prices rising at increasing rate)
    """
    from .quant_metrics import _extract_closes

    closes = _extract_closes(prices)
    flags = []

    if len(closes) < 252:
        return MetricResult(
            value=0, interpretation="Insufficient price history for bubble analysis",
            flags=["Need at least 1 year of price data"], data_quality=0.3
        )

    current = closes[-1]

    # 1. Price-to-trend deviation
    # Calculate log-linear trend and measure deviation
    n = len(closes)
    log_prices = [math.log(p) for p in closes if p > 0]
    if len(log_prices) >= 252:
        # Simple linear regression on log prices
        x_mean = (n - 1) / 2
        x_vals = list(range(n))
        y_mean = mean(log_prices)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, log_prices))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        slope = numerator / denominator if denominator > 0 else 0
        intercept = y_mean - slope * x_mean
        trend_value = math.exp(intercept + slope * (n - 1))
        price_to_trend = (current / trend_value) - 1
    else:
        price_to_trend = 0

    # 2. Price growth vs earnings growth divergence
    pe_divergence = 0
    if earnings_history and len(earnings_history) >= 3:
        earnings_growth = (earnings_history[-1] / earnings_history[0]) - 1 if earnings_history[0] != 0 else 0
        price_growth = (closes[-1] / closes[0]) - 1 if closes[0] != 0 else 0
        pe_divergence = price_growth - earnings_growth

    # 3. Valuation percentile vs own history (using P/E proxy from price/earnings)
    val_percentile = 50.0  # Default
    if earnings_history and len(earnings_history) >= 5:
        # Rough PE at each year-end
        pe_history = []
        for i, earnings in enumerate(earnings_history):
            if earnings > 0 and i < len(closes) // 252:
                price_at_year = closes[min((i + 1) * 252 - 1, len(closes) - 1)]
                pe_history.append(price_at_year / (earnings / closes[-1] * current) if earnings != 0 else 0)
        if pe_history:
            current_pe = current / (earnings_history[-1] / 1) if earnings_history[-1] > 0 else 0
            val_percentile = sum(1 for pe in pe_history if pe < current_pe) / len(pe_history) * 100

    # 4. Price acceleration (is price growth accelerating?)
    if len(closes) >= 504:  # 2 years
        growth_yr1 = (closes[-252] / closes[-504]) - 1
        growth_yr2 = (closes[-1] / closes[-252]) - 1
        acceleration = growth_yr2 - growth_yr1
    elif len(closes) >= 252:
        growth_h1 = (closes[-126] / closes[-252]) - 1 if len(closes) >= 252 else 0
        growth_h2 = (closes[-1] / closes[-126]) - 1 if len(closes) >= 126 else 0
        acceleration = growth_h2 - growth_h1
    else:
        acceleration = 0

    # Composite bubble score: 0 (no bubble) to 100 (extreme bubble)
    bubble_score = 0
    bubble_score += max(0, min(30, price_to_trend * 50))  # Up to 30 from trend deviation
    bubble_score += max(0, min(25, pe_divergence * 25))  # Up to 25 from PE divergence
    bubble_score += max(0, min(25, (val_percentile - 50) / 2))  # Up to 25 from percentile
    bubble_score += max(0, min(20, acceleration * 40))  # Up to 20 from acceleration
    bubble_score = max(0, min(100, bubble_score))

    components = {
        "price_to_trend_deviation": round(price_to_trend * 100, 2),
        "price_vs_earnings_divergence": round(pe_divergence * 100, 2),
        "valuation_percentile_vs_history": round(val_percentile, 1),
        "price_acceleration": round(acceleration * 100, 2),
        "bubble_score": round(bubble_score, 1),
    }

    if bubble_score > 75:
        interpretation = f"High bubble risk ({bubble_score:.0f}/100) — multiple overvaluation signals"
        flags.append("Multiple bubble indicators elevated — historical parallels suggest caution")
    elif bubble_score > 50:
        interpretation = f"Elevated bubble risk ({bubble_score:.0f}/100) — extended but not extreme"
        flags.append("Valuations stretched — monitor for acceleration")
    elif bubble_score > 25:
        interpretation = f"Moderate bubble risk ({bubble_score:.0f}/100) — some elevation"
    else:
        interpretation = f"Low bubble risk ({bubble_score:.0f}/100) — no bubble characteristics"

    if price_to_trend > 0.50:
        flags.append(f"Price {price_to_trend*100:.0f}% above long-term trend — significant mean reversion risk")
    if acceleration > 0.20:
        flags.append(f"Price growth accelerating (+{acceleration*100:.0f}pp) — classic late-stage bubble behavior")

    return MetricResult(
        value=round(bubble_score, 1),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def narrative_momentum_score(
    news_sentiment_positive: int = 0,
    news_sentiment_negative: int = 0,
    news_total: int = 0,
    analyst_estimates_high: float = None,
    analyst_estimates_low: float = None,
    analyst_estimates_mean: float = None,
) -> MetricResult:
    """
    Quantitative proxy for Shiller's narrative economics.

    Measures:
    - News sentiment ratio (positive vs negative coverage)
    - Analyst estimate dispersion (disagreement = narrative uncertainty)

    Higher score = stronger positive narrative momentum.
    """
    flags = []
    components = {}

    # News sentiment ratio
    if news_total > 0:
        pos_ratio = news_sentiment_positive / news_total
        neg_ratio = news_sentiment_negative / news_total
        sentiment_score = (pos_ratio - neg_ratio) * 100  # -100 to +100
        components["news_positive_ratio"] = round(pos_ratio * 100, 1)
        components["news_negative_ratio"] = round(neg_ratio * 100, 1)
        components["news_sentiment_score"] = round(sentiment_score, 1)
        components["news_total_articles"] = news_total
    else:
        sentiment_score = 0
        components["news_sentiment_score"] = 0

    # Analyst estimate dispersion
    dispersion = 0
    if analyst_estimates_high is not None and analyst_estimates_low is not None and analyst_estimates_mean:
        range_pct = (analyst_estimates_high - analyst_estimates_low) / abs(analyst_estimates_mean) if analyst_estimates_mean != 0 else 0
        dispersion = range_pct * 100
        components["analyst_estimate_dispersion"] = round(dispersion, 1)
        components["analyst_high"] = analyst_estimates_high
        components["analyst_low"] = analyst_estimates_low
        components["analyst_mean"] = analyst_estimates_mean

    # Composite narrative score: -100 (extreme negative narrative) to +100 (extreme positive)
    narrative_score = sentiment_score * 0.7  # 70% from sentiment
    # High dispersion reduces narrative strength (uncertainty)
    if dispersion > 50:
        narrative_score *= 0.7  # Dampen when analysts disagree

    components["composite_narrative_score"] = round(narrative_score, 1)

    if narrative_score > 50:
        interpretation = "Strong positive narrative — widespread bullish storytelling"
        flags.append("Dominant positive narrative — Shiller warns this often precedes disappointment")
    elif narrative_score > 20:
        interpretation = "Moderately positive narrative"
    elif narrative_score < -50:
        interpretation = "Strong negative narrative — widespread pessimism"
        flags.append("Extreme negative narrative — contrarian opportunity if fundamentals intact")
    elif narrative_score < -20:
        interpretation = "Moderately negative narrative"
    else:
        interpretation = "Neutral narrative — no dominant story"

    if dispersion > 80:
        flags.append(f"Extreme analyst disagreement (dispersion {dispersion:.0f}%) — high narrative uncertainty")
    elif dispersion > 50:
        flags.append(f"High analyst disagreement (dispersion {dispersion:.0f}%) — contested narrative")

    return MetricResult(
        value=round(narrative_score, 1),
        interpretation=interpretation,
        components=components,
        flags=flags,
        data_quality=0.5 if news_total < 5 else 1.0,
    )
