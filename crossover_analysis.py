
"""
crossover_analysis.py
Analyses the trade log to determine:
1. Holding period distribution
2. Post-crossover confirmation signals (price, ADX, RSI)
3. Volume behaviour before, on, and after the crossover day

Usage:
    python crossover_analysis.py

Inputs:
    - trade_log.csv  : C:\Projects\trading_engine\logs\trade_log.csv
    - Price data     : C:\Projects\Backtesting System\data\
"""

import os
import pandas as pd
import numpy as np

# =============================================================================
# CONFIGURATION
# =============================================================================

TRADE_LOG_PATH = r"C:\Projects\trading_engine\logs\trade_log.csv"
DATA_DIR       = r"C:\Projects\Backtesting System\data"
PRE_DAYS       = 10
POST_DAYS      = 5
VOLUME_MA      = 20
RSI_PERIOD     = 14
ADX_PERIOD     = 14

# =============================================================================
# HELPERS
# =============================================================================

def symbol_to_filename(symbol):
    return symbol.replace(".", "_") + ".csv"

def load_price_data(symbol):
    filepath = os.path.join(DATA_DIR, symbol_to_filename(symbol))
    if not os.path.exists(filepath):
        return None
    df = pd.read_csv(filepath, parse_dates=["Date"])
    return df.sort_values("Date").reset_index(drop=True)

def calculate_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_adx(df, period=14):
    high  = df["High"]
    low   = df["Low"]
    close = df["Adj Close"]
    tr    = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr   = tr.ewm(alpha=1/period, min_periods=period).mean()
    up    = high.diff()
    down  = -low.diff()
    pdm   = up.where((up > down) & (up > 0), 0.0)
    ndm   = down.where((down > up) & (down > 0), 0.0)
    pdi   = 100 * pdm.ewm(alpha=1/period, min_periods=period).mean() / atr
    ndi   = 100 * ndm.ewm(alpha=1/period, min_periods=period).mean() / atr
    dx    = (100 * (pdi - ndi).abs() / (pdi + ndi)).fillna(0)
    return dx.ewm(alpha=1/period, min_periods=period).mean()

def _days_above_ema200(df, entry_i, lookback=252):
    """Count consecutive days price was above EMA200 before crossover."""
    if 'EMA_200' not in df.columns:
        df['EMA_200'] = df['Adj Close'].ewm(span=200, adjust=False).mean()
    # Look back up to 252 trading days before crossover
    start_i = max(0, entry_i - lookback)
    window  = df.iloc[start_i:entry_i]
    above   = window['Adj Close'] > window['EMA_200']
    # Count consecutive days from the crossover backwards
    count = 0
    for val in reversed(above.values):
        if val:
            count += 1
        else:
            break
    return count

def _ema200_rising(df, entry_i, lookback=20):
    """Check if EMA200 slope is positive over last N days before crossover."""
    if 'EMA_200' not in df.columns:
        df['EMA_200'] = df['Adj Close'].ewm(span=200, adjust=False).mean()
    if entry_i < lookback:
        return 0
    window = df.iloc[entry_i - lookback : entry_i + 1]
    slope  = np.polyfit(range(len(window)), window['EMA_200'].values, 1)[0]
    return int(slope > 0)

def _ema200_slope(df, entry_i, lookback=20):
    """EMA200 slope as % change over last N days."""
    if 'EMA_200' not in df.columns:
        df['EMA_200'] = df['Adj Close'].ewm(span=200, adjust=False).mean()
    if entry_i < lookback:
        return 0.0
    start_val = df.iloc[entry_i - lookback]['EMA_200']
    end_val   = df.iloc[entry_i]['EMA_200']
    if start_val == 0:
        return 0.0
    return ((end_val - start_val) / start_val) * 100

