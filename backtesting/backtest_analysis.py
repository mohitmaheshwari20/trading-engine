"""
backtest_analysis.py
====================
Strategy 2 Backtesting Framework — Component 4: Analysis

Computes performance metrics, equity curve, year-by-year breakdown,
and Pass 1 vs Pass 2 comparison from the trade log.

Usage:
    from backtest_analysis import run_analysis, print_report, compare_passes

    # Analyse Pass 1 results
    summary, equity = run_analysis(trades_df, pass_label="pass_1")

    # Print human-readable report
    print_report(summary, equity, trades_df)

    # Compare Pass 1 vs Pass 2
    compare_passes(trades_p1, trades_p2)
"""

import os
import datetime
import math
import pandas as pd
import numpy as np
from typing import Optional

from backtest_trade_simulator import (
    EXIT_STOP_LOSS, EXIT_TARGET_1, EXIT_TARGET_2,
    EXIT_BREAKEVEN_STOP, EXIT_END_OF_DATA, EXIT_AMBIGUOUS,
    TOTAL_CAPITAL, RISK_PER_TRADE,
)

TEST_RESULTS_DIR = r"C:\Projects\trading_engine\test_results"


# ─── CORE METRICS ─────────────────────────────────────────────────────────────

def compute_metrics(trades: pd.DataFrame, label: str = "") -> dict:
    """
    Compute performance metrics from a trade log DataFrame.

    AMBIGUOUS trades are excluded from all metrics.
    END_OF_DATA trades are included — they represent real outcomes.

    Args:
        trades: Trade log DataFrame (output of backtest_runner)
        label:  Optional label for reporting

    Returns:
        Dict of metric name → value
    """
    if trades is None or trades.empty:
        return _empty_metrics(label)

    # Exclude AMBIGUOUS trades from all metrics
    clean = trades[trades["exit_reason"] != EXIT_AMBIGUOUS].copy()
    ambiguous_count = len(trades) - len(clean)

    if clean.empty:
        return _empty_metrics(label)

    total_trades = len(clean)

    # Win = positive return
    wins   = clean[clean["return_pct"] > 0]
    losses = clean[clean["return_pct"] <= 0]

    win_count  = len(wins)
    loss_count = len(losses)
    win_rate   = win_count / total_trades * 100 if total_trades > 0 else 0

    avg_win  = wins["return_pct"].mean()   if not wins.empty   else 0.0
    avg_loss = losses["return_pct"].mean() if not losses.empty else 0.0

    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    gross_profit = wins["pnl"].sum()   if not wins.empty   else 0.0
    gross_loss   = abs(losses["pnl"].sum()) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    avg_holding = clean["holding_days"].mean() if "holding_days" in clean.columns else 0

    # Exit reason breakdown
    exit_counts = clean["exit_reason"].value_counts().to_dict()
    pct = lambda r: exit_counts.get(r, 0) / total_trades * 100

    # Signal frequency (trades per month)
    if "entry_date" in clean.columns and total_trades > 0:
        clean["entry_date"] = pd.to_datetime(clean["entry_date"])
        date_range_months = (
            (clean["entry_date"].max() - clean["entry_date"].min()).days / 30.44
        )
        signal_freq = total_trades / date_range_months if date_range_months > 0 else 0
    else:
        signal_freq = 0

    return {
        "label":              label,
        "total_trades":       total_trades,
        "ambiguous_excluded": ambiguous_count,
        "win_count":          win_count,
        "loss_count":         loss_count,
        "win_rate_pct":       round(win_rate, 2),
        "avg_win_pct":        round(avg_win, 2),
        "avg_loss_pct":       round(avg_loss, 2),
        "win_loss_ratio":     round(win_loss_ratio, 2),
        "gross_profit":       round(gross_profit, 2),
        "gross_loss":         round(gross_loss, 2),
        "profit_factor":      round(profit_factor, 2),
        "expectancy_pct":     round(expectancy, 2),
        "avg_holding_days":   round(avg_holding, 1),
        "signal_freq_per_month": round(signal_freq, 2),
        "pct_stop_loss":      round(pct(EXIT_STOP_LOSS), 1),
        "pct_target_1":       round(pct(EXIT_TARGET_1), 1),
        "pct_target_2":       round(pct(EXIT_TARGET_2), 1),
        "pct_breakeven_stop": round(pct(EXIT_BREAKEVEN_STOP), 1),
        "pct_end_of_data":    round(pct(EXIT_END_OF_DATA), 1),
        "pct_ambiguous":      round(ambiguous_count / len(trades) * 100, 1) if len(trades) > 0 else 0,
    }


