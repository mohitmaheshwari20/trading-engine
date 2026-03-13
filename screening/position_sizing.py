"""
position_sizing.py
==================
Strategy 2 — Phase D: Position Sizing Module

Computes how many shares to buy for each confirmed entry signal so that
if the stop loss is hit, the loss equals no more than 2% of total capital.

METHOD: Fixed Fractional Position Sizing
    Research: Van Tharp, Trade Your Way to Financial Freedom (1997)
              O'Neil, How to Make Money in Stocks
              Schwager, Market Wizards

FORMULA:
    Risk Amount (INR)  = Total Capital x Risk Per Trade %
    Stop Distance (INR) = Entry Price - Stop Loss Price
    Raw Shares          = Risk Amount / Stop Distance  (floor)
    Position Value      = Raw Shares x Entry Price

    If Position Value > Available Capital:
        Final Shares = floor(Available Capital / Entry Price)  [scale down]
    Else:
        Final Shares = Raw Shares  [full position]

    If Final Shares = 0: skip trade, flag INSUFFICIENT CAPITAL
    If Open Positions >= Max Concurrent: skip trade, flag MAX POSITIONS REACHED

CAPITAL TRACKING:
    Available Capital = Total Capital - sum(Entry Price x Shares for all open positions)
    Open positions read from: C:\Projects\trading_engine\logs\open_positions.csv
    Columns expected: Symbol, Entry_Date, Entry_Price, SL_Price, Shares

EXIT SIZING:
    Target 1 (partial exit): sell floor(Shares x 0.50) — 50% of position
    Target 2 / Stop Loss:    sell all remaining shares

Usage:
    # Run on all entry signals from entry_signal.py output
    python position_sizing.py

    # Run on a specific symbol
    python position_sizing.py --symbol BSE.NS

    # Override capital or risk parameters
    python position_sizing.py --total_capital 100000 --risk_pct 0.02

Output:
    C:/Projects/trading_engine/logs/Entry Logs/sized_signals_latest.csv
    C:/Projects/trading_engine/logs/Entry Logs/sized_signals_YYYYMMDD.csv
"""

import os
import argparse
import datetime
import math
import pandas as pd
from typing import Optional

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TOTAL_CAPITAL           = 100_000.0     # INR — update when capital changes
RISK_PER_TRADE          = 0.02          # 2% of total capital per trade
MAX_CONCURRENT_POSITIONS = 2            # hard limit on open positions
PARTIAL_BOOKING_PCT     = 0.50          # sell 50% at Target 1

ENTRY_LOG_DIR           = r"C:\Projects\trading_engine\logs\Entry Logs"
OPEN_POSITIONS_FILE     = r"C:\Projects\trading_engine\logs\open_positions.csv"
ENTRY_LATEST_FILE       = "entry_signals_latest.csv"
SIZED_LATEST_FILE       = "sized_signals_latest.csv"

# open_positions.csv expected columns
COL_SYMBOL      = "Symbol"
COL_ENTRY_DATE  = "Entry_Date"
COL_ENTRY_PRICE = "Entry_Price"
COL_SL_PRICE    = "SL_Price"
COL_SHARES      = "Shares"
COL_STRATEGY    = "Strategy"

MAX_PORTFOLIO_HEAT  = 0.06      # 6% maximum total risk across all open positions
STRATEGY_ID         = 2         # this module only counts Strategy 2 positions


# ─── OPEN POSITIONS ───────────────────────────────────────────────────────────

