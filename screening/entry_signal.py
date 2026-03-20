"""
entry_signal.py
===============
Strategy 2 — Phase C: Entry Signal Module

Identifies confirmed entry signals on Scenario B candidates where price is
testing or approaching a significant S/R zone identified by sr_detection.py.

LOGIC SUMMARY:
    Step 1 — Market Filter        : Nifty 50 above/below 50-day MA
    Step 2 — Candidate Loading    : Load TESTING/APPROACHING stocks from sr_signals_latest.csv
    Step 3 — Pattern Detection    : Pin Bar, Bullish Engulfing, Inside Bar Breakout
    Step 4 — Stop Loss Placement  : Below candle/zone low + ATR buffer, max 6% hard filter
    Step 5 — Target Calculation   : Target 1 (nearest zone above), Target 2 (next zone above)
    Step 6 — Signal Output        : Entry price, stop, targets, RR ratios

Pattern priority (when multiple patterns fire on same day):
    1. Bullish Engulfing  — strongest, buyers overwhelmed sellers completely
    2. Pin Bar            — strong rejection of lower prices
    3. Inside Bar Breakout — two-step confirmation, slowest to develop

Entry price:
    Pin Bar / Bullish Engulfing : Open of next candle after confirmation candle
    Inside Bar Breakout         : Open of candle after breakout candle (day 3)

Research basis:
    Nison, Japanese Candlestick Charting Techniques (1991) — pattern definitions
    Bulkowski, Encyclopedia of Candlestick Charts (2008) — reversal rates
    Brooks, Trading Price Action (2011) — stop placement, inside bar logic
    Wilder (1978) — ATR
    O'Neil, How to Make Money in Stocks — market direction filter
    Minervini, Trade Like a Stock Market Wizard (2013) — market direction filter
    Connors & Alvarez (2008) — next day open entry

Usage:
    # Run full scan on all TESTING/APPROACHING candidates
    python entry_signal.py

    # Scan a specific symbol
    python entry_signal.py --symbol BSE.NS

    # Disable market filter
    python entry_signal.py --market_filter_enabled False

Output:
    C:/Projects/trading_engine/logs/Entry Logs/entry_signals_YYYYMMDD.csv
    C:/Projects/trading_engine/logs/Entry Logs/entry_signals_latest.csv
"""

import os
import argparse
import datetime
import pandas as pd
import numpy as np
from typing import Optional

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DATA_DIR        = r"C:\Projects\trading_engine\data\Historical Daily Data"
SR_LOG_DIR      = r"C:\Projects\trading_engine\logs\SR Logs"
LOG_DIR         = r"C:\Projects\trading_engine\logs\Entry Logs"
NIFTY_FILE      = "NIFTY_NS.CSV"
SR_LATEST_FILE  = "sr_signals_latest.csv"
LATEST_FILE     = "entry_signals_latest.csv"

# Pattern detection
DEFAULT_SCAN_DAYS           = 3         # how many days back to scan for patterns
DEFAULT_MIN_CANDLE_ATR_MULT = 0.5       # min candle size = ATR(14) x 0.5
DEFAULT_PIN_WICK_RATIO      = 2.0       # lower wick >= 2x body length for pin bar
DEFAULT_PIN_CLOSE_PCT       = 0.30      # close must be in upper 30% of candle range

# Stop loss
DEFAULT_MAX_STOP_PCT        = 0.06      # hard rejection if stop > 6% from entry
DEFAULT_ATR_PERIOD          = 14
DEFAULT_ATR_BUFFER_MULT     = 0.5       # stop buffer = ATR(14) x 0.5

# Target
DEFAULT_PARTIAL_BOOKING_PCT = 0.50      # book 50% at Target 1
DEFAULT_FALLBACK_RR_T1      = 1.5       # fallback RR for Target 1 if no zone above
DEFAULT_FALLBACK_RR_T2      = 2.0       # fallback RR for Target 2 if no second zone

# Market filter
DEFAULT_MARKET_FILTER       = True
DEFAULT_MARKET_MA_PERIOD    = 50        # Nifty 50 above 50-day MA = market uptrend

COL_DATE    = "Date"
COL_OPEN    = "Open"
COL_HIGH    = "High"
COL_LOW     = "Low"
COL_CLOSE   = "Close"
COL_VOLUME  = "Volume"


# ─── DATA LOADING ─────────────────────────────────────────────────────────────

