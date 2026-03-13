"""
nifty_regime_diagnostic.py
===========================
Diagnostic script to cross-reference Strategy 2 backtest trade log
against Nifty 50 annual performance and trend character.

For each year in the trade log, computes:
    1. Nifty annual return
    2. % of trading days Nifty was above its 50-day MA
    3. Nifty 50-day MA slope at year end (rising or falling)
    4. Nifty max drawdown for the year

Then lays this alongside the strategy year-by-year results to identify
whether trend strength correlates with strategy performance.

Usage:
    python nifty_regime_diagnostic.py

Output:
    Printed table + C:\\Projects\\trading_engine\\test_results\\nifty_regime_analysis.csv
"""

import os
import pandas as pd
import numpy as np

# ─── CONFIG ───────────────────────────────────────────────────────────────────

NIFTY_CSV       = r"C:\Projects\Backtesting System\data\NIFTY_NS.CSV"
TRADE_LOG       = r"C:\Projects\trading_engine\test_results\s2_backtest_trades_pass1.csv"
OUTPUT_DIR      = r"C:\Projects\trading_engine\test_results"

MA_PERIOD       = 50      # 50-day MA — matches the market filter in entry_signal.py
SLOPE_LOOKBACK  = 20      # days to measure MA slope direction at year end

# ─── STRATEGY YEAR-BY-YEAR (from backtest output — hardcoded for reference) ───

STRATEGY_RESULTS = {
    2017: {"trades": 12,  "win_pct": 50.0,  "pf": 1.33, "exp_pct":  1.13, "cagr":  4.92,  "mdd":  5.46},
    2018: {"trades": 48,  "win_pct": 50.0,  "pf": 0.86, "exp_pct": -0.27, "cagr": -6.62,  "mdd": 21.21},
    2019: {"trades": 47,  "win_pct": 42.55, "pf": 0.52, "exp_pct": -1.16, "cagr":-30.30,  "mdd": 34.42},
    2020: {"trades": 8,   "win_pct": 37.5,  "pf": 0.44, "exp_pct": -1.96, "cagr": -6.08,  "mdd":  7.11},
    2021: {"trades": 21,  "win_pct": 57.14, "pf": 0.76, "exp_pct": -0.59, "cagr": -5.41,  "mdd":  7.95},
    2022: {"trades": 31,  "win_pct": 35.48, "pf": 0.38, "exp_pct": -1.79, "cagr":-25.37,  "mdd": 25.27},
    2023: {"trades": 39,  "win_pct": 58.97, "pf": 1.30, "exp_pct":  0.38, "cagr":  9.63,  "mdd":  6.25},
    2024: {"trades": 15,  "win_pct": 53.33, "pf": 0.80, "exp_pct": -0.56, "cagr": -3.48,  "mdd": 10.46},
    2025: {"trades": 39,  "win_pct": 51.28, "pf": 0.91, "exp_pct": -0.57, "cagr": -3.29,  "mdd": 17.19},
}


# ─── LOAD NIFTY DATA ──────────────────────────────────────────────────────────