def compute_equity_curve(
    trades: pd.DataFrame,
    total_capital: float = TOTAL_CAPITAL,
    risk_pct: float      = RISK_PER_TRADE,
) -> pd.DataFrame:
    """
    Build an equity curve from the trade log.

    Each trade contributes its PnL on its exit date.
    Uses fixed fractional sizing: INR 2,000 risk per trade.

    Returns DataFrame with columns: date, pnl, equity, drawdown_pct
    """
    if trades is None or trades.empty:
        return pd.DataFrame()

    clean = trades[trades["exit_reason"] != EXIT_AMBIGUOUS].copy()
    if clean.empty:
        return pd.DataFrame()

    clean["exit_date"] = pd.to_datetime(clean["exit_date"])
    clean = clean.sort_values("exit_date").reset_index(drop=True)

    equity  = total_capital
    peak    = total_capital
    rows    = []

    for _, trade in clean.iterrows():
        equity += trade["pnl"]
        peak    = max(peak, equity)
        dd_pct  = (peak - equity) / peak * 100 if peak > 0 else 0
        rows.append({
            "date":         trade["exit_date"].date(),
            "symbol":       trade["symbol"],
            "exit_reason":  trade["exit_reason"],
            "pnl":          round(trade["pnl"], 2),
            "equity":       round(equity, 2),
            "peak":         round(peak, 2),
            "drawdown_pct": round(dd_pct, 2),
        })

    return pd.DataFrame(rows)


def compute_annual_return(equity_df: pd.DataFrame, total_capital: float = TOTAL_CAPITAL) -> float:
    """Compute CAGR from equity curve."""
    if equity_df is None or equity_df.empty:
        return 0.0

    start_equity = total_capital
    end_equity   = equity_df["equity"].iloc[-1]
    start_date   = pd.to_datetime(equity_df["date"].iloc[0])
    end_date     = pd.to_datetime(equity_df["date"].iloc[-1])

    years = (end_date - start_date).days / 365.25
    if years <= 0 or start_equity <= 0:
        return 0.0

    cagr = ((end_equity / start_equity) ** (1 / years) - 1) * 100
    return round(cagr, 2)


def compute_max_drawdown(equity_df: pd.DataFrame) -> float:
    """Return maximum drawdown % from equity curve."""
    if equity_df is None or equity_df.empty:
        return 0.0
    return round(equity_df["drawdown_pct"].max(), 2)


# ─── YEAR-BY-YEAR BREAKDOWN ───────────────────────────────────────────────────

