"""Collect historical funding rates and prices from CEX exchanges via CCXT.

Supports: Binance, Bybit, OKX, BitMEX.
"""

import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd

from src.config import EXCHANGES, ASSETS, RAW_DIR, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)

CEX_EXCHANGES = ["binance", "bybit", "okx", "bitmex"]

# Per-exchange max page sizes (some exchanges have lower limits)
MAX_PAGE_SIZE = {
    "bitmex": 500,
}


def _make_exchange(exchange_name: str) -> ccxt.Exchange:
    """Instantiate a CCXT exchange with public-only access."""
    cfg = EXCHANGES[exchange_name]
    cls = getattr(ccxt, cfg["ccxt_id"])
    return cls({"enableRateLimit": True})


def _symbol(exchange_name: str, asset: str) -> str:
    return EXCHANGES[exchange_name]["symbol_template"].format(asset=asset)


def fetch_funding_rate_history(
    exchange_name: str,
    asset: str,
    since: datetime | None = None,
    limit_per_page: int = 1000,
) -> pd.DataFrame:
    """Fetch full funding rate history for one exchange-asset pair.

    Returns DataFrame with columns: [timestamp, datetime, funding_rate, exchange, asset].
    """
    ex = _make_exchange(exchange_name)
    symbol = _symbol(exchange_name, asset)
    since_ms = int(since.timestamp() * 1000) if since else None
    limit_per_page = min(limit_per_page, MAX_PAGE_SIZE.get(exchange_name, limit_per_page))

    all_records = []
    page = 0

    while True:
        try:
            rates = ex.fetch_funding_rate_history(
                symbol, since=since_ms, limit=limit_per_page
            )
        except Exception as e:
            logger.warning(f"{exchange_name}/{asset} page {page}: {e}")
            break

        if not rates:
            break

        for r in rates:
            all_records.append({
                "timestamp": r["timestamp"],
                "datetime": r["datetime"],
                "funding_rate": r["fundingRate"],
            })

        logger.info(
            f"{exchange_name}/{asset} page {page}: {len(rates)} records "
            f"(total {len(all_records)})"
        )

        # Advance pagination cursor
        since_ms = rates[-1]["timestamp"] + 1
        page += 1
        time.sleep(RATE_LIMIT_SLEEP)

    if not all_records:
        logger.warning(f"{exchange_name}/{asset}: no funding rate data returned")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["exchange"] = exchange_name
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["datetime"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_ohlcv(
    exchange_name: str,
    asset: str,
    timeframe: str = "1h",
    since: datetime | None = None,
    limit_per_page: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV price data for one exchange-asset pair."""
    ex = _make_exchange(exchange_name)
    symbol = _symbol(exchange_name, asset)
    since_ms = int(since.timestamp() * 1000) if since else None

    all_candles = []
    page = 0

    while True:
        try:
            candles = ex.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since_ms, limit=limit_per_page
            )
        except Exception as e:
            logger.warning(f"{exchange_name}/{asset} OHLCV page {page}: {e}")
            break

        if not candles:
            break

        all_candles.extend(candles)
        logger.info(
            f"{exchange_name}/{asset} OHLCV page {page}: {len(candles)} candles "
            f"(total {len(all_candles)})"
        )

        since_ms = candles[-1][0] + 1
        page += 1
        time.sleep(RATE_LIMIT_SLEEP)

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["exchange"] = exchange_name
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def save_parquet(df: pd.DataFrame, category: str, exchange_name: str, asset: str) -> Path:
    """Save DataFrame to parquet in raw data directory."""
    out_dir = RAW_DIR / category / exchange_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{asset}.parquet"
    df.to_parquet(path, index=False)
    logger.info(f"Saved {len(df)} rows to {path}")
    return path


def collect_all_funding_rates(
    exchanges: list[str] | None = None,
    assets: list[str] | None = None,
    since: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Collect funding rates for all CEX exchange-asset combinations."""
    exchanges = exchanges or CEX_EXCHANGES
    assets = assets or ASSETS
    results = {}

    for ex_name in exchanges:
        for asset in assets:
            key = f"{ex_name}/{asset}"
            logger.info(f"Collecting funding rates: {key}")
            try:
                df = fetch_funding_rate_history(ex_name, asset, since=since)
                if not df.empty:
                    save_parquet(df, "funding_rates", ex_name, asset)
                    results[key] = df
                else:
                    logger.warning(f"{key}: empty result")
            except Exception as e:
                logger.error(f"{key}: {e}")

    return results


def collect_all_prices(
    exchanges: list[str] | None = None,
    assets: list[str] | None = None,
    since: datetime | None = None,
    timeframe: str = "1h",
) -> dict[str, pd.DataFrame]:
    """Collect OHLCV prices for all CEX exchange-asset combinations."""
    exchanges = exchanges or CEX_EXCHANGES
    assets = assets or ASSETS
    results = {}

    for ex_name in exchanges:
        for asset in assets:
            key = f"{ex_name}/{asset}"
            logger.info(f"Collecting prices: {key}")
            try:
                df = fetch_ohlcv(ex_name, asset, timeframe=timeframe, since=since)
                if not df.empty:
                    save_parquet(df, "prices", ex_name, asset)
                    results[key] = df
            except Exception as e:
                logger.error(f"{key}: {e}")

    return results
