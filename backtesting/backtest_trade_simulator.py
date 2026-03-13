"""
backtest_trade_simulator.py
============================
Strategy 2 Backtesting Framework — Component 3: Trade Simulator

Simulates trade outcomes given an entry signal and subsequent OHLC data.
Walks forward day by day from entry date to find the exit condition.

EXIT LOGIC — PASS 1 (T1 only):
    Check order each day:
    1. Low <= SL AND High >= T1 on same day  → AMBIGUOUS (excluded from metrics)
    2. Low <= Stop Loss                       → STOP_LOSS at stop_loss price
    3. High >= Target 1                       → TARGET_1 at target_1 price
    4. End of data                            → END_OF_DATA at last close

EXIT LOGIC — PASS 2 (T1 partial + T2):
    Same as Pass 1 until TARGET_1 hit. Then for remaining 50% of position:
    1. Low <= Entry Price (breakeven)         → BREAKEVEN_STOP at entry price
    2. High >= Target 2                       → TARGET_2 at target_2 price
    3. End of data                            → END_OF_DATA at last close

Research basis:
    Brooks (2011): price action exit management
    Van Tharp (1997): fixed fractional position sizing and exit discipline
"""

import datetime
import pandas as pd
from typing import Optional
from backtest_data_slicer import slice_to_date_range


# ─── CONSTANTS ────────────────────────────────────────────────────────────────

PASS_1 = "pass_1"
PASS_2 = "pass_2"

EXIT_STOP_LOSS      = "STOP_LOSS"
EXIT_TARGET_1       = "TARGET_1"
EXIT_TARGET_2       = "TARGET_2"
EXIT_BREAKEVEN_STOP = "BREAKEVEN_STOP"
EXIT_END_OF_DATA    = "END_OF_DATA"
EXIT_AMBIGUOUS      = "AMBIGUOUS"

TOTAL_CAPITAL       = 100_000.0
RISK_PER_TRADE      = 0.02          # 2% of capital = INR 2,000 risk per trade
PARTIAL_BOOKING_PCT = 0.50          # sell 50% at Target 1 in Pass 2


# ─── PASS 1 SIMULATOR ─────────────────────────────────────────────────────────

def simulate_trade_pass1(
    symbol: str,
    entry_date: datetime.date,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    price_df: pd.DataFrame,
    total_capital: float = TOTAL_CAPITAL,
    risk_pct: float      = RISK_PER_TRADE,
) -> dict:
    """
    Simulate a single trade — Pass 1 (exit 100% at T1 or SL).

    Args:
        symbol:       Stock ticker
        entry_date:   Date signal fired. Entry at NEXT day's open.
        entry_price:  Entry price (next day open)
        stop_loss:    Stop loss price
        target_1:     Target 1 price
        price_df:     Full price DataFrame for the symbol (unsliced)
        total_capital: Total capital for risk calculation
        risk_pct:      Risk % per trade

    Returns:
        Dict with full trade record
    """
    import math

    # Build base result
    result = _base_trade_record(
        symbol, entry_date, entry_price, stop_loss, target_1,
        None, None, None, total_capital, risk_pct
    )

    # Get forward data: from day after entry signal to end of data
    forward = _get_forward_data(price_df, entry_date)

    if forward.empty:
        result.update({
            "exit_date":    entry_date,
            "exit_price":   entry_price,
            "exit_reason":  EXIT_END_OF_DATA,
            "holding_days": 0,
            "return_pct":   0.0,
            "rr_achieved":  0.0,
            "pnl":          0.0,
        })
        return result

    # Walk forward day by day
    for _, row in forward.iterrows():
        trade_date = row["Date"].date() if hasattr(row["Date"], "date") else row["Date"]
        low        = float(row["Low"])
        high       = float(row["High"])
        close      = float(row["Close"] if "Close" in row else row.get("Adj Close", entry_price))

        ambiguous  = (low <= stop_loss) and (high >= target_1)
        hit_stop   = low <= stop_loss
        hit_target = high >= target_1

        if ambiguous:
            return _finalise(result, trade_date, entry_price, EXIT_AMBIGUOUS,
                             entry_date, entry_price, stop_loss)

        if hit_stop:
            return _finalise(result, trade_date, stop_loss, EXIT_STOP_LOSS,
                             entry_date, entry_price, stop_loss)

        if hit_target:
            return _finalise(result, trade_date, target_1, EXIT_TARGET_1,
                             entry_date, entry_price, stop_loss)

    # End of data
    last_row   = forward.iloc[-1]
    last_date  = last_row["Date"].date() if hasattr(last_row["Date"], "date") else last_row["Date"]
    last_close = float(last_row.get("Close", last_row.get("Adj Close", entry_price)))
    return _finalise(result, last_date, last_close, EXIT_END_OF_DATA,
                     entry_date, entry_price, stop_loss)