def load_open_positions(filepath: str = OPEN_POSITIONS_FILE) -> pd.DataFrame:
    """
    Load open positions from CSV.
    Returns empty DataFrame if file does not exist or is empty.
    """
    if not os.path.exists(filepath):
        return pd.DataFrame(columns=[
            COL_SYMBOL, COL_ENTRY_DATE, COL_ENTRY_PRICE, COL_SL_PRICE, COL_SHARES
        ])

    try:
        df = pd.read_csv(filepath)
        required = [COL_SYMBOL, COL_ENTRY_PRICE, COL_SHARES]
        for col in required:
            if col not in df.columns:
                print(f"[WARNING] open_positions.csv missing column: {col}")
                return pd.DataFrame()

        df[COL_ENTRY_PRICE] = pd.to_numeric(df[COL_ENTRY_PRICE], errors="coerce")
        df[COL_SHARES]      = pd.to_numeric(df[COL_SHARES],      errors="coerce")
        df = df.dropna(subset=[COL_ENTRY_PRICE, COL_SHARES])

        # Filter for Strategy 2 positions only.
        # Strategy 1 positions run on a separate capital allocation and must
        # not consume Strategy 2 capital or affect portfolio heat calculations.
        if COL_STRATEGY in df.columns:
            df[COL_STRATEGY] = pd.to_numeric(df[COL_STRATEGY], errors="coerce")
            strategy_2 = df[df[COL_STRATEGY] == STRATEGY_ID].copy()
            excluded   = len(df) - len(strategy_2)
            if excluded > 0:
                print(f"[INFO] Excluded {excluded} Strategy 1 position(s) from capital calculation.")
            return strategy_2
        else:
            # Strategy column missing — warn but do not crash.
            # Treat all positions as Strategy 2 to be safe (conservative).
            print(f"[WARNING] open_positions.csv missing 'Strategy' column.")
            print(f"[WARNING] All positions counted as Strategy 2. Add Strategy column to open_positions.csv.")
            return df

    except Exception as e:
        print(f"[WARNING] Could not load open_positions.csv: {e}")
        return pd.DataFrame()


def compute_deployed_capital(open_positions: pd.DataFrame) -> float:
    """
    Compute total capital currently deployed in open positions.
    Deployed = sum(Entry_Price x Shares) for all open positions.
    """
    if open_positions.empty:
        return 0.0
    deployed = (open_positions[COL_ENTRY_PRICE] * open_positions[COL_SHARES]).sum()
    return float(deployed)


def compute_available_capital(
    total_capital: float,
    open_positions: pd.DataFrame,
) -> float:
    """Available capital = Total Capital - Deployed Capital."""
    deployed = compute_deployed_capital(open_positions)
    return max(0.0, total_capital - deployed)


def compute_portfolio_heat(
    open_positions: pd.DataFrame,
    total_capital: float,
) -> float:
    """
    Compute current portfolio heat as a fraction (0.0 – 1.0).

    Portfolio heat = sum of (stop distance % x position weight) for all open
    Strategy 2 positions. Represents total % of capital at risk if all stops
    are hit simultaneously.

    Formula per position:
        position_heat = (Entry_Price - SL_Price) / Entry_Price * (Entry_Price * Shares / Total_Capital)
                      = (Entry_Price - SL_Price) * Shares / Total_Capital

    Research: Van Tharp (1997) — portfolio heat as the correct measure of
              simultaneous maximum loss across all open positions.
    """
    if open_positions.empty or total_capital <= 0:
        return 0.0

    required = [COL_ENTRY_PRICE, COL_SL_PRICE, COL_SHARES]
    if not all(c in open_positions.columns for c in required):
        return 0.0

    df = open_positions.copy()
    df[COL_SL_PRICE] = pd.to_numeric(df[COL_SL_PRICE], errors="coerce").fillna(0)

    heat = (
        (df[COL_ENTRY_PRICE] - df[COL_SL_PRICE]) * df[COL_SHARES]
    ).sum() / total_capital

    return max(0.0, float(heat))


# ─── POSITION SIZING CORE ─────────────────────────────────────────────────────

