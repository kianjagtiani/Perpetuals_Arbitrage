"""Exchange configurations, constants, and shared settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = ROOT_DIR / "figures"

# ── Assets ─────────────────────────────────────────────────────────────
ASSETS = ["BTC", "ETH", "SOL", "XRP", "BNB"]

# ── Exchange definitions ───────────────────────────────────────────────
EXCHANGES = {
    # CEX — 8h funding intervals
    "binance": {
        "type": "CEX",
        "funding_interval_hours": 8,
        "settlement_utc": ["00:00", "08:00", "16:00"],
        "ccxt_id": "binance",
        "symbol_template": "{asset}/USDT:USDT",
        "api_key_env": "BINANCE_API_KEY",
        "secret_env": "BINANCE_SECRET",
    },
    "bybit": {
        "type": "CEX",
        "funding_interval_hours": 8,
        "settlement_utc": ["00:00", "08:00", "16:00"],
        "ccxt_id": "bybit",
        "symbol_template": "{asset}/USDT:USDT",
        "api_key_env": "BYBIT_API_KEY",
        "secret_env": "BYBIT_SECRET",
    },
    "okx": {
        "type": "CEX",
        "funding_interval_hours": 8,
        "settlement_utc": ["00:00", "08:00", "16:00"],
        "ccxt_id": "okx",
        "symbol_template": "{asset}/USDT:USDT",
        "api_key_env": "OKX_API_KEY",
        "secret_env": "OKX_SECRET",
    },
    "bitmex": {
        "type": "CEX",
        "funding_interval_hours": 8,
        "settlement_utc": ["04:00", "12:00", "20:00"],  # 4h offset
        "ccxt_id": "bitmex",
        "symbol_template": "{asset}/USD:BTC",  # inverse contracts
        "api_key_env": "BITMEX_API_KEY",
        "secret_env": "BITMEX_SECRET",
    },
    # DEX — 1h funding intervals
    "dydx": {
        "type": "DEX",
        "funding_interval_hours": 1,
        "settlement_utc": "every_hour",
        "base_url": os.getenv("DYDX_INDEXER_URL", "https://indexer.dydx.trade/v4"),
        "symbol_template": "{asset}-USD",
    },
    "drift": {
        "type": "DEX",
        "funding_interval_hours": 1,
        "settlement_utc": "every_hour",
        "base_url": os.getenv("DRIFT_DATA_URL", "https://data.api.drift.trade"),
        "symbol_template": "{asset}-PERP",
    },
    "hyperliquid": {
        "type": "DEX",
        "funding_interval_hours": 1,
        "settlement_utc": "every_hour",
        "base_url": os.getenv("HYPERLIQUID_URL", "https://api.hyperliquid.xyz"),
        "symbol_template": "{asset}",
    },
}

# ── Fee schedule (base tier, as percentage) ────────────────────────────
FEES = {
    "binance":     {"maker": 0.0002, "taker": 0.0005},
    "bybit":       {"maker": 0.0002, "taker": 0.00055},
    "okx":         {"maker": 0.0002, "taker": 0.0005},
    "bitmex":      {"maker": -0.0001, "taker": 0.00075},  # maker rebate
    "dydx":        {"maker": 0.0002, "taker": 0.0005},
    "drift":       {"maker": 0.0002, "taker": 0.0005},
    "hyperliquid": {"maker": 0.0001, "taker": 0.00035},
}

# ── Drift market index mapping ─────────────────────────────────────────
DRIFT_MARKET_INDEX = {
    "SOL": 0,
    "BTC": 1,
    "ETH": 2,
    "XRP": 23,
    "BNB": 20,
}

# ── Collection settings ────────────────────────────────────────────────
TARGET_HISTORY_DAYS = 365  # 12 months target
MIN_HISTORY_DAYS = 180     # 6 months minimum
RATE_LIMIT_SLEEP = 0.5     # seconds between paginated requests
