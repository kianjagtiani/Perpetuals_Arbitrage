"""Data cleaning: outlier detection, gap handling, quality flags.

Applied after normalization but before analysis. Identifies suspicious data
points that could distort statistical analysis.
"""

import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def detect_outliers_zscore(
    series: pd.Series,
    threshold: float = 5.0,
) -> pd.Series:
    """Flag outliers using z-score method.

    Funding rates can legitimately spike (e.g., during squeezes), so we use
    a generous threshold (5 sigma) to only catch data errors, not real events.

    Returns boolean Series (True = outlier).
    """
    if series.dropna().empty:
        return pd.Series(False, index=series.index)

    mean = series.mean()
    std = series.std()

    if std == 0:
        return pd.Series(False, index=series.index)

    z_scores = (series - mean).abs() / std
    return z_scores > threshold


def detect_outliers_iqr(
    series: pd.Series,
    multiplier: float = 5.0,
) -> pd.Series:
    """Flag outliers using IQR method (robust to non-normal distributions).

    Returns boolean Series (True = outlier).
    """
    if series.dropna().empty:
        return pd.Series(False, index=series.index)

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return pd.Series(False, index=series.index)

    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    return (series < lower) | (series > upper)


def flag_stale_prices(
    series: pd.Series,
    max_identical: int = 5,
) -> pd.Series:
    """Flag sequences where the funding rate is identical for too many periods.

    This can indicate stale/frozen data feeds.
    Returns boolean Series (True = potentially stale).
    """
    if series.dropna().empty:
        return pd.Series(False, index=series.index)

    # Count consecutive identical values
    different = series != series.shift(1)
    groups = different.cumsum()
    group_sizes = groups.map(groups.value_counts())

    return group_sizes >= max_identical


def clean_funding_rates(
    df: pd.DataFrame,
    zscore_threshold: float = 5.0,
    iqr_multiplier: float = 5.0,
    max_stale: int = 5,
    replace_outliers: bool = False,
) -> pd.DataFrame:
    """Clean funding rate data by detecting (and optionally replacing) outliers.

    Args:
        df: Long-format normalized funding rates.
        zscore_threshold: Z-score threshold for outlier detection.
        iqr_multiplier: IQR multiplier for outlier detection.
        max_stale: Max consecutive identical values before flagging as stale.
        replace_outliers: If True, replace outliers with NaN. If False, only flag them.

    Returns:
        DataFrame with additional columns:
            is_outlier_zscore, is_outlier_iqr, is_stale, funding_rate_clean
    """
    df = df.copy()

    # Initialize flag columns
    df["is_outlier_zscore"] = False
    df["is_outlier_iqr"] = False
    df["is_stale"] = False

    # Apply outlier detection per exchange-asset group
    for (exchange, asset), group in df.groupby(["exchange", "asset"]):
        idx = group.index
        rates = group["funding_rate_8h"]

        df.loc[idx, "is_outlier_zscore"] = detect_outliers_zscore(rates, zscore_threshold)
        df.loc[idx, "is_outlier_iqr"] = detect_outliers_iqr(rates, iqr_multiplier)
        df.loc[idx, "is_stale"] = flag_stale_prices(rates, max_stale)

    # Combined outlier flag (both methods agree)
    df["is_outlier"] = df["is_outlier_zscore"] & df["is_outlier_iqr"]

    # Clean version: replace outliers with NaN if requested
    df["funding_rate_clean"] = df["funding_rate_8h"]
    if replace_outliers:
        df.loc[df["is_outlier"], "funding_rate_clean"] = np.nan

    # Summary
    n_outliers = df["is_outlier"].sum()
    n_stale = df["is_stale"].sum()
    total = len(df)
    logger.info(
        f"Cleaning: {n_outliers}/{total} outliers ({n_outliers/total*100:.2f}%), "
        f"{n_stale}/{total} stale ({n_stale/total*100:.2f}%)"
    )

    return df


def generate_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Generate a per-exchange-asset quality summary.

    Returns DataFrame with quality metrics per pair.
    """
    records = []

    for (exchange, asset), group in df.groupby(["exchange", "asset"]):
        rates = group["funding_rate_8h"]
        records.append({
            "exchange": exchange,
            "asset": asset,
            "n_observations": len(group),
            "n_missing": rates.isna().sum(),
            "n_outliers": group["is_outlier"].sum() if "is_outlier" in group.columns else 0,
            "n_stale": group["is_stale"].sum() if "is_stale" in group.columns else 0,
            "mean_rate": rates.mean(),
            "median_rate": rates.median(),
            "std_rate": rates.std(),
            "min_rate": rates.min(),
            "max_rate": rates.max(),
            "pct_positive": (rates > 0).mean() * 100,
            "first_date": group["timestamp"].min(),
            "last_date": group["timestamp"].max(),
        })

    return pd.DataFrame(records).sort_values(["asset", "exchange"]).reset_index(drop=True)
