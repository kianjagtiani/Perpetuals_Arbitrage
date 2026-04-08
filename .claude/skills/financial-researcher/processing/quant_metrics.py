"""
Quantitative Factor Metrics for Jim Simons Expert Analysis

Statistical and factor-based analysis using price/volume data
and fundamental metrics. All functions return MetricResult.

No external dependencies — uses Python stdlib (math, statistics).
"""

from typing import List, Dict, Any, Optional
from statistics import mean, stdev, median
import math

from .metrics_calculator import MetricResult


# =============================================================================
# HELPERS
# =============================================================================

def _extract_closes(prices: List[Dict[str, Any]]) -> List[float]:
    """Extract close prices from price history, oldest first."""
    sorted_prices = sorted(prices, key=lambda p: p.get('date', p.get('time', '')))
    return [p.get('close', p.get('price', 0)) for p in sorted_prices if p.get('close', p.get('price', 0)) > 0]


def _extract_volumes(prices: List[Dict[str, Any]]) -> List[float]:
    """Extract volumes from price history, oldest first."""
    sorted_prices = sorted(prices, key=lambda p: p.get('date', p.get('time', '')))
    return [p.get('volume', 0) for p in sorted_prices]


def _returns(prices: List[float]) -> List[float]:
    """Calculate daily returns from price series."""
    return [(prices[i] / prices[i-1]) - 1 for i in range(1, len(prices)) if prices[i-1] != 0]


def _sma(values: List[float], window: int) -> float:
    """Simple moving average of last `window` values."""
    if len(values) < window:
        return mean(values) if values else 0
    return mean(values[-window:])


