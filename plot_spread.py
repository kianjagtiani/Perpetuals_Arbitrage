"""Plot BitMEX vs Drift SOL funding rate spread using full historical data."""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Load data
bitmex = pd.read_parquet("data/raw/funding_rates/bitmex/SOL_full.parquet")
drift_hist = pd.read_parquet("data/raw/funding_rates/drift/SOL_full.parquet")
drift_gap = pd.read_parquet("data/raw/funding_rates/drift/SOL_gap.parquet")
drift_orig = pd.read_parquet("data/raw/funding_rates/drift/SOL.parquet")

# Combine drift data (historical + gap + original)
drift = pd.concat(
    [drift_hist, drift_gap[["timestamp", "funding_rate"]], drift_orig[["timestamp", "funding_rate"]]],
    ignore_index=True,
)
drift = drift.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

# Normalize Drift 1h -> 8h
drift["hour"] = drift["timestamp"].dt.floor("h")
drift = drift.set_index("hour").sort_index()
drift_8h = drift["funding_rate"].resample("8h", offset="4h").sum()
drift_8h = drift_8h[drift_8h != 0]
drift_8h.index = drift_8h.index.floor("8h")

# BitMEX already 8h
bitmex_series = bitmex.set_index("timestamp")["funding_rate"]
bitmex_series.index = bitmex_series.index.floor("8h")

# Merge
merged = pd.DataFrame({"bitmex": bitmex_series, "drift": drift_8h}).dropna()
merged["spread"] = merged["bitmex"] - merged["drift"]
bps = merged["spread"] * 10000

# Rolling average
rolling_7d = bps.rolling(21, min_periods=5).mean()  # 21 periods = 7 days

# --- Plot ---
fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

# 1. Raw spread
ax1 = axes[0]
ax1.bar(bps.index, bps.values, width=0.3, color=np.where(bps > 0, "#2ecc71", "#e74c3c"), alpha=0.6)
ax1.plot(rolling_7d.index, rolling_7d.values, color="black", linewidth=1.5, label="7-day rolling mean")
ax1.axhline(0, color="grey", linewidth=0.5)
ax1.set_ylabel("Spread (bps per 8h)")
ax1.set_title("BitMEX − Drift SOL Funding Rate Spread (Full History)")
ax1.legend()

# Annotate events
ax1.annotate("FTX aftermath\nBitMEX shorts surge", xy=(pd.Timestamp("2023-01-04", tz="UTC"), -70),
             xytext=(pd.Timestamp("2023-03-01", tz="UTC"), -55),
             arrowprops=dict(arrowstyle="->", color="black"), fontsize=8)
ax1.annotate("SVB / USDC depeg", xy=(pd.Timestamp("2023-03-11", tz="UTC"), -22),
             xytext=(pd.Timestamp("2023-05-01", tz="UTC"), -40),
             arrowprops=dict(arrowstyle="->", color="black"), fontsize=8)

# 2. Cumulative spread (equity proxy)
ax2 = axes[1]
cumulative = merged["spread"].cumsum() * 10000
ax2.fill_between(cumulative.index, 0, cumulative.values,
                 where=cumulative >= 0, color="#2ecc71", alpha=0.3)
ax2.fill_between(cumulative.index, 0, cumulative.values,
                 where=cumulative < 0, color="#e74c3c", alpha=0.3)
ax2.plot(cumulative.index, cumulative.values, color="black", linewidth=1)
ax2.axhline(0, color="grey", linewidth=0.5)
ax2.set_ylabel("Cumulative Spread (bps)")
ax2.set_title("Cumulative Spread (Buy-and-Hold Carry P&L Proxy)")

# 3. Rolling % positive
rolling_pct = (bps > 0).rolling(90, min_periods=30).mean() * 100  # 30-day window
ax3 = axes[2]
ax3.plot(rolling_pct.index, rolling_pct.values, color="#3498db", linewidth=1.5)
ax3.axhline(80, color="green", linewidth=0.8, linestyle="--", alpha=0.5, label="80% threshold")
ax3.axhline(50, color="red", linewidth=0.8, linestyle="--", alpha=0.5, label="50% (coin flip)")
ax3.set_ylabel("% Positive (30-day rolling)")
ax3.set_title("Rolling 30-Day Positive Rate")
ax3.set_ylim(0, 105)
ax3.legend()

# Format x-axis for all subplots
for ax in axes:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.tick_params(axis="x", rotation=45, labelbottom=True)
ax3.set_xlabel("Date")

plt.tight_layout()
plt.savefig("figures/bitmex_drift_sol_spread.pdf", bbox_inches="tight")
plt.savefig("figures/bitmex_drift_sol_spread.png", dpi=150, bbox_inches="tight")
plt.show()
print("Saved to figures/bitmex_drift_sol_spread.pdf and .png")