def compute_yearly_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Compute metrics for each calendar year.
    Returns DataFrame with one row per year.
    """
    if trades is None or trades.empty:
        return pd.DataFrame()

    clean = trades[trades["exit_reason"] != EXIT_AMBIGUOUS].copy()
    clean["exit_date"] = pd.to_datetime(clean["exit_date"])
    clean["year"]      = clean["exit_date"].dt.year

    rows = []
    for year in sorted(clean["year"].unique()):
        year_trades = clean[clean["year"] == year]
        m = compute_metrics(year_trades, label=str(year))
        # Add equity stats for the year
        eq = compute_equity_curve(year_trades)
        m["annual_return_pct"] = compute_annual_return(eq)
        m["max_drawdown_pct"]  = compute_max_drawdown(eq)
        m["year"]              = year
        rows.append(m)

    return pd.DataFrame(rows)


# ─── PASS 1 vs PASS 2 COMPARISON ─────────────────────────────────────────────

def compare_passes(
    trades_p1: pd.DataFrame,
    trades_p2: pd.DataFrame,
    total_capital: float = TOTAL_CAPITAL,
) -> dict:
    """
    Compare Pass 1 (T1 only) vs Pass 2 (T1 partial + T2) results.

    This answers: does the partial booking + T2 approach add or subtract value?

    Key caveat: Pass 2 introduces BREAKEVEN_STOP — a zero-gain exit that
    does not exist in Pass 1. Comparing average trade return alone is
    misleading. This function surfaces the full picture.

    Returns dict with side-by-side comparison metrics.
    """
    m1 = compute_metrics(trades_p1, "Pass 1 — T1 Only")
    m2 = compute_metrics(trades_p2, "Pass 2 — T1+T2")

    eq1 = compute_equity_curve(trades_p1, total_capital)
    eq2 = compute_equity_curve(trades_p2, total_capital)

    comparison = {
        "metric":                       ["Pass 1 (T1 Only)", "Pass 2 (T1+T2)", "Difference"],
        "total_trades":                 [m1["total_trades"],       m2["total_trades"],       "—"],
        "win_rate_pct":                 [m1["win_rate_pct"],       m2["win_rate_pct"],       round(m2["win_rate_pct"] - m1["win_rate_pct"], 2)],
        "avg_win_pct":                  [m1["avg_win_pct"],        m2["avg_win_pct"],        round(m2["avg_win_pct"] - m1["avg_win_pct"], 2)],
        "avg_loss_pct":                 [m1["avg_loss_pct"],       m2["avg_loss_pct"],       round(m2["avg_loss_pct"] - m1["avg_loss_pct"], 2)],
        "win_loss_ratio":               [m1["win_loss_ratio"],     m2["win_loss_ratio"],     round(m2["win_loss_ratio"] - m1["win_loss_ratio"], 2)],
        "profit_factor":                [m1["profit_factor"],      m2["profit_factor"],      round(m2["profit_factor"] - m1["profit_factor"], 2)],
        "expectancy_pct":               [m1["expectancy_pct"],     m2["expectancy_pct"],     round(m2["expectancy_pct"] - m1["expectancy_pct"], 2)],
        "annual_return_pct":            [compute_annual_return(eq1), compute_annual_return(eq2), "—"],
        "max_drawdown_pct":             [compute_max_drawdown(eq1),  compute_max_drawdown(eq2),  "—"],
        "pct_stop_loss":                [m1["pct_stop_loss"],      m2["pct_stop_loss"],      "—"],
        "pct_target_1":                 [m1["pct_target_1"],       m2["pct_target_1"],       "—"],
        "pct_target_2":                 [0,                        m2["pct_target_2"],       "—"],
        "pct_breakeven_stop":           [0,                        m2["pct_breakeven_stop"], "—"],
        "pct_end_of_data":              [m1["pct_end_of_data"],    m2["pct_end_of_data"],    "—"],
    }

    return comparison


# ─── DECISION GATE ────────────────────────────────────────────────────────────

def should_run_pass2(trades_p1: pd.DataFrame, threshold_pct: float = 50.0) -> tuple:
    """
    Evaluate whether to run Pass 2 based on Pass 1 results.

    Decision gate: if TARGET_1 exits represent > threshold_pct of all
    clean exits, recommend running Pass 2.

    Returns:
        (bool, str) — (run_pass2, reason_string)
    """
    if trades_p1 is None or trades_p1.empty:
        return False, "No trades in Pass 1."

    clean = trades_p1[trades_p1["exit_reason"] != EXIT_AMBIGUOUS]
    if clean.empty:
        return False, "All trades were AMBIGUOUS."

    total     = len(clean)
    t1_count  = len(clean[clean["exit_reason"] == EXIT_TARGET_1])
    sl_count  = len(clean[clean["exit_reason"] == EXIT_STOP_LOSS])
    t1_pct    = t1_count / total * 100

    if t1_pct > threshold_pct:
        reason = (
            f"TARGET_1 exits = {t1_pct:.1f}% of trades ({t1_count}/{total}). "
            f"Majority reached target — run Pass 2 to evaluate partial booking."
        )
        return True, reason
    else:
        reason = (
            f"TARGET_1 exits = {t1_pct:.1f}% of trades ({t1_count}/{total}). "
            f"STOP_LOSS dominates ({sl_count}/{total} = {sl_count/total*100:.1f}%). "
            f"Strategy not consistently reaching target — do not run Pass 2. "
            f"Revisit entry signal logic first."
        )
        return False, reason


# ─── REPORT PRINTER ───────────────────────────────────────────────────────────

def print_report(
    metrics: dict,
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    yearly_df: pd.DataFrame,
    pass_label: str = "Pass 1",
    output_file: Optional[str] = None,
) -> str:
    """
    Print a human-readable performance report.
    Optionally writes to a text file.
    Returns the report as a string.
    """
    lines = []
    sep   = "=" * 72
    dash  = "─" * 72

    lines.append(sep)
    lines.append(f"  STRATEGY 2 BACKTEST REPORT — {pass_label.upper()}")
    lines.append(f"  Generated: {datetime.date.today()}")
    lines.append(sep)

    lines.append(f"\n  OVERALL PERFORMANCE")
    lines.append(dash)
    lines.append(f"  Total Trades          : {metrics['total_trades']}")
    lines.append(f"  Ambiguous (excluded)  : {metrics['ambiguous_excluded']}")
    lines.append(f"  Win Rate              : {metrics['win_rate_pct']}%  ({metrics['win_count']}W / {metrics['loss_count']}L)")
    lines.append(f"  Avg Win               : {metrics['avg_win_pct']}%")
    lines.append(f"  Avg Loss              : {metrics['avg_loss_pct']}%")
    lines.append(f"  Win / Loss Ratio      : {metrics['win_loss_ratio']}x")
    lines.append(f"  Profit Factor         : {metrics['profit_factor']}")
    lines.append(f"  Expectancy            : {metrics['expectancy_pct']}%")
    lines.append(f"  Avg Holding Days      : {metrics['avg_holding_days']}")
    lines.append(f"  Signal Freq           : {metrics['signal_freq_per_month']} trades/month")

    if equity_df is not None and not equity_df.empty:
        cagr = compute_annual_return(equity_df)
        mdd  = compute_max_drawdown(equity_df)
        final_equity = equity_df["equity"].iloc[-1]
        total_return = (final_equity - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100
        lines.append(f"  Annual Return (CAGR)  : {cagr}%")
        lines.append(f"  Total Return          : {round(total_return, 2)}%")
        lines.append(f"  Max Drawdown          : {mdd}%")
        lines.append(f"  Final Equity          : INR {final_equity:,.0f}")

    lines.append(f"\n  EXIT REASON BREAKDOWN")
    lines.append(dash)
    lines.append(f"  Stop Loss             : {metrics['pct_stop_loss']}%")
    lines.append(f"  Target 1              : {metrics['pct_target_1']}%")
    if metrics.get("pct_target_2", 0) > 0:
        lines.append(f"  Target 2              : {metrics['pct_target_2']}%")
    if metrics.get("pct_breakeven_stop", 0) > 0:
        lines.append(f"  Breakeven Stop        : {metrics['pct_breakeven_stop']}%")
    lines.append(f"  End of Data           : {metrics['pct_end_of_data']}%")
    lines.append(f"  Ambiguous             : {metrics['pct_ambiguous']}%")

    lines.append(f"\n  SUCCESS CRITERIA (Strategy 2 One-Pager)")
    lines.append(dash)
    _gate = lambda val, threshold, direction="above": "✅ PASS" if (val >= threshold if direction == "above" else val <= threshold) else "❌ FAIL"
    lines.append(f"  Win Rate > 55%        : {metrics['win_rate_pct']}%   {_gate(metrics['win_rate_pct'], 55)}")
    lines.append(f"  Win/Loss Ratio > 1.5  : {metrics['win_loss_ratio']}x   {_gate(metrics['win_loss_ratio'], 1.5)}")
    lines.append(f"  Profit Factor > 2.0   : {metrics['profit_factor']}   {_gate(metrics['profit_factor'], 2.0)}")
    if equity_df is not None and not equity_df.empty:
        mdd = compute_max_drawdown(equity_df)
        lines.append(f"  Max Drawdown < 12%    : {mdd}%   {_gate(mdd, 12, direction='below')}")

    if yearly_df is not None and not yearly_df.empty:
        lines.append(f"\n  YEAR-BY-YEAR BREAKDOWN")
        lines.append(dash)
        lines.append(f"  {'Year':<6} {'Trades':<8} {'Win%':<8} {'PF':<8} {'Exp%':<10} {'CAGR%':<8} {'MDD%'}")
        lines.append(f"  {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*9} {'─'*7} {'─'*6}")
        for _, row in yearly_df.iterrows():
            lines.append(
                f"  {int(row['year']):<6} "
                f"{int(row['total_trades']):<8} "
                f"{row['win_rate_pct']:<8} "
                f"{row['profit_factor']:<8} "
                f"{row['expectancy_pct']:<10} "
                f"{row.get('annual_return_pct', 'N/A'):<8} "
                f"{row.get('max_drawdown_pct', 'N/A')}"
            )

    lines.append(f"\n{sep}\n")
    report = "\n".join(lines)
    print(report)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)

    return report


def print_comparison_report(
    comparison: dict,
    output_file: Optional[str] = None,
) -> str:
    """Print Pass 1 vs Pass 2 comparison report."""
    lines = []
    sep   = "=" * 72
    dash  = "─" * 72

    lines.append(sep)
    lines.append("  STRATEGY 2 — PASS 1 vs PASS 2 COMPARISON")
    lines.append(f"  Generated: {datetime.date.today()}")
    lines.append(sep)
    lines.append(f"\n  {'Metric':<30} {'Pass 1 (T1 Only)':<20} {'Pass 2 (T1+T2)':<20} {'Diff'}")
    lines.append(f"  {'─'*30} {'─'*19} {'─'*19} {'─'*10}")

    metric_labels = {
        "win_rate_pct":       "Win Rate %",
        "avg_win_pct":        "Avg Win %",
        "avg_loss_pct":       "Avg Loss %",
        "win_loss_ratio":     "Win/Loss Ratio",
        "profit_factor":      "Profit Factor",
        "expectancy_pct":     "Expectancy %",
        "annual_return_pct":  "Annual Return %",
        "max_drawdown_pct":   "Max Drawdown %",
        "pct_stop_loss":      "% Stop Loss exits",
        "pct_target_1":       "% Target 1 exits",
        "pct_target_2":       "% Target 2 exits",
        "pct_breakeven_stop": "% Breakeven Stop",
        "pct_end_of_data":    "% End of Data exits",
    }

    for key, label in metric_labels.items():
        if key in comparison:
            vals = comparison[key]
            lines.append(f"  {label:<30} {str(vals[0]):<20} {str(vals[1]):<20} {str(vals[2])}")

    lines.append(f"\n{sep}\n")

    lines.append("  NOTE ON COMPARISON:")
    lines.append("  Pass 2 introduces BREAKEVEN_STOP — a zero-gain exit that does not")
    lines.append("  exist in Pass 1. If this outcome is frequent, Pass 2 may hurt overall")
    lines.append("  returns even if individual T2 trades are profitable. Evaluate both")
    lines.append("  profit factor AND breakeven stop frequency before choosing a pass.")
    lines.append(f"\n{sep}\n")

    report = "\n".join(lines)
    print(report)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)

    return report


# ─── FULL ANALYSIS RUNNER ─────────────────────────────────────────────────────

def run_analysis(
    trades_df: pd.DataFrame,
    pass_label: str       = "Pass 1",
    output_dir: str       = TEST_RESULTS_DIR,
    total_capital: float  = TOTAL_CAPITAL,
    save_files: bool      = True,
) -> tuple:
    """
    Run complete analysis on a trade log.

    Returns:
        (metrics_dict, equity_df, yearly_df)
    """
    os.makedirs(output_dir, exist_ok=True)

    metrics   = compute_metrics(trades_df, label=pass_label)
    equity_df = compute_equity_curve(trades_df, total_capital)
    yearly_df = compute_yearly_metrics(trades_df)

    pass_slug = pass_label.lower().replace(" ", "_").replace("—", "").replace("(", "").replace(")", "").strip("_")

    report_path = os.path.join(output_dir, f"s2_backtest_report_{pass_slug}.txt")
    print_report(metrics, equity_df, trades_df, yearly_df, pass_label, output_file=report_path)

    if save_files:
        if equity_df is not None and not equity_df.empty:
            equity_df.to_csv(
                os.path.join(output_dir, f"s2_backtest_equity_{pass_slug}.csv"),
                index=False
            )
        if yearly_df is not None and not yearly_df.empty:
            yearly_df.to_csv(
                os.path.join(output_dir, f"s2_backtest_yearly_{pass_slug}.csv"),
                index=False
            )

    return metrics, equity_df, yearly_df


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _empty_metrics(label: str) -> dict:
    return {
        "label": label, "total_trades": 0, "ambiguous_excluded": 0,
        "win_count": 0, "loss_count": 0, "win_rate_pct": 0.0,
        "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "win_loss_ratio": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": 0.0,
        "expectancy_pct": 0.0, "avg_holding_days": 0.0,
        "signal_freq_per_month": 0.0,
        "pct_stop_loss": 0.0, "pct_target_1": 0.0, "pct_target_2": 0.0,
        "pct_breakeven_stop": 0.0, "pct_end_of_data": 0.0, "pct_ambiguous": 0.0,
    }
