# Cross-Exchange Perpetual Futures Funding Rate Arbitrage Research Plan

## Context

**Research question**: Do variations in perpetual futures funding rates across exchanges enable profitable, market-neutral arbitrage after accounting for transaction costs and basis risk?

**Reference paper**: "Exploring Risk and Return Profiles of Funding Rate Arbitrage on CEX and DEX" (Werapun et al., 2025) — studied CEX/DEX arbitrage across Binance, BitMEX, ApolloX, Drift on BTC/ETH/XRP/BNB/SOL. Found returns up to 115.9% over 6 months with max drawdown of 1.92%, zero correlation with HODL.

**Strategy focus**: Cross-exchange funding rate arbitrage — short perp on high-funding exchange, long perp on low-funding exchange.

**Stack**: Python, Jupyter notebooks, academic/analytical focus.

---

## Project Structure

```
perps/
├── pyproject.toml / requirements.txt
├── .env.example              # API keys template (never committed)
├── data/
│   ├── raw/funding_rates/{exchange}/   # Untouched API responses (parquet)
│   ├── raw/prices/{exchange}/          # Mark/index prices, OHLCV
│   ├── raw/orderbooks/                 # Snapshots for slippage estimation
│   └── processed/                      # Normalized, aligned data
├── src/
│   ├── config.py                       # Exchange configs, constants
│   ├── collectors/                     # Data collection per exchange
│   │   ├── ccxt_collector.py           # Binance, Bybit, OKX, BitMEX via CCXT
│   │   ├── hyperliquid_collector.py    # Native SDK
│   │   ├── drift_collector.py          # REST API (data.api.drift.trade)
│   │   └── dydx_collector.py           # Indexer API (indexer.dydx.trade)
│   ├── processing/
│   │   ├── normalizer.py              # 1h/8h rate harmonization
│   │   ├── aligner.py                 # Temporal alignment across exchanges
│   │   └── cleaner.py                 # Outlier detection, gap handling
│   └── models/
│       ├── cost_model.py              # Fees, slippage, gas costs
│       ├── basis_risk.py              # Price divergence quantification
│       ├── backtester.py              # Event-driven backtest engine
│       └── risk_metrics.py            # Sharpe, Sortino, VaR, drawdown
├── notebooks/
│   ├── 00_data_collection.ipynb
│   ├── 01_exploratory_analysis.ipynb
│   ├── 02_spread_analysis.ipynb       # Core analytical notebook
│   ├── 03_cost_modeling.ipynb
│   ├── 04_basis_risk.ipynb
│   ├── 05_backtest.ipynb
│   ├── 06_risk_analysis.ipynb
│   └── 07_results_synthesis.ipynb
├── tests/
└── figures/                           # Publication-ready plots (PDF/SVG)
```

---

## Exchanges and Data

### Target Exchanges

| Exchange | Type | Funding Interval | Settlement (UTC) | Symbol Format | API |
|----------|------|-----------------|------------------|---------------|-----|
| Binance | CEX | 8h | 00:00, 08:00, 16:00 | BTC/USDT:USDT | CCXT |
| Bybit | CEX | 8h | 00:00, 08:00, 16:00 | BTC/USDT:USDT | CCXT |
| OKX | CEX | 8h | 00:00, 08:00, 16:00 | BTC/USDT:USDT | CCXT |
| BitMEX | CEX | 8h | 04:00, 12:00, 20:00 | BTC/USD:BTC (inverse) | CCXT |
| dYdX v4 | DEX | 1h | Every hour | BTC-USD | REST |
| Drift | DEX | 1h | Every hour | BTC-PERP | REST |
| Hyperliquid | DEX | 1h | Every hour | BTC | Native SDK |

### Assets
BTC, ETH, SOL, XRP, BNB (matching reference paper). Not all assets available on all DEXs — collector will discover availability dynamically.

### Historical Depth
- Minimum 6 months (matching Werapun et al.), target 12 months
- Paginated collection with rate limiting, cached locally as parquet

---

## Key Technical Challenges

### 1. Funding Rate Interval Harmonization
CEX = 8h intervals, DEX = 1h intervals. **Approach**: Aggregate 8 consecutive hourly DEX rates into 8h windows (sum) to align with CEX native resolution. Handle BitMEX's 4h offset settlement times separately.

### 2. Basis Risk
Cross-exchange positions are independently margined — a sharp price move can push one leg toward liquidation while the other profits, but you can't transfer margin across exchanges instantly. Must track per-leg margin ratios and model liquidation scenarios.

### 3. DEX-Specific Data Quirks
- **Drift**: `fundingRate` is in 1e9 precision, `oraclePriceTwap` in 1e6 — requires conversion: `rate_pct = (fundingRate / 1e9) / (oraclePriceTwap / 1e6)`
- **Hyperliquid**: Includes both `fundingRate` and `premium` components
- **dYdX**: Returns `rate`, `price`, `effectiveAt` from indexer

---

## Analysis Pipeline (7 Notebooks)

### NB 00: Data Collection
Acquire all historical funding rates, prices, and order book snapshots. Generate data quality report (coverage, missing periods, observations per exchange-asset).

### NB 01: Exploratory Analysis
- Descriptive statistics per exchange-asset (mean, median, std, skew, kurtosis)
- Time series plots of funding rates across exchanges
- Distribution analysis (KDE, normality tests: Shapiro-Wilk, Jarque-Bera)
- Autocorrelation (ACF/PACF) — persistent spreads are exploitable
- Regime analysis (bull/bear/sideways using BTC price)
- Cross-exchange correlation matrix
- Stationarity tests (ADF, KPSS)