def find_price_csv(symbol: str, data_dir: str) -> Optional[str]:
    """Find price CSV for a symbol. Tries multiple naming conventions."""
    candidates = [
        os.path.join(data_dir, f"{symbol}.csv"),
        os.path.join(data_dir, f"{symbol}.CSV"),
        os.path.join(data_dir, f"{symbol.replace('.NS', '')}.csv"),
        os.path.join(data_dir, f"{symbol.replace('.NS', '')}_NS.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def load_ohlcv(csv_path: str) -> Optional[pd.DataFrame]:
    """
    Load OHLCV data from CSV.
    Returns DataFrame with Date index and OHLCV columns, sorted ascending.
    """
    try:
        df = pd.read_csv(csv_path, parse_dates=[COL_DATE])
        col_map = {c.lower(): c for c in df.columns}

        required = [COL_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]
        for col in required:
            if col.lower() not in col_map:
                return None

        cols = {col.lower(): col_map[col.lower()] for col in required}
        df = df[[cols[c.lower()] for c in required]].copy()
        df.columns = required

        df[COL_DATE] = pd.to_datetime(df[COL_DATE])
        for col in [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna().sort_values(COL_DATE).reset_index(drop=True)
        df = df.set_index(COL_DATE)
        return df

    except Exception:
        return None


# ─── STEP 1: MARKET FILTER ────────────────────────────────────────────────────

def check_market_filter(
    data_dir: str             = DATA_DIR,
    nifty_file: str           = NIFTY_FILE,
    ma_period: int            = DEFAULT_MARKET_MA_PERIOD,
) -> tuple:
    """
    Check if Nifty 50 is above its MA — market uptrend filter.

    Returns (pass: bool, message: str)

    Research: O'Neil CAN SLIM market direction filter, Minervini SEPA (2013).
    No staleness check needed — data download runs before signal scan in daily workflow.
    On a holiday markets are closed so no scan runs.
    """
    nifty_path = os.path.join(data_dir, nifty_file)

    if not os.path.exists(nifty_path):
        return False, f"Nifty file not found: {nifty_path}"

    df = load_ohlcv(nifty_path)
    if df is None or len(df) < ma_period + 1:
        return False, "Insufficient Nifty data for market filter"

    current_close = float(df[COL_CLOSE].iloc[-1])
    ma_value      = float(df[COL_CLOSE].iloc[-ma_period:].mean())
    latest_date   = df.index[-1].date()

    if current_close >= ma_value:
        return True, (
            f"PASS — Nifty 50 at {current_close:.2f} above {ma_period}-day MA "
            f"{ma_value:.2f} as of {latest_date}"
        )
    else:
        return False, (
            f"BLOCKED — Nifty 50 at {current_close:.2f} below {ma_period}-day MA "
            f"{ma_value:.2f} as of {latest_date}. No long entries."
        )


# ─── ATR ──────────────────────────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = DEFAULT_ATR_PERIOD) -> Optional[float]:
    """Compute ATR(period) for the most recent bar. Research: Wilder (1978)."""
    if len(df) < period + 1:
        return None

    highs  = df[COL_HIGH].values
    lows   = df[COL_LOW].values
    closes = df[COL_CLOSE].values

    tr_values = []
    for i in range(1, len(df)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        tr_values.append(tr)

    if len(tr_values) < period:
        return None

    return float(np.mean(tr_values[-period:]))


# ─── STEP 3: PATTERN DETECTION ───────────────────────────────────────────────

def is_pin_bar(
    candle: pd.Series,
    atr: float,
    zone_low: float,
    zone_high: float,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
    wick_ratio: float          = DEFAULT_PIN_WICK_RATIO,
    close_pct: float           = DEFAULT_PIN_CLOSE_PCT,
) -> bool:
    """
    Detect a pin bar (hammer) at support.

    Conditions (all must be met):
    1. Candle range >= min_candle_atr_mult x ATR — meaningful candle size
    2. Candle low touches or enters zone boundary (low <= zone_high)
    3. Lower wick >= wick_ratio x body length — strong rejection
    4. Close is in upper close_pct of candle range — buyers closed strong
    5. Close >= zone_low — candle closes above zone

    Research: Nison (1991), Bulkowski (2008) 60%+ reversal rate at support.
    """
    o = candle[COL_OPEN]
    h = candle[COL_HIGH]
    l = candle[COL_LOW]
    c = candle[COL_CLOSE]

    candle_range = h - l
    if candle_range == 0:
        return False

    # Condition 1: meaningful candle size
    if candle_range < min_candle_atr_mult * atr:
        return False

    # Condition 2: candle tested the zone
    if l > zone_high:
        return False

    # Condition 3: lower wick >= wick_ratio x body
    body       = abs(c - o)
    lower_wick = min(o, c) - l
    if body == 0:
        return False
    if lower_wick < wick_ratio * body:
        return False

    # Condition 4: close in upper close_pct of range
    close_position = (c - l) / candle_range
    if close_position < (1 - close_pct):
        return False

    # Condition 5: close above zone
    if c < zone_low:
        return False

    return True


def is_bullish_engulfing(
    prev_candle: pd.Series,
    curr_candle: pd.Series,
    atr: float,
    zone_low: float,
    zone_high: float,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
) -> bool:
    """
    Detect a bullish engulfing pattern at support.

    Conditions (all must be met):
    1. Current candle range >= min_candle_atr_mult x ATR — meaningful size
    2. Current candle is green (close > open)
    3. Current candle body completely engulfs prior candle body
    4. At least one candle (prev or curr) touches or enters zone boundary
    5. Current candle closes above zone low

    Research: Nison (1991), Bulkowski (2008) 63% reversal rate at support.
    """
    po = prev_candle[COL_OPEN]
    pc = prev_candle[COL_CLOSE]
    co = curr_candle[COL_OPEN]
    cc = curr_candle[COL_CLOSE]
    cl = curr_candle[COL_LOW]
    pl = prev_candle[COL_LOW]

    candle_range = curr_candle[COL_HIGH] - cl
    if candle_range == 0:
        return False

    # Condition 1: meaningful size
    if candle_range < min_candle_atr_mult * atr:
        return False

    # Condition 2: current candle is green
    if cc <= co:
        return False

    # Condition 3: current body engulfs prior body
    prev_body_high = max(po, pc)
    prev_body_low  = min(po, pc)
    curr_body_high = max(co, cc)
    curr_body_low  = min(co, cc)

    if not (curr_body_high > prev_body_high and curr_body_low < prev_body_low):
        return False

    # Condition 4: at least one candle touches the zone
    if pl > zone_high and cl > zone_high:
        return False

    # Condition 5: close above zone low
    if cc < zone_low:
        return False

    return True


def is_inside_bar(
    prev_candle: pd.Series,
    curr_candle: pd.Series,
) -> bool:
    """
    Detect an inside bar at support.

    Conditions:
    1. Current candle high <= prior candle high
    2. Current candle low >= prior candle low
    (Current candle range is completely inside the prior candle range)

    Research: Brooks (2011) — inside bar at S/R = institutional accumulation.
    """
    return (
        curr_candle[COL_HIGH] <= prev_candle[COL_HIGH] and
        curr_candle[COL_LOW]  >= prev_candle[COL_LOW]
    )


def is_inside_bar_breakout(
    inside_bar: pd.Series,
    breakout_candle: pd.Series,
    atr: float,
    zone_low: float,
    zone_high: float,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
) -> bool:
    """
    Detect breakout above inside bar high — confirms inside bar setup.

    Conditions:
    1. Breakout candle closes above inside bar high
    2. Breakout candle range >= min_candle_atr_mult x ATR
    3. Inside bar low is at or near zone boundary

    Entry is on open of the NEXT candle after breakout confirmation.
    Research: Brooks (2011).
    """
    breakout_range = breakout_candle[COL_HIGH] - breakout_candle[COL_LOW]
    if breakout_range == 0:
        return False

    # Condition 1: breakout candle closes above inside bar high
    if breakout_candle[COL_CLOSE] <= inside_bar[COL_HIGH]:
        return False

    # Condition 2: meaningful size
    if breakout_range < min_candle_atr_mult * atr:
        return False

    # Condition 3: inside bar tested the zone
    if inside_bar[COL_LOW] > zone_high:
        return False

    return True


def detect_pattern(
    df: pd.DataFrame,
    zone_low: float,
    zone_high: float,
    atr: float,
    scan_days: int             = DEFAULT_SCAN_DAYS,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
    wick_ratio: float          = DEFAULT_PIN_WICK_RATIO,
    close_pct: float           = DEFAULT_PIN_CLOSE_PCT,
) -> Optional[dict]:
    """
    Scan the last scan_days candles for a qualifying pattern.

    Priority order (professionals use when multiple patterns fire):
        1. Bullish Engulfing — strongest momentum shift signal
        2. Pin Bar           — strong rejection of lower prices
        3. Inside Bar Breakout — two-step confirmation

    Returns dict with pattern name, signal_date, confirmation_date, and
    entry_day_index (index of candle whose OPEN is the entry price).
    Returns None if no pattern found.
    """
    if len(df) < scan_days + 3:
        return None

    # Scan from most recent back scan_days
    # We need at least 2 candles for engulfing/inside bar + 1 for breakout
    last_idx = len(df) - 1

    for offset in range(scan_days):
        i = last_idx - offset  # index of potential confirmation candle

        if i < 2:
            break

        curr = df.iloc[i]
        prev = df.iloc[i - 1]

        # Priority 1: Bullish Engulfing
        if is_bullish_engulfing(
            prev, curr, atr, zone_low, zone_high,
            min_candle_atr_mult=min_candle_atr_mult
        ):
            return {
                "pattern":          "Bullish Engulfing",
                "signal_date":      df.index[i].date(),
                "confirmation_idx": i,
                "entry_idx":        i + 1,   # open of next candle
                "stop_candle_idx":  i,        # stop below current candle low
                "prior_candle_idx": i - 1,
            }

        # Priority 2: Pin Bar
        if is_pin_bar(
            curr, atr, zone_low, zone_high,
            min_candle_atr_mult=min_candle_atr_mult,
            wick_ratio=wick_ratio,
            close_pct=close_pct,
        ):
            return {
                "pattern":          "Pin Bar",
                "signal_date":      df.index[i].date(),
                "confirmation_idx": i,
                "entry_idx":        i + 1,   # open of next candle
                "stop_candle_idx":  i,
                "prior_candle_idx": None,
            }

        # Priority 3: Inside Bar Breakout (requires 3 candles)
        # inside_bar = i-1, breakout_candle = i, entry = open of i+1
        if i >= 2:
            inside_bar_candle = df.iloc[i - 1]
            pre_inside        = df.iloc[i - 2]

            if is_inside_bar(pre_inside, inside_bar_candle):
                if is_inside_bar_breakout(
                    inside_bar_candle, curr, atr, zone_low, zone_high,
                    min_candle_atr_mult=min_candle_atr_mult,
                ):
                    return {
                        "pattern":          "Inside Bar Breakout",
                        "signal_date":      df.index[i].date(),
                        "confirmation_idx": i,
                        "entry_idx":        i + 1,   # open of candle after breakout
                        "stop_candle_idx":  i - 1,   # stop below inside bar's PRIOR candle low
                        "prior_candle_idx": i - 2,
                    }

    return None


# ─── STEP 4: STOP LOSS ────────────────────────────────────────────────────────

def compute_stop_loss(
    pattern_result: dict,
    df: pd.DataFrame,
    zone_low: float,
    atr: float,
    max_stop_pct: float        = DEFAULT_MAX_STOP_PCT,
    atr_buffer_mult: float     = DEFAULT_ATR_BUFFER_MULT,
) -> Optional[float]:
    """
    Compute stop loss price.

    Formula:
        stop = min(confirmation_candle_low, zone_low) - (ATR x atr_buffer_mult)

    Inside Bar Breakout exception (Brooks 2011):
        Stop below prior candle's low (not inside bar itself — its low is too
        high and normal price movement would trigger it).

        stop = prior_candle_low - (ATR x atr_buffer_mult)

    Hard rejection: if stop > max_stop_pct from entry, return None.
    """
    stop_candle_idx  = pattern_result["stop_candle_idx"]
    prior_candle_idx = pattern_result["prior_candle_idx"]
    entry_idx        = pattern_result["entry_idx"]

    if entry_idx >= len(df):
        return None

    entry_price = float(df.iloc[entry_idx][COL_OPEN])
    atr_buffer  = atr * atr_buffer_mult

    if pattern_result["pattern"] == "Inside Bar Breakout" and prior_candle_idx is not None:
        # Stop below the candle prior to the inside bar
        prior_low  = float(df.iloc[prior_candle_idx][COL_LOW])
        stop_price = prior_low - atr_buffer
    else:
        candle_low = float(df.iloc[stop_candle_idx][COL_LOW])
        stop_price = min(candle_low, zone_low) - atr_buffer

    # Hard rejection: stop > max_stop_pct from entry
    stop_distance_pct = (entry_price - stop_price) / entry_price
    if stop_distance_pct > max_stop_pct:
        return None

    return round(stop_price, 2)


# ─── STEP 5: TARGET CALCULATION ──────────────────────────────────────────────

def compute_targets(
    entry_price: float,
    stop_price: float,
    significant_zones_above: list,
    fallback_rr_t1: float = DEFAULT_FALLBACK_RR_T1,
    fallback_rr_t2: float = DEFAULT_FALLBACK_RR_T2,
) -> tuple:
    """
    Compute Target 1 and Target 2.

    Target 1: nearest significant S/R zone above entry price
              Fallback: entry + fallback_rr_t1 x risk if no zone above

    Target 2: next significant S/R zone above Target 1
              Fallback: entry + fallback_rr_t2 x risk if no second zone

    No hard minimum RR enforcement — backtest validates whether actual win
    rate supports the natural targets. Partial booking at Target 1 (default 50%)
    locks in gains while holding remaining position for Target 2.

    Returns (target_1, target_2, t1_source, t2_source)
    """
    risk = entry_price - stop_price

    zones_above = sorted(
        [z for z in significant_zones_above if z > entry_price]
    )

    if zones_above:
        t1       = round(zones_above[0], 2)
        t1_source = "S/R zone"
    else:
        t1        = round(entry_price + fallback_rr_t1 * risk, 2)
        t1_source = f"{fallback_rr_t1}x RR fallback"

    if len(zones_above) >= 2:
        t2        = round(zones_above[1], 2)
        t2_source = "S/R zone"
    else:
        t2        = round(entry_price + fallback_rr_t2 * risk, 2)
        t2_source = f"{fallback_rr_t2}x RR fallback"

    return t1, t2, t1_source, t2_source


# ─── SECONDARY INDICATORS (OPTIONAL) ─────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute RSI(period) for the most recent bar. Research: Wilder (1978)."""
    if len(df) < period + 1:
        return None

    closes = df[COL_CLOSE].values
    deltas = np.diff(closes[-(period + 2):])

    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2)


def compute_macd_confirmed(df: pd.DataFrame) -> bool:
    """
    Check if MACD line has crossed above signal line on the most recent bar.
    Standard MACD (12, 26, 9). Research: Appel (2005).
    """
    if len(df) < 35:
        return False

    closes = df[COL_CLOSE]

    ema12   = closes.ewm(span=12, adjust=False).mean()
    ema26   = closes.ewm(span=26, adjust=False).mean()
    macd    = ema12 - ema26
    signal  = macd.ewm(span=9, adjust=False).mean()

    # Cross above: today MACD > signal AND yesterday MACD <= signal
    if len(macd) < 2:
        return False

    return (
        float(macd.iloc[-1]) > float(signal.iloc[-1]) and
        float(macd.iloc[-2]) <= float(signal.iloc[-2])
    )


# ─── CORE: ANALYSE ONE SYMBOL ────────────────────────────────────────────────

def analyse_symbol(
    symbol: str,
    zone_center: float,
    zone_low: float,
    zone_high: float,
    all_zone_centers: list,
    data_dir: str              = DATA_DIR,
    scan_days: int             = DEFAULT_SCAN_DAYS,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
    wick_ratio: float          = DEFAULT_PIN_WICK_RATIO,
    close_pct: float           = DEFAULT_PIN_CLOSE_PCT,
    max_stop_pct: float        = DEFAULT_MAX_STOP_PCT,
    atr_period: int            = DEFAULT_ATR_PERIOD,
    atr_buffer_mult: float     = DEFAULT_ATR_BUFFER_MULT,
    fallback_rr_t1: float      = DEFAULT_FALLBACK_RR_T1,
    fallback_rr_t2: float      = DEFAULT_FALLBACK_RR_T2,
    partial_booking_pct: float = DEFAULT_PARTIAL_BOOKING_PCT,
    secondary_filters: bool    = False,
) -> dict:
    """
    Run full entry signal pipeline for one symbol.

    Returns result dict with signal details or error message.
    """
    result = {
        "symbol":           symbol,
        "zone_center":      zone_center,
        "pattern":          None,
        "signal_date":      None,
        "entry_price":      None,
        "stop_loss":        None,
        "target_1":         None,
        "target_2":         None,
        "t1_source":        None,
        "t2_source":        None,
        "partial_booking":  partial_booking_pct,
        "risk_pct":         None,
        "rr_ratio_1":       None,
        "rr_ratio_2":       None,
        "rsi_at_signal":    None,
        "macd_confirmed":   None,
        "signal":           "NONE",
        "error":            None,
    }

    csv_path = find_price_csv(symbol, data_dir)
    if csv_path is None:
        result["error"] = "No CSV found"
        return result

    df = load_ohlcv(csv_path)
    if df is None or len(df) < 30:
        result["error"] = "Insufficient OHLCV data"
        return result

    # ATR
    atr = compute_atr(df, period=atr_period)
    if atr is None:
        result["error"] = "ATR computation failed"
        return result

    # Pattern detection — scan last scan_days candles
    # Need extra candle ahead for entry price (open of next candle)
    # Only scan if we have a future candle available for entry price
    # In live trading the "next candle" will be tomorrow's open
    # In the scan we use iloc[-1] as a proxy — entry will be next day's open

    pattern = detect_pattern(
        df, zone_low, zone_high, atr,
        scan_days=scan_days,
        min_candle_atr_mult=min_candle_atr_mult,
        wick_ratio=wick_ratio,
        close_pct=close_pct,
    )

    if pattern is None:
        result["error"] = "No qualifying pattern found in scan window"
        return result

    # Entry price — open of next candle after confirmation
    # For live signals the confirmation candle is the most recent completed candle
    # Entry is tomorrow's open — we use today's close as a proxy for now
    # This will be replaced with actual next-day open when signal fires
    entry_idx = pattern["entry_idx"]
    if entry_idx < len(df):
        entry_price = float(df.iloc[entry_idx][COL_OPEN])
    else:
        # Confirmation was on the last candle — entry is next trading day open
        # Use close of last candle as proxy for next open (conservative estimate)
        entry_price = float(df.iloc[-1][COL_CLOSE])

    # Stop loss
    stop_price = compute_stop_loss(
        pattern, df, zone_low, atr,
        max_stop_pct=max_stop_pct,
        atr_buffer_mult=atr_buffer_mult,
    )

    if stop_price is None:
        result["error"] = (
            f"Stop loss rejected — exceeds {max_stop_pct*100:.0f}% hard limit from entry"
        )
        return result

    # Targets — find significant zones above entry price
    zones_above = [z for z in all_zone_centers if z > entry_price]
    t1, t2, t1_source, t2_source = compute_targets(
        entry_price, stop_price, zones_above,
        fallback_rr_t1=fallback_rr_t1,
        fallback_rr_t2=fallback_rr_t2,
    )

    # Risk and RR ratios
    risk    = entry_price - stop_price
    reward1 = t1 - entry_price
    reward2 = t2 - entry_price

    risk_pct   = round(risk / entry_price * 100, 2)
    rr_ratio_1 = round(reward1 / risk, 2) if risk > 0 else None
    rr_ratio_2 = round(reward2 / risk, 2) if risk > 0 else None

    # Secondary indicators
    rsi_val      = compute_rsi(df) if secondary_filters else None
    macd_confirm = compute_macd_confirmed(df) if secondary_filters else None

    # Populate result
    result.update({
        "pattern":        pattern["pattern"],
        "signal_date":    str(pattern["signal_date"]),
        "entry_price":    round(entry_price, 2),
        "stop_loss":      stop_price,
        "target_1":       t1,
        "target_2":       t2,
        "t1_source":      t1_source,
        "t2_source":      t2_source,
        "risk_pct":       risk_pct,
        "rr_ratio_1":     rr_ratio_1,
        "rr_ratio_2":     rr_ratio_2,
        "rsi_at_signal":  rsi_val,
        "macd_confirmed": macd_confirm,
        "signal":         "ENTRY SIGNAL",
    })

    return result


# ─── BATCH SCAN ───────────────────────────────────────────────────────────────

def scan_candidates(
    sr_signals: pd.DataFrame,
    data_dir: str              = DATA_DIR,
    log_dir: str               = LOG_DIR,
    market_filter_pass: bool   = True,
    market_filter_msg: str     = "",
    secondary_filters: bool    = False,
    **kwargs,
) -> pd.DataFrame:
    """
    Run entry signal detection on all TESTING/APPROACHING candidates
    from sr_signals_latest.csv.
    """
    os.makedirs(log_dir, exist_ok=True)
    calc_date = datetime.date.today().strftime("%Y-%m-%d")

    print(f"\n{'=' * 72}")
    print(f"ENTRY SIGNAL MODULE — Strategy 2")
    print(f"Scan date      : {calc_date}")
    print(f"Market filter  : {market_filter_msg}")
    print(f"{'=' * 72}")

    if not market_filter_pass:
        print(f"\n  No signals generated — market filter active.")
        print(f"  {market_filter_msg}")
        print(f"{'=' * 72}\n")
        return pd.DataFrame()

    # Filter for actionable candidates only
    actionable = sr_signals[
        sr_signals["top_signal"].str.contains("BUY|ALERT|MONITOR", na=False)
    ].copy()

    if actionable.empty:
        print(f"  No TESTING/APPROACHING candidates from S/R detection.")
        print(f"{'=' * 72}\n")
        return pd.DataFrame()

    print(f"Candidates     : {len(actionable)}")
    print(f"{'─' * 72}")

    rows = []

    for _, sr_row in actionable.iterrows():
        symbol      = sr_row["symbol"]
        zone_center = sr_row.get("primary_zone_center", None)
        zone_low    = sr_row.get("primary_zone_low", None)
        zone_high   = sr_row.get("primary_zone_high", None)

        if pd.isna(zone_center) or pd.isna(zone_low) or pd.isna(zone_high):
            print(f"  {symbol:<22}  --  No primary zone data in SR signals")
            continue

        # Collect all zone centers for target calculation
        # Includes primary and secondary zones from sr_detection output
        all_zone_centers = []
        for col in ["primary_zone_center", "secondary_zone_center"]:
            val = sr_row.get(col)
            if val is not None and not pd.isna(val):
                all_zone_centers.append(float(val))

        res = analyse_symbol(
            symbol,
            zone_center   = float(zone_center),
            zone_low      = float(zone_low),
            zone_high     = float(zone_high),
            all_zone_centers = all_zone_centers,
            data_dir      = data_dir,
            secondary_filters = secondary_filters,
            **kwargs,
        )

        if res["signal"] == "ENTRY SIGNAL":
            print(
                f"  {symbol:<22}  ENTRY SIGNAL  "
                f"Pattern: {res['pattern']:<22}  "
                f"Entry: {res['entry_price']:>9.2f}  "
                f"Stop: {res['stop_loss']:>9.2f}  "
                f"T1: {res['target_1']:>9.2f}  "
                f"RR1: {res['rr_ratio_1']}"
            )
        else:
            print(f"  {symbol:<22}  --  {res['error']}")

        row = {
            "scan_date":        calc_date,
            "symbol":           symbol,
            "sr_signal":        sr_row.get("top_signal"),
            "zone_center":      zone_center,
            "pattern":          res["pattern"],
            "signal_date":      res["signal_date"],
            "entry_price":      res["entry_price"],
            "stop_loss":        res["stop_loss"],
            "target_1":         res["target_1"],
            "target_2":         res["target_2"],
            "t1_source":        res["t1_source"],
            "t2_source":        res["t2_source"],
            "partial_booking":  res["partial_booking"],
            "risk_pct":         res["risk_pct"],
            "rr_ratio_1":       res["rr_ratio_1"],
            "rr_ratio_2":       res["rr_ratio_2"],
            "rsi_at_signal":    res["rsi_at_signal"],
            "macd_confirmed":   res["macd_confirmed"],
            "market_filter":    "PASS" if market_filter_pass else "BLOCKED",
            "signal":           res["signal"],
            "error":            res["error"],
        }
        rows.append(row)

    df_out = pd.DataFrame(rows)

    if not df_out.empty:
        signals = df_out[df_out["signal"] == "ENTRY SIGNAL"]
        print(f"\n{'─' * 72}")
        print(f"  ENTRY SIGNALS SUMMARY")
        print(f"{'─' * 72}")
        if not signals.empty:
            for _, row in signals.iterrows():
                print(
                    f"  {row['symbol']:<22}  "
                    f"{row['pattern']:<22}  "
                    f"Entry: {row['entry_price']:>9.2f}  "
                    f"Stop: {row['stop_loss']:>9.2f}  "
                    f"T1: {row['target_1']:>9.2f}  "
                    f"T2: {row['target_2']:>9.2f}  "
                    f"RR1: {row['rr_ratio_1']}  RR2: {row['rr_ratio_2']}"
                )
        else:
            print("  No entry signals generated this scan.")

        # Save outputs
        dated_path  = os.path.join(log_dir, f"entry_signals_{calc_date.replace('-','')}.csv")
        latest_path = os.path.join(log_dir, LATEST_FILE)
        df_out.to_csv(dated_path,  index=False, encoding="utf-8")
        df_out.to_csv(latest_path, index=False, encoding="utf-8")
        print(f"\n  Dated output  : {dated_path}")
        print(f"  Latest output : {latest_path}")

    print(f"{'=' * 72}\n")
    return df_out


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def run(
    symbol: Optional[str]      = None,
    data_dir: str              = DATA_DIR,
    sr_log_dir: str            = SR_LOG_DIR,
    log_dir: str               = LOG_DIR,
    market_filter_enabled: bool = DEFAULT_MARKET_FILTER,
    market_ma_period: int      = DEFAULT_MARKET_MA_PERIOD,
    scan_days: int             = DEFAULT_SCAN_DAYS,
    min_candle_atr_mult: float = DEFAULT_MIN_CANDLE_ATR_MULT,
    wick_ratio: float          = DEFAULT_PIN_WICK_RATIO,
    close_pct: float           = DEFAULT_PIN_CLOSE_PCT,
    max_stop_pct: float        = DEFAULT_MAX_STOP_PCT,
    atr_period: int            = DEFAULT_ATR_PERIOD,
    atr_buffer_mult: float     = DEFAULT_ATR_BUFFER_MULT,
    fallback_rr_t1: float      = DEFAULT_FALLBACK_RR_T1,
    fallback_rr_t2: float      = DEFAULT_FALLBACK_RR_T2,
    partial_booking_pct: float = DEFAULT_PARTIAL_BOOKING_PCT,
    secondary_filters: bool    = False,
) -> pd.DataFrame:
    """
    Core function — callable from other modules.

    Loads S/R signals from sr_signals_latest.csv, applies market filter,
    scans for entry patterns, and outputs actionable signals.

    Returns DataFrame of results.
    """
    # Market filter
    if market_filter_enabled:
        market_pass, market_msg = check_market_filter(
            data_dir=data_dir,
            ma_period=market_ma_period,
        )
    else:
        market_pass = True
        market_msg  = "DISABLED"

    # Load SR signals
    if symbol:
        # Single symbol mode — load its data from sr_signals_latest
        sr_path = os.path.join(sr_log_dir, SR_LATEST_FILE)
        if os.path.exists(sr_path):
            sr_df = pd.read_csv(sr_path)
            sr_df = sr_df[sr_df["symbol"] == symbol].copy()
            if sr_df.empty:
                # Run SR detection on the symbol on the fly
                print(f"[INFO] {symbol} not in SR signals. Add it via sr_detection.py first.")
                return pd.DataFrame()
        else:
            print(f"[WARNING] SR signals file not found: {sr_path}")
            print("[WARNING] Run sr_detection.py first.")
            return pd.DataFrame()
    else:
        sr_path = os.path.join(sr_log_dir, SR_LATEST_FILE)
        if not os.path.exists(sr_path):
            print(f"[WARNING] SR signals file not found: {sr_path}")
            print("[WARNING] Run sr_detection.py first.")
            return pd.DataFrame()
        sr_df = pd.read_csv(sr_path)

    return scan_candidates(
        sr_df,
        data_dir            = data_dir,
        log_dir             = log_dir,
        market_filter_pass  = market_pass,
        market_filter_msg   = market_msg,
        secondary_filters   = secondary_filters,
        scan_days           = scan_days,
        min_candle_atr_mult = min_candle_atr_mult,
        wick_ratio          = wick_ratio,
        close_pct           = close_pct,
        max_stop_pct        = max_stop_pct,
        atr_period          = atr_period,
        atr_buffer_mult     = atr_buffer_mult,
        fallback_rr_t1      = fallback_rr_t1,
        fallback_rr_t2      = fallback_rr_t2,
        partial_booking_pct = partial_booking_pct,
    )


# ─── CLI ENTRY POINT ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Strategy 2 Entry Signal Module\n"
            "Scans S/R candidates for confirmed entry patterns.\n"
            "Outputs entry price, stop loss, and targets."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol",               type=str,   default=None)
    parser.add_argument("--market_filter_enabled",type=str,   default="True")
    parser.add_argument("--market_ma_period",     type=int,   default=DEFAULT_MARKET_MA_PERIOD)
    parser.add_argument("--scan_days",            type=int,   default=DEFAULT_SCAN_DAYS)
    parser.add_argument("--min_candle_atr_mult",  type=float, default=DEFAULT_MIN_CANDLE_ATR_MULT)
    parser.add_argument("--wick_ratio",           type=float, default=DEFAULT_PIN_WICK_RATIO)
    parser.add_argument("--close_pct",            type=float, default=DEFAULT_PIN_CLOSE_PCT)
    parser.add_argument("--max_stop_pct",         type=float, default=DEFAULT_MAX_STOP_PCT)
    parser.add_argument("--atr_period",           type=int,   default=DEFAULT_ATR_PERIOD)
    parser.add_argument("--atr_buffer_mult",      type=float, default=DEFAULT_ATR_BUFFER_MULT)
    parser.add_argument("--fallback_rr_t1",       type=float, default=DEFAULT_FALLBACK_RR_T1)
    parser.add_argument("--fallback_rr_t2",       type=float, default=DEFAULT_FALLBACK_RR_T2)
    parser.add_argument("--partial_booking_pct",  type=float, default=DEFAULT_PARTIAL_BOOKING_PCT)
    parser.add_argument("--secondary_filters",    type=str,   default="False")
    parser.add_argument("--data_dir",             type=str,   default=DATA_DIR)
    parser.add_argument("--sr_log_dir",           type=str,   default=SR_LOG_DIR)
    parser.add_argument("--log_dir",              type=str,   default=LOG_DIR)

    args = parser.parse_args()

    run(
        symbol                = args.symbol,
        data_dir              = args.data_dir,
        sr_log_dir            = args.sr_log_dir,
        log_dir               = args.log_dir,
        market_filter_enabled = args.market_filter_enabled.lower() == "true",
        market_ma_period      = args.market_ma_period,
        scan_days             = args.scan_days,
        min_candle_atr_mult   = args.min_candle_atr_mult,
        wick_ratio            = args.wick_ratio,
        close_pct             = args.close_pct,
        max_stop_pct          = args.max_stop_pct,
        atr_period            = args.atr_period,
        atr_buffer_mult       = args.atr_buffer_mult,
        fallback_rr_t1        = args.fallback_rr_t1,
        fallback_rr_t2        = args.fallback_rr_t2,
        partial_booking_pct   = args.partial_booking_pct,
        secondary_filters     = args.secondary_filters.lower() == "true",
    )


if __name__ == "__main__":
    main()
