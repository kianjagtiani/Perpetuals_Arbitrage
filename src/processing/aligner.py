"""Temporal alignment of normalized funding rates across exchanges.

Produces a wide-format DataFrame where each column is an exchange's funding rate
at each 8h timestamp, enabling direct cross-exchange spread computation.

Also handles:
- BitMEX's 4h offset (04:00/12:00/20:00 vs standard 00:00/08:00/16:00)
- Missing data forward-fill within reason (max 1 period)
- Coverage reporting
"""

import logging
from itertools import combinations

import pandas as pd
import numpy as np

from src.config import EXCHANGES, PROCESSED_DIR

logger = logging.getLogger(__name__)


def align_funding_rates(
    df: pd.DataFrame,
    handle_bitmex_offset: bool = True,
    ffill_limit: int = 1,
) -> pd.DataFrame:
    """Pivot normalized funding rates into wide format aligned by timestamp.

    Args:
        df: Normalized 8h funding rates (long format) with columns
            [timestamp, funding_rate_8h, exchange, asset].
        handle_bitmex_offset: If True, shift BitMEX timestamps by -4h to align
            with standard settlement windows. This is an approximation that
            enables direct comparison, with the caveat noted in analysis.
        ffill_limit: Max number of missing periods to forward-fill (default 1 = 8h).

    Returns:
        DataFrame with MultiIndex columns (exchange, asset) and DatetimeIndex.
    """
    if df.empty:
        return df

    df = df.copy()

    # Handle BitMEX offset: shift 4h back to align with standard windows
    # BitMEX settles at 04:00 -> maps to 00:00 window
    # BitMEX settles at 12:00 -> maps to 08:00 window
    # BitMEX settles at 20:00 -> maps to 16:00 window
    if handle_bitmex_offset:
        mask = df["exchange"] == "bitmex"
        df.loc[mask, "timestamp"] = df.loc[mask, "timestamp"] - pd.Timedelta(hours=4)

    # Pivot to wide format: rows=timestamp, columns=(exchange, asset)
    wide = df.pivot_table(
        index="timestamp",
        columns=["exchange", "asset"],
        values="funding_rate_8h",
        aggfunc="last",  # take last if duplicates
    )

    # Sort index
    wide = wide.sort_index()

    # Forward-fill small gaps (max 1 period = 8h)
    if ffill_limit > 0:
        wide = wide.ffill(limit=ffill_limit)

    return wide


def compute_coverage(wide: pd.DataFrame) -> pd.DataFrame:
    """Compute data coverage statistics per exchange-asset pair.

    Returns DataFrame with columns:
        exchange, asset, total_periods, non_null, coverage_pct,
        first_date, last_date, gaps_count
    """
    records = []

    for exchange, asset in wide.columns:
        series = wide[(exchange, asset)]
        total = len(series)
        non_null = series.notna().sum()
        coverage = non_null / total * 100 if total > 0 else 0

        # Count gaps (consecutive NaN sequences)
        is_gap = series.isna()
        gap_starts = is_gap & ~is_gap.shift(1, fill_value=False)
        gaps = gap_starts.sum()

        # Date range
        valid = series.dropna()
        first = valid.index.min() if not valid.empty else None
        last = valid.index.max() if not valid.empty else None

        records.append({
            "exchange": exchange,
            "asset": asset,
            "total_periods": total,
            "non_null": non_null,
            "coverage_pct": round(coverage, 1),
            "first_date": first,
            "last_date": last,
            "gaps_count": gaps,
        })

    return pd.DataFrame(records).sort_values(["asset", "exchange"]).reset_index(drop=True)


def compute_spreads(wide: pd.DataFrame, asset: str) -> pd.DataFrame:
    """Compute pairwise funding rate spreads for a single asset.

    Spread = exchange_A rate - exchange_B rate
    For arbitrage: short the higher-rate exchange, long the lower-rate exchange.

    Returns long-format DataFrame with columns:
        [timestamp, exchange_long, exchange_short, spread, asset]
    """
    # Get exchanges that have data for this asset
    available = [ex for ex, a in wide.columns if a == asset]
    available = sorted(set(available))

    if len(available) < 2:
        logger.warning(f"{asset}: fewer than 2 exchanges with data")
        return pd.DataFrame()

    records = []

    for ex_a, ex_b in combinations(available, 2):
        rate_a = wide[(ex_a, asset)]
        rate_b = wide[(ex_b, asset)]
        spread = rate_a - rate_b

        # Drop NaN spreads
        valid = spread.dropna()

        for ts, s in valid.items():
            # Convention: positive spread means ex_a has higher rate
            # Strategy: short ex_a (receive funding), long ex_b (pay funding)
            if s >= 0:
                records.append({
                    "timestamp": ts,
                    "exchange_short": ex_a,  # short high-rate
                    "exchange_long": ex_b,   # long low-rate
                    "spread": s,
                    "asset": asset,
                })
            else:
                records.append({
                    "timestamp": ts,
                    "exchange_short": ex_b,
                    "exchange_long": ex_a,
                    "spread": abs(s),
                    "asset": asset,
                })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)


def align_and_save(
    normalized_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full alignment pipeline: load, align, compute coverage, save.

    Returns: (wide_df, coverage_df)
    """
    if normalized_df is None:
        path = PROCESSED_DIR / "funding_rates_8h.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Normalized data not found: {path}")
        normalized_df = pd.read_parquet(path)

    wide = align_funding_rates(normalized_df)
    coverage = compute_coverage(wide)

    # Save
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(PROCESSED_DIR / "funding_rates_aligned.parquet")
    coverage.to_parquet(PROCESSED_DIR / "coverage_report.parquet", index=False)

    logger.info(f"Aligned data: {wide.shape[0]} timestamps x {wide.shape[1]} series")
    logger.info(f"Coverage:\n{coverage.to_string()}")

    return wide, coverage