def extract_features(df, entry_date):
    """
    Extract all features — price, volume, ADX, RSI —
    in the window around the crossover date.
    Returns dict of features or None if insufficient data.
    """
    df = df.copy()

    # Indicators
    df["EMA20"]     = df["Adj Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"]     = df["Adj Close"].ewm(span=50, adjust=False).mean()
    df["RSI"]       = calculate_rsi(df["Adj Close"], RSI_PERIOD)
    df["ADX"]       = calculate_adx(df, ADX_PERIOD)
    df["Vol_MA"]    = df["Volume"].rolling(VOLUME_MA).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_MA"]
    df["EMA_200"]   = df["Adj Close"].ewm(span=200, adjust=False).mean()

    # Find entry index
    entry_idx = df[df["Date"] <= entry_date].index
    if len(entry_idx) == 0:
        return None
    entry_i = entry_idx[-1]

    if entry_i < PRE_DAYS or entry_i + POST_DAYS >= len(df):
        return None

    pre   = df.iloc[entry_i - PRE_DAYS : entry_i]
    cross = df.iloc[entry_i]
    post  = df.iloc[entry_i + 1 : entry_i + 1 + POST_DAYS]

    if len(post) < POST_DAYS:
        return None

    # Volume trend before crossover
    pre_vol_slope = np.polyfit(range(len(pre)), pre["Volume"].values, 1)[0]

    return {
        # ── Price features ────────────────────────────────────────────
        "price_held_above_ema20"    : int(all(post["Adj Close"] > post["EMA20"])),
        "consecutive_up_days"       : int(all(post["Adj Close"].diff().dropna() > 0)),
        "pct_change_5d"             : (post.iloc[-1]["Adj Close"] - cross["Adj Close"]) / cross["Adj Close"] * 100,

        # ── ADX features ──────────────────────────────────────────────
        "crossover_adx"             : cross["ADX"],
        "adx_rising"                : int(post["ADX"].iloc[-1] > cross["ADX"]),
        "adx_change_5d"             : post["ADX"].iloc[-1] - cross["ADX"],

        # ── RSI features ──────────────────────────────────────────────
        "crossover_rsi"             : cross["RSI"],
        "rsi_above_50"              : int(cross["RSI"] >= 50),
        "avg_rsi_5d"                : post["RSI"].mean(),

        # ── Volume: pre-crossover ─────────────────────────────────────
        "avg_vol_ratio_pre10d"      : pre["Vol_Ratio"].mean(),
        "vol_above_avg_days_pre10"  : int((pre["Vol_Ratio"] > 1.0).sum()),
        "vol_rising_into_crossover" : int(pre_vol_slope > 0),
        "max_vol_ratio_pre10d"      : pre["Vol_Ratio"].max(),

        # ── Volume: crossover day ─────────────────────────────────────
        "vol_ratio_crossover_day"   : cross["Vol_Ratio"],

        # ── Volume: post-crossover ────────────────────────────────────
        "vol_ratio_day1_post"       : post.iloc[0]["Vol_Ratio"],
        "vol_ratio_day2_post"       : post.iloc[1]["Vol_Ratio"],
        "vol_ratio_day3_post"       : post.iloc[2]["Vol_Ratio"],
        "avg_vol_ratio_post5d"      : post["Vol_Ratio"].mean(),
        "vol_above_avg_days_post5"  : int((post["Vol_Ratio"] > 1.0).sum()),
        "vol_expanded_post_vs_pre"  : int(post["Vol_Ratio"].mean() > pre["Vol_Ratio"].mean()),
        "vol_contracted_post"       : int(post["Vol_Ratio"].mean() < 0.8),

        # ── EMA200 uptrend strength ───────────────────────────────────
        "days_above_ema200"         : _days_above_ema200(df, entry_i),
        "ema200_rising"             : _ema200_rising(df, entry_i),
        "ema200_slope_pct"          : _ema200_slope(df, entry_i),
    }

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 65)
    print("  Crossover Analysis — Confirmation Signal Study")
    print("=" * 65)

    if not os.path.exists(TRADE_LOG_PATH):
        print(f"\nERROR: Trade log not found at {TRADE_LOG_PATH}")
        return

    trades = pd.read_csv(TRADE_LOG_PATH, parse_dates=["entry_date", "exit_date"])
    trades["hold_days"] = (trades["exit_date"] - trades["entry_date"]).dt.days
    trades["is_winner"] = trades["exit_price"] > trades["entry_price"]
    print(f"Trades loaded: {len(trades)} | Winners: {trades['is_winner'].sum()} | Losers: {(~trades['is_winner']).sum()}\n")

    # ==========================================================================
    # SECTION 1: HOLDING PERIOD DISTRIBUTION
    # ==========================================================================
    print("--- SECTION 1: HOLDING PERIOD DISTRIBUTION ---")
    print(f"  Minimum   : {trades['hold_days'].min():.0f} days")
    print(f"  25th Pct  : {trades['hold_days'].quantile(0.25):.0f} days")
    print(f"  Median    : {trades['hold_days'].median():.0f} days")
    print(f"  Mean      : {trades['hold_days'].mean():.0f} days")
    print(f"  75th Pct  : {trades['hold_days'].quantile(0.75):.0f} days")
    print(f"  90th Pct  : {trades['hold_days'].quantile(0.90):.0f} days")
    print(f"  Maximum   : {trades['hold_days'].max():.0f} days")

    winners = trades[trades["is_winner"]]
    losers  = trades[~trades["is_winner"]]
    print(f"\n  Winners — Median: {winners['hold_days'].median():.0f} days | Mean: {winners['hold_days'].mean():.0f} days | Count: {len(winners)}")
    print(f"  Losers  — Median: {losers['hold_days'].median():.0f} days  | Mean: {losers['hold_days'].mean():.0f} days  | Count: {len(losers)}")

    # ==========================================================================
    # SECTION 2: EXTRACT FEATURES
    # ==========================================================================
    print("\n--- EXTRACTING FEATURES (loading price data...) ---")

    winner_features, loser_features, skipped = [], [], 0

    for _, trade in trades.iterrows():
        df = load_price_data(trade["symbol"])
        if df is None:
            skipped += 1
            continue
        features = extract_features(df, trade["entry_date"])
        if features is None:
            skipped += 1
            continue
        if trade["is_winner"]:
            winner_features.append(features)
        else:
            loser_features.append(features)

    print(f"  Processed: {len(winner_features) + len(loser_features)} | Skipped: {skipped}")

    if not winner_features or not loser_features:
        print("  Insufficient data for comparison.")
        return

    w = pd.DataFrame(winner_features)
    l = pd.DataFrame(loser_features)

    # ==========================================================================
    # SECTION 3: PRICE & MOMENTUM SIGNALS
    # ==========================================================================
    print("\n--- SECTION 2: PRICE & MOMENTUM SIGNALS ---")
    print(f"  {'Feature':<38} {'Winners':>10} {'Losers':>10} {'Edge':>10}")
    print(f"  {'-'*68}")

    continuous = [
        ("crossover_rsi",    "RSI on Crossover Day",            "{:.1f}"),
        ("crossover_adx",    "ADX on Crossover Day",            "{:.1f}"),
        ("adx_change_5d",    "ADX Change 5d Post Entry",        "{:.2f}"),
        ("avg_rsi_5d",       "Avg RSI 5d Post Entry",           "{:.1f}"),
        ("pct_change_5d",    "Price Change 5d Post Entry (%)",  "{:.2f}%"),
    ]
    for col, label, fmt in continuous:
        w_val = w[col].mean()
        l_val = l[col].mean()
        print(f"  {label:<38} {fmt.format(w_val):>10} {fmt.format(l_val):>10} {w_val-l_val:>+10.2f}")

    print(f"\n  {'Signal':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    binary = [
        ("price_held_above_ema20", "Price held above EMA20 all 5d"),
        ("adx_rising",             "ADX rising after crossover"),
        ("rsi_above_50",           "RSI >= 50 on crossover day"),
        ("consecutive_up_days",    "5 consecutive up days"),
    ]
    for col, label in binary:
        print(f"  {label:<38} {w[col].mean()*100:>9.1f}% {l[col].mean()*100:>9.1f}%")

    # ==========================================================================
    # SECTION 4: VOLUME ANALYSIS
    # ==========================================================================
    print("\n--- SECTION 3: VOLUME ANALYSIS ---")
    print(f"  {'Period':<38} {'Winners':>10} {'Losers':>10} {'Edge':>10}")
    print(f"  {'-'*68}")

    vol_continuous = [
        ("avg_vol_ratio_pre10d",     "Avg Volume Ratio (10d before)"),
        ("max_vol_ratio_pre10d",     "Max Volume Spike (10d before)"),
        ("vol_ratio_crossover_day",  "Volume Ratio on Crossover Day"),
        ("vol_ratio_day1_post",      "Volume Ratio Day 1 After"),
        ("vol_ratio_day2_post",      "Volume Ratio Day 2 After"),
        ("vol_ratio_day3_post",      "Volume Ratio Day 3 After"),
        ("avg_vol_ratio_post5d",     "Avg Volume Ratio (5d after)"),
    ]

    # Binary: what % of individual trades had volume above average on crossover day
    print("\n--- CROSSOVER DAY VOLUME: INDIVIDUAL TRADE BREAKDOWN ---")
    print(f"  {'Threshold':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    for threshold in [0.8, 1.0, 1.25, 1.5, 2.0]:
        w_pct = (w["vol_ratio_crossover_day"] > threshold).mean() * 100
        l_pct = (l["vol_ratio_crossover_day"] > threshold).mean() * 100
        label = f"Volume > {threshold:.2f}x average"
        print(f"  {label:<38} {w_pct:>9.1f}% {l_pct:>9.1f}%")

    # Distribution of crossover day volume ratios
    print("\n--- CROSSOVER DAY VOLUME: DISTRIBUTION ---")
    print(f"  {'Percentile':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    for pct in [25, 50, 75, 90]:
        w_val = w["vol_ratio_crossover_day"].quantile(pct/100)
        l_val = l["vol_ratio_crossover_day"].quantile(pct/100)
        label = f"{pct}th percentile volume ratio"
        print(f"  {label:<38} {w_val:>9.2f}x {l_val:>9.2f}x")
    for col, label in vol_continuous:
        w_val = w[col].mean()
        l_val = l[col].mean()
        print(f"  {label:<38} {w_val:>9.2f}x {l_val:>9.2f}x {w_val-l_val:>+10.2f}")

    print(f"\n  {'Signal':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    vol_binary = [
        ("vol_rising_into_crossover",  "Volume rising into crossover"),
        ("vol_expanded_post_vs_pre",   "Volume expanded post vs pre"),
        ("vol_contracted_post",        "Volume contracted post (<0.8x)"),
    ]
    for col, label in vol_binary:
        print(f"  {label:<38} {w[col].mean()*100:>9.1f}% {l[col].mean()*100:>9.1f}%")

    w_above_pre  = w["vol_above_avg_days_pre10"].mean()
    l_above_pre  = l["vol_above_avg_days_pre10"].mean()
    w_above_post = w["vol_above_avg_days_post5"].mean()
    l_above_post = l["vol_above_avg_days_post5"].mean()
    print(f"  {'Days above avg vol (of 10 pre)':<38} {w_above_pre:>10.1f} {l_above_pre:>10.1f}")
    print(f"  {'Days above avg vol (of 5 post)':<38} {w_above_post:>10.1f} {l_above_post:>10.1f}")

    # ==========================================================================
    # SECTION 4: EMA200 UPTREND STRENGTH
    # ==========================================================================
    print("\n--- SECTION 4: EMA200 UPTREND STRENGTH ---")
    print(f"  {'Metric':<38} {'Winners':>10} {'Losers':>10} {'Edge':>10}")
    print(f"  {'-'*68}")

    ema200_continuous = [
        ("days_above_ema200",  "Days above EMA200 before crossover", "{:.0f}"),
        ("ema200_slope_pct",   "EMA200 slope % (20d before)",        "{:.3f}%"),
    ]
    for col, label, fmt in ema200_continuous:
        w_val = w[col].mean()
        l_val = l[col].mean()
        print(f"  {label:<38} {fmt.format(w_val):>10} {fmt.format(l_val):>10} {w_val-l_val:>+10.2f}")

    print(f"\n  {'Signal':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    print(f"  {'EMA200 rising at crossover':<38} {w['ema200_rising'].mean()*100:>9.1f}% {l['ema200_rising'].mean()*100:>9.1f}%")

    print("\n--- EMA200 DAYS ABOVE: DISTRIBUTION ---")
    print(f"  {'Percentile':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    for pct in [25, 50, 75, 90]:
        w_val = w["days_above_ema200"].quantile(pct/100)
        l_val = l["days_above_ema200"].quantile(pct/100)
        print(f"  {pct}th percentile (days above EMA200)       {w_val:>10.0f} {l_val:>10.0f}")

    print("\n--- EMA200 DAYS ABOVE: THRESHOLD BREAKDOWN ---")
    print(f"  {'Threshold':<38} {'Winners':>10} {'Losers':>10}")
    print(f"  {'-'*58}")
    for days in [1, 5, 10, 20, 40, 60]:
        w_pct = (w["days_above_ema200"] >= days).mean() * 100
        l_pct = (l["days_above_ema200"] >= days).mean() * 100
        label = f"Above EMA200 for >= {days} days"
        print(f"  {label:<38} {w_pct:>9.1f}% {l_pct:>9.1f}%")

    print("\n" + "=" * 65)
    print("  Analysis complete.")
    print("=" * 65)

if __name__ == "__main__":
    main()