# ─── PASS 2 SIMULATOR ─────────────────────────────────────────────────────────

def simulate_trade_pass2(
    symbol: str,
    entry_date: datetime.date,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    price_df: pd.DataFrame,
    total_capital: float       = TOTAL_CAPITAL,
    risk_pct: float            = RISK_PER_TRADE,
    partial_booking_pct: float = PARTIAL_BOOKING_PCT,
) -> dict:
    """
    Simulate a single trade — Pass 2 (50% exit at T1, remaining to T2 or breakeven).

    Two-leg exit:
    - Leg 1: 50% position exits at T1 or SL (same as Pass 1)
    - Leg 2: remaining 50% exits at T2 or breakeven stop (after T1 hit)

    Returns dict with blended trade record including both legs.
    """
    result = _base_trade_record(
        symbol, entry_date, entry_price, stop_loss, target_1,
        target_2, partial_booking_pct, None, total_capital, risk_pct
    )

    forward = _get_forward_data(price_df, entry_date)

    if forward.empty:
        result.update({
            "exit_date":          entry_date,
            "exit_price":         entry_price,
            "exit_reason":        EXIT_END_OF_DATA,
            "leg2_exit_date":     None,
            "leg2_exit_price":    None,
            "leg2_exit_reason":   None,
            "holding_days":       0,
            "return_pct":         0.0,
            "rr_achieved":        0.0,
            "pnl":                0.0,
            "blended_return_pct": 0.0,
        })
        return result

    t1_hit      = False
    t1_date     = None
    t1_price    = None
    breakeven   = entry_price   # stop moves to entry after T1

    for _, row in forward.iterrows():
        trade_date = row["Date"].date() if hasattr(row["Date"], "date") else row["Date"]
        low        = float(row["Low"])
        high       = float(row["High"])
        close      = float(row.get("Close", row.get("Adj Close", entry_price)))

        if not t1_hit:
            # --- Leg 1: looking for T1 or SL ---
            ambiguous  = (low <= stop_loss) and (high >= target_1)
            hit_stop   = low <= stop_loss
            hit_t1     = high >= target_1

            if ambiguous:
                result.update({
                    "exit_date":          trade_date,
                    "exit_price":         entry_price,
                    "exit_reason":        EXIT_AMBIGUOUS,
                    "leg2_exit_date":     None,
                    "leg2_exit_price":    None,
                    "leg2_exit_reason":   None,
                })
                return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                                       partial_booking_pct, total_capital, risk_pct)

            if hit_stop:
                result.update({
                    "exit_date":          trade_date,
                    "exit_price":         stop_loss,
                    "exit_reason":        EXIT_STOP_LOSS,
                    "leg2_exit_date":     None,
                    "leg2_exit_price":    None,
                    "leg2_exit_reason":   None,
                })
                return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                                       partial_booking_pct, total_capital, risk_pct)

            if hit_t1:
                t1_hit   = True
                t1_date  = trade_date
                t1_price = target_1
                # Do NOT return yet — continue walking for Leg 2

        else:
            # --- Leg 2: looking for T2 or breakeven stop ---
            hit_be  = low <= breakeven
            hit_t2  = high >= target_2

            ambiguous_2 = hit_be and hit_t2

            if ambiguous_2:
                # Conservative for leg 2 ambiguity: assume breakeven stop hit
                result.update({
                    "exit_date":        t1_date,
                    "exit_price":       t1_price,
                    "exit_reason":      EXIT_TARGET_1,
                    "leg2_exit_date":   trade_date,
                    "leg2_exit_price":  breakeven,
                    "leg2_exit_reason": EXIT_BREAKEVEN_STOP,
                })
                return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                                       partial_booking_pct, total_capital, risk_pct)

            if hit_be:
                result.update({
                    "exit_date":        t1_date,
                    "exit_price":       t1_price,
                    "exit_reason":      EXIT_TARGET_1,
                    "leg2_exit_date":   trade_date,
                    "leg2_exit_price":  breakeven,
                    "leg2_exit_reason": EXIT_BREAKEVEN_STOP,
                })
                return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                                       partial_booking_pct, total_capital, risk_pct)

            if hit_t2:
                result.update({
                    "exit_date":        t1_date,
                    "exit_price":       t1_price,
                    "exit_reason":      EXIT_TARGET_1,
                    "leg2_exit_date":   trade_date,
                    "leg2_exit_price":  target_2,
                    "leg2_exit_reason": EXIT_TARGET_2,
                })
                return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                                       partial_booking_pct, total_capital, risk_pct)

    # End of data
    last_row   = forward.iloc[-1]
    last_date  = last_row["Date"].date() if hasattr(last_row["Date"], "date") else last_row["Date"]
    last_close = float(last_row.get("Close", last_row.get("Adj Close", entry_price)))

    if t1_hit:
        result.update({
            "exit_date":        t1_date,
            "exit_price":       t1_price,
            "exit_reason":      EXIT_TARGET_1,
            "leg2_exit_date":   last_date,
            "leg2_exit_price":  last_close,
            "leg2_exit_reason": EXIT_END_OF_DATA,
        })
    else:
        result.update({
            "exit_date":          last_date,
            "exit_price":         last_close,
            "exit_reason":        EXIT_END_OF_DATA,
            "leg2_exit_date":     None,
            "leg2_exit_price":    None,
            "leg2_exit_reason":   None,
        })

    return _finalise_pass2(result, entry_date, entry_price, stop_loss,
                           partial_booking_pct, total_capital, risk_pct)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _get_forward_data(price_df: pd.DataFrame, entry_date: datetime.date) -> pd.DataFrame:
    """Return price rows strictly AFTER entry_date (entry is next day open)."""
    if price_df.empty:
        return pd.DataFrame()

    df = price_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    entry_ts = pd.Timestamp(entry_date)
    forward  = df[df["Date"] > entry_ts].copy().sort_values("Date").reset_index(drop=True)
    return forward


