"""
momentum_ranker.py
==================
Strategy 2 — Phase A: Momentum Ranker

Ranks all Nifty 200 stocks by price / N-day moving average ratio.
Selects top 10% as the Strategy 2 tradeable universe.

Run weekly. On each run:
  - Overwrites momentum_ranks_latest.csv with full ranked list of all 200 stocks
  - Appends top 10% rows to momentum_history.csv (long format, never overwritten)

Customizable:
    --ma_days     : Moving average lookback period (default: 60)
    --offset_days : Compute momentum as of N trading days ago (default: 0 = today)

Usage:
    # Today's 60-day momentum
    python momentum_ranker.py

    # 90-day momentum
    python momentum_ranker.py --ma_days 90

    # 60-day momentum as of 10 trading days ago
    python momentum_ranker.py --offset_days 10

    # 90-day momentum as of 10 trading days ago
    python momentum_ranker.py --ma_days 90 --offset_days 10

Output files (C:/Projects/trading_engine/logs/Momentum Logs/):
    momentum_ranks_latest.csv
        Full ranked list of all 200 stocks. Overwritten on every run.
        Metadata header rows prefixed with # for clean CSV parsing:
            df = pd.read_csv('momentum_ranks_latest.csv', comment='#')

    momentum_history.csv
        Top 10% only. One row per symbol per week. Appended on every run.
        Used for Scenario B candidate identification.
        Columns: week_date, symbol, ratio, price, ma_value, ref_date, data_days, note

Research basis:
    Jegadeesh & Titman (1993) cross-sectional momentum
    Faber (2007) tactical asset allocation
    IBD Relative Strength Rating methodology
"""

import os
import argparse
import datetime
import pandas as pd
import numpy as np

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DATA_DIR        = r"C:\Projects\Backtesting System\data"
LOG_DIR         = r"C:\Projects\trading_engine\logs\Momentum Logs"
SYMBOLS_FILE    = r"C:\Projects\trading_engine\nifty200_symbols.txt"
LATEST_FILE     = "momentum_ranks_latest.csv"
HISTORY_FILE    = "momentum_history.csv"

DEFAULT_MA_DAYS         = 60
DEFAULT_OFFSET_DAYS     = 0
DEFAULT_LOOKBACK_WEEKS  = 4
TOP_PERCENTILE          = 0.10      # top 10% = ~20 stocks from Nifty 200

