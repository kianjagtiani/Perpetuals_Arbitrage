"""
Financial Metrics Orchestrator

Ties together data extraction and metric calculation into a single pipeline.
Produces a structured analysis output ready for LLM expert consumption.

Usage:
    from processing import run_analysis

    result = run_analysis(
        ticker="AAPL",
        income_statements=[...],
        balance_sheets=[...],
        cash_flows=[...],
        metrics={...},
        price_data={...},
    )
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import json

from .data_extractor import (
    CompanyData,
    FinancialData,
    extract_company_data,
    get_current_and_previous,
)
from .metrics_calculator import (
    MetricResult,
    BenchmarkResult,
    ComprehensiveAnalysis,
    piotroski_f_score,
    altman_z_score,
    ohlson_o_score,
    beneish_m_score,
    magic_formula_rank,
    sloan_accrual_ratio,
    gross_profitability,
    fcf_conversion,
    shareholder_yield,
    economic_value_added,
    owner_earnings,
    dupont_5_factor,
    sustainable_growth_rate,
    analyze_trend,
    benchmark_metric,
    aggregate_flags,
    calculate_quality_score,
)
from .quant_metrics import (
    momentum_score,
    volatility_metrics,
    mean_reversion_signals,
    factor_exposure as calc_factor_exposure,
    statistical_anomalies as calc_statistical_anomalies,
    sector_relative_strength as calc_sector_relative_strength,
    correlation_regime as calc_correlation_regime,
    liquidity_metrics,
    return_distribution as calc_return_distribution,
)
from .behavioral_metrics import (
    cape_ratio,
    bubble_indicators as calc_bubble_indicators,
    narrative_momentum_score,
)


@dataclass
class AnalysisResult:
    """Complete analysis output for LLM consumption."""
    ticker: str
    company_name: str
    analysis_date: str

    # Raw company data
    company_data: CompanyData = None

    # Calculated metrics
    comprehensive_analysis: ComprehensiveAnalysis = None

    # Summary for quick reference
    summary: Dict[str, Any] = field(default_factory=dict)

    # Data quality notes
    data_quality_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "analysis_date": self.analysis_date,
            "summary": self.summary,
            "data_quality_notes": self.data_quality_notes,
        }

    def to_llm_context(self) -> str:
        """Format as context string for LLM experts."""
        lines = [
            f"# Pre-Calculated Metrics for {self.ticker}",
            f"Company: {self.company_name}",
            f"Analysis Date: {self.analysis_date}",
            "",
            "## Composite Scores",
        ]

        if self.comprehensive_analysis:
            ca = self.comprehensive_analysis

            # Piotroski
            if ca.piotroski:
                lines.append(f"### Piotroski F-Score: {ca.piotroski.value}/9")
                lines.append(f"Interpretation: {ca.piotroski.interpretation}")
                if ca.piotroski.flags:
                    lines.append(f"Flags: {', '.join(ca.piotroski.flags)}")
                lines.append("")

            # Altman Z
            if ca.altman_z:
                lines.append(f"### Altman Z-Score: {ca.altman_z.value}")
                lines.append(f"Interpretation: {ca.altman_z.interpretation}")
                if ca.altman_z.flags:
                    lines.append(f"Flags: {', '.join(ca.altman_z.flags)}")
                lines.append("")

            # Beneish M
            if ca.beneish_m:
                lines.append(f"### Beneish M-Score: {ca.beneish_m.value}")
                lines.append(f"Interpretation: {ca.beneish_m.interpretation}")
                if ca.beneish_m.flags:
                    lines.append(f"Flags: {', '.join(ca.beneish_m.flags)}")
                lines.append("")

            # Ohlson O
            if ca.ohlson_o:
                lines.append(f"### Ohlson O-Score (Bankruptcy Probability): {ca.ohlson_o.value}")
                lines.append(f"Interpretation: {ca.ohlson_o.interpretation}")
                lines.append("")

            # Quality Metrics
            lines.append("## Quality Metrics")

            if ca.sloan_accrual:
                lines.append(f"### Sloan Accrual Ratio: {ca.sloan_accrual.value}%")
                lines.append(f"Interpretation: {ca.sloan_accrual.interpretation}")
                lines.append("")

            if ca.fcf_conversion:
                lines.append(f"### FCF Conversion: {ca.fcf_conversion.value}%")
                lines.append(f"Interpretation: {ca.fcf_conversion.interpretation}")
                lines.append("")

            if ca.gross_profitability:
                lines.append(f"### Gross Profitability (GP/Assets): {ca.gross_profitability.value}%")
                lines.append(f"Interpretation: {ca.gross_profitability.interpretation}")
                lines.append("")

            # Value Creation
            lines.append("## Value Creation")

            if ca.owner_earnings:
                lines.append(f"### Owner Earnings: ${ca.owner_earnings.value:,.0f}")
                lines.append(f"Interpretation: {ca.owner_earnings.interpretation}")
                lines.append("")

            if ca.eva:
                lines.append(f"### Economic Value Added (EVA): ${ca.eva.value:,.0f}")
                lines.append(f"Interpretation: {ca.eva.interpretation}")
                lines.append("")

            # Shareholder Returns
            if ca.shareholder_yield:
                lines.append("## Shareholder Returns")
                lines.append(f"### Total Shareholder Yield: {ca.shareholder_yield.value}%")
                lines.append(f"Interpretation: {ca.shareholder_yield.interpretation}")
                if ca.shareholder_yield.components:
                    comp = ca.shareholder_yield.components
                    lines.append(f"  - Dividend Yield: {comp.get('dividend_yield', 'N/A')}%")
                    lines.append(f"  - Buyback Yield: {comp.get('buyback_yield', 'N/A')}%")
                    lines.append(f"  - Debt Paydown Yield: {comp.get('debt_paydown_yield', 'N/A')}%")
                lines.append("")

            # DuPont Analysis
            if ca.dupont:
                lines.append("## ROE Decomposition (DuPont 5-Factor)")
                lines.append(f"ROE: {ca.dupont.value}%")
                lines.append(f"Analysis: {ca.dupont.interpretation}")
                if ca.dupont.components:
                    comp = ca.dupont.components
                    lines.append(f"  - Tax Burden: {comp.get('tax_burden', 'N/A')}")
                    lines.append(f"  - Interest Burden: {comp.get('interest_burden', 'N/A')}")
                    lines.append(f"  - EBIT Margin: {comp.get('ebit_margin', 'N/A')}%")
                    lines.append(f"  - Asset Turnover: {comp.get('asset_turnover', 'N/A')}")
                    lines.append(f"  - Leverage: {comp.get('leverage', 'N/A')}x")
                lines.append("")

            # Growth
            if ca.sustainable_growth:
                lines.append("## Sustainable Growth")
                lines.append(f"Sustainable Growth Rate: {ca.sustainable_growth.value}%")
                lines.append(f"Interpretation: {ca.sustainable_growth.interpretation}")
                lines.append("")

            # Quant Metrics
            if any([ca.momentum, ca.volatility, ca.mean_reversion, ca.factor_exposure]):
                lines.append("## Quant Metrics")

                if ca.momentum:
                    lines.append(f"### Momentum: {ca.momentum.value}%")
                    lines.append(f"Interpretation: {ca.momentum.interpretation}")
                    lines.append("")

                if ca.volatility:
                    lines.append(f"### Volatility (20d annualized): {ca.volatility.value}%")
                    lines.append(f"Regime: {ca.volatility.components.get('regime', 'N/A')}")
                    lines.append(f"Interpretation: {ca.volatility.interpretation}")
                    lines.append("")

                if ca.mean_reversion:
                    lines.append(f"### Mean Reversion Score: {ca.mean_reversion.value}")
                    lines.append(f"Interpretation: {ca.mean_reversion.interpretation}")
                    lines.append("")

                if ca.factor_exposure:
                    lines.append(f"### Factor Exposure: {ca.factor_exposure.value}")
                    lines.append(f"Interpretation: {ca.factor_exposure.interpretation}")
                    lines.append("")

                if ca.sector_relative_strength:
                    lines.append(f"### Relative Strength vs SPY: {ca.sector_relative_strength.value}%")
                    lines.append(f"Interpretation: {ca.sector_relative_strength.interpretation}")
                    lines.append("")

                if ca.return_distribution:
                    lines.append(f"### Risk/Return (Sharpe): {ca.return_distribution.value}")
                    lines.append(f"Max Drawdown: {ca.return_distribution.components.get('max_drawdown', 'N/A')}%")
                    lines.append(f"Interpretation: {ca.return_distribution.interpretation}")
                    lines.append("")

            # Behavioral Metrics
            if any([ca.cape, ca.bubble_indicators]):
                lines.append("## Behavioral/Valuation Metrics")

                if ca.cape:
                    lines.append(f"### CAPE Ratio: {ca.cape.value}")
                    lines.append(f"Excess CAPE Yield: {ca.cape.components.get('excess_cape_yield', 'N/A')}%")
                    lines.append(f"Implied 10yr Real Return: {ca.cape.components.get('implied_10yr_real_return', 'N/A')}%")
                    lines.append(f"Interpretation: {ca.cape.interpretation}")
                    lines.append("")

                if ca.bubble_indicators:
                    lines.append(f"### Bubble Score: {ca.bubble_indicators.value}/100")
                    lines.append(f"Interpretation: {ca.bubble_indicators.interpretation}")
                    lines.append("")

                if ca.narrative_momentum:
                    lines.append(f"### Narrative Momentum: {ca.narrative_momentum.value}")
                    lines.append(f"Interpretation: {ca.narrative_momentum.interpretation}")
                    lines.append("")

            # Red/Green Flags
            if ca.red_flags:
                lines.append("## ⚠️ RED FLAGS")
                for flag in ca.red_flags:
                    lines.append(f"- {flag}")
                lines.append("")

            if ca.green_flags:
                lines.append("## ✓ GREEN FLAGS")
                for flag in ca.green_flags:
                    lines.append(f"- {flag}")
                lines.append("")

            # Overall Quality
            lines.append(f"## Overall Quality Score: {ca.overall_quality_score}/100")

        return "\n".join(lines)


def calculate_all_metrics(company: CompanyData, wacc: float = 0.10) -> ComprehensiveAnalysis:
    """
    Calculate all professional metrics from extracted company data.

    Args:
        company: Extracted CompanyData object
        wacc: Weighted average cost of capital (default 10%)

    Returns:
        ComprehensiveAnalysis with all calculated metrics
    """
    analysis = ComprehensiveAnalysis(ticker=company.ticker)

    # Get current and previous year data
    current, previous = get_current_and_previous(company.financials_annual)

    if current.fiscal_year == 0:
        return analysis  # No data available

    # === COMPOSITE SCORES ===

    # Piotroski F-Score
    try:
        analysis.piotroski = piotroski_f_score(
            net_income=current.net_income,
            operating_cash_flow=current.operating_cash_flow,
            total_assets=current.total_assets,
            long_term_debt=current.long_term_debt,
            current_assets=current.current_assets,
            current_liabilities=current.current_liabilities,
            shares_outstanding=current.shares_outstanding,
            gross_profit=current.gross_profit,
            revenue=current.revenue,
            net_income_prev=previous.net_income,
            total_assets_prev=previous.total_assets,
            long_term_debt_prev=previous.long_term_debt,
            current_assets_prev=previous.current_assets,
            current_liabilities_prev=previous.current_liabilities,
            shares_outstanding_prev=previous.shares_outstanding,
            gross_profit_prev=previous.gross_profit,
            revenue_prev=previous.revenue,
        )
    except Exception:
        pass

    # Altman Z-Score
    try:
        # Determine if manufacturing based on sector
        is_manufacturing = company.sector.lower() in ['industrials', 'materials', 'manufacturing']

        analysis.altman_z = altman_z_score(
            working_capital=current.working_capital,
            retained_earnings=current.retained_earnings,
            ebit=current.ebit,
            market_cap=company.price.market_cap,
            revenue=current.revenue,
            total_assets=current.total_assets,
            total_liabilities=current.total_liabilities,
            is_manufacturing=is_manufacturing,
        )
    except Exception:
        pass

    # Ohlson O-Score
    try:
        analysis.ohlson_o = ohlson_o_score(
            total_assets=current.total_assets,
            total_liabilities=current.total_liabilities,
            working_capital=current.working_capital,
            current_liabilities=current.current_liabilities,
            net_income=current.net_income,
            funds_from_operations=current.operating_cash_flow,
            net_income_prev=previous.net_income,
            total_liabilities_prev=previous.total_liabilities,
        )
    except Exception:
        pass

    # Beneish M-Score
    try:
        analysis.beneish_m = beneish_m_score(
            receivables=current.accounts_receivable,
            revenue=current.revenue,
            gross_profit=current.gross_profit,
            total_assets=current.total_assets,
            ppe=current.ppe_net,
            depreciation=current.depreciation,
            sga=current.sga_expense,
            total_debt=current.total_debt,
            current_assets=current.current_assets,
            current_liabilities=current.current_liabilities,
            receivables_prev=previous.accounts_receivable,
            revenue_prev=previous.revenue,
            gross_profit_prev=previous.gross_profit,
            total_assets_prev=previous.total_assets,
            ppe_prev=previous.ppe_net,
            depreciation_prev=previous.depreciation,
            sga_prev=previous.sga_expense,
            total_debt_prev=previous.total_debt,
            net_income=current.net_income,
            operating_cash_flow=current.operating_cash_flow,
        )
    except Exception:
        pass

    # Magic Formula
    try:
        ev = company.price.market_cap + current.total_debt - current.cash
        analysis.magic_formula = magic_formula_rank(
            ebit=current.ebit,
            enterprise_value=ev,
            total_equity=current.shareholders_equity,
            total_debt=current.total_debt,
            cash=current.cash,
            ppe_net=current.ppe_net,
            working_capital=current.working_capital,
        )
    except Exception:
        pass

    # === QUALITY METRICS ===

    # Sloan Accrual Ratio
    try:
        analysis.sloan_accrual = sloan_accrual_ratio(
            net_income=current.net_income,
            operating_cash_flow=current.operating_cash_flow,
            total_assets=current.total_assets,
            total_assets_prev=previous.total_assets,
        )
    except Exception:
        pass

    # Gross Profitability
    try:
        analysis.gross_profitability = gross_profitability(
            gross_profit=current.gross_profit,
            total_assets=current.total_assets,
        )
    except Exception:
        pass

    # FCF Conversion
    try:
        analysis.fcf_conversion = fcf_conversion(
            free_cash_flow=current.free_cash_flow,
            ebitda=current.ebitda,
            net_income=current.net_income,
        )
    except Exception:
        pass

    # === SHAREHOLDER RETURNS ===

    try:
        analysis.shareholder_yield = shareholder_yield(
            dividends_paid=current.dividends_paid,
            shares_repurchased=current.shares_repurchased,
            shares_issued=current.shares_issued,
            debt_repaid=current.debt_repaid,
            market_cap=company.price.market_cap,
        )
    except Exception:
        pass

    # === VALUE CREATION ===

    # Owner Earnings
    try:
        wc_change = current.working_capital - previous.working_capital
        analysis.owner_earnings = owner_earnings(
            net_income=current.net_income,
            depreciation=current.depreciation,
            amortization=current.amortization if hasattr(current, 'amortization') else 0,
            capex=current.capex,
            working_capital_change=wc_change,
            shares_outstanding=current.shares_outstanding,
        )
    except Exception:
        pass

    # EVA
    try:
        tax_rate = current.income_tax / current.ebt if current.ebt != 0 else 0.25
        nopat = current.ebit * (1 - tax_rate)
        invested_capital = current.shareholders_equity + current.total_debt - current.cash

        analysis.eva = economic_value_added(
            nopat=nopat,
            invested_capital=invested_capital,
            wacc=wacc,
        )
    except Exception:
        pass

    # === DECOMPOSITION ===

    # DuPont 5-Factor
    try:
        analysis.dupont = dupont_5_factor(
            net_income=current.net_income,
            ebt=current.ebt,
            ebit=current.ebit,
            revenue=current.revenue,
            total_assets=current.total_assets,
            shareholders_equity=current.shareholders_equity,
        )
    except Exception:
        pass

    # === GROWTH ===

    # Sustainable Growth Rate
    try:
        roe = current.net_income / current.shareholders_equity if current.shareholders_equity > 0 else 0
        payout = abs(current.dividends_paid) / current.net_income if current.net_income > 0 else 0

        analysis.sustainable_growth = sustainable_growth_rate(
            roe=roe,
            dividend_payout_ratio=payout,
        )
    except Exception:
        pass

    # Revenue Trend
    if len(company.financials_annual) >= 3:
        revenues = [f.revenue for f in reversed(company.financials_annual)]
        analysis.revenue_trend = analyze_trend(revenues, "Revenue")

        earnings = [f.net_income for f in reversed(company.financials_annual)]
        analysis.earnings_trend = analyze_trend(earnings, "Earnings")

    # === QUANT METRICS (Simons) ===

    if company.price.price_history:
        try:
            analysis.momentum = momentum_score(company.price.price_history)
        except Exception:
            pass

        try:
            analysis.volatility = volatility_metrics(
                company.price.price_history,
                vix_prices=company.benchmarks.vix_prices if hasattr(company, 'benchmarks') else None,
            )
        except Exception:
            pass

        try:
            analysis.mean_reversion = mean_reversion_signals(company.price.price_history)
        except Exception:
            pass

        try:
            analysis.statistical_anomalies = calc_statistical_anomalies(
                company.price.price_history,
                earnings_values=[f.net_income for f in reversed(company.financials_annual)] if company.financials_annual else None,
            )
        except Exception:
            pass

        try:
            analysis.liquidity = liquidity_metrics(company.price.price_history)
        except Exception:
            pass

        try:
            analysis.return_distribution = calc_return_distribution(company.price.price_history)
        except Exception:
            pass

    # Factor exposure (uses API metrics + momentum)
    try:
        mom_12m = analysis.momentum.components.get("momentum_12m_skip1m", 0) / 100 if analysis.momentum else None
        analysis.factor_exposure = calc_factor_exposure(
            pe_ratio=company.metrics.pe_ratio,
            pb_ratio=company.metrics.pb_ratio,
            roe=company.metrics.roe,
            accrual_ratio=analysis.sloan_accrual.value / 100 if analysis.sloan_accrual else None,
            market_cap=company.price.market_cap,
            momentum_12m=mom_12m,
        )
    except Exception:
        pass

    # Relative strength and correlation (need benchmark data)
    if hasattr(company, 'benchmarks') and company.benchmarks.spy_prices:
        try:
            analysis.sector_relative_strength = calc_sector_relative_strength(
                company.price.price_history,
                company.benchmarks.sector_etf_prices or company.benchmarks.spy_prices,
                company.benchmarks.spy_prices,
            )
        except Exception:
            pass

        try:
            analysis.correlation_regime = calc_correlation_regime(
                company.price.price_history,
                company.benchmarks.spy_prices,
            )
        except Exception:
            pass

    # === BEHAVIORAL METRICS (Shiller) ===

    # CAPE ratio
    if company.financials_annual and company.price.current_price > 0:
        try:
            earnings_hist = [f.net_income for f in reversed(company.financials_annual)]
            shares = company.financials_annual[0].shares_outstanding or company.price.shares_outstanding
            analysis.cape = cape_ratio(
                earnings_history=earnings_hist,
                current_price=company.price.current_price,
                shares_outstanding=shares,
            )
        except Exception:
            pass

    # Bubble indicators
    if company.price.price_history:
        try:
            earnings_hist = [f.net_income for f in reversed(company.financials_annual)] if company.financials_annual else None
            analysis.bubble_indicators = calc_bubble_indicators(
                company.price.price_history,
                earnings_history=earnings_hist,
            )
        except Exception:
            pass

    # === SUMMARY ===

    # Aggregate flags
    analysis.red_flags, analysis.green_flags = aggregate_flags(analysis)

    # Calculate overall quality score
    analysis.overall_quality_score = calculate_quality_score(analysis)

    return analysis


def run_analysis(
    ticker: str,
    income_statements: List[Dict[str, Any]],
    balance_sheets: List[Dict[str, Any]],
    cash_flows: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    price_data: Dict[str, Any],
    holdings_by_investor: Dict[str, List[Dict[str, Any]]] = None,
    insider_trades: List[Dict[str, Any]] = None,
    analyst_estimates: List[Dict[str, Any]] = None,
    company_facts: Dict[str, Any] = None,
    wacc: float = 0.10,
) -> AnalysisResult:
    """
    Run complete financial analysis pipeline.

    This is the main entry point for the processing layer.

    Args:
        ticker: Stock ticker symbol
        income_statements: List of income statement API responses
        balance_sheets: List of balance sheet API responses
        cash_flows: List of cash flow API responses
        metrics: Financial metrics API response
        price_data: Price/quote API response
        holdings_by_investor: Dict mapping investor name to holdings
        insider_trades: List of insider trade API responses
        analyst_estimates: List of analyst estimate API responses
        company_facts: Company facts API response
        wacc: Weighted average cost of capital for EVA calculation

    Returns:
        AnalysisResult with complete analysis
    """
    result = AnalysisResult(
        ticker=ticker,
        company_name=company_facts.get('name', ticker) if company_facts else ticker,
        analysis_date=datetime.now().isoformat(),
    )

    # Track data quality issues
    if not income_statements:
        result.data_quality_notes.append("No income statements provided")
    if not balance_sheets:
        result.data_quality_notes.append("No balance sheets provided")
    if not cash_flows:
        result.data_quality_notes.append("No cash flows provided")

    # Extract company data
    company = extract_company_data(
        ticker=ticker,
        income_statements=income_statements or [],
        balance_sheets=balance_sheets or [],
        cash_flows=cash_flows or [],
        metrics=metrics or {},
        price_data=price_data or {},
        holdings_by_investor=holdings_by_investor,
        insider_trades=insider_trades,
        analyst_estimates=analyst_estimates,
        company_facts=company_facts,
    )
    result.company_data = company

    # Calculate all metrics
    analysis = calculate_all_metrics(company, wacc=wacc)
    result.comprehensive_analysis = analysis

    # Build summary
    result.summary = {
        "ticker": ticker,
        "company_name": result.company_name,
        "current_price": company.price.current_price,
        "market_cap": company.price.market_cap,
        "data_periods_annual": len(company.financials_annual),
        "data_periods_quarterly": len(company.financials_quarterly),
        "composite_scores": {
            "piotroski_f_score": analysis.piotroski.value if analysis.piotroski else None,
            "altman_z_score": analysis.altman_z.value if analysis.altman_z else None,
            "beneish_m_score": analysis.beneish_m.value if analysis.beneish_m else None,
            "ohlson_o_probability": analysis.ohlson_o.value if analysis.ohlson_o else None,
        },
        "quality_score": analysis.overall_quality_score,
        "red_flag_count": len(analysis.red_flags),
        "green_flag_count": len(analysis.green_flags),
    }

    return result


def format_for_expert(result: AnalysisResult, expert_type: str) -> str:
    """
    Format analysis for a specific expert type.

    Args:
        result: Complete analysis result
        expert_type: One of "buffett", "graham", "lynch", "wood", "soros", "dalio", "burry", "simons", "shiller"

    Returns:
        Formatted string context for the expert
    """
    base_context = result.to_llm_context()

    # Add expert-specific emphasis
    expert_emphasis = {
        "buffett": [
            "\n## Buffett-Relevant Highlights",
            f"- Owner Earnings: See above",
            f"- FCF Conversion: {result.comprehensive_analysis.fcf_conversion.value if result.comprehensive_analysis and result.comprehensive_analysis.fcf_conversion else 'N/A'}%",
            f"- ROE Quality: See DuPont analysis above",
        ],
        "graham": [
            "\n## Graham-Relevant Highlights",
            f"- Altman Z-Score (Safety): {result.comprehensive_analysis.altman_z.value if result.comprehensive_analysis and result.comprehensive_analysis.altman_z else 'N/A'}",
            f"- Earnings Quality: See Beneish M-Score and Sloan Accrual above",
        ],
        "lynch": [
            "\n## Lynch-Relevant Highlights",
            f"- Growth Trends: See revenue/earnings trend analysis above",
            f"- Sustainable Growth Rate: {result.comprehensive_analysis.sustainable_growth.value if result.comprehensive_analysis and result.comprehensive_analysis.sustainable_growth else 'N/A'}%",
        ],
        "wood": [
            "\n## Wood-Relevant Highlights",
            f"- Gross Profitability: {result.comprehensive_analysis.gross_profitability.value if result.comprehensive_analysis and result.comprehensive_analysis.gross_profitability else 'N/A'}%",
            f"- Growth Trajectory: See trend analysis above",
        ],
        "soros": [
            "\n## Soros-Relevant Highlights",
            f"- Market Cap: ${result.company_data.price.market_cap:,.0f}" if result.company_data else "",
            "- (Price action and sentiment data from other sources)",
        ],
        "dalio": [
            "\n## Dalio-Relevant Highlights",
            f"- Altman Z-Score (Stress): {result.comprehensive_analysis.altman_z.value if result.comprehensive_analysis and result.comprehensive_analysis.altman_z else 'N/A'}",
            f"- Ohlson O-Score (Bankruptcy Risk): {result.comprehensive_analysis.ohlson_o.value if result.comprehensive_analysis and result.comprehensive_analysis.ohlson_o else 'N/A'}",
        ],
        "burry": [
            "\n## Burry-Relevant Highlights",
            f"- Beneish M-Score (Manipulation): {result.comprehensive_analysis.beneish_m.value if result.comprehensive_analysis and result.comprehensive_analysis.beneish_m else 'N/A'}",
            f"- Sloan Accrual Ratio: {result.comprehensive_analysis.sloan_accrual.value if result.comprehensive_analysis and result.comprehensive_analysis.sloan_accrual else 'N/A'}%",
            f"- All Red Flags: {len(result.comprehensive_analysis.red_flags) if result.comprehensive_analysis else 0}",
        ],
        "simons": [
            "\n## Simons-Relevant Highlights",
            f"- Momentum: See quant metrics above",
            f"- Volatility Regime: {result.comprehensive_analysis.volatility.components.get('regime', 'N/A') if result.comprehensive_analysis and result.comprehensive_analysis.volatility else 'N/A'}",
            f"- Factor Exposure: {result.comprehensive_analysis.factor_exposure.value if result.comprehensive_analysis and result.comprehensive_analysis.factor_exposure else 'N/A'}",
            f"- Relative Strength vs SPY: {result.comprehensive_analysis.sector_relative_strength.value if result.comprehensive_analysis and result.comprehensive_analysis.sector_relative_strength else 'N/A'}%",
        ],
        "shiller": [
            "\n## Shiller-Relevant Highlights",
            f"- CAPE Ratio: {result.comprehensive_analysis.cape.value if result.comprehensive_analysis and result.comprehensive_analysis.cape else 'N/A'}",
            f"- Bubble Score: {result.comprehensive_analysis.bubble_indicators.value if result.comprehensive_analysis and result.comprehensive_analysis.bubble_indicators else 'N/A'}/100",
            f"- Narrative Momentum: {result.comprehensive_analysis.narrative_momentum.value if result.comprehensive_analysis and result.comprehensive_analysis.narrative_momentum else 'N/A'}",
        ],
    }

    emphasis = expert_emphasis.get(expert_type.lower(), [])
    return base_context + "\n".join(emphasis)