def _base_trade_record(
    symbol, entry_date, entry_price, stop_loss, target_1,
    target_2, partial_booking_pct, pattern, total_capital, risk_pct
) -> dict:
    """Build the base trade record dict with entry fields populated."""
    import math
    stop_distance = entry_price - stop_loss
    risk_amount   = total_capital * risk_pct
    shares        = math.floor(risk_amount / stop_distance) if stop_distance > 0 else 0

    return {
        "symbol":               symbol,
        "entry_date":           entry_date,
        "entry_price":          round(entry_price, 2),
        "stop_loss":            round(stop_loss, 2),
        "target_1":             round(target_1, 2) if target_1 else None,
        "target_2":             round(target_2, 2) if target_2 else None,
        "stop_distance":        round(stop_distance, 2),
        "stop_distance_pct":    round(stop_distance / entry_price * 100, 2),
        "shares":               shares,
        "risk_amount":          round(risk_amount, 2),
        "partial_booking_pct":  partial_booking_pct,
        # To be filled by simulator
        "exit_date":            None,
        "exit_price":           None,
        "exit_reason":          None,
        "holding_days":         None,
        "return_pct":           None,
        "rr_achieved":          None,
        "pnl":                  None,
    }


def _finalise(
    result: dict,
    exit_date: datetime.date,
    exit_price: float,
    exit_reason: str,
    entry_date: datetime.date,
    entry_price: float,
    stop_loss: float,
) -> dict:
    """Compute holding days, return %, RR achieved, and PnL for Pass 1."""
    holding_days = (exit_date - entry_date).days if exit_date and entry_date else 0
    return_pct   = (exit_price - entry_price) / entry_price * 100 if entry_price else 0
    stop_dist    = entry_price - stop_loss
    rr_achieved  = (exit_price - entry_price) / stop_dist if stop_dist > 0 else 0
    pnl          = result["shares"] * (exit_price - entry_price) if result["shares"] else 0

    result.update({
        "exit_date":    exit_date,
        "exit_price":   round(exit_price, 2),
        "exit_reason":  exit_reason,
        "holding_days": holding_days,
        "return_pct":   round(return_pct, 2),
        "rr_achieved":  round(rr_achieved, 2),
        "pnl":          round(pnl, 2),
    })
    return result