COL_DATE    = "Date"
COL_CLOSE   = "Close"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def load_symbols(filepath: str) -> list:
    """Load Nifty 200 symbols from text file. One symbol per line."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Symbols file not found: {filepath}")
    symbols = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(line)
    if not symbols:
        raise ValueError(f"No symbols loaded from {filepath}")
    return symbols


def find_price_csv(symbol: str, data_dir: str) -> str | None:
    """
    Find price CSV for a symbol in data_dir.
    Tries multiple naming conventions.
    """
    candidates = [
        os.path.join(data_dir, f"{symbol}.csv"),
        os.path.join(data_dir, f"{symbol.replace('.NS', '')}.csv"),
        os.path.join(data_dir, f"{symbol.replace('.NS', '')}_NS.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def load_price_series(csv_path: str) -> pd.Series | None:
    """
    Load closing price series from CSV.
    Returns a pd.Series indexed by date sorted ascending, or None on failure.
    """
    try:
        df = pd.read_csv(csv_path, parse_dates=[COL_DATE])

        col_map = {c.lower(): c for c in df.columns}
        if COL_DATE.lower() not in col_map:
            return None
        if COL_CLOSE.lower() not in col_map:
            return None

        date_col  = col_map[COL_DATE.lower()]
        close_col = col_map[COL_CLOSE.lower()]

        df = df[[date_col, close_col]].copy()
        df.columns = [COL_DATE, COL_CLOSE]
        df = df.dropna(subset=[COL_DATE, COL_CLOSE])
        df[COL_DATE]  = pd.to_datetime(df[COL_DATE])
        df[COL_CLOSE] = pd.to_numeric(df[COL_CLOSE], errors="coerce")
        df = df.dropna(subset=[COL_CLOSE])
        df = df.sort_values(COL_DATE).reset_index(drop=True)

        series = df.set_index(COL_DATE)[COL_CLOSE]
        return series

    except Exception:
        return None


def get_reference_index(series: pd.Series, offset_days: int) -> int | None:
    """
    Get the integer index position of the reference date in the series.

    offset_days=0 : most recent trading day in the series
    offset_days=N : N trading days back from the most recent date

    Uses the actual trading calendar from the price data.
    Returns None if there is insufficient data for the requested offset.
    """
    last_idx = len(series) - 1
    ref_idx  = last_idx - offset_days

    if ref_idx < 0:
        return None
    return ref_idx


def compute_momentum_ratio(
    series: pd.Series,
    ma_days: int,
    offset_days: int
) -> dict:
    """
    Compute price / N-day MA ratio at the reference date.

    Returns a dict with:
        ratio       : float or None
        price       : price on reference date
        ma_value    : MA value on reference date
        ref_date    : reference date as string
        data_days   : total trading days available in series
        note        : warning message if applicable
    """
    result = {
        "ratio":     None,
        "price":     None,
        "ma_value":  None,
        "ref_date":  None,
        "data_days": len(series) if series is not None else 0,
        "note":      "",
    }

    if series is None or len(series) == 0:
        result["note"] = "No price data"
        return result

    result["data_days"] = len(series)

    ref_idx = get_reference_index(series, offset_days)

    if ref_idx is None:
        result["note"] = (
            f"Insufficient data for offset: {len(series)} days available, "
            f"{offset_days + 1} required"
        )
        return result

    ma_start_idx = ref_idx - ma_days + 1

    if ma_start_idx < 0:
        result["note"] = (
            f"Insufficient data for MA: {ref_idx + 1} days at reference point, "
            f"{ma_days} required"
        )
        return result

    ma_window    = series.iloc[ma_start_idx : ref_idx + 1]
    price_at_ref = series.iloc[ref_idx]
    ref_date     = series.index[ref_idx]

    if len(ma_window) < ma_days:
        result["note"] = (
            f"Insufficient data for MA: {len(ma_window)} days in window, "
            f"{ma_days} required"
        )
        return result

    ma_val = ma_window.mean()

    if ma_val == 0:
        result["note"] = "MA value is zero — cannot compute ratio"
        return result

    ratio = price_at_ref / ma_val

    result["ratio"]    = round(float(ratio), 4)
    result["price"]    = round(float(price_at_ref), 2)
    result["ma_value"] = round(float(ma_val), 2)
    result["ref_date"] = str(ref_date.date())

    if ratio < 1.0:
        result["note"] = "Below MA — weak momentum"

    return result


# ─── OUTPUT ──────────────────────────────────────────────────────────────────

def write_output(
    records: list,
    log_dir: str,
    ma_days: int,
    offset_days: int,
    calc_date: str,
) -> tuple:
    """
    Write two output files on every run.

    1. momentum_ranks_latest.csv
       Full ranked list of all 200 stocks. Overwritten on every run.
       Includes metadata header rows prefixed with # for clean parsing:
           df = pd.read_csv('momentum_ranks_latest.csv', comment='#')

    2. momentum_history.csv
       Top 10% only. Appended on every run. Never overwritten.
       Long format — one row per symbol per weekly run.
       Columns: week_date, symbol, ratio, price, ma_value, ref_date, data_days, note

    Returns (latest_path, history_path).
    """
    os.makedirs(log_dir, exist_ok=True)

    # ── Build ranked DataFrame ────────────────────────────────────────────────
    df_valid   = pd.DataFrame([r for r in records if r["ratio"] is not None])
    df_invalid = pd.DataFrame([r for r in records if r["ratio"] is None])

    if not df_valid.empty:
        df_valid = df_valid.sort_values("ratio", ascending=False).reset_index(drop=True)
        df_valid["rank"] = df_valid.index + 1
        cutoff = max(1, int(np.ceil(len(df_valid) * TOP_PERCENTILE)))
        df_valid["in_universe"] = df_valid["rank"] <= cutoff
    else:
        df_valid["rank"]        = pd.Series(dtype=int)
        df_valid["in_universe"] = pd.Series(dtype=bool)
        cutoff = 0

    if not df_invalid.empty:
        df_invalid["rank"]        = None
        df_invalid["in_universe"] = False

    df_all = pd.concat([df_valid, df_invalid], ignore_index=True)

    df_out = df_all[[
        "rank", "symbol", "ratio", "price", "ma_value",
        "ref_date", "data_days", "in_universe", "note"
    ]].copy()

    # ── File 1: momentum_ranks_latest.csv (full 200, overwrite) ──────────────
    latest_path = os.path.join(log_dir, LATEST_FILE)
    with open(latest_path, "w", encoding="utf-8", newline="") as f:
        f.write(f"# calculation_date: {calc_date}\n")
        f.write(f"# ma_days: {ma_days}\n")
        f.write(f"# offset_days: {offset_days}\n")
        df_out.to_csv(f, index=False)

    # ── File 2: momentum_history.csv (top 10% only, append) ──────────────────
    history_path = os.path.join(log_dir, HISTORY_FILE)

    if not df_valid.empty and cutoff > 0:
        df_universe = df_valid[df_valid["in_universe"] == True].copy()
        df_universe.insert(0, "week_date", calc_date)
        history_cols = ["week_date", "symbol", "ratio", "price", "ma_value",
                        "ref_date", "data_days", "note"]
        df_history = df_universe[history_cols].copy()

        file_exists = os.path.exists(history_path)
        df_history.to_csv(
            history_path,
            mode    = "a" if file_exists else "w",
            index   = False,
            header  = not file_exists,
            encoding= "utf-8",
        )

    return latest_path, history_path


# ─── SCENARIO B CANDIDATES ────────────────────────────────────────────────────

def get_scenario_b_candidates(
    log_dir: str = LOG_DIR,
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
) -> list:
    """
    Identify Scenario B candidates — stocks that were in the top 10% momentum
    universe within the last N weeks but are NOT in the current week's universe.

    These are active trading candidates for the S/R retest pullback strategy.
    A stock that had genuine momentum and is now consolidating is a candidate
    once the S/R retest entry signal fires.

    Parameters
    ----------
    log_dir        : Directory containing momentum_history.csv
    lookback_weeks : How many weeks back to look for prior universe membership.
                     Default: 4 weeks. Calibrated to 15-45 day holding period.
                     Stocks that dropped out more than 4 weeks ago are likely
                     past the consolidation window relevant to our strategy.
                     (Bulkowski 2005, Carter 2005)

    Returns
    -------
    list of str : Scenario B candidate symbols, sorted alphabetically.
                  Empty list if history file is missing or has insufficient data.
    """
    history_path = os.path.join(log_dir, HISTORY_FILE)

    if not os.path.exists(history_path):
        print(f"[WARNING] History file not found: {history_path}")
        print("[WARNING] Run the ranker at least once to build history.")
        return []

    try:
        df = pd.read_csv(history_path, parse_dates=["week_date"], encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Could not read history file: {e}")
        return []

    if df.empty or "week_date" not in df.columns or "symbol" not in df.columns:
        print("[WARNING] History file is empty or missing required columns.")
        return []

    # Most recent week in the history file
    latest_week = df["week_date"].max()

    # Lookback cutoff — N weeks before the most recent run
    lookback_cutoff = latest_week - pd.Timedelta(weeks=lookback_weeks)

    # Current universe: symbols in the most recent week
    current_universe = set(
        df[df["week_date"] == latest_week]["symbol"].unique()
    )

    # Recent history: symbols that appeared in any prior week within the lookback window
    recent_history = df[
        (df["week_date"] > lookback_cutoff) &
        (df["week_date"] < latest_week)
    ]
    recent_universe = set(recent_history["symbol"].unique())

    # Scenario B: was in universe recently, not in universe now
    scenario_b = sorted(recent_universe - current_universe)

    return scenario_b


# ─── CONSOLE SUMMARY ─────────────────────────────────────────────────────────

def print_summary(
    records: list,
    ma_days: int,
    offset_days: int,
    latest_path: str,
    history_path: str,
    scenario_b: list,
) -> None:
    """Print ranked universe, summary statistics, and Scenario B candidates."""

    valid   = [r for r in records if r["ratio"] is not None]
    invalid = [r for r in records if r["ratio"] is None]

    if not valid:
        print("\n[WARNING] No valid momentum ratios computed. Check price data.")
        return

    valid_sorted = sorted(valid, key=lambda x: x["ratio"], reverse=True)
    cutoff       = max(1, int(np.ceil(len(valid_sorted) * TOP_PERCENTILE)))
    ref_date     = valid_sorted[0]["ref_date"] if valid_sorted else "N/A"

    print(f"\n{'=' * 72}")
    print(f"MOMENTUM RANKER — Strategy 2 Universe")
    print(f"Reference date : {ref_date}  (offset: {offset_days} trading days back)")
    print(f"MA period      : {ma_days} days")
    print(f"Universe       : Top {int(TOP_PERCENTILE * 100)}%  "
          f"({cutoff} of {len(valid_sorted)} ranked stocks)")
    print(f"{'=' * 72}")
    print(f"  {'Rank':<5} {'Symbol':<18} {'Ratio':>7}  {'Price':>9}  {'MA':>9}  {'Note'}")
    print(f"  {'-' * 67}")

    for i, r in enumerate(valid_sorted, 1):
        marker = "  ◀ UNIVERSE" if i <= cutoff else ""
        note   = r.get("note", "")
        print(
            f"  {i:<5} "
            f"{r['symbol']:<18} "
            f"{r['ratio']:>7.4f}  "
            f"{r['price']:>9.2f}  "
            f"{r['ma_value']:>9.2f}  "
            f"{note}{marker}"
        )

    if invalid:
        print(f"\n  Stocks with missing data or CSV errors: {len(invalid)}")
        for r in invalid:
            print(f"    {r['symbol']:<20}  {r.get('note', '')}")

    # Market condition warnings
    below_ma = sum(1 for r in valid_sorted if r["ratio"] < 1.0)
    if below_ma == len(valid_sorted):
        print(f"\n  WARNING: All {below_ma} stocks below their {ma_days}-day MA.")
        print(f"     Market is broadly weak. Treat this as a no-trade week.")
    elif below_ma > len(valid_sorted) * 0.7:
        print(f"\n  NOTE: {below_ma}/{len(valid_sorted)} stocks below {ma_days}-day MA.")
        print(f"     Market conditions are weak. Review universe carefully.")

    # Scenario B candidates
    print(f"\n{'─' * 72}")
    print(f"  SCENARIO B CANDIDATES  (in top 10% recently, now consolidating)")
    print(f"{'─' * 72}")
    if scenario_b:
        for sym in scenario_b:
            print(f"    {sym}")
    else:
        print(f"    None identified — insufficient history or all stocks still in universe.")

    print(f"\n  Latest rankings : {latest_path}")
    print(f"  History file    : {history_path}")
    print(f"  To load latest  : pd.read_csv(r'{latest_path}', comment='#')")
    print(f"  To load history : pd.read_csv(r'{history_path}')")
    print(f"{'=' * 72}\n")


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def run(
    ma_days: int = DEFAULT_MA_DAYS,
    offset_days: int = DEFAULT_OFFSET_DAYS,
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    symbols_file: str = SYMBOLS_FILE,
    data_dir: str = DATA_DIR,
    log_dir: str = LOG_DIR,
) -> tuple:
    """
    Core function — callable from other modules (S/R detection, strategy).

    On every run:
      - Overwrites momentum_ranks_latest.csv with full ranked list of all 200 stocks
      - Appends top 10% rows to momentum_history.csv
      - Identifies and returns Scenario B candidates

    Parameters
    ----------
    ma_days        : Moving average lookback period in trading days
    offset_days    : How many trading days back to compute momentum
                     0 = most recent trading day
                     N = N trading days back (uses actual trading calendar)
    lookback_weeks : Weeks back to search for Scenario B candidates (default: 4)
    symbols_file   : Path to Nifty 200 symbols text file
    data_dir       : Directory containing price CSV files
    log_dir        : Directory to write output files

    Returns
    -------
    tuple : (latest_path, history_path, scenario_b_candidates)
        latest_path           : Full path to momentum_ranks_latest.csv
        history_path          : Full path to momentum_history.csv
        scenario_b_candidates : List of Scenario B candidate symbols
    """
    calc_date = datetime.date.today().strftime("%Y-%m-%d")
    symbols   = load_symbols(symbols_file)
    total     = len(symbols)

    print(f"\n[INFO] Momentum Ranker")
    print(f"[INFO] Symbols     : {total} from {symbols_file}")
    print(f"[INFO] MA period   : {ma_days} days")
    print(f"[INFO] Offset      : {offset_days} trading days back")
    print(f"[INFO] Data dir    : {data_dir}")
    print(f"[INFO] Output dir  : {log_dir}")
    print("-" * 60)

    records = []

    for i, symbol in enumerate(symbols, 1):
        csv_path = find_price_csv(symbol, data_dir)

        if csv_path is None:
            records.append({
                "symbol":    symbol,
                "ratio":     None,
                "price":     None,
                "ma_value":  None,
                "ref_date":  None,
                "data_days": 0,
                "note":      "No CSV found",
            })
            print(f"  [{i:3d}/{total}] {symbol:<20}  X  No CSV found")
            continue

        series = load_price_series(csv_path)

        if series is None:
            records.append({
                "symbol":    symbol,
                "ratio":     None,
                "price":     None,
                "ma_value":  None,
                "ref_date":  None,
                "data_days": 0,
                "note":      "CSV load failed",
            })
            print(f"  [{i:3d}/{total}] {symbol:<20}  X  CSV load failed")
            continue

        m           = compute_momentum_ratio(series, ma_days, offset_days)
        m["symbol"] = symbol
        records.append(m)

        if m["ratio"] is not None:
            print(f"  [{i:3d}/{total}] {symbol:<20}  {m['ratio']:.4f}  {m.get('note', '')}")
        else:
            print(f"  [{i:3d}/{total}] {symbol:<20}  !  {m['note']}")

    latest_path, history_path = write_output(
        records, log_dir, ma_days, offset_days, calc_date
    )

    scenario_b = get_scenario_b_candidates(log_dir, lookback_weeks)

    print_summary(records, ma_days, offset_days, latest_path, history_path, scenario_b)

    return latest_path, history_path, scenario_b


# ─── CLI ENTRY POINT ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Strategy 2 Momentum Ranker\n"
            "Ranks Nifty 200 stocks by price / N-day MA ratio.\n"
            "Selects top 10% as the weekly tradeable universe.\n"
            "Appends top 10% to momentum_history.csv for Scenario B tracking."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ma_days", type=int, default=DEFAULT_MA_DAYS,
        help=f"MA lookback in trading days (default: {DEFAULT_MA_DAYS})"
    )
    parser.add_argument(
        "--offset_days", type=int, default=DEFAULT_OFFSET_DAYS,
        help=(
            "Compute momentum N trading days back from most recent data. "
            f"Default: {DEFAULT_OFFSET_DAYS} (most recent trading day). "
            "Uses actual trading calendar from price CSVs."
        )
    )
    parser.add_argument(
        "--lookback_weeks", type=int, default=DEFAULT_LOOKBACK_WEEKS,
        help=(
            "Weeks back to search for Scenario B candidates. "
            f"Default: {DEFAULT_LOOKBACK_WEEKS} weeks."
        )
    )
    parser.add_argument(
        "--symbols_file", type=str, default=SYMBOLS_FILE,
        help=f"Path to Nifty 200 symbols file (default: {SYMBOLS_FILE})"
    )
    parser.add_argument(
        "--data_dir", type=str, default=DATA_DIR,
        help=f"Directory containing price CSVs (default: {DATA_DIR})"
    )
    parser.add_argument(
        "--log_dir", type=str, default=LOG_DIR,
        help=f"Output directory for momentum files (default: {LOG_DIR})"
    )

    args = parser.parse_args()

    run(
        ma_days        = args.ma_days,
        offset_days    = args.offset_days,
        lookback_weeks = args.lookback_weeks,
        symbols_file   = args.symbols_file,
        data_dir       = args.data_dir,
        log_dir        = args.log_dir,
    )


if __name__ == "__main__":
    main()
