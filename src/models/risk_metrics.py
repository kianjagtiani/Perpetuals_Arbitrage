"""Risk and performance metrics for strategy evaluation.

Standard quantitative finance metrics used for evaluating
funding rate arbitrage strategy performance.
"""

import numpy as np
import pandas as pd
from scipy import stats


def annualized_return(returns: pd.Series, periods_per_year: float = 1095) -> float:
    """Annualized return from periodic returns.

    Default assumes 8h periods: 365 * 3 = 1095 per year.
    """
    total = (1 + returns).prod()
    n = len(returns)
    if n == 0 or total <= 0:
        return 0.0
    return total ** (periods_per_year / n) - 1


def annualized_volatility(returns: pd.Series, periods_per_year: float = 1095) -> float:
    """Annualized volatility."""
    return returns.std() * np.sqrt(periods_per_year)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: float = 1095,
) -> float:
    """Annualized Sharpe ratio.

    Args:
        returns: Period returns.
        risk_free_rate: Annual risk-free rate (default 5%).
        periods_per_year: Periods per year (1095 for 8h).
    """
    ann_ret = annualized_return(returns, periods_per_year)
    ann_vol = annualized_volatility(returns, periods_per_year)

    if ann_vol == 0:
        return 0.0

    return (ann_ret - risk_free_rate) / ann_vol


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: float = 1095,
) -> float:
    """Sortino ratio — uses downside deviation instead of total volatility."""
    ann_ret = annualized_return(returns, periods_per_year)
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1

    downside = returns[returns < rf_per_period] - rf_per_period
    downside_dev = np.sqrt((downside ** 2).mean()) * np.sqrt(periods_per_year)

    if downside_dev == 0:
        return 0.0

    return (ann_ret - risk_free_rate) / downside_dev


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown as a positive fraction (e.g., 0.05 = 5% drawdown)."""
    peak = equity_curve.expanding().max()
    drawdown = (equity_curve - peak) / peak
    return abs(drawdown.min())


def calmar_ratio(
    returns: pd.Series,
    periods_per_year: float = 1095,
) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    equity = (1 + returns).cumprod()
    mdd = max_drawdown(equity)

    if mdd == 0:
        return 0.0

    return annualized_return(returns, periods_per_year) / mdd


def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR at given confidence level.

    Returns the loss threshold (positive number).
    """
    return -np.percentile(returns.dropna(), (1 - confidence) * 100)


def conditional_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall) at given confidence level."""
    var = value_at_risk(returns, confidence)
    tail = returns[returns <= -var]
    if tail.empty:
        return var
    return -tail.mean()


def hit_rate(returns: pd.Series) -> float:
    """Fraction of periods with positive returns."""
    return (returns > 0).mean()


def profit_factor(returns: pd.Series) -> float:
    """Gross profit / gross loss."""
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def ttest_positive_mean(returns: pd.Series) -> tuple[float, float]:
    """One-sided t-test: H0: mean return <= 0, H1: mean return > 0.

    Returns (t_statistic, p_value).
    """
    t_stat, p_two = stats.ttest_1samp(returns.dropna(), 0)
    p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
    return t_stat, p_one


def bootstrap_metric(
    returns: pd.Series,
    metric_fn,
    n_bootstrap: int = 10_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    """Bootstrap confidence interval for any metric function.

    Args:
        returns: Return series.
        metric_fn: Function that takes returns Series and returns a scalar.
        n_bootstrap: Number of bootstrap resamples.
        confidence: Confidence level for CI.
        seed: Random seed for reproducibility.

    Returns:
        Dict with point_estimate, ci_lower, ci_upper, std_error.
    """
    rng = np.random.RandomState(seed)
    n = len(returns)
    point = metric_fn(returns)

    boot_values = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample = returns.iloc[rng.randint(0, n, size=n)]
        boot_values[i] = metric_fn(sample)

    alpha = (1 - confidence) / 2
    ci_lower = np.percentile(boot_values, alpha * 100)
    ci_upper = np.percentile(boot_values, (1 - alpha) * 100)

    return {
        "point_estimate": point,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "std_error": boot_values.std(),
    }


def compute_all_metrics(
    returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: float = 1095,
    n_bootstrap: int = 10_000,
) -> dict:
    """Compute comprehensive performance metrics.

    Returns dict with all standard metrics plus bootstrap CIs for key ones.
    """
    equity = (1 + returns).cumprod()

    metrics = {
        "n_periods": len(returns),
        "total_return": (1 + returns).prod() - 1,
        "annualized_return": annualized_return(returns, periods_per_year),
        "annualized_volatility": annualized_volatility(returns, periods_per_year),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate, periods_per_year),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate, periods_per_year),
        "max_drawdown": max_drawdown(equity),
        "calmar_ratio": calmar_ratio(returns, periods_per_year),
        "var_95": value_at_risk(returns, 0.95),
        "var_99": value_at_risk(returns, 0.99),
        "cvar_95": conditional_var(returns, 0.95),
        "cvar_99": conditional_var(returns, 0.99),
        "hit_rate": hit_rate(returns),
        "profit_factor": profit_factor(returns),
    }

    # Statistical significance
    t_stat, p_val = ttest_positive_mean(returns)
    metrics["ttest_t_stat"] = t_stat
    metrics["ttest_p_value"] = p_val

    # Bootstrap CIs for Sharpe and total return
    sharpe_fn = lambda r: sharpe_ratio(r, risk_free_rate, periods_per_year)
    total_fn = lambda r: (1 + r).prod() - 1

    metrics["sharpe_bootstrap"] = bootstrap_metric(returns, sharpe_fn, n_bootstrap)
    metrics["total_return_bootstrap"] = bootstrap_metric(returns, total_fn, n_bootstrap)

    return metrics