def _finalise_pass2(
    result: dict,
    entry_date: datetime.date,
    entry_price: float,
    stop_loss: float,
    partial_pct: float,
    total_capital: float,
    risk_pct: float,
) -> dict:
    """Compute blended return for Pass 2 (two-leg exit)."""
    import math

    stop_dist  = entry_price - stop_loss
    risk_amt   = total_capital * risk_pct
    shares     = math.floor(risk_amt / stop_dist) if stop_dist > 0 else 0

    leg1_shares = math.floor(shares * partial_pct)
    leg2_shares = shares - leg1_shares

    leg1_exit   = result.get("exit_price")   or entry_price
    leg1_reason = result.get("exit_reason")  or EXIT_END_OF_DATA
    leg2_exit   = result.get("leg2_exit_price") or entry_price
    leg1_date   = result.get("exit_date")    or entry_date
    leg2_date   = result.get("leg2_exit_date") or leg1_date

    # Leg 1 return
    leg1_ret = (leg1_exit - entry_price) / entry_price * 100 if entry_price else 0

    # Leg 2 return (0 if no leg 2)
    if result.get("leg2_exit_reason") is not None:
        leg2_ret = (leg2_exit - entry_price) / entry_price * 100 if entry_price else 0
    else:
        leg2_ret = leg1_ret  # if no T1 hit, both legs exit together

    # Blended return (weighted by share count)
    blended = (leg1_shares * leg1_ret + leg2_shares * leg2_ret) / shares if shares else 0

    # Final holding days = last exit date
    final_exit_date = leg2_date if leg2_date else leg1_date
    holding_days    = (final_exit_date - entry_date).days if final_exit_date and entry_date else 0

    # Overall PnL
    leg1_pnl = leg1_shares * (leg1_exit - entry_price)
    leg2_pnl = leg2_shares * (leg2_exit - entry_price)
    total_pnl = leg1_pnl + leg2_pnl

    stop_dist_val = entry_price - stop_loss
    rr_achieved = (blended / 100) * entry_price / stop_dist_val if stop_dist_val > 0 else 0

    result.update({
        "shares":             shares,
        "leg1_shares":        leg1_shares,
        "leg2_shares":        leg2_shares,
        "leg1_return_pct":    round(leg1_ret, 2),
        "leg2_return_pct":    round(leg2_ret, 2),
        "blended_return_pct": round(blended, 2),
        "return_pct":         round(blended, 2),
        "holding_days":       holding_days,
        "rr_achieved":        round(rr_achieved, 2),
        "pnl":                round(total_pnl, 2),
    })
    return result
