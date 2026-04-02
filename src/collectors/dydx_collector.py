"""Collect historical funding rates from dYdX v4 via Indexer API.

API: GET https://indexer.dydx.trade/v4/historicalFunding/{ticker}
Params: limit (default 100), effectiveBeforeOrAt (ISO timestamp for pagination)
Response: { historicalFunding: [{ ticker, rate, price, effectiveAt, effectiveAtHeight }] }
"""

import time
import logging
from datetime import datetime, timezone

import requests
import pandas as pd

from src.config import EXCHANGES, RAW_DIR, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)

BASE_URL = EXCHANGES["dydx"]["base_url"]

# dYdX v4 uses {ASSET}-USD format
DYDX_SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    # BNB may not be available on dYdX
}


def fetch_funding_rate_history(
    asset: str,
    since: datetime | None = None,
    limit_per_page: int = 100,
) -> pd.DataFrame:
    """Fetch historical funding rates from dYdX v4 indexer.

    Paginates backwards using effectiveBeforeOrAt cursor.
    Returns DataFrame with columns: [timestamp, funding_rate, price, exchange, asset].
    """
    ticker = DYDX_SYMBOLS.get(asset)
    if ticker is None:
        logger.warning(f"dYdX: {asset} not supported")
        return pd.DataFrame()

    since_ts = since if since else datetime(2024, 1, 1, tzinfo=timezone.utc)

    all_records = []
    cursor = None
    page = 0

    while True:
        params = {"limit": limit_per_page}
        if cursor:
            params["effectiveBeforeOrAt"] = cursor

        try:
            resp = requests.get(
                f"{BASE_URL}/historicalFunding/{ticker}",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"dYdX/{asset} page {page}: {e}")
            break

        records = data.get("historicalFunding", [])
        if not records:
            break

        for r in records:
            effective_at = r["effectiveAt"]
            ts = pd.Timestamp(effective_at)

            # Stop if we've gone past our target start date
            if ts < pd.Timestamp(since_ts):
                all_records.append({
                    "timestamp": effective_at,
                    "funding_rate": float(r["rate"]),
                    "price": float(r["price"]),
                })
                # We've reached our target, stop paginating
                break

            all_records.append({
                "timestamp": effective_at,
                "funding_rate": float(r["rate"]),
                "price": float(r["price"]),
            })
        else:
            # Didn't break — keep paginating
            # Use the oldest record's effectiveAt as cursor
            cursor = records[-1]["effectiveAt"]
            logger.info(
                f"dYdX/{asset} page {page}: {len(records)} records "
                f"(total {len(all_records)})"
            )
            page += 1
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        # Inner loop broke — we hit our target date
        logger.info(
            f"dYdX/{asset} page {page}: reached target date "
            f"(total {len(all_records)})"
        )
        break

    if not all_records:
        logger.warning(f"dYdX/{asset}: no data returned")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["exchange"] = "dydx"
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def collect_all_funding_rates(
    assets: list[str] | None = None,
    since: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Collect funding rates for all assets on dYdX v4."""
    assets = assets or list(DYDX_SYMBOLS.keys())
    results = {}

    for asset in assets:
        key = f"dydx/{asset}"
        logger.info(f"Collecting: {key}")
        try:
            df = fetch_funding_rate_history(asset, since=since)
            if not df.empty:
                out_dir = RAW_DIR / "funding_rates" / "dydx"
                out_dir.mkdir(parents=True, exist_ok=True)
                df.to_parquet(out_dir / f"{asset}.parquet", index=False)
                results[key] = df
                logger.info(f"{key}: {len(df)} records saved")
        except Exception as e:
            logger.error(f"{key}: {e}")

    return results
