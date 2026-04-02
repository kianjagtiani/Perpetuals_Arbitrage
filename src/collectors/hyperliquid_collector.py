"""Collect historical funding rates from Hyperliquid via native REST API.

API: POST https://api.hyperliquid.xyz/info
Rate limit: 1200 weight/min per IP. fundingHistory = 20 base + 1 per 20 items.
"""

import time
import logging
from datetime import datetime, timezone

import requests
import pandas as pd

from src.config import EXCHANGES, RAW_DIR, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)

BASE_URL = EXCHANGES["hyperliquid"]["base_url"]

# Hyperliquid uses coin names directly
HL_SYMBOLS = {
    "BTC": "BTC",
    "ETH": "ETH",
    "SOL": "SOL",
    "XRP": "XRP",
    "BNB": "BNB",
}


def fetch_funding_rate_history(
    asset: str,
    since: datetime | None = None,
    batch_hours: int = 500,
) -> pd.DataFrame:
    """Fetch historical funding rates from Hyperliquid.

    Hyperliquid returns max ~500 hours per request. We paginate by advancing
    startTime forward in batches.

    Returns DataFrame with columns: [timestamp, funding_rate, premium, exchange, asset].
    """
    coin = HL_SYMBOLS.get(asset)
    if coin is None:
        logger.warning(f"Hyperliquid: {asset} not supported")
        return pd.DataFrame()

    since_ms = int(since.timestamp() * 1000) if since else None
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    all_records = []
    page = 0

    # Paginate forward in time
    cursor = since_ms or (now_ms - batch_hours * 3600 * 1000)

    while cursor < now_ms:
        body = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": cursor,
        }

        try:
            resp = requests.post(f"{BASE_URL}/info", json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Hyperliquid/{asset} page {page}: {e}")
            break

        if not data:
            # No more data, advance cursor
            cursor += batch_hours * 3600 * 1000
            page += 1
            continue

        for entry in data:
            all_records.append({
                "timestamp": entry["time"],
                "funding_rate": float(entry["fundingRate"]),
                "premium": float(entry.get("premium", 0)),
            })

        # Advance past last returned timestamp
        last_ts = max(entry["time"] for entry in data)
        cursor = last_ts + 1

        logger.info(
            f"Hyperliquid/{asset} page {page}: {len(data)} records "
            f"(total {len(all_records)})"
        )

        page += 1
        time.sleep(RATE_LIMIT_SLEEP)

    if not all_records:
        logger.warning(f"Hyperliquid/{asset}: no data returned")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["exchange"] = "hyperliquid"
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def collect_all_funding_rates(
    assets: list[str] | None = None,
    since: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Collect funding rates for all assets on Hyperliquid."""
    assets = assets or list(HL_SYMBOLS.keys())
    results = {}

    for asset in assets:
        key = f"hyperliquid/{asset}"
        logger.info(f"Collecting: {key}")
        try:
            df = fetch_funding_rate_history(asset, since=since)
            if not df.empty:
                out_dir = RAW_DIR / "funding_rates" / "hyperliquid"
                out_dir.mkdir(parents=True, exist_ok=True)
                df.to_parquet(out_dir / f"{asset}.parquet", index=False)
                results[key] = df
                logger.info(f"{key}: {len(df)} records saved")
        except Exception as e:
            logger.error(f"{key}: {e}")

    return results
