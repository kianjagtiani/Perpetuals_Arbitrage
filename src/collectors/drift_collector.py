"""Collect historical funding rates from Drift Protocol via REST API.

API: https://data.api.drift.trade
- Recent: GET /market/{symbol}/fundingRates?limit=750
- Historical: GET /market/{symbol}/fundingRates/{year}/{month}/{day}

The data API returns already-converted values (not raw on-chain precision):
  fundingRate: dollar amount per unit of base asset
  oraclePriceTwap: oracle price in USD
  rate = fundingRate / oraclePriceTwap (gives decimal rate per hour)
"""

import time
import logging
from datetime import datetime, date, timedelta, timezone

import requests
import pandas as pd

from src.config import EXCHANGES, DRIFT_MARKET_INDEX, RAW_DIR, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)

BASE_URL = EXCHANGES["drift"]["base_url"]

# Drift uses {ASSET}-PERP symbol format
DRIFT_SYMBOLS = {
    "SOL": "SOL-PERP",
    "BTC": "BTC-PERP",
    "ETH": "ETH-PERP",
    "XRP": "XRP-PERP",
    "BNB": "BNB-PERP",
}


def _convert_funding_rate(record: dict) -> float:
    """Convert Drift's funding rate to a decimal rate.

    The data API returns already-converted values:
      fundingRate: dollar funding amount per unit
      oraclePriceTwap: oracle price in USD
    Rate = fundingRate / oraclePriceTwap
    """
    funding_raw = float(record.get("fundingRate", 0))
    oracle_twap = float(record.get("oraclePriceTwap", 1))

    if oracle_twap == 0:
        return 0.0

    return funding_raw / oracle_twap


def fetch_funding_rates_recent(
    asset: str,
    limit: int = 750,
) -> pd.DataFrame:
    """Fetch recent funding rates (last ~31 days) using paginated endpoint."""
    symbol = DRIFT_SYMBOLS.get(asset)
    if symbol is None:
        logger.warning(f"Drift: {asset} not supported")
        return pd.DataFrame()

    all_records = []
    next_page = None
    page = 0

    while True:
        params = {"limit": limit}
        if next_page:
            params["page"] = next_page

        try:
            resp = requests.get(
                f"{BASE_URL}/market/{symbol}/fundingRates",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Drift/{asset} page {page}: {e}")
            break

        if not data.get("success") or not data.get("records"):
            break

        for r in data["records"]:
            all_records.append({
                "timestamp": r["ts"],
                "funding_rate": _convert_funding_rate(r),
                "funding_rate_long": float(r.get("fundingRateLong", 0)) / 1e9,
                "funding_rate_short": float(r.get("fundingRateShort", 0)) / 1e9,
                "oracle_price_twap": float(r.get("oraclePriceTwap", 0)) / 1e6,
                "mark_price_twap": float(r.get("markPriceTwap", 0)) / 1e6,
            })

        logger.info(
            f"Drift/{asset} recent page {page}: {len(data['records'])} records "
            f"(total {len(all_records)})"
        )

        next_page = data.get("meta", {}).get("nextPage")
        if next_page is None:
            break

        page += 1
        time.sleep(RATE_LIMIT_SLEEP)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["exchange"] = "drift"
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_funding_rates_day(
    asset: str,
    target_date: date,
) -> pd.DataFrame:
    """Fetch funding rates for a specific day using the historical endpoint."""
    symbol = DRIFT_SYMBOLS.get(asset)
    if symbol is None:
        return pd.DataFrame()

    all_records = []
    page = 1

    while True:
        url = (
            f"{BASE_URL}/market/{symbol}/fundingRates"
            f"/{target_date.year}/{target_date.month}/{target_date.day}"
        )

        try:
            resp = requests.get(url, params={"page": page}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Drift/{asset}/{target_date} page {page}: {e}")
            break

        if not data.get("success") or not data.get("records"):
            break

        for r in data["records"]:
            all_records.append({
                "timestamp": r["ts"],
                "funding_rate": _convert_funding_rate(r),
                "funding_rate_long": float(r.get("fundingRateLong", 0)) / 1e9,
                "funding_rate_short": float(r.get("fundingRateShort", 0)) / 1e9,
                "oracle_price_twap": float(r.get("oraclePriceTwap", 0)) / 1e6,
                "mark_price_twap": float(r.get("markPriceTwap", 0)) / 1e6,
            })

        meta = data.get("meta", {})
        next_page = meta.get("nextPage")
        if next_page is None:
            break

        page = next_page
        time.sleep(RATE_LIMIT_SLEEP)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["exchange"] = "drift"
    df["asset"] = asset
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def fetch_funding_rate_history(
    asset: str,
    since: datetime | None = None,
) -> pd.DataFrame:
    """Fetch full historical funding rates by iterating day-by-day.

    Falls back to recent endpoint for the last ~31 days.
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=365)

    start_date = since.date()
    end_date = date.today()

    all_dfs = []
    current = start_date

    while current <= end_date:
        logger.info(f"Drift/{asset}: fetching {current}")
        df = fetch_funding_rates_day(asset, current)
        if not df.empty:
            all_dfs.append(df)
        current += timedelta(days=1)
        time.sleep(RATE_LIMIT_SLEEP * 0.5)

    if not all_dfs:
        logger.warning(f"Drift/{asset}: no historical data, trying recent endpoint")
        return fetch_funding_rates_recent(asset)

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return combined


def collect_all_funding_rates(
    assets: list[str] | None = None,
    since: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Collect funding rates for all assets on Drift."""
    assets = assets or list(DRIFT_SYMBOLS.keys())
    results = {}

    for asset in assets:
        key = f"drift/{asset}"
        logger.info(f"Collecting: {key}")
        try:
            df = fetch_funding_rate_history(asset, since=since)
            if not df.empty:
                out_dir = RAW_DIR / "funding_rates" / "drift"
                out_dir.mkdir(parents=True, exist_ok=True)
                df.to_parquet(out_dir / f"{asset}.parquet", index=False)
                results[key] = df
                logger.info(f"{key}: {len(df)} records saved")
        except Exception as e:
            logger.error(f"{key}: {e}")

    return results