def _ema(values: List[float], window: int) -> float:
    """Exponential moving average."""
    if not values:
        return 0
    multiplier = 2 / (window + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = (price * multiplier) + (ema_val * (1 - multiplier))
    return ema_val


def _rsi(prices: List[float], period: int = 14) -> float:
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return 50.0  # Neutral default
    rets = _returns(prices[-(period + 1):])
    gains = [r for r in rets if r > 0]
    losses = [-r for r in rets if r < 0]
    avg_gain = mean(gains) if gains else 0
    avg_loss = mean(losses) if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# =============================================================================
# METRIC FUNCTIONS
# =============================================================================

def momentum_score(
    prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Price momentum analysis (Jegadeesh & Titman).

    Calculates:
    - 12-month momentum (skip last month)
    - 6-month momentum
    - 3-month momentum
    - 1-month momentum (short-term reversal signal)
    - Momentum persistence (consistency of monthly returns)

    Medium-term focus: 1-6 month horizon.
    """
    closes = _extract_closes(prices)
    flags = []

    if len(closes) < 252:
        return MetricResult(
            value=0, interpretation="Insufficient price data for momentum analysis",
            flags=["Need at least 252 trading days"], data_quality=0.3
        )

    current = closes[-1]

    # Momentum calculations
    mom_12m_skip1m = (closes[-22] / closes[-252]) - 1 if len(closes) >= 252 else 0  # 12m skip last month
    mom_6m = (current / closes[-126]) - 1 if len(closes) >= 126 else 0
    mom_3m = (current / closes[-63]) - 1 if len(closes) >= 63 else 0
    mom_1m = (current / closes[-22]) - 1 if len(closes) >= 22 else 0

    # Momentum persistence: % of positive months in last 12
    monthly_returns = []
    for i in range(12):
        start_idx = -(i + 1) * 22
        end_idx = -i * 22 if i > 0 else None
        if abs(start_idx) <= len(closes):
            month_start = closes[start_idx]
            month_end = closes[end_idx] if end_idx else closes[-1]
            if month_start > 0:
                monthly_returns.append((month_end / month_start) - 1)

    persistence = sum(1 for r in monthly_returns if r > 0) / len(monthly_returns) if monthly_returns else 0.5

    # Composite momentum score: weighted blend
    composite = (mom_12m_skip1m * 0.4) + (mom_6m * 0.3) + (mom_3m * 0.2) + (mom_1m * 0.1)

    components = {
        "momentum_12m_skip1m": round(mom_12m_skip1m * 100, 2),
        "momentum_6m": round(mom_6m * 100, 2),
        "momentum_3m": round(mom_3m * 100, 2),
        "momentum_1m": round(mom_1m * 100, 2),
        "persistence": round(persistence * 100, 1),
        "composite": round(composite * 100, 2),
    }

    # Interpretation
    if composite > 0.20:
        interpretation = "Strong positive momentum — trend following favored"
    elif composite > 0.05:
        interpretation = "Moderate positive momentum"
    elif composite > -0.05:
        interpretation = "Neutral momentum — no clear trend"
    elif composite > -0.20:
        interpretation = "Moderate negative momentum"
    else:
        interpretation = "Strong negative momentum — trend is down"

    # Flags
    if mom_1m < -0.10 and mom_12m_skip1m > 0.15:
        flags.append("Short-term reversal in a long-term uptrend — potential buying opportunity")
    if mom_1m > 0.10 and mom_12m_skip1m < -0.15:
        flags.append("Short-term bounce in a long-term downtrend — potential dead cat bounce")
    if persistence > 0.75:
        flags.append(f"High momentum persistence ({persistence*100:.0f}% positive months) — trend is strong")
    if persistence < 0.25:
        flags.append(f"Persistent decline ({(1-persistence)*100:.0f}% negative months)")

    return MetricResult(
        value=round(composite * 100, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def volatility_metrics(
    prices: List[Dict[str, Any]],
    vix_prices: List[Dict[str, Any]] = None,
) -> MetricResult:
    """
    Volatility regime analysis.

    Calculates:
    - Realized volatility (20d, 60d, 252d annualized)
    - Volatility regime (high/normal/low relative to own history)
    - Vol-of-vol (stability of volatility)
    - VIX context (if available)
    """
    closes = _extract_closes(prices)
    flags = []

    if len(closes) < 60:
        return MetricResult(
            value=0, interpretation="Insufficient data for volatility analysis",
            flags=["Need at least 60 trading days"], data_quality=0.3
        )

    rets = _returns(closes)
    annualize = math.sqrt(252)

    # Realized volatility at different windows
    vol_20d = stdev(rets[-20:]) * annualize if len(rets) >= 20 else 0
    vol_60d = stdev(rets[-60:]) * annualize if len(rets) >= 60 else 0
    vol_252d = stdev(rets[-252:]) * annualize if len(rets) >= 252 else vol_60d

    # Vol regime: compare short-term vol to long-term
    vol_ratio = vol_20d / vol_252d if vol_252d > 0 else 1.0

    # Vol-of-vol: rolling 20d vol measured over 60d windows
    if len(rets) >= 120:
        rolling_vols = []
        for i in range(0, len(rets) - 20, 5):  # Every 5 days
            window = rets[i:i+20]
            if len(window) >= 20:
                rolling_vols.append(stdev(window) * annualize)
        vol_of_vol = stdev(rolling_vols) if len(rolling_vols) >= 2 else 0
    else:
        vol_of_vol = 0

    # VIX context
    vix_current = None
    if vix_prices:
        vix_closes = _extract_closes(vix_prices)
        if vix_closes:
            vix_current = vix_closes[-1]

    components = {
        "vol_20d": round(vol_20d * 100, 2),
        "vol_60d": round(vol_60d * 100, 2),
        "vol_252d": round(vol_252d * 100, 2),
        "vol_ratio_20d_vs_252d": round(vol_ratio, 2),
        "vol_of_vol": round(vol_of_vol * 100, 2),
        "vix_current": round(vix_current, 2) if vix_current else None,
    }

    # Regime classification
    if vol_ratio > 1.5:
        regime = "HIGH"
        interpretation = f"High volatility regime — 20d vol ({vol_20d*100:.1f}%) well above normal ({vol_252d*100:.1f}%)"
        flags.append("Elevated volatility — larger position sizing risk")
    elif vol_ratio > 1.15:
        regime = "ELEVATED"
        interpretation = f"Elevated volatility — 20d vol ({vol_20d*100:.1f}%) above normal"
    elif vol_ratio < 0.65:
        regime = "COMPRESSED"
        interpretation = f"Compressed volatility — potential breakout setup"
        flags.append("Vol compression often precedes large moves — direction unclear")
    elif vol_ratio < 0.85:
        regime = "LOW"
        interpretation = f"Low volatility — calm market conditions"
    else:
        regime = "NORMAL"
        interpretation = f"Normal volatility regime ({vol_20d*100:.1f}% annualized)"

    components["regime"] = regime

    if vix_current and vix_current > 30:
        flags.append(f"VIX at {vix_current:.1f} — market-wide fear elevated")
    elif vix_current and vix_current < 15:
        flags.append(f"VIX at {vix_current:.1f} — market complacency, low hedging demand")

    return MetricResult(
        value=round(vol_20d * 100, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def mean_reversion_signals(
    prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Mean reversion signal detection.

    Calculates:
    - Z-score vs 50-day and 200-day moving average
    - RSI (14-day)
    - Bollinger Band position (% B)
    - Distance from 52-week high/low
    """
    closes = _extract_closes(prices)
    flags = []

    if len(closes) < 50:
        return MetricResult(
            value=0, interpretation="Insufficient data for mean reversion analysis",
            flags=["Need at least 50 trading days"], data_quality=0.3
        )

    current = closes[-1]

    # Moving averages
    sma_50 = _sma(closes, 50)
    sma_200 = _sma(closes, 200) if len(closes) >= 200 else sma_50

    # Z-scores vs MAs
    std_50 = stdev(closes[-50:]) if len(closes) >= 50 else stdev(closes)
    z_vs_50 = (current - sma_50) / std_50 if std_50 > 0 else 0

    std_200 = stdev(closes[-200:]) if len(closes) >= 200 else std_50
    z_vs_200 = (current - sma_200) / std_200 if std_200 > 0 else 0

    # RSI
    rsi_val = _rsi(closes)

    # Bollinger Bands (20-day, 2 std)
    bb_sma = _sma(closes, 20)
    bb_std = stdev(closes[-20:]) if len(closes) >= 20 else stdev(closes)
    bb_upper = bb_sma + 2 * bb_std
    bb_lower = bb_sma - 2 * bb_std
    bb_pct = (current - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

    # 52-week range position
    high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)
    range_position = (current - low_52w) / (high_52w - low_52w) if (high_52w - low_52w) > 0 else 0.5
    dist_from_high = (current / high_52w) - 1 if high_52w > 0 else 0

    components = {
        "z_score_vs_50dma": round(z_vs_50, 2),
        "z_score_vs_200dma": round(z_vs_200, 2),
        "rsi_14": round(rsi_val, 1),
        "bollinger_pct_b": round(bb_pct * 100, 1),
        "range_52w_position": round(range_position * 100, 1),
        "distance_from_52w_high": round(dist_from_high * 100, 2),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
    }

    # Composite mean reversion score: -100 (oversold) to +100 (overbought)
    mr_score = (
        (z_vs_50 * 20) +  # Z-score contribution
        ((rsi_val - 50) * 0.8) +  # RSI contribution (centered on 50)
        ((bb_pct - 0.5) * 40) +  # Bollinger contribution
        ((range_position - 0.5) * 20)  # Range position contribution
    )
    mr_score = max(-100, min(100, mr_score))

    # Interpretation
    if mr_score > 50:
        interpretation = "Strongly overbought — high mean reversion probability to downside"
        flags.append("Multiple overbought signals aligned — caution on new longs")
    elif mr_score > 20:
        interpretation = "Moderately overbought — extended but not extreme"
    elif mr_score < -50:
        interpretation = "Strongly oversold — high mean reversion probability to upside"
        flags.append("Multiple oversold signals aligned — potential buying opportunity")
    elif mr_score < -20:
        interpretation = "Moderately oversold — pullback may present opportunity"
    else:
        interpretation = "Neutral — no strong mean reversion signal"

    # Specific flags
    if rsi_val > 70:
        flags.append(f"RSI overbought at {rsi_val:.0f}")
    elif rsi_val < 30:
        flags.append(f"RSI oversold at {rsi_val:.0f}")
    if current > sma_50 > sma_200:
        flags.append("Golden cross — price > 50 DMA > 200 DMA (bullish structure)")
    elif current < sma_50 < sma_200:
        flags.append("Death cross — price < 50 DMA < 200 DMA (bearish structure)")

    return MetricResult(
        value=round(mr_score, 1),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def factor_exposure(
    pe_ratio: float = None,
    pb_ratio: float = None,
    roe: float = None,
    accrual_ratio: float = None,
    market_cap: float = None,
    momentum_12m: float = None,
) -> MetricResult:
    """
    Multi-factor exposure analysis.

    Scores exposure to academic risk factors:
    - Value (low P/E, low P/B)
    - Quality (high ROE, low accruals)
    - Size (small cap premium)
    - Momentum (12-month return)

    Each factor scored -2 (strong negative) to +2 (strong positive).
    """
    components = {}
    flags = []

    # Value factor
    value_score = 0
    if pe_ratio is not None and pe_ratio > 0:
        if pe_ratio < 12:
            value_score = 2
        elif pe_ratio < 18:
            value_score = 1
        elif pe_ratio > 35:
            value_score = -2
        elif pe_ratio > 25:
            value_score = -1
    if pb_ratio is not None and pb_ratio > 0:
        if pb_ratio < 1.5:
            value_score = min(2, value_score + 1)
        elif pb_ratio > 5:
            value_score = max(-2, value_score - 1)
    components["value_factor"] = value_score

    # Quality factor
    quality_score = 0
    if roe is not None:
        if roe > 0.20:
            quality_score = 2
        elif roe > 0.12:
            quality_score = 1
        elif roe < 0:
            quality_score = -2
        elif roe < 0.05:
            quality_score = -1
    if accrual_ratio is not None:
        if abs(accrual_ratio) < 0.05:
            quality_score = min(2, quality_score + 1)
        elif abs(accrual_ratio) > 0.15:
            quality_score = max(-2, quality_score - 1)
    components["quality_factor"] = quality_score

    # Size factor
    size_score = 0
    if market_cap is not None:
        if market_cap < 2e9:
            size_score = 2  # Small cap
        elif market_cap < 10e9:
            size_score = 1  # Mid cap
        elif market_cap > 200e9:
            size_score = -1  # Mega cap (less size premium)
    components["size_factor"] = size_score

    # Momentum factor
    mom_score = 0
    if momentum_12m is not None:
        if momentum_12m > 0.30:
            mom_score = 2
        elif momentum_12m > 0.10:
            mom_score = 1
        elif momentum_12m < -0.30:
            mom_score = -2
        elif momentum_12m < -0.10:
            mom_score = -1
    components["momentum_factor"] = mom_score

    # Composite
    composite = value_score + quality_score + size_score + mom_score
    components["composite_factor_score"] = composite

    if composite >= 4:
        interpretation = "Strong multi-factor tailwind — value, quality, and momentum aligned"
    elif composite >= 2:
        interpretation = "Positive factor exposure — favorable characteristics"
    elif composite <= -4:
        interpretation = "Strong multi-factor headwind — expensive, low quality, poor momentum"
    elif composite <= -2:
        interpretation = "Negative factor exposure — unfavorable characteristics"
    else:
        interpretation = "Neutral factor exposure — mixed signals"

    # Crowding flags
    if value_score >= 2 and mom_score >= 2:
        flags.append("Value + momentum aligned — historically strong signal")
    if value_score <= -2 and mom_score >= 2:
        flags.append("Expensive with strong momentum — growth/momentum trade, vulnerable to rotation")
    if quality_score <= -1 and mom_score >= 2:
        flags.append("Low quality with high momentum — potential blow-up risk")

    return MetricResult(
        value=composite,
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def statistical_anomalies(
    prices: List[Dict[str, Any]],
    earnings_values: List[float] = None,
) -> MetricResult:
    """
    Statistical anomaly detection in return distribution.

    Detects:
    - Non-normal return distribution (skewness, kurtosis)
    - Unusual volume patterns
    - Price-earnings divergence
    """
    closes = _extract_closes(prices)
    volumes = _extract_volumes(prices)
    flags = []

    if len(closes) < 60:
        return MetricResult(
            value=0, interpretation="Insufficient data for anomaly detection",
            flags=["Need at least 60 trading days"], data_quality=0.3
        )

    rets = _returns(closes)
    n = len(rets)

    # Skewness
    avg = mean(rets)
    std = stdev(rets)
    if std > 0 and n >= 30:
        skewness = sum((r - avg) ** 3 for r in rets) / (n * std ** 3)
        kurtosis = sum((r - avg) ** 4 for r in rets) / (n * std ** 4) - 3  # Excess kurtosis
    else:
        skewness = 0
        kurtosis = 0

    # Volume anomaly: recent volume vs historical
    if len(volumes) >= 60 and any(v > 0 for v in volumes):
        recent_vol = mean(volumes[-20:]) if volumes[-20:] else 0
        historical_vol = mean(volumes[-252:]) if len(volumes) >= 252 else mean(volumes)
        volume_ratio = recent_vol / historical_vol if historical_vol > 0 else 1.0
    else:
        volume_ratio = 1.0

    # Price-earnings divergence (if earnings provided)
    pe_divergence = None
    if earnings_values and len(earnings_values) >= 3 and len(closes) >= 252:
        # Compare price change to earnings change
        price_change_1yr = (closes[-1] / closes[-252]) - 1 if len(closes) >= 252 else 0
        earnings_change = (earnings_values[-1] / earnings_values[-2]) - 1 if earnings_values[-2] != 0 else 0
        pe_divergence = price_change_1yr - earnings_change

    # Anomaly score: 0 = normal, higher = more anomalous
    anomaly_score = 0
    anomaly_score += min(abs(skewness), 3)  # Skewness contribution
    anomaly_score += min(abs(kurtosis) / 2, 3)  # Kurtosis contribution
    anomaly_score += min(abs(volume_ratio - 1) * 2, 2)  # Volume contribution
    if pe_divergence is not None:
        anomaly_score += min(abs(pe_divergence), 2)  # Divergence contribution

    components = {
        "skewness": round(skewness, 3),
        "excess_kurtosis": round(kurtosis, 3),
        "volume_ratio_recent_vs_historical": round(volume_ratio, 2),
        "price_earnings_divergence": round(pe_divergence * 100, 2) if pe_divergence is not None else None,
        "anomaly_score": round(anomaly_score, 2),
    }

    # Flags
    if skewness < -0.5:
        flags.append(f"Negative skew ({skewness:.2f}) — more frequent large drops than gains")
    elif skewness > 0.5:
        flags.append(f"Positive skew ({skewness:.2f}) — occasional large gains")
    if kurtosis > 3:
        flags.append(f"Fat tails (excess kurtosis {kurtosis:.1f}) — extreme moves more likely than normal")
    if volume_ratio > 2.0:
        flags.append(f"Abnormal volume ({volume_ratio:.1f}x normal) — increased attention or distribution")
    elif volume_ratio < 0.5:
        flags.append(f"Low volume ({volume_ratio:.1f}x normal) — reduced liquidity/interest")
    if pe_divergence is not None and abs(pe_divergence) > 0.30:
        if pe_divergence > 0:
            flags.append(f"Price outrunning earnings by {pe_divergence*100:.0f}pp — multiple expansion")
        else:
            flags.append(f"Earnings outrunning price by {abs(pe_divergence)*100:.0f}pp — potential value")

    if anomaly_score > 5:
        interpretation = "Multiple statistical anomalies detected — unusual market behavior"
    elif anomaly_score > 3:
        interpretation = "Some anomalies present — warrants attention"
    else:
        interpretation = "Return distribution roughly normal — no major anomalies"

    return MetricResult(
        value=round(anomaly_score, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def sector_relative_strength(
    stock_prices: List[Dict[str, Any]],
    sector_etf_prices: List[Dict[str, Any]],
    spy_prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Relative strength analysis: stock vs sector ETF vs S&P 500.

    Calculates relative outperformance over 1m, 3m, 6m, 12m.
    """
    stock = _extract_closes(stock_prices)
    sector = _extract_closes(sector_etf_prices)
    spy = _extract_closes(spy_prices)
    flags = []

    min_len = min(len(stock), len(sector), len(spy))
    if min_len < 22:
        return MetricResult(
            value=0, interpretation="Insufficient data for relative strength",
            flags=["Need at least 22 trading days of benchmark data"], data_quality=0.3
        )

    # Align lengths (use most recent data)
    stock = stock[-min_len:]
    sector = sector[-min_len:]
    spy = spy[-min_len:]

    def rel_perf(a, b, days):
        """Relative performance over N days."""
        if len(a) < days or len(b) < days:
            return 0
        return ((a[-1] / a[-days]) - 1) - ((b[-1] / b[-days]) - 1)

    components = {}
    for label, days in [("1m", 22), ("3m", 63), ("6m", 126), ("12m", 252)]:
        if min_len >= days:
            components[f"vs_sector_{label}"] = round(rel_perf(stock, sector, days) * 100, 2)
            components[f"vs_spy_{label}"] = round(rel_perf(stock, spy, days) * 100, 2)
        else:
            components[f"vs_sector_{label}"] = None
            components[f"vs_spy_{label}"] = None

    # Composite: weighted average of available periods (recent weighted more)
    weights = {"1m": 0.1, "3m": 0.2, "6m": 0.3, "12m": 0.4}
    vs_spy_composite = 0
    total_weight = 0
    for label, w in weights.items():
        val = components.get(f"vs_spy_{label}")
        if val is not None:
            vs_spy_composite += val * w
            total_weight += w
    vs_spy_composite = vs_spy_composite / total_weight if total_weight > 0 else 0

    components["vs_spy_composite"] = round(vs_spy_composite, 2)

    if vs_spy_composite > 15:
        interpretation = "Strong outperformer — significant leadership vs market"
    elif vs_spy_composite > 5:
        interpretation = "Outperforming market — positive relative strength"
    elif vs_spy_composite < -15:
        interpretation = "Strong underperformer — lagging market significantly"
    elif vs_spy_composite < -5:
        interpretation = "Underperforming market — negative relative strength"
    else:
        interpretation = "In line with market — neutral relative strength"

    # Flags
    vs_sector_3m = components.get("vs_sector_3m", 0) or 0
    vs_sector_12m = components.get("vs_sector_12m", 0) or 0
    if vs_sector_3m > 10:
        flags.append(f"Outperforming sector by {vs_sector_3m:.1f}pp over 3 months — sector leadership")
    if vs_sector_3m < -10:
        flags.append(f"Underperforming sector by {abs(vs_sector_3m):.1f}pp over 3 months — sector laggard")
    if vs_spy_composite > 10 and vs_sector_12m and vs_sector_12m > 10:
        flags.append("Outperforming both market AND sector — strong stock-specific strength")

    return MetricResult(
        value=round(vs_spy_composite, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def correlation_regime(
    stock_prices: List[Dict[str, Any]],
    spy_prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Correlation and beta analysis vs S&P 500.

    Calculates:
    - Rolling correlation (30d, 90d, 252d)
    - Beta (90d, 252d)
    - Correlation breakdown detection
    """
    stock = _extract_closes(stock_prices)
    spy = _extract_closes(spy_prices)
    flags = []

    min_len = min(len(stock), len(spy))
    if min_len < 30:
        return MetricResult(
            value=0, interpretation="Insufficient data for correlation analysis",
            flags=["Need at least 30 trading days"], data_quality=0.3
        )

    stock = stock[-min_len:]
    spy = spy[-min_len:]

    stock_rets = _returns(stock)
    spy_rets = _returns(spy)
    min_rets = min(len(stock_rets), len(spy_rets))
    stock_rets = stock_rets[-min_rets:]
    spy_rets = spy_rets[-min_rets:]

    def calc_corr(a, b, n):
        if len(a) < n or len(b) < n:
            return None
        x, y = a[-n:], b[-n:]
        mx, my = mean(x), mean(y)
        sx, sy = stdev(x), stdev(y)
        if sx == 0 or sy == 0:
            return 0
        cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
        return cov / (sx * sy)

    def calc_beta(stock_r, mkt_r, n):
        if len(stock_r) < n or len(mkt_r) < n:
            return None
        x, y = mkt_r[-n:], stock_r[-n:]
        mx = mean(x)
        var_x = sum((xi - mx) ** 2 for xi in x) / (n - 1)
        if var_x == 0:
            return 0
        cov = sum((xi - mx) * (yi - mean(y)) for xi, yi in zip(x, y)) / (n - 1)
        return cov / var_x

    corr_30d = calc_corr(stock_rets, spy_rets, 30)
    corr_90d = calc_corr(stock_rets, spy_rets, 90)
    corr_252d = calc_corr(stock_rets, spy_rets, 252)
    beta_90d = calc_beta(stock_rets, spy_rets, 90)
    beta_252d = calc_beta(stock_rets, spy_rets, 252)

    components = {
        "correlation_30d": round(corr_30d, 3) if corr_30d is not None else None,
        "correlation_90d": round(corr_90d, 3) if corr_90d is not None else None,
        "correlation_252d": round(corr_252d, 3) if corr_252d is not None else None,
        "beta_90d": round(beta_90d, 2) if beta_90d is not None else None,
        "beta_252d": round(beta_252d, 2) if beta_252d is not None else None,
    }

    # Correlation breakdown detection
    if corr_30d is not None and corr_252d is not None:
        corr_change = corr_30d - corr_252d
        components["correlation_change_short_vs_long"] = round(corr_change, 3)
        if abs(corr_change) > 0.3:
            flags.append(f"Correlation regime shift: 30d={corr_30d:.2f} vs 252d={corr_252d:.2f} — stock decoupling from market")

    primary_corr = corr_90d if corr_90d is not None else (corr_30d or 0)

    if primary_corr > 0.8:
        interpretation = f"High market correlation ({primary_corr:.2f}) — moves with S&P 500"
    elif primary_corr > 0.5:
        interpretation = f"Moderate market correlation ({primary_corr:.2f})"
    elif primary_corr > 0.2:
        interpretation = f"Low market correlation ({primary_corr:.2f}) — partial diversifier"
    else:
        interpretation = f"Very low/negative correlation ({primary_corr:.2f}) — strong diversifier"

    if beta_90d is not None:
        if beta_90d > 1.5:
            flags.append(f"High beta ({beta_90d:.2f}) — amplifies market moves")
        elif beta_90d < 0.5:
            flags.append(f"Low beta ({beta_90d:.2f}) — defensive characteristics")

    return MetricResult(
        value=round(primary_corr, 3) if primary_corr else 0,
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def liquidity_metrics(
    prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Market microstructure and liquidity analysis.

    Calculates:
    - Amihud illiquidity ratio
    - High-low spread proxy (Corwin-Schultz)
    - Volume trend
    - Abnormal volume detection
    """
    closes = _extract_closes(prices)
    volumes = _extract_volumes(prices)
    flags = []

    if len(closes) < 22 or not any(v > 0 for v in volumes):
        return MetricResult(
            value=0, interpretation="Insufficient data for liquidity analysis",
            flags=["Need at least 22 trading days with volume"], data_quality=0.3
        )

    rets = _returns(closes)

    # Amihud illiquidity: average |return| / volume (higher = less liquid)
    amihud_values = []
    for i in range(min(len(rets), len(volumes) - 1)):
        vol = volumes[i + 1]
        if vol > 0:
            amihud_values.append(abs(rets[i]) / vol)
    amihud = mean(amihud_values) * 1e6 if amihud_values else 0  # Scale for readability

    # High-low spread proxy
    sorted_prices = sorted(prices, key=lambda p: p.get('date', p.get('time', '')))
    spreads = []
    for p in sorted_prices:
        high = p.get('high', 0)
        low = p.get('low', 0)
        if high > 0 and low > 0:
            spreads.append((high - low) / ((high + low) / 2))
    avg_spread = mean(spreads[-20:]) if len(spreads) >= 20 else (mean(spreads) if spreads else 0)

    # Volume trend: 20-day avg vs 60-day avg
    vol_20 = mean(volumes[-20:]) if len(volumes) >= 20 else mean(volumes)
    vol_60 = mean(volumes[-60:]) if len(volumes) >= 60 else vol_20
    vol_trend = (vol_20 / vol_60) - 1 if vol_60 > 0 else 0

    # Abnormal volume: current vs 252-day average
    vol_252 = mean(volumes[-252:]) if len(volumes) >= 252 else mean(volumes)
    vol_ratio = vol_20 / vol_252 if vol_252 > 0 else 1.0

    components = {
        "amihud_illiquidity": round(amihud, 4),
        "avg_spread_pct": round(avg_spread * 100, 3),
        "volume_trend_20d_vs_60d": round(vol_trend * 100, 1),
        "volume_ratio_vs_252d": round(vol_ratio, 2),
        "avg_daily_volume_20d": round(vol_20, 0),
    }

    # Interpretation
    if amihud > 1.0:
        interpretation = "Low liquidity — significant price impact risk"
        flags.append("Illiquid stock — position sizing should be conservative")
    elif amihud > 0.1:
        interpretation = "Moderate liquidity"
    else:
        interpretation = "High liquidity — easy to trade in size"

    if vol_ratio > 2.0:
        flags.append(f"Volume surge ({vol_ratio:.1f}x normal) — heightened activity")
    if vol_trend > 0.50:
        flags.append(f"Volume trending up {vol_trend*100:.0f}% — increasing interest")
    elif vol_trend < -0.30:
        flags.append(f"Volume trending down {vol_trend*100:.0f}% — waning interest")

    return MetricResult(
        value=round(amihud, 4),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )


def return_distribution(
    prices: List[Dict[str, Any]],
) -> MetricResult:
    """
    Full return distribution and tail risk analysis.

    Calculates:
    - Annualized return and Sharpe proxy (assuming 0% risk-free)
    - Max drawdown
    - CVaR (Expected Shortfall) at 5%
    - Calmar ratio (return / max drawdown)
    """
    closes = _extract_closes(prices)
    flags = []

    if len(closes) < 60:
        return MetricResult(
            value=0, interpretation="Insufficient data for return distribution",
            flags=["Need at least 60 trading days"], data_quality=0.3
        )

    rets = _returns(closes)
    annualize = 252

    # Annualized return
    total_return = (closes[-1] / closes[0]) - 1
    years = len(rets) / annualize
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # Annualized volatility and Sharpe proxy
    annual_vol = stdev(rets) * math.sqrt(annualize)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0

    # Max drawdown
    peak = closes[0]
    max_dd = 0
    for price in closes:
        if price > peak:
            peak = price
        dd = (price / peak) - 1
        if dd < max_dd:
            max_dd = dd

    # CVaR at 5% (average of worst 5% of daily returns)
    sorted_rets = sorted(rets)
    cutoff = max(1, int(len(sorted_rets) * 0.05))
    cvar_5 = mean(sorted_rets[:cutoff])

    # Calmar ratio
    calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

    components = {
        "annual_return": round(annual_return * 100, 2),
        "annual_volatility": round(annual_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "cvar_5pct": round(cvar_5 * 100, 3),
        "calmar_ratio": round(calmar, 2),
    }

    # Interpretation based on risk-adjusted returns
    if sharpe > 1.0:
        interpretation = f"Excellent risk-adjusted returns (Sharpe {sharpe:.2f})"
    elif sharpe > 0.5:
        interpretation = f"Good risk-adjusted returns (Sharpe {sharpe:.2f})"
    elif sharpe > 0:
        interpretation = f"Positive but weak risk-adjusted returns (Sharpe {sharpe:.2f})"
    else:
        interpretation = f"Negative risk-adjusted returns (Sharpe {sharpe:.2f})"

    if max_dd < -0.40:
        flags.append(f"Severe max drawdown ({max_dd*100:.1f}%) — high tail risk")
    elif max_dd < -0.25:
        flags.append(f"Significant drawdown ({max_dd*100:.1f}%)")
    if cvar_5 < -0.03:
        flags.append(f"High tail risk — worst 5% of days average {cvar_5*100:.2f}% loss")
    if calmar > 1.0:
        flags.append(f"Strong Calmar ratio ({calmar:.2f}) — good return per unit of drawdown")

    return MetricResult(
        value=round(sharpe, 2),
        interpretation=interpretation,
        components=components,
        flags=flags,
    )