def load_nifty(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Nifty CSV not found: {filepath}")

    df = pd.read_csv(filepath)

    # Normalise column names (case-insensitive)
    col_map = {c.lower(): c for c in df.columns}
    date_col  = col_map.get("date")
    close_col = col_map.get("close") or col_map.get("adj close")

    if not date_col or not close_col:
        raise ValueError(f"Could not find Date/Close columns. Found: {list(df.columns)}")

    df = df[[date_col, close_col]].copy()
    df.columns = ["Date", "Close"]
    df["Date"]  = pd.to_datetime(df["Date"])
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna().sort_values("Date").reset_index(drop=True)
    return df


# ─── COMPUTE NIFTY METRICS PER YEAR ──────────────────────────────────────────

def compute_nifty_yearly(df: pd.DataFrame, ma_period: int, slope_lookback: int) -> pd.DataFrame:
    """
    For each calendar year, compute:
        - nifty_annual_return_pct : first close to last close % change
        - pct_days_above_ma       : % of trading days price > MA(50)
        - ma_slope_at_year_end    : RISING / FALLING / FLAT
        - nifty_max_drawdown_pct  : max peak-to-trough drawdown within year
        - nifty_trend_char        : qualitative label based on above metrics
    """
    # Compute MA on full series (needs prior data for early-year accuracy)
    df = df.copy()
    df["MA"] = df["Close"].rolling(ma_period, min_periods=ma_period).mean()
    df["Year"] = df["Date"].dt.year

    rows = []
    for year in sorted(df["Year"].unique()):
        yr_df = df[df["Year"] == year].copy()
        if len(yr_df) < 10:
            continue

        # 1. Annual return
        first_close = yr_df["Close"].iloc[0]
        last_close  = yr_df["Close"].iloc[-1]
        annual_ret  = (last_close - first_close) / first_close * 100

        # 2. % days above MA
        yr_valid = yr_df.dropna(subset=["MA"])
        if len(yr_valid) > 0:
            pct_above_ma = (yr_valid["Close"] > yr_valid["MA"]).sum() / len(yr_valid) * 100
        else:
            pct_above_ma = 0.0

        # 3. MA slope at year end
        # Compare MA value at year end vs slope_lookback trading days earlier
        yr_valid_reset = yr_valid.reset_index(drop=True)
        if len(yr_valid_reset) >= slope_lookback + 1:
            ma_end   = yr_valid_reset["MA"].iloc[-1]
            ma_prior = yr_valid_reset["MA"].iloc[-(slope_lookback + 1)]
            slope_pct = (ma_end - ma_prior) / ma_prior * 100
            if slope_pct > 0.5:
                slope_label = "RISING"
            elif slope_pct < -0.5:
                slope_label = "FALLING"
            else:
                slope_label = "FLAT"
        else:
            slope_pct   = 0.0
            slope_label = "N/A"

        # 4. Max drawdown within year
        peak = yr_df["Close"].expanding().max()
        dd   = (yr_df["Close"] - peak) / peak * 100
        max_dd = abs(dd.min())

        # 5. Qualitative trend character
        if pct_above_ma >= 70 and annual_ret > 5 and slope_label == "RISING":
            trend_char = "STRONG BULL"
        elif pct_above_ma >= 55 and annual_ret > 0:
            trend_char = "MODERATE BULL"
        elif pct_above_ma >= 45 and abs(annual_ret) < 5:
            trend_char = "SIDEWAYS"
        elif pct_above_ma < 45 and annual_ret < -5:
            trend_char = "BEAR"
        else:
            trend_char = "MIXED"

        rows.append({
            "year":               year,
            "nifty_annual_ret":   round(annual_ret, 2),
            "pct_days_above_ma":  round(pct_above_ma, 1),
            "ma_slope_yr_end":    slope_label,
            "ma_slope_pct":       round(slope_pct, 2),
            "nifty_max_dd":       round(max_dd, 2),
            "trend_character":    trend_char,
        })

    return pd.DataFrame(rows)


# ─── MERGE AND PRINT ──────────────────────────────────────────────────────────

def build_combined_table(nifty_yearly: pd.DataFrame) -> pd.DataFrame:
    strat_rows = []
    for year, m in STRATEGY_RESULTS.items():
        strat_rows.append({"year": year, **m})
    strat_df = pd.DataFrame(strat_rows)

    combined = pd.merge(strat_df, nifty_yearly, on="year", how="left")
    return combined


def print_report(combined: pd.DataFrame):
    sep  = "=" * 100
    dash = "─" * 100

    print(f"\n{sep}")
    print("  STRATEGY 2 vs NIFTY REGIME — YEAR-BY-YEAR ANALYSIS")
    print(sep)

    print(f"\n{'Year':<6} {'Trades':<8} {'S2 Win%':<10} {'S2 PF':<8} {'S2 CAGR%':<11} "
          f"{'Nifty Ret%':<12} {'Above MA%':<11} {'MA Slope':<10} {'Trend'}")
    print(f"{'─'*6} {'─'*7} {'─'*9} {'─'*7} {'─'*10} {'─'*11} {'─'*10} {'─'*9} {'─'*15}")

    for _, row in combined.iterrows():
        print(
            f"  {int(row['year']):<4} "
            f"{int(row['trades']):<8} "
            f"{row['win_pct']:<10} "
            f"{row['pf']:<8} "
            f"{row['cagr']:<11} "
            f"{row.get('nifty_annual_ret', 'N/A'):<12} "
            f"{row.get('pct_days_above_ma', 'N/A'):<11} "
            f"{row.get('ma_slope_yr_end', 'N/A'):<10} "
            f"{row.get('trend_character', 'N/A')}"
        )

    print(f"\n{dash}")
    print("  CORRELATION ANALYSIS")
    print(dash)

    # Correlation between pct_days_above_ma and strategy PF
    valid = combined.dropna(subset=["pct_days_above_ma", "pf"])
    if len(valid) >= 4:
        corr_pf    = valid["pct_days_above_ma"].corr(valid["pf"])
        corr_winrt = valid["pct_days_above_ma"].corr(valid["win_pct"])
        corr_ret   = valid["nifty_annual_ret"].corr(valid["pf"])
        print(f"  Correlation: % days above MA  vs  Strategy PF     : {corr_pf:.3f}")
        print(f"  Correlation: % days above MA  vs  Strategy Win%   : {corr_winrt:.3f}")
        print(f"  Correlation: Nifty annual ret vs  Strategy PF     : {corr_ret:.3f}")
        print()
        print("  Interpretation guide:")
        print("  > +0.6  : strong positive — market trend strongly drives strategy results")
        print("    0–0.6 : weak/moderate — market trend matters but isn't the sole driver")
        print("  < 0     : negative — strategy performs better in weak markets (counter-trend)")

    print(f"\n{dash}")
    print("  REGIME BREAKDOWN — STRATEGY PERFORMANCE BY TREND CHARACTER")
    print(dash)

    for regime in ["STRONG BULL", "MODERATE BULL", "SIDEWAYS", "BEAR", "MIXED"]:
        regime_rows = combined[combined["trend_character"] == regime]
        if regime_rows.empty:
            continue
        years    = sorted(regime_rows["year"].astype(int).tolist())
        avg_pf   = regime_rows["pf"].mean()
        avg_win  = regime_rows["win_pct"].mean()
        avg_cagr = regime_rows["cagr"].mean()
        profitable = (regime_rows["pf"] >= 1.0).sum()
        print(f"\n  {regime} — years: {years}")
        print(f"    Avg PF: {avg_pf:.2f}  Avg Win%: {avg_win:.1f}%  Avg CAGR: {avg_cagr:.1f}%  "
              f"Profitable: {profitable}/{len(regime_rows)}")

    print(f"\n{sep}\n")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n  Loading Nifty data from: {NIFTY_CSV}")
    nifty_df = load_nifty(NIFTY_CSV)
    print(f"  Loaded {len(nifty_df)} rows  ({nifty_df['Date'].min().date()} to {nifty_df['Date'].max().date()})")

    print(f"  Computing yearly Nifty metrics (MA={MA_PERIOD}, slope lookback={SLOPE_LOOKBACK} days)...")
    nifty_yearly = compute_nifty_yearly(nifty_df, MA_PERIOD, SLOPE_LOOKBACK)

    combined = build_combined_table(nifty_yearly)

    print_report(combined)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "nifty_regime_analysis.csv")
    combined.to_csv(out_path, index=False)
    print(f"  Full table saved to: {out_path}\n")


if __name__ == "__main__":
    main()
