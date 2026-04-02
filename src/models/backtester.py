"""Event-driven backtester for cross-exchange funding rate arbitrage.

Strategy: When the funding rate spread between two exchanges exceeds a threshold,
short the high-funding-rate perp and long the low-funding-rate perp. Collect the
spread as profit each funding period.

Key features:
- Per-leg margin tracking (independent margin on each exchange)
- Configurable entry/exit thresholds
- Position sizing with leverage
- Basis risk stop-loss
- In-sample / out-of-sample split
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.models.cost_model import total_cost_round_trip

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """An open arbitrage position (two legs)."""
    open_time: pd.Timestamp
    exchange_short: str   # Short the high-funding exchange
    exchange_long: str    # Long the low-funding exchange
    asset: str
    notional: float       # USD notional per leg
    leverage: float
    entry_spread: float   # Spread at entry (8h rate)
    entry_cost: float     # Round-trip cost as fraction

    # Running state
    cumulative_pnl: float = 0.0
    periods_held: int = 0
    max_adverse_spread: float = 0.0

    def margin_per_leg(self) -> float:
        """Initial margin required per leg."""
        return self.notional / self.leverage


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    entry_threshold: float = 0.0005   # Min spread to open (0.05% per 8h)
    close_threshold: float = 0.0001   # Close when spread drops below
    max_holding_periods: int = 90     # Max ~30 days at 8h intervals
    basis_stop_loss: float = 0.005    # Close if basis exceeds 50bps
    notional_per_trade: float = 10_000
    leverage: float = 1.0
    max_positions: int = 5            # Max simultaneous positions
    in_sample_frac: float = 0.7       # 70% in-sample


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    config: BacktestConfig
    exchange_a: str
    exchange_b: str
    asset: str
    sample_type: str  # "in_sample" or "out_of_sample"

    # Trade log
    trades: list[dict] = field(default_factory=list)

    # Time series
    equity_curve: pd.Series | None = None
    returns: pd.Series | None = None

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def total_return(self) -> float:
        if self.returns is None or self.returns.empty:
            return 0.0
        return (1 + self.returns).prod() - 1

    def summary(self) -> dict:
        """Quick summary statistics."""
        if self.returns is None or self.returns.empty:
            return {"n_trades": 0, "total_return": 0.0}

        from src.models.risk_metrics import compute_all_metrics
        metrics = compute_all_metrics(self.returns)
        metrics["n_trades"] = self.n_trades
        metrics["sample_type"] = self.sample_type
        metrics["exchange_a"] = self.exchange_a
        metrics["exchange_b"] = self.exchange_b
        metrics["asset"] = self.asset
        metrics["config"] = {
            "entry_threshold": self.config.entry_threshold,
            "close_threshold": self.config.close_threshold,
            "leverage": self.config.leverage,
        }
        return metrics


def run_backtest(
    spreads: pd.DataFrame,
    exchange_a: str,
    exchange_b: str,
    asset: str,
    config: BacktestConfig | None = None,
    sample_type: str = "full",
) -> BacktestResult:
    """Run event-driven backtest on funding rate spreads.

    Args:
        spreads: Wide-format aligned funding rates (from aligner).
        exchange_a: First exchange name.
        exchange_b: Second exchange name.
        asset: Asset symbol.
        config: Backtest configuration.
        sample_type: Label for this run ("in_sample", "out_of_sample", "full").

    Returns:
        BacktestResult with trades, equity curve, and returns.
    """
    config = config or BacktestConfig()
    result = BacktestResult(
        config=config,
        exchange_a=exchange_a,
        exchange_b=exchange_b,
        asset=asset,
        sample_type=sample_type,
    )

    # Extract rates for both exchanges
    try:
        rate_a = spreads[(exchange_a, asset)]
        rate_b = spreads[(exchange_b, asset)]
    except KeyError:
        logger.warning(f"Data not found for {exchange_a}/{exchange_b}/{asset}")
        return result

    spread = rate_a - rate_b
    spread = spread.dropna()

    if spread.empty:
        return result

    # Track state
    positions: list[Position] = []
    capital = config.notional_per_trade * config.max_positions  # Total capital
    period_returns = []
    timestamps = []

    for ts, spread_val in spread.items():
        period_pnl = 0.0

        # ── Update existing positions ──
        closed_positions = []
        for pos in positions:
            pos.periods_held += 1

            # The spread at this timestamp for this position's direction
            if pos.exchange_short == exchange_a:
                current_spread = spread_val  # a - b
            else:
                current_spread = -spread_val  # b - a

            # PnL = spread * notional (we collect the spread each period)
            period_pnl_pos = current_spread * pos.notional
            pos.cumulative_pnl += period_pnl_pos
            period_pnl += period_pnl_pos

            # Track adverse spread
            if current_spread < 0:
                pos.max_adverse_spread = max(pos.max_adverse_spread, abs(current_spread))

            # ── Check exit conditions ──
            should_close = False
            close_reason = ""

            if abs(current_spread) < config.close_threshold:
                should_close = True
                close_reason = "spread_reverted"
            elif pos.periods_held >= config.max_holding_periods:
                should_close = True
                close_reason = "max_holding"
            elif pos.max_adverse_spread > config.basis_stop_loss:
                should_close = True
                close_reason = "basis_stop"

            if should_close:
                # Deduct closing costs (half of round-trip already paid at open)
                close_cost = pos.entry_cost / 2 * pos.notional
                pos.cumulative_pnl -= close_cost
                period_pnl -= close_cost

                result.trades.append({
                    "open_time": pos.open_time,
                    "close_time": ts,
                    "exchange_short": pos.exchange_short,
                    "exchange_long": pos.exchange_long,
                    "asset": pos.asset,
                    "entry_spread": pos.entry_spread,
                    "periods_held": pos.periods_held,
                    "cumulative_pnl": pos.cumulative_pnl,
                    "close_reason": close_reason,
                })
                closed_positions.append(pos)

        for pos in closed_positions:
            positions.remove(pos)

        # ── Check entry conditions ──
        if len(positions) < config.max_positions:
            abs_spread = abs(spread_val)

            if abs_spread >= config.entry_threshold:
                # Determine direction
                if spread_val > 0:
                    ex_short, ex_long = exchange_a, exchange_b
                else:
                    ex_short, ex_long = exchange_b, exchange_a

                # Check we don't already have this pair open
                already_open = any(
                    p.exchange_short == ex_short and p.exchange_long == ex_long
                    for p in positions
                )

                if not already_open:
                    costs = total_cost_round_trip(
                        ex_short, ex_long,
                        notional_usd=config.notional_per_trade,
                    )

                    # Only enter if spread exceeds costs
                    if abs_spread > costs["total"]:
                        pos = Position(
                            open_time=ts,
                            exchange_short=ex_short,
                            exchange_long=ex_long,
                            asset=asset,
                            notional=config.notional_per_trade,
                            leverage=config.leverage,
                            entry_spread=abs_spread,
                            entry_cost=costs["total"],
                        )
                        # Deduct opening costs
                        open_cost = costs["total"] / 2 * config.notional_per_trade
                        period_pnl -= open_cost
                        positions.append(pos)

        # Record period return
        period_ret = period_pnl / capital if capital > 0 else 0.0
        period_returns.append(period_ret)
        timestamps.append(ts)

    # Build return series
    result.returns = pd.Series(period_returns, index=pd.DatetimeIndex(timestamps))
    result.equity_curve = (1 + result.returns).cumprod()

    # Close any remaining positions at end
    for pos in positions:
        result.trades.append({
            "open_time": pos.open_time,
            "close_time": timestamps[-1] if timestamps else None,
            "exchange_short": pos.exchange_short,
            "exchange_long": pos.exchange_long,
            "asset": pos.asset,
            "entry_spread": pos.entry_spread,
            "periods_held": pos.periods_held,
            "cumulative_pnl": pos.cumulative_pnl,
            "close_reason": "end_of_period",
        })

    return result


def run_backtest_grid(
    spreads: pd.DataFrame,
    exchange_a: str,
    exchange_b: str,
    asset: str,
    entry_thresholds: list[float] | None = None,
    leverage_levels: list[float] | None = None,
    in_sample_frac: float = 0.7,
) -> list[BacktestResult]:
    """Run backtest across parameter grid with in-sample/out-of-sample split.

    Returns list of BacktestResult for each parameter combination and sample type.
    """
    entry_thresholds = entry_thresholds or [0.0001, 0.00025, 0.0005, 0.001]
    leverage_levels = leverage_levels or [1, 2, 3, 5]

    # Split data chronologically
    n = spreads.shape[0]
    split_idx = int(n * in_sample_frac)

    in_sample = spreads.iloc[:split_idx]
    out_sample = spreads.iloc[split_idx:]

    results = []

    for threshold in entry_thresholds:
        for leverage in leverage_levels:
            config = BacktestConfig(
                entry_threshold=threshold,
                leverage=leverage,
                in_sample_frac=in_sample_frac,
            )

            # In-sample
            is_result = run_backtest(
                in_sample, exchange_a, exchange_b, asset,
                config=config, sample_type="in_sample",
            )
            results.append(is_result)

            # Out-of-sample
            os_result = run_backtest(
                out_sample, exchange_a, exchange_b, asset,
                config=config, sample_type="out_of_sample",
            )
            results.append(os_result)

    return results


def results_to_dataframe(results: list[BacktestResult]) -> pd.DataFrame:
    """Convert list of BacktestResults to a summary DataFrame."""
    records = []
    for r in results:
        s = r.summary()
        # Flatten nested dicts
        flat = {}
        for k, v in s.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if not isinstance(vv, dict):
                        flat[f"{k}_{kk}"] = vv
            else:
                flat[k] = v
        records.append(flat)
    return pd.DataFrame(records)
