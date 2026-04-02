"""Transaction cost modeling for cross-exchange funding rate arbitrage.

Costs include:
1. Trading fees (maker/taker, per exchange, per leg)
2. Slippage estimation as f(trade_size, volatility)
3. DEX gas costs (Solana tx for Drift, negligible for dYdX/Hyperliquid)
4. Break-even spread calculation
"""

import numpy as np
import pandas as pd

from src.config import FEES


# DEX gas costs in USD (approximate)
GAS_COSTS_USD = {
    "drift": 0.01,        # Solana tx fee (~0.000005 SOL * ~$200)
    "dydx": 0.0,          # No gas on dYdX v4 (Cosmos-based, fees in USDC)
    "hyperliquid": 0.0,   # L1, no gas for trading
    "binance": 0.0,
    "bybit": 0.0,
    "okx": 0.0,
    "bitmex": 0.0,
}


def trading_fee_round_trip(
    exchange_a: str,
    exchange_b: str,
    order_type: str = "taker",
) -> float:
    """Calculate total round-trip trading fees for a pair trade.

    A round trip = open both legs + close both legs = 4 trades.
    Returns fee as a fraction of notional (e.g., 0.002 = 0.2%).
    """
    fee_key = "taker" if order_type == "taker" else "maker"

    fee_a = FEES[exchange_a][fee_key]
    fee_b = FEES[exchange_b][fee_key]

    # Open: 1 trade on each exchange. Close: 1 trade on each exchange.
    return 2 * (fee_a + fee_b)


def estimate_slippage(
    trade_size_usd: float,
    daily_volume_usd: float = 1e9,
    volatility: float = 0.02,
    impact_coefficient: float = 0.1,
) -> float:
    """Estimate market impact / slippage using square-root model.

    Slippage ≈ impact_coefficient * volatility * sqrt(trade_size / daily_volume)

    Returns slippage as a fraction of notional (one-way).
    """
    if daily_volume_usd <= 0:
        return 0.01  # Conservative 1% if no volume data

    participation = trade_size_usd / daily_volume_usd
    return impact_coefficient * volatility * np.sqrt(participation)


def gas_cost_fraction(
    exchange: str,
    notional_usd: float,
) -> float:
    """Gas cost as fraction of notional value."""
    if notional_usd <= 0:
        return 0.0
    return GAS_COSTS_USD.get(exchange, 0.0) / notional_usd


def total_cost_round_trip(
    exchange_a: str,
    exchange_b: str,
    notional_usd: float = 10_000,
    order_type: str = "taker",
    daily_volume_a: float = 1e9,
    daily_volume_b: float = 1e9,
    volatility: float = 0.02,
) -> dict:
    """Calculate total round-trip costs for a funding rate arbitrage trade.

    Returns dict with cost breakdown and total, all as fractions of notional.
    """
    fees = trading_fee_round_trip(exchange_a, exchange_b, order_type)

    slippage_a = estimate_slippage(notional_usd, daily_volume_a, volatility)
    slippage_b = estimate_slippage(notional_usd, daily_volume_b, volatility)
    slippage = 2 * (slippage_a + slippage_b)  # 4 trades total

    gas_a = gas_cost_fraction(exchange_a, notional_usd)
    gas_b = gas_cost_fraction(exchange_b, notional_usd)
    gas = 2 * (gas_a + gas_b)  # open + close

    total = fees + slippage + gas

    return {
        "fees": fees,
        "slippage": slippage,
        "gas": gas,
        "total": total,
        "break_even_spread_8h": total,  # min spread per 8h to be profitable
    }


def break_even_spread(
    exchange_a: str,
    exchange_b: str,
    holding_periods: int = 1,
    **kwargs,
) -> float:
    """Minimum funding rate spread needed to cover costs.

    If holding for N periods, costs are amortized: break_even = total_cost / N.
    """
    costs = total_cost_round_trip(exchange_a, exchange_b, **kwargs)
    return costs["total"] / max(holding_periods, 1)


def cost_sensitivity_analysis(
    exchange_a: str,
    exchange_b: str,
    trade_sizes: list[float] | None = None,
    fee_multipliers: list[float] | None = None,
    holding_periods: list[int] | None = None,
) -> pd.DataFrame:
    """Run cost sensitivity analysis across parameter grid.

    Returns DataFrame with columns:
        [trade_size, fee_multiplier, holding_periods, fees, slippage, gas, total, break_even]
    """
    trade_sizes = trade_sizes or [1_000, 5_000, 10_000, 25_000, 50_000, 100_000]
    fee_multipliers = fee_multipliers or [0.5, 1.0, 1.5, 2.0]
    holding_periods = holding_periods or [1, 3, 7, 14, 30]

    records = []

    for size in trade_sizes:
        for mult in fee_multipliers:
            # Temporarily scale fees
            orig_a = FEES[exchange_a].copy()
            orig_b = FEES[exchange_b].copy()

            for k in FEES[exchange_a]:
                FEES[exchange_a][k] *= mult
            for k in FEES[exchange_b]:
                FEES[exchange_b][k] *= mult

            costs = total_cost_round_trip(exchange_a, exchange_b, notional_usd=size)

            # Restore
            FEES[exchange_a] = orig_a
            FEES[exchange_b] = orig_b

            for hp in holding_periods:
                records.append({
                    "exchange_a": exchange_a,
                    "exchange_b": exchange_b,
                    "trade_size_usd": size,
                    "fee_multiplier": mult,
                    "holding_periods": hp,
                    "fees": costs["fees"] * mult,
                    "slippage": costs["slippage"],
                    "gas": costs["gas"],
                    "total_cost": costs["total"],
                    "break_even_per_period": costs["total"] / hp,
                })

    return pd.DataFrame(records)