### NB 02: Spread Analysis (core notebook)
- Compute spreads for all 21 exchange pairs × 5 assets
- Spread persistence via Ornstein-Uhlenbeck half-life estimation
- Directional consistency (signal reliability)
- CEX-CEX vs CEX-DEX vs DEX-DEX spread comparison
- Time-of-day / day-of-week effects
- Cointegration tests (Engle-Granger, Johansen)

### NB 03: Cost Modeling
- Trading fees (maker/taker per exchange, tiered)
- Slippage estimation from order book depth as f(trade_size)
- DEX gas costs (Solana tx fees for Drift, negligible for dYdX/Hyperliquid)
- Break-even spread = total round-trip cost / notional
- Sensitivity: trade size ($1K–$100K), fee tier, volatility regime

**Reference fee schedule:**

| Exchange | Maker | Taker | Notes |
|----------|-------|-------|-------|
| Binance | 0.02% | 0.05% | USDT-M perps, base tier |
| Bybit | 0.02% | 0.055% | Linear perps, base tier |
| OKX | 0.02% | 0.05% | USDT-M perps, base tier |
| BitMEX | -0.01% | 0.075% | Maker rebate |
| dYdX | 0.02% | 0.05% | Approximate, tier-dependent |
| Drift | 0.02% | 0.05% | Approximate |
| Hyperliquid | 0.01% | 0.035% | Lowest taker fee |

### NB 04: Basis Risk
- Rolling price correlation between exchange pairs
- Price spread (mark_A − mark_B) statistics
- Basis risk VaR at 95%/99% over 8h holding periods
- Tail risk: basis divergence during high-volatility events
- DEX oracle lag analysis (Pyth-based prices vs CEX)
- Liquidation risk: margin-of-safety simulations at various leverage levels

### NB 05: Backtesting
- **Entry**: Spread exceeds threshold (grid: 0.01%, 0.025%, 0.05%, 0.1% per 8h)
- **Position**: Short high-funding perp, long low-funding perp
- **Exit**: Spread reverts below close threshold, max holding period reached, or basis stop-loss hit
- **Scenarios**: All viable exchange pairs × assets × entry thresholds × leverage (1x, 2x, 3x, 5x)
- **Split**: 70% in-sample / 30% out-of-sample (chronological)
- Track per-leg margin independently for liquidation detection

### NB 06: Risk Analysis & Statistical Tests
- Risk metrics: Sharpe, Sortino, max drawdown, VaR, CVaR, Calmar ratio
- t-test for mean return > 0
- Bootstrap confidence intervals (10K resamples) for Sharpe and total return
- Multiple comparison correction (Bonferroni/BH) across exchange pairs
- Correlation of strategy returns with BTC buy-and-hold (expect ~0)
- Regime-conditional performance (high-vol vs low-vol)
- Comparison with Werapun et al. results

### NB 07: Results Synthesis
- Publication-quality tables and figures
- Best exchange pairs ranked by risk-adjusted return
- Equity curves, heatmaps, sensitivity plots
- Transaction cost waterfall charts
- Head-to-head comparison with reference paper

---

## Dependencies

```
# Core
pandas, numpy, scipy, statsmodels, scikit-learn, arch

# Exchange APIs
ccxt, hyperliquid-python-sdk, requests

# Visualization
matplotlib, plotly, seaborn

# Notebooks
jupyter, jupyterlab, papermill, nbconvert

# Utilities
python-dotenv, tqdm, pyarrow
```

---

## Implementation Phases

### Phase 1: Foundation
- Project scaffolding (pyproject.toml, venv, directory structure)
- `src/config.py` with exchange configurations
- `src/collectors/` — data collection from all 7 exchanges
- `src/processing/normalizer.py` and `aligner.py`
- Run NB 00 to acquire all data

### Phase 2: Exploration
- Run NB 01 (EDA) and NB 02 (spread analysis)
- Identify most promising exchange pairs
- May surface data quality issues requiring Phase 1 revisits

### Phase 3: Cost & Risk Modeling
- `src/models/cost_model.py` and `basis_risk.py`
- Run NB 03 and NB 04
- Determine break-even spreads and realistic risk bounds

### Phase 4: Backtesting
- `src/models/backtester.py` and `risk_metrics.py`
- Run NB 05 and NB 06
- In-sample optimization, out-of-sample validation

### Phase 5: Synthesis
- Run NB 07 for final results
- Robustness checks: parameter sensitivity, subperiod analysis, Monte Carlo
- Reproducibility: pin versions, random seeds, document exact data ranges

---

## Verification

1. **Sanity checks**: Average funding rates should be positive (~0.01%/8h baseline), spread sums should equal theoretical integral
2. **Replication**: Reproduce a subset of Werapun et al. results using their exchange pairs and time window
3. **Out-of-sample**: Primary results from 30% held-out data
4. **Robustness**: Results across subperiods, asset-level breakdown, cost sensitivity (0.5x–2x costs)
5. **Reproducibility**: Entire pipeline runnable from scratch via `papermill`

---

## Known Limitations to Acknowledge
- Survivorship bias (only studying active exchanges)
- Market impact not modeled (assumes trades don't move the market)
- Fee schedules may have changed over the backtest period
- Smart contract / oracle risk on DEXs not quantifiable from historical data
- Cross-exchange capital transfer delays in stressed markets