def size_position(
    entry_price: float,
    stop_loss: float,
    available_capital: float,
    current_heat_pct: float,    # total risk % across existing open positions
    total_capital: float       = TOTAL_CAPITAL,
    risk_pct: float            = RISK_PER_TRADE,
    max_heat: float            = MAX_PORTFOLIO_HEAT,
    partial_booking_pct: float = PARTIAL_BOOKING_PCT,
) -> dict:
    """
    Compute position size for a single trade.

    Returns dict with sizing details and action note.

    Sizing logic:
    1. Check concurrent position limit — skip if already at max
    2. Compute risk amount = total_capital x risk_pct
    3. Compute raw shares = floor(risk_amount / stop_distance)
    4. Check capital availability — scale down if needed
    5. If final shares = 0 — flag INSUFFICIENT CAPITAL

    Research: Van Tharp (1997) fixed fractional method.
              Scale down rather than skip — partial position better than no position.
    """
    result = {
        "entry_price":          round(entry_price, 2),
        "stop_loss":            round(stop_loss, 2),
        "stop_distance":        None,
        "stop_distance_pct":    None,
        "risk_amount":          None,
        "raw_shares":           None,
        "final_shares":         None,
        "shares_at_target_1":   None,
        "shares_at_target_2":   None,
        "position_value":       None,
        "capital_used_pct":     None,
        "actual_risk_amount":   None,
        "actual_risk_pct":      None,
        "current_heat_pct":     round(current_heat_pct * 100, 2),
        "new_heat_pct":         None,
        "sizing_note":          None,
    }

    # Gate 1: portfolio heat limit
    # Maximum total risk across all open Strategy 2 positions = 6% of capital
    # Research: Van Tharp (1997) — portfolio heat as primary risk control
    #
    # Heat contribution = (stop_distance * shares) / total_capital
    # We estimate shares before sizing to check heat first.
    # Raw shares capped by available capital to get a conservative estimate.
    stop_distance_for_gate = entry_price - stop_loss
    if stop_distance_for_gate > 0:
        raw_for_gate       = math.floor((total_capital * risk_pct) / stop_distance_for_gate)
        capped_for_gate    = min(raw_for_gate, math.floor(available_capital / entry_price))
        estimated_heat_add = (stop_distance_for_gate * capped_for_gate) / total_capital
    else:
        estimated_heat_add = 0.0

    projected_heat = current_heat_pct + estimated_heat_add
    if projected_heat > max_heat:
        result["sizing_note"] = (
            f"MAX HEAT REACHED — current heat {current_heat_pct*100:.2f}% + "
            f"new trade {estimated_heat_add*100:.2f}% = {projected_heat*100:.2f}% "
            f"exceeds {max_heat*100:.0f}% limit"
        )
        return result

    # Gate 2: valid stop loss
    stop_distance = entry_price - stop_loss
    if stop_distance <= 0:
        result["sizing_note"] = "INVALID STOP — stop loss must be below entry price"
        return result

    stop_distance_pct = stop_distance / entry_price * 100
    risk_amount       = total_capital * risk_pct

    # Raw shares: how many shares to risk exactly risk_amount
    # floor — never round up, rounding up increases risk beyond limit
    raw_shares = math.floor(risk_amount / stop_distance)

    result["stop_distance"]     = round(stop_distance, 2)
    result["stop_distance_pct"] = round(stop_distance_pct, 2)
    result["risk_amount"]       = round(risk_amount, 2)
    result["raw_shares"]        = raw_shares

    if raw_shares == 0:
        result["sizing_note"] = "INSUFFICIENT CAPITAL — stop distance too wide for minimum 1 share"
        return result

    # Gate 3: capital availability check
    required_capital = raw_shares * entry_price

    if required_capital <= available_capital:
        final_shares  = raw_shares
        sizing_note   = "FULL"
    else:
        # Scale down to available capital
        final_shares = math.floor(available_capital / entry_price)
        sizing_note  = "SCALED DOWN"

    if final_shares == 0:
        result["sizing_note"] = "INSUFFICIENT CAPITAL — available capital cannot fund even 1 share"
        return result

    # Exit sizing
    shares_at_target_1 = math.floor(final_shares * partial_booking_pct)
    shares_at_target_2 = final_shares - shares_at_target_1

    # Final metrics
    position_value    = final_shares * entry_price
    capital_used_pct  = position_value / total_capital * 100
    actual_risk       = final_shares * stop_distance
    actual_risk_pct   = actual_risk / total_capital * 100

    new_heat = current_heat_pct + (actual_risk / total_capital)

    result.update({
        "final_shares":       final_shares,
        "shares_at_target_1": shares_at_target_1,
        "shares_at_target_2": shares_at_target_2,
        "position_value":     round(position_value, 2),
        "capital_used_pct":   round(capital_used_pct, 2),
        "actual_risk_amount": round(actual_risk, 2),
        "actual_risk_pct":    round(actual_risk_pct, 2),
        "new_heat_pct":       round(new_heat * 100, 2),
        "sizing_note":        sizing_note,
    })

    return result


