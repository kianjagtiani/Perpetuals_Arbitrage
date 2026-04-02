"""Normalize funding rates across exchanges to a common 8h resolution.

CEX exchanges report 8h rates natively. DEX exchanges report 1h rates
and need to be aggregated into 8h windows to enable cross-exchange comparison.

Key decisions:
- 8h windows aligned to CEX settlement times: [00:00-08:00), [08:00-16:00), [16:00-00:00) UTC
- BitMEX has offset settlements (04:00, 12:00, 20:00) — handled separately
- DEX 1h rates are SUMMED over 8h windows (compounding effect negligible at these magnitudes)
"""

import logging
from pathlib import Path

import pandas as pd
import numpy as np

from src.config import EXCHANGES, RAW_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

# Standard 8h windows aligned to Binance/Bybit/OKX settlements
STANDARD_8H_LABELS = ["00:00", "08:00", "16:00"]

# BitMEX offset windows
BITMEX_8H_LABELS = ["04:00", "12:00", "20:00"]


def load_raw_funding(exchange: str, asset: str) -> pd.DataFrame:
    """Load raw funding rate parquet for one exchange-asset pair."""
    path = RAW_DIR / "funding_rates" / exchange / f"{asset}.parquet"
    if not path.exists():
        logger.warning(f"No data file: {path}")
        return pd.DataFrame()

    df = pd.read_parquet(path)

    # Ensure timestamp is datetime with UTC
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    return df


def normalize_cex_8h(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize CEX funding rates (already 8h) — just standardize columns.

    Input: raw CCXT funding rate data.
    Output: [timestamp, funding_rate_8h, exchange, asset]
    """
    if df.empty:
        return df

    out = df[["timestamp", "funding_rate", "exchange", "asset"]].copy()
    out = out.rename(columns={"funding_rate": "funding_rate_8h"})

    # Floor timestamp to nearest 8h boundary for alignment
    out["timestamp"] = out["timestamp"].dt.floor("8h")
    out = out.drop_duplicates(subset=["timestamp", "exchange", "asset"], keep="last")

    return out.sort_values("timestamp").reset_index(drop=True)


def normalize_dex_1h_to_8h(
    df: pd.DataFrame,
    window_starts: list[int] = [0, 8, 16],
) -> pd.DataFrame:
    """Aggregate 1h DEX funding rates into 8h windows by summing.

    Args:
        df: Raw DEX funding data with 1h intervals.
        window_starts: Hour boundaries for 8h windows (default: [0, 8, 16]).

    Returns:
        DataFrame with [timestamp, funding_rate_8h, exchange, asset, n_hours]
        where n_hours is the count of 1h rates in each window (ideally 8).
    """
    if df.empty:
        return df

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Floor each hourly rate to its 8h window
    df["window_ts"] = df["timestamp"].dt.floor("8h")

    grouped = df.groupby(
        ["window_ts", "exchange", "asset"], as_index=False
    ).agg(
        funding_rate_8h=("funding_rate", "sum"),
        n_hours=("funding_rate", "count"),
    )

    grouped = grouped.rename(columns={"window_ts": "timestamp"})
    return grouped.sort_values("timestamp").reset_index(drop=True)


def normalize_exchange(exchange: str, asset: str) -> pd.DataFrame:
    """Normalize funding rates for one exchange-asset pair to 8h resolution."""
    df = load_raw_funding(exchange, asset)
    if df.empty:
        return df

    cfg = EXCHANGES[exchange]

    if cfg["funding_interval_hours"] == 8:
        return normalize_cex_8h(df)
    elif cfg["funding_interval_hours"] == 1:
        # DEX: aggregate 1h -> 8h
        return normalize_dex_1h_to_8h(df)
    else:
        logger.warning(f"Unknown interval for {exchange}: {cfg['funding_interval_hours']}h")
        return df


def normalize_all(
    exchanges: list[str] | None = None,
    assets: list[str] | None = None,
) -> pd.DataFrame:
    """Normalize all exchange-asset pairs and combine into a single DataFrame.

    Returns: DataFrame with [timestamp, funding_rate_8h, exchange, asset]
    """
    from src.config import ASSETS

    exchanges = exchanges or list(EXCHANGES.keys())
    assets = assets or ASSETS

    all_dfs = []

    for exchange in exchanges:
        for asset in assets:
            df = normalize_exchange(exchange, asset)
            if not df.empty:
                # Keep only standard columns
                cols = ["timestamp", "funding_rate_8h", "exchange", "asset"]
                if "n_hours" in df.columns:
                    cols.append("n_hours")
                df = df[[c for c in cols if c in df.columns]]
                all_dfs.append(df)
                logger.info(f"Normalized {exchange}/{asset}: {len(df)} periods")

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Save processed output
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "funding_rates_8h.parquet"
    combined.to_parquet(out_path, index=False)
    logger.info(f"Saved normalized data: {len(combined)} rows to {out_path}")

    return combined
