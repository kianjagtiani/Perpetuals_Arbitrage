"""Basis risk quantification for cross-exchange perpetual futures positions.

Basis risk arises because positions on different exchanges are independently
margined. A sharp price divergence can force liquidation on one leg while
the other shows profit. This module quantifies that risk.
"""

import numpy as np
import pandas as pd
from scipy import stats


def price_spread_stats(
    prices_a: pd.Series,
    prices_b: pd.Series,
) -> dict:
    """Compute statistics on price spread between two exchanges.

    Args:
        prices_a: Mark/close prices from exchange A.
        prices_b: Mark/close prices from exchange B (same timestamps).

    Returns:
        Dict with spread statistics (in price terms and bps).
    """
    spread = prices_a - prices_b
    mid = (prices_a + prices_b) / 2
    spread_bps = (spread / mid) * 10_000  # basis points

    return {
        "mean_spread_usd": spread.mean(),
        "std_spread_usd": spread.std(),
        "max_spread_usd": spread.abs().max(),
        "mean_spread_bps": spread_bps.mean(),
        "std_spread_bps": spread_bps.std(),
        "max_spread_bps": spread_bps.abs().max(),
        "correlation": prices_a.corr(prices_b),
    }


def rolling_correlation(
    prices_a: pd.Series,
    prices_b: pd.Series,
    window: int = 24,  # 24 periods = 24*8h = 8 days
) -> pd.Series:
    """Rolling correlation between exchange prices."""
    return prices_a.rolling(window).corr(prices_b)


def basis_var(
    spread_bps: pd.Series,
    confidence: float = 0.99,
    holding_periods: int = 1,
) -> float:
    """Value-at-Risk of basis spread over holding period.

    Returns VaR in basis points (positive = loss direction).
    Uses historical simulation.
    """
    if holding_periods > 1:
        # Roll up to holding period returns
        spread_bps = spread_bps.rolling(holding_periods).sum().dropna()

    return np.percentile(spread_bps.abs().dropna(), confidence * 100)


def basis_cvar(
    spread_bps: pd.Series,
    confidence: float = 0.99,
    holding_periods: int = 1,
) -> float:
    """Conditional VaR (Expected Shortfall) of basis spread."""
    if holding_periods > 1:
        spread_bps = spread_bps.rolling(holding_periods).sum().dropna()

    var = basis_var(spread_bps, confidence, holding_periods=1)
    tail = spread_bps.abs().dropna()
    return tail[tail >= var].mean()


def liquidation_margin_simulation(
    price_series: pd.Series,
    leverage: float = 3.0,
    maintenance_margin: float = 0.005,  # 0.5% typical
    initial_margin: float | None = None,
    holding_period_hours: int = 8,
) -> dict:
    """Simulate margin safety across price movements.

    For a given leverage, compute how often the price move over a holding
    period would bring the position close to liquidation.

    Args:
        price_series: Hourly or 8h prices.
        leverage: Position leverage (e.g., 3x).
        maintenance_margin: Exchange maintenance margin requirement.
        initial_margin: Starting margin ratio (default: 1/leverage).
        holding_period_hours: Hours between margin checks.

    Returns:
        Dict with liquidation risk metrics.
    """
    if initial_margin is None:
        initial_margin = 1.0 / leverage

    # Price changes over holding period
    pct_changes = price_series.pct_change(periods=1).dropna()

    # For a leveraged position, PnL = leverage * price_change * direction
    # Margin ratio after move = initial_margin + pnl (as fraction)
    # Liquidation when margin_ratio < maintenance_margin

    # Worst case: adverse move on one leg
    adverse_moves = pct_changes.abs()  # absolute price change
    margin_after = initial_margin - leverage * adverse_moves

    liquidation_events = (margin_after < maintenance_margin).sum()
    close_calls = (margin_after < 2 * maintenance_margin).sum()
    total = len(margin_after)

    return {
        "leverage": leverage,
        "initial_margin": initial_margin,
        "maintenance_margin": maintenance_margin,
        "liquidation_frequency": liquidation_events / total if total > 0 else 0,
        "close_call_frequency": close_calls / total if total > 0 else 0,
        "worst_margin": margin_after.min(),
        "median_margin": margin_after.median(),
        "margin_at_risk_99": np.percentile(margin_after.dropna(), 1),  # 1st percentile
        "n_observations": total,
    }


def comprehensive_basis_analysis(
    prices_a: pd.Series,
    prices_b: pd.Series,
    leverage_levels: list[float] | None = None,
) -> dict:
    """Run full basis risk analysis for an exchange pair.

    Returns nested dict with spread stats, VaR, CVaR, and liquidation sims.
    """
    leverage_levels = leverage_levels or [1, 2, 3, 5]

    spread = prices_a - prices_b
    mid = (prices_a + prices_b) / 2
    spread_bps = (spread / mid) * 10_000

    result = {
        "spread_stats": price_spread_stats(prices_a, prices_b),
        "var_95_bps": basis_var(spread_bps, 0.95),
        "var_99_bps": basis_var(spread_bps, 0.99),
        "cvar_95_bps": basis_cvar(spread_bps, 0.95),
        "cvar_99_bps": basis_cvar(spread_bps, 0.99),
        "liquidation_sims": {},
    }

    for lev in leverage_levels:
        # Use exchange A prices for liquidation sim (worst-case leg)
        sim = liquidation_margin_simulation(prices_a, leverage=lev)
        result["liquidation_sims"][f"{lev}x"] = sim

    return result