# ─── BATCH PROCESSING ─────────────────────────────────────────────────────────

def process_signals(
    entry_signals: pd.DataFrame,
    open_positions: pd.DataFrame,
    total_capital: float       = TOTAL_CAPITAL,
    risk_pct: float            = RISK_PER_TRADE,
    max_heat: float            = MAX_PORTFOLIO_HEAT,
    partial_booking_pct: float = PARTIAL_BOOKING_PCT,
    log_dir: str               = ENTRY_LOG_DIR,
) -> pd.DataFrame:
    """
    Apply position sizing to all ENTRY SIGNAL rows from entry_signals_latest.csv.
    Returns DataFrame with sizing columns appended.

    Only counts Strategy 2 positions for capital and heat calculations.
    Strategy 1 positions are excluded — they operate on a separate allocation.
    """
    os.makedirs(log_dir, exist_ok=True)
    calc_date = datetime.date.today().strftime("%Y-%m-%d")

    # Filter to actionable signals only
    signals = entry_signals[
        entry_signals["signal"] == "ENTRY SIGNAL"
    ].copy()

    # open_positions has already been filtered to Strategy 2 only by load_open_positions
    available_capital = compute_available_capital(total_capital, open_positions)
    deployed_capital  = compute_deployed_capital(open_positions)
    current_heat      = compute_portfolio_heat(open_positions, total_capital)
    open_count        = len(open_positions)

    print(f"\n{'=' * 72}")
    print(f"POSITION SIZING MODULE — Strategy 2")
    print(f"Date              : {calc_date}")
    print(f"Total Capital     : INR {total_capital:,.0f}")
    print(f"Deployed Capital  : INR {deployed_capital:,.0f}  ({open_count} Strategy 2 position(s))")
    print(f"Available Capital : INR {available_capital:,.0f}")
    print(f"Portfolio Heat    : {current_heat*100:.2f}% / {max_heat*100:.0f}% limit")
    print(f"Risk Per Trade    : {risk_pct*100:.1f}% = INR {total_capital*risk_pct:,.0f}")
    print(f"{'=' * 72}")

    if signals.empty:
        print(f"\n  No entry signals to size.")
        print(f"{'=' * 72}\n")
        return pd.DataFrame()

    print(f"\n  Entry signals to size: {len(signals)}")
    print(f"{'─' * 72}")

    rows = []

    # Track state across signals in this batch — each accepted signal
    # consumes capital and increases heat before the next is evaluated
    running_heat      = current_heat
    running_capital   = available_capital

    for _, sig in signals.iterrows():
        symbol      = sig["symbol"]
        entry_price = float(sig["entry_price"])
        stop_loss   = float(sig["stop_loss"])
        target_1    = sig.get("target_1")
        target_2    = sig.get("target_2")

        sizing = size_position(
            entry_price         = entry_price,
            stop_loss           = stop_loss,
            available_capital   = running_capital,
            current_heat_pct    = running_heat,
            total_capital       = total_capital,
            risk_pct            = risk_pct,
            max_heat            = max_heat,
            partial_booking_pct = partial_booking_pct,
        )

        # Print result
        note = sizing["sizing_note"]
        if note in ("FULL", "SCALED DOWN"):
            print(
                f"  {symbol:<22}  {note:<14}  "
                f"Shares: {sizing['final_shares']:>4}  "
                f"Value: INR {sizing['position_value']:>9,.0f}  "
                f"Risk: INR {sizing['actual_risk_amount']:>6,.0f} "
                f"({sizing['actual_risk_pct']:.2f}%)  "
                f"Heat after: {sizing['new_heat_pct']:.2f}%  "
                f"T1 sell: {sizing['shares_at_target_1']}  "
                f"T2 sell: {sizing['shares_at_target_2']}"
            )
            # Update running state for next signal evaluation
            running_capital -= sizing["position_value"]
            running_heat     = sizing["new_heat_pct"] / 100.0
        else:
            print(f"  {symbol:<22}  SKIPPED — {note}")

        row = {
            "scan_date":            calc_date,
            "symbol":               symbol,
            "pattern":              sig.get("pattern"),
            "signal_date":          sig.get("signal_date"),
            "entry_price":          entry_price,
            "stop_loss":            stop_loss,
            "target_1":             target_1,
            "target_2":             sig.get("target_2"),
            "t1_source":            sig.get("t1_source"),
            "t2_source":            sig.get("t2_source"),
            "stop_distance":        sizing["stop_distance"],
            "stop_distance_pct":    sizing["stop_distance_pct"],
            "risk_amount":          sizing["risk_amount"],
            "raw_shares":           sizing["raw_shares"],
            "final_shares":         sizing["final_shares"],
            "shares_at_target_1":   sizing["shares_at_target_1"],
            "shares_at_target_2":   sizing["shares_at_target_2"],
            "position_value":       sizing["position_value"],
            "capital_used_pct":     sizing["capital_used_pct"],
            "actual_risk_amount":   sizing["actual_risk_amount"],
            "actual_risk_pct":      sizing["actual_risk_pct"],
            "portfolio_heat_pct":   sizing["current_heat_pct"],
            "new_heat_pct":         sizing["new_heat_pct"],
            "sizing_note":          sizing["sizing_note"],
            "rr_ratio_1":           sig.get("rr_ratio_1"),
            "rr_ratio_2":           sig.get("rr_ratio_2"),
            "market_filter":        sig.get("market_filter"),
            "sr_signal":            sig.get("sr_signal"),
            "zone_center":          sig.get("zone_center"),
        }
        rows.append(row)

    df_out = pd.DataFrame(rows)

    # Print summary and action prompts
    actionable = df_out[df_out["sizing_note"].isin(["FULL", "SCALED DOWN"])]

    print(f"\n{'─' * 72}")
    print(f"  SIZED SIGNALS — ACTION REQUIRED")
    print(f"{'─' * 72}")

    if actionable.empty:
        print(f"  No actionable signals after position sizing.")
    else:
        for _, row in actionable.iterrows():
            print(f"\n  ► {row['symbol']}")
            print(f"    Pattern      : {row['pattern']}")
            print(f"    Entry Price  : INR {row['entry_price']:,.2f}  (buy at market open tomorrow)")
            print(f"    Stop Loss    : INR {row['stop_loss']:,.2f}")
            print(f"    Target 1     : INR {row['target_1']:,.2f}  → sell {row['shares_at_target_1']} shares, move stop to breakeven")
            print(f"    Target 2     : INR {row['target_2']:,.2f}  → sell {row['shares_at_target_2']} shares, trade closed")
            print(f"    Shares       : {row['final_shares']} ({row['sizing_note']})")
            print(f"    Position     : INR {row['position_value']:,.0f}  ({row['capital_used_pct']:.1f}% of capital)")
            print(f"    Max Risk     : INR {row['actual_risk_amount']:,.0f}  ({row['actual_risk_pct']:.2f}% of capital)")
            print(f"    Portfolio Heat: {row['portfolio_heat_pct']:.2f}% → {row['new_heat_pct']:.2f}% after trade")
            print(f"    RR Ratio     : {row['rr_ratio_1']}x (T1)  /  {row['rr_ratio_2']}x (T2)")
            print()
            print(f"    ACTION: Add to open_positions.csv after placing order:")
            print(f"    {row['symbol']},{datetime.date.today()},{row['entry_price']},{row['stop_loss']},{row['final_shares']},2")

    # Save outputs
    dated_path  = os.path.join(log_dir, f"sized_signals_{calc_date.replace('-','')}.csv")
    latest_path = os.path.join(log_dir, SIZED_LATEST_FILE)
    df_out.to_csv(dated_path,  index=False, encoding="utf-8")
    df_out.to_csv(latest_path, index=False, encoding="utf-8")

    print(f"\n{'─' * 72}")
    print(f"  Dated output  : {dated_path}")
    print(f"  Latest output : {latest_path}")
    print(f"{'=' * 72}\n")

    return df_out


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def run(
    symbol: Optional[str]        = None,
    total_capital: float         = TOTAL_CAPITAL,
    risk_pct: float              = RISK_PER_TRADE,
    max_heat: float              = MAX_PORTFOLIO_HEAT,
    partial_booking_pct: float   = PARTIAL_BOOKING_PCT,
    entry_log_dir: str           = ENTRY_LOG_DIR,
    open_positions_file: str     = OPEN_POSITIONS_FILE,
) -> pd.DataFrame:
    """
    Core function — callable from other modules.

    Reads entry_signals_latest.csv, loads open positions (Strategy 2 only),
    computes share quantities, and outputs sized_signals_latest.csv.
    """
    # Load entry signals
    entry_path = os.path.join(entry_log_dir, ENTRY_LATEST_FILE)
    if not os.path.exists(entry_path):
        print(f"[WARNING] Entry signals file not found: {entry_path}")
        print("[WARNING] Run entry_signal.py first.")
        return pd.DataFrame()

    entry_signals = pd.read_csv(entry_path)

    # Filter to specific symbol if requested
    if symbol:
        entry_signals = entry_signals[entry_signals["symbol"] == symbol].copy()
        if entry_signals.empty:
            print(f"[INFO] {symbol} not found in entry signals.")
            return pd.DataFrame()

    # Load open positions — filtered to Strategy 2 only inside this function
    open_positions = load_open_positions(open_positions_file)

    return process_signals(
        entry_signals       = entry_signals,
        open_positions      = open_positions,
        total_capital       = total_capital,
        risk_pct            = risk_pct,
        max_heat            = max_heat,
        partial_booking_pct = partial_booking_pct,
        log_dir             = entry_log_dir,
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Strategy 2 Position Sizing Module\n"
            "Reads entry signals and computes share quantities.\n"
            "Outputs sized_signals_latest.csv with full trade details."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol",              type=str,   default=None)
    parser.add_argument("--total_capital",        type=float, default=TOTAL_CAPITAL)
    parser.add_argument("--risk_pct",             type=float, default=RISK_PER_TRADE)
    parser.add_argument("--max_heat",             type=float, default=MAX_PORTFOLIO_HEAT,
                        help="Max portfolio heat as decimal, e.g. 0.06 = 6%%")
    parser.add_argument("--partial_booking_pct",  type=float, default=PARTIAL_BOOKING_PCT)
    parser.add_argument("--entry_log_dir",        type=str,   default=ENTRY_LOG_DIR)
    parser.add_argument("--open_positions_file",  type=str,   default=OPEN_POSITIONS_FILE)

    args = parser.parse_args()

    run(
        symbol              = args.symbol,
        total_capital       = args.total_capital,
        risk_pct            = args.risk_pct,
        max_heat            = args.max_heat,
        partial_booking_pct = args.partial_booking_pct,
        entry_log_dir       = args.entry_log_dir,
        open_positions_file = args.open_positions_file,
    )


if __name__ == "__main__":
    main()
