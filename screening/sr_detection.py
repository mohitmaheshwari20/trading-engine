"""
sr_detection.py
===============
Strategy 2 — Phase B: Support/Resistance Detection Module

Identifies significant S/R zones for Scenario B candidates using daily OHLCV data.
Operates on stocks that were recently in the top 10% momentum universe but have
since dropped out — stocks in early-to-mid consolidation after a momentum move.

LOGIC SUMMARY:
    Step 1 — Fractal Detection       : Williams fractal swing highs/lows (N=2)
    Step 2 — Zone Clustering         : Group nearby swings within 1% tolerance
    Step 3 — Significance Filter     : Binary gates — touch count, age, volume
    Step 4 — Trend Direction         : 20-day price change vs 2% threshold
    Step 5 — Proximity Classification: ATR(14) x 0.5 dynamic thresholds
    Step 6 — Signal Priority         : BUY / ALERT / MONITOR / WATCH

Research basis:
    Williams (1995) — fractal definition
    Murphy, Technical Analysis of Financial Markets (1999) — S/R zones
    Bulkowski, Encyclopedia of Chart Patterns (2005) — significance criteria
    Carter, Mastering the Trade (2005) — swing trading thresholds
    Brooks, Trading Price Action (2011) — proximity classification
    Wilder (1978), Connors & Alvarez (2008) — ATR-based proximity
    O'Neil, How to Make Money in Stocks — volume threshold

Usage:
    # Scan all Scenario B candidates
    python sr_detection.py

    # Scan a specific symbol
    python sr_detection.py --symbol BHARATFORG.NS

    # Custom parameters
    python sr_detection.py --lookback_days 90 --min_touches 2 --vol_multiplier 1.4

Output:
    C:/Projects/trading_engine/logs/SR Logs/sr_signals_YYYYMMDD.csv
    C:/Projects/trading_engine/logs/SR Logs/sr_signals_latest.csv
"""

import os
import argparse
import datetime
import pandas as pd
import numpy as np
from typing import Optional

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DATA_DIR        = r"C:\Projects\Backtesting System\data"
LOG_DIR         = r"C:\Projects\trading_engine\logs\SR Logs"
MOMENTUM_LOG    = r"C:\Projects\trading_engine\logs\Momentum Logs"
SYMBOLS_FILE    = r"C:\Projects\trading_engine\nifty200_symbols.txt"

LATEST_FILE     = "sr_signals_latest.csv"

# Fractal detection
DEFAULT_FRACTAL_N       = 2         # bars each side for swing high/low
DEFAULT_LOOKBACK_DAYS   = 90        # trading days to look back for S/R

# Zone clustering
DEFAULT_ZONE_TOLERANCE  = 0.01      # 1% — cluster swings within this range

# Significance filter (all three must be met — binary gates)
DEFAULT_MIN_TOUCHES     = 2         # minimum touch count
DEFAULT_MIN_AGE_DAYS    = 5         # minimum trading days since first touch
DEFAULT_VOL_MULTIPLIER  = 1.4       # volume threshold: 1.4x = 40% above average
DEFAULT_VOL_PERIOD      = 20        # reference period for average volume

# Trend direction
DEFAULT_TREND_DAYS      = 20        # lookback for trend direction
DEFAULT_TREND_THRESHOLD = 0.02      # 2% threshold for up/down classification

# Proximity classification (ATR-based)
DEFAULT_ATR_PERIOD      = 14        # ATR lookback period
DEFAULT_ATR_MULTIPLIER  = 0.5       # ATR x 0.5 = ~0.8-1.2% for NSE stocks
DEFAULT_TEST_ATR_MULT   = 1.0       # within 1x ATR*0.5 = Testing
DEFAULT_APPROACH_ATR_MULT = 3.0     # within 3x ATR*0.5 = Approaching

# Fixed % fallback (used if ATR cannot be computed)
FALLBACK_TEST_PCT       = 0.01      # 1%
FALLBACK_APPROACH_PCT   = 0.03      # 3%

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
    Returns None on failure.
    """
    try:
        df = pd.read_csv(csv_path, parse_dates=[COL_DATE])
        col_map = {c.lower(): c for c in df.columns}

        required = [COL_DATE, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]
        for col in required:
            if col.lower() not in col_map:
                return None

        cols = {col.lower(): col_map[col.lower()] for col in required}
        df = df[[cols[c.lower()] for c in required]].copy()
        df.columns = required

        df[COL_DATE]   = pd.to_datetime(df[COL_DATE])
        for col in [COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna().sort_values(COL_DATE).reset_index(drop=True)
        df = df.set_index(COL_DATE)
        return df

    except Exception:
        return None


# ─── STEP 1: FRACTAL DETECTION ───────────────────────────────────────────────

def detect_fractals(df: pd.DataFrame, n: int = DEFAULT_FRACTAL_N) -> pd.DataFrame:
    """
    Detect Williams fractal swing highs and lows.

    Swing high at day i: high[i] > high of N bars before AND N bars after
    Swing low  at day i: low[i]  < low  of N bars before AND N bars after

    Returns DataFrame with columns: date, price, type ('high' or 'low')
    Only returns bars where both N preceding and N following bars exist.

    Research: Williams (1995), Carter Mastering the Trade (2005)
    """
    highs = df[COL_HIGH].values
    lows  = df[COL_LOW].values
    dates = df.index
    n_bars = len(df)

    fractals = []

    for i in range(n, n_bars - n):
        # Swing high: high[i] strictly greater than N bars each side
        is_swing_high = all(highs[i] > highs[i - j] for j in range(1, n + 1)) and \
                        all(highs[i] > highs[i + j] for j in range(1, n + 1))

        # Swing low: low[i] strictly less than N bars each side
        is_swing_low  = all(lows[i] < lows[i - j] for j in range(1, n + 1)) and \
                        all(lows[i] < lows[i + j] for j in range(1, n + 1))

        if is_swing_high:
            fractals.append({"date": dates[i], "price": highs[i], "type": "high"})
        if is_swing_low:
            fractals.append({"date": dates[i], "price": lows[i],  "type": "low"})

    return pd.DataFrame(fractals) if fractals else pd.DataFrame(
        columns=["date", "price", "type"]
    )


# ─── STEP 2: ZONE CLUSTERING ─────────────────────────────────────────────────

def cluster_into_zones(
    fractals: pd.DataFrame,
    tolerance: float = DEFAULT_ZONE_TOLERANCE,
) -> list:
    """
    Cluster nearby fractal prices into zones using tolerance as a % of price.

    Two fractal points are merged into the same zone if their prices are within
    tolerance % of each other. Zone center = mean of all merged prices.

    Returns list of dicts:
        zone_center   : mean price of all fractals in zone
        zone_high     : upper boundary of zone
        zone_low      : lower boundary of zone
        touches       : list of dicts {date, price, type, volume}
        touch_count   : number of fractal touches in zone
        first_touch   : earliest date any fractal hit this zone
        last_touch    : most recent date any fractal hit this zone

    Research: Murphy (1999), Bulkowski (2005) — S/R as zones, not precise levels
    """
    if fractals.empty:
        return []

    # Sort by price for greedy clustering
    sorted_fractals = fractals.sort_values("price").to_dict("records")
    zones = []

    for fractal in sorted_fractals:
        price = fractal["price"]
        merged = False

        for zone in zones:
            # Check if this fractal is within tolerance % of the zone center
            if abs(price - zone["zone_center"]) / zone["zone_center"] <= tolerance:
                zone["touches"].append(fractal)
                # Recompute zone center as mean of all touch prices
                all_prices = [t["price"] for t in zone["touches"]]
                zone["zone_center"] = float(np.mean(all_prices))
                zone["zone_high"]   = zone["zone_center"] * (1 + tolerance)
                zone["zone_low"]    = zone["zone_center"] * (1 - tolerance)
                zone["touch_count"] = len(zone["touches"])
                merged = True
                break

        if not merged:
            zones.append({
                "zone_center": price,
                "zone_high":   price * (1 + tolerance),
                "zone_low":    price * (1 - tolerance),
                "touches":     [fractal],
                "touch_count": 1,
            })

    # Add first and last touch dates
    for zone in zones:
        dates = [t["date"] for t in zone["touches"] if "date" in t]
        zone["first_touch"] = min(dates) if dates else None
        zone["last_touch"]  = max(dates) if dates else None

    return zones


# ─── STEP 3: SIGNIFICANCE FILTER ─────────────────────────────────────────────

def apply_significance_filter(
    zones: list,
    df: pd.DataFrame,
    min_touches: int    = DEFAULT_MIN_TOUCHES,
    min_age_days: int   = DEFAULT_MIN_AGE_DAYS,
    vol_multiplier: float = DEFAULT_VOL_MULTIPLIER,
    vol_period: int     = DEFAULT_VOL_PERIOD,
) -> list:
    """
    Apply three binary significance gates. ALL three must be met.

    Gate 1 — Touch count: zone must have >= min_touches fractal touches
    Gate 2 — Age: zone must have >= min_age_days since first touch
    Gate 3 — Volume: at least one touch must occur on volume >= vol_multiplier
             times the vol_period-day average volume

    Returns only zones that pass all three gates.

    Research:
        Bulkowski (2005): 2+ touches on daily chart confirm significance
        Bulkowski (2005), Carter (2005): 5+ trading days minimum consolidation
        O'Neil: 40% above average (1.4x) = institutional participation threshold
    """
    if not zones or df.empty:
        return []

    # Precompute vol_period-day rolling average volume
    vol_avg = df[COL_VOLUME].rolling(vol_period, min_periods=vol_period).mean()

    significant = []

    for zone in zones:
        # Gate 1 — Touch count
        if zone["touch_count"] < min_touches:
            continue

        # Gate 2 — Age: days between first and last touch
        if zone["first_touch"] is None or zone["last_touch"] is None:
            continue
        first = pd.Timestamp(zone["first_touch"])
        last  = pd.Timestamp(zone["last_touch"])
        # Count actual trading days between first and last touch
        if first == last:
            trading_days_span = 0
        else:
            idx_first = df.index.get_indexer([first], method="nearest")[0]
            idx_last  = df.index.get_indexer([last],  method="nearest")[0]
            trading_days_span = abs(idx_last - idx_first)

        if trading_days_span < min_age_days:
            continue

        # Gate 3 — Volume: at least one touch on high volume
        vol_confirmed = False
        for touch in zone["touches"]:
            touch_date = pd.Timestamp(touch["date"])
            if touch_date not in vol_avg.index:
                continue
            avg_vol = vol_avg.loc[touch_date]
            if pd.isna(avg_vol):
                continue
            # Get actual volume on the touch date
            if touch_date not in df.index:
                continue
            actual_vol = df.loc[touch_date, COL_VOLUME]
            if actual_vol >= vol_multiplier * avg_vol:
                vol_confirmed = True
                break

        if not vol_confirmed:
            continue

        # All three gates passed — zone is significant
        zone["age_trading_days"] = trading_days_span
        zone["vol_confirmed"]    = True
        significant.append(zone)

    return significant


# ─── STEP 4: TREND DIRECTION ─────────────────────────────────────────────────

def detect_trend(
    df: pd.DataFrame,
    trend_days: int       = DEFAULT_TREND_DAYS,
    trend_threshold: float = DEFAULT_TREND_THRESHOLD,
) -> str:
    """
    Determine near-term trend direction using price change over trend_days.

    Returns:
        'down'    — price fell > trend_threshold over trend_days
        'up'      — price rose > trend_threshold over trend_days
        'neutral' — price moved within ±trend_threshold

    Research: Carter (2005), Brooks (2011) — 20-day trend for swing trading
    """
    if len(df) < trend_days + 1:
        return "neutral"

    current_price = df[COL_CLOSE].iloc[-1]
    past_price    = df[COL_CLOSE].iloc[-(trend_days + 1)]

    if past_price == 0:
        return "neutral"

    pct_change = (current_price - past_price) / past_price

    if pct_change < -trend_threshold:
        return "down"
    elif pct_change > trend_threshold:
        return "up"
    else:
        return "neutral"


# ─── STEP 5: ATR AND PROXIMITY ────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = DEFAULT_ATR_PERIOD) -> Optional[float]:
    """
    Compute ATR(period) for the most recent bar.

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = rolling mean of True Range over period bars

    Returns ATR value as float, or None if insufficient data.
    Research: Wilder (1978)
    """
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


def classify_proximity(
    current_price: float,
    zone: dict,
    atr: Optional[float],
    atr_multiplier: float   = DEFAULT_ATR_MULTIPLIER,
    test_atr_mult: float    = DEFAULT_TEST_ATR_MULT,
    approach_atr_mult: float = DEFAULT_APPROACH_ATR_MULT,
) -> str:
    """
    Classify price proximity to a zone using ATR-based dynamic thresholds.

    Thresholds:
        Testing    : price within test_atr_mult    × ATR × atr_multiplier of zone boundary
        Approaching: price within approach_atr_mult × ATR × atr_multiplier of zone boundary
        Inactive   : price beyond approach_atr_mult × ATR × atr_multiplier

    Falls back to fixed percentages if ATR is unavailable.

    Returns: 'testing', 'approaching', or 'inactive'

    Research: Wilder (1978), Connors & Alvarez (2008) ATR-based proximity
    """
    zone_high = zone["zone_high"]
    zone_low  = zone["zone_low"]

    # Compute proximity threshold
    if atr is not None and atr > 0:
        base_threshold = atr * atr_multiplier
        test_threshold     = test_atr_mult     * base_threshold
        approach_threshold = approach_atr_mult * base_threshold
    else:
        # Fixed % fallback
        test_threshold     = current_price * FALLBACK_TEST_PCT
        approach_threshold = current_price * FALLBACK_APPROACH_PCT

    # Distance from price to nearest zone boundary
    if current_price > zone_high:
        distance = current_price - zone_high   # price above zone
    elif current_price < zone_low:
        distance = zone_low - current_price    # price below zone
    else:
        distance = 0.0                         # price inside zone

    if distance <= test_threshold:
        return "testing"
    elif distance <= approach_threshold:
        return "approaching"
    else:
        return "inactive"


def check_flip_risk(
    primary_zone: dict,
    all_zones: list,
    current_price: float,
    trend: str,
    atr: Optional[float],
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
) -> bool:
    """
    Flag flip risk: strong opposing zone within 2× ATR×0.5 of primary zone.

    If trend is 'down' and we are watching a support zone, flip risk exists
    if there is a resistance zone very close above — the trade has no room.

    Returns True if flip risk exists.
    """
    if atr is None or atr <= 0:
        flip_threshold = primary_zone["zone_center"] * 0.02
    else:
        flip_threshold = 2 * atr * atr_multiplier

    for zone in all_zones:
        if zone is primary_zone:
            continue

        distance = abs(zone["zone_center"] - primary_zone["zone_center"])
        if distance <= flip_threshold:
            # Check if it is an opposing zone
            if trend == "down" and zone["zone_center"] > primary_zone["zone_center"]:
                return True
            if trend == "up" and zone["zone_center"] < primary_zone["zone_center"]:
                return True

    return False


# ─── STEP 6: SIGNAL PRIORITY ─────────────────────────────────────────────────

def generate_signal(
    proximity: str,
    zone_rank: int,         # 1 = primary, 2 = secondary
    trend: str,
    flip_risk: bool,
) -> str:
    """
    Generate signal label based on proximity, zone rank, trend, and flip risk.

    Signal hierarchy:
        BUY     : Downtrend + Testing Primary Support
        ALERT   : Downtrend + Approaching Primary Support
        MONITOR : Testing Secondary Support
        WATCH   : Approaching Secondary Support
        NONE    : Inactive or no qualifying condition

    Flip risk is appended as a flag: 'BUY [FLIP RISK]'
    """
    signal = "NONE"

    if trend == "down":
        if zone_rank == 1:
            if proximity == "testing":
                signal = "BUY"
            elif proximity == "approaching":
                signal = "ALERT"
        elif zone_rank == 2:
            if proximity == "testing":
                signal = "MONITOR"
            elif proximity == "approaching":
                signal = "WATCH"

    elif trend == "up":
        # Resistance zones in uptrend — informational only for now
        if zone_rank == 1:
            if proximity == "testing":
                signal = "RESISTANCE TEST"
            elif proximity == "approaching":
                signal = "APPROACHING RESISTANCE"

    elif trend == "neutral":
        if proximity == "testing":
            signal = "MONITOR"
        elif proximity == "approaching":
            signal = "WATCH"

    if flip_risk and signal not in ("NONE",):
        signal += " [FLIP RISK]"

    return signal


# ─── CORE: ANALYSE ONE SYMBOL ────────────────────────────────────────────────

def analyse_symbol(
    symbol: str,
    data_dir: str             = DATA_DIR,
    lookback_days: int        = DEFAULT_LOOKBACK_DAYS,
    fractal_n: int            = DEFAULT_FRACTAL_N,
    zone_tolerance: float     = DEFAULT_ZONE_TOLERANCE,
    min_touches: int          = DEFAULT_MIN_TOUCHES,
    min_age_days: int         = DEFAULT_MIN_AGE_DAYS,
    vol_multiplier: float     = DEFAULT_VOL_MULTIPLIER,
    vol_period: int           = DEFAULT_VOL_PERIOD,
    trend_days: int           = DEFAULT_TREND_DAYS,
    trend_threshold: float    = DEFAULT_TREND_THRESHOLD,
    atr_period: int           = DEFAULT_ATR_PERIOD,
    atr_multiplier: float     = DEFAULT_ATR_MULTIPLIER,
) -> dict:
    """
    Run full S/R detection pipeline for one symbol.

    Returns a result dict with:
        symbol        : stock symbol
        current_price : latest closing price
        trend         : 'up', 'down', or 'neutral'
        atr           : ATR(14) value
        zones         : list of significant zone dicts with proximity and signal
        primary_zone  : the primary actionable zone (or None)
        top_signal    : highest priority signal across all zones
        error         : error message if processing failed
    """
    result = {
        "symbol":        symbol,
        "current_price": None,
        "trend":         None,
        "atr":           None,
        "zones":         [],
        "primary_zone":  None,
        "top_signal":    "NONE",
        "error":         None,
    }

    # Load data
    csv_path = find_price_csv(symbol, data_dir)
    if csv_path is None:
        result["error"] = "No CSV found"
        return result

    df_full = load_ohlcv(csv_path)
    if df_full is None or df_full.empty:
        result["error"] = "OHLCV load failed"
        return result

    # Restrict to lookback window for S/R detection
    if len(df_full) < lookback_days:
        df_lookback = df_full.copy()
    else:
        df_lookback = df_full.iloc[-lookback_days:].copy()

    if len(df_lookback) < fractal_n * 2 + 5:
        result["error"] = f"Insufficient data: {len(df_lookback)} days in lookback"
        return result

    current_price = float(df_full[COL_CLOSE].iloc[-1])
    result["current_price"] = round(current_price, 2)

    # Step 1: Fractal detection
    fractals = detect_fractals(df_lookback, n=fractal_n)
    if fractals.empty:
        result["error"] = "No fractals detected in lookback window"
        return result

    # Step 2: Zone clustering
    zones = cluster_into_zones(fractals, tolerance=zone_tolerance)
    if not zones:
        result["error"] = "No zones formed from fractals"
        return result

    # Step 3: Significance filter
    significant_zones = apply_significance_filter(
        zones, df_lookback,
        min_touches=min_touches,
        min_age_days=min_age_days,
        vol_multiplier=vol_multiplier,
        vol_period=vol_period,
    )
    if not significant_zones:
        result["error"] = "No zones passed significance filter"
        return result

    # Step 4: Trend direction
    trend = detect_trend(df_full, trend_days=trend_days, trend_threshold=trend_threshold)
    result["trend"] = trend

    # Step 5: ATR
    atr = compute_atr(df_full, period=atr_period)
    result["atr"] = round(atr, 4) if atr else None

    # Filter zones by trend direction and sort by proximity to current price
    if trend == "down":
        candidate_zones = [z for z in significant_zones if z["zone_center"] < current_price]
        candidate_zones = sorted(candidate_zones, key=lambda z: current_price - z["zone_center"])
    elif trend == "up":
        candidate_zones = [z for z in significant_zones if z["zone_center"] > current_price]
        candidate_zones = sorted(candidate_zones, key=lambda z: z["zone_center"] - current_price)
    else:
        candidate_zones = sorted(significant_zones, key=lambda z: abs(z["zone_center"] - current_price))

    if not candidate_zones:
        result["error"] = f"No significant zones found in trend direction ({trend})"
        return result

    # Classify proximity and generate signals
    signal_priority = {"BUY": 6, "ALERT": 5, "MONITOR": 4, "WATCH": 3,
                       "RESISTANCE TEST": 2, "APPROACHING RESISTANCE": 1, "NONE": 0}

    enriched_zones = []
    top_signal     = "NONE"
    primary_zone   = None

    for rank, zone in enumerate(candidate_zones[:5], 1):  # top 5 zones in direction
        proximity = classify_proximity(
            current_price, zone, atr,
            atr_multiplier=atr_multiplier,
        )
        flip_risk = check_flip_risk(
            zone, significant_zones, current_price, trend, atr,
            atr_multiplier=atr_multiplier,
        )
        signal = generate_signal(proximity, rank, trend, flip_risk)

        zone_out = {
            "rank":             rank,
            "zone_center":      round(zone["zone_center"], 2),
            "zone_high":        round(zone["zone_high"], 2),
            "zone_low":         round(zone["zone_low"], 2),
            "touch_count":      zone["touch_count"],
            "age_trading_days": zone.get("age_trading_days", 0),
            "first_touch":      str(zone["first_touch"])[:10] if zone["first_touch"] else None,
            "last_touch":       str(zone["last_touch"])[:10]  if zone["last_touch"] else None,
            "proximity":        proximity,
            "flip_risk":        flip_risk,
            "signal":           signal,
        }
        enriched_zones.append(zone_out)

        # Track top signal
        base_signal = signal.replace(" [FLIP RISK]", "")
        if signal_priority.get(base_signal, 0) > signal_priority.get(
            top_signal.replace(" [FLIP RISK]", ""), 0
        ):
            top_signal   = signal
            primary_zone = zone_out

    result["zones"]        = enriched_zones
    result["primary_zone"] = primary_zone
    result["top_signal"]   = top_signal

    return result


# ─── BATCH SCAN ───────────────────────────────────────────────────────────────

def scan_candidates(
    symbols: list,
    data_dir: str   = DATA_DIR,
    log_dir: str    = LOG_DIR,
    **kwargs,
) -> pd.DataFrame:
    """
    Run S/R detection for a list of symbols.
    Saves results to sr_signals_YYYYMMDD.csv and sr_signals_latest.csv.
    Returns a DataFrame of results.
    """
    os.makedirs(log_dir, exist_ok=True)
    calc_date = datetime.date.today().strftime("%Y-%m-%d")

    print(f"\n{'=' * 72}")
    print(f"S/R DETECTION — Strategy 2 Signal Scan")
    print(f"Scan date  : {calc_date}")
    print(f"Candidates : {len(symbols)}")
    print(f"{'=' * 72}")

    rows = []

    for i, symbol in enumerate(symbols, 1):
        res = analyse_symbol(symbol, data_dir=data_dir, **kwargs)

        if res["error"]:
            print(f"  [{i:3d}/{len(symbols)}] {symbol:<22}  --  {res['error']}")
        else:
            print(
                f"  [{i:3d}/{len(symbols)}] {symbol:<22}  "
                f"Price: {res['current_price']:>9.2f}  "
                f"Trend: {res['trend']:<8}  "
                f"Signal: {res['top_signal']}"
            )

        row = {
            "scan_date":     calc_date,
            "symbol":        symbol,
            "current_price": res["current_price"],
            "trend":         res["trend"],
            "atr":           res["atr"],
            "top_signal":    res["top_signal"],
            "error":         res["error"],
        }

        # Flatten primary zone fields
        if res["primary_zone"]:
            pz = res["primary_zone"]
            row["primary_zone_center"]  = pz["zone_center"]
            row["primary_zone_high"]    = pz["zone_high"]
            row["primary_zone_low"]     = pz["zone_low"]
            row["primary_touch_count"]  = pz["touch_count"]
            row["primary_age_days"]     = pz["age_trading_days"]
            row["primary_proximity"]    = pz["proximity"]
            row["primary_flip_risk"]    = pz["flip_risk"]
            row["primary_first_touch"]  = pz["first_touch"]
            row["primary_last_touch"]   = pz["last_touch"]
        else:
            for col in ["primary_zone_center", "primary_zone_high", "primary_zone_low",
                        "primary_touch_count", "primary_age_days", "primary_proximity",
                        "primary_flip_risk", "primary_first_touch", "primary_last_touch"]:
                row[col] = None

        # Flatten secondary zone fields (rank 2 — next zone after primary in trend direction)
        secondary_zone = next(
            (z for z in res.get("zones", []) if z["rank"] == 2), None
        )
        if secondary_zone:
            sz = secondary_zone
            row["secondary_zone_center"]  = sz["zone_center"]
            row["secondary_zone_high"]    = sz["zone_high"]
            row["secondary_zone_low"]     = sz["zone_low"]
            row["secondary_touch_count"]  = sz["touch_count"]
            row["secondary_age_days"]     = sz["age_trading_days"]
            row["secondary_proximity"]    = sz["proximity"]
            row["secondary_flip_risk"]    = sz["flip_risk"]
            row["secondary_first_touch"]  = sz["first_touch"]
            row["secondary_last_touch"]   = sz["last_touch"]
        else:
            for col in ["secondary_zone_center", "secondary_zone_high", "secondary_zone_low",
                        "secondary_touch_count", "secondary_age_days", "secondary_proximity",
                        "secondary_flip_risk", "secondary_first_touch", "secondary_last_touch"]:
                row[col] = None

        rows.append(row)

    df_out = pd.DataFrame(rows)

    # Save dated file
    dated_path  = os.path.join(log_dir, f"sr_signals_{calc_date.replace('-', '')}.csv")
    latest_path = os.path.join(log_dir, LATEST_FILE)

    df_out.to_csv(dated_path,  index=False, encoding="utf-8")
    df_out.to_csv(latest_path, index=False, encoding="utf-8")

    # Print signal summary
    print(f"\n{'─' * 72}")
    print(f"  SIGNAL SUMMARY")
    print(f"{'─' * 72}")
    actionable = df_out[df_out["top_signal"].str.contains("BUY|ALERT|MONITOR", na=False)]
    if not actionable.empty:
        for _, row in actionable.iterrows():
            print(f"  {row['symbol']:<22}  {row['top_signal']:<30}  "
                  f"Zone: {row['primary_zone_center']}")
    else:
        print("  No actionable signals this scan.")

    print(f"\n  Dated output : {dated_path}")
    print(f"  Latest output: {latest_path}")
    print(f"{'=' * 72}\n")

    return df_out


# ─── SCENARIO B INTEGRATION ───────────────────────────────────────────────────

def get_scenario_b_symbols(momentum_log: str = MOMENTUM_LOG) -> list:
    """
    Load Scenario B candidates from momentum_history.csv.
    Returns list of symbols or empty list if unavailable.
    """
    history_path = os.path.join(momentum_log, "momentum_history.csv")
    latest_path  = os.path.join(momentum_log, "momentum_ranks_latest.csv")

    if not os.path.exists(history_path):
        print(f"[WARNING] momentum_history.csv not found at {history_path}")
        print("[WARNING] Run momentum_ranker.py first to build history.")
        return []

    if not os.path.exists(latest_path):
        print(f"[WARNING] momentum_ranks_latest.csv not found at {latest_path}")
        return []

    try:
        df_history = pd.read_csv(history_path, parse_dates=["week_date"])
        df_latest  = pd.read_csv(latest_path, comment="#")

        current_universe = set(
            df_latest[df_latest["in_universe"] == True]["symbol"].unique()
        )
        latest_week    = df_history["week_date"].max()
        lookback_cutoff = latest_week - pd.Timedelta(weeks=4)

        recent_history = df_history[
            (df_history["week_date"] > lookback_cutoff) &
            (df_history["week_date"] < latest_week)
        ]
        recent_universe = set(recent_history["symbol"].unique())
        scenario_b      = sorted(recent_universe - current_universe)

        print(f"[INFO] Scenario B candidates from momentum history: {len(scenario_b)}")
        return scenario_b

    except Exception as e:
        print(f"[ERROR] Could not load Scenario B candidates: {e}")
        return []


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def run(
    symbol: Optional[str]   = None,
    data_dir: str           = DATA_DIR,
    log_dir: str            = LOG_DIR,
    momentum_log: str       = MOMENTUM_LOG,
    lookback_days: int      = DEFAULT_LOOKBACK_DAYS,
    fractal_n: int          = DEFAULT_FRACTAL_N,
    zone_tolerance: float   = DEFAULT_ZONE_TOLERANCE,
    min_touches: int        = DEFAULT_MIN_TOUCHES,
    min_age_days: int       = DEFAULT_MIN_AGE_DAYS,
    vol_multiplier: float   = DEFAULT_VOL_MULTIPLIER,
    vol_period: int         = DEFAULT_VOL_PERIOD,
    trend_days: int         = DEFAULT_TREND_DAYS,
    trend_threshold: float  = DEFAULT_TREND_THRESHOLD,
    atr_period: int         = DEFAULT_ATR_PERIOD,
    atr_multiplier: float   = DEFAULT_ATR_MULTIPLIER,
) -> pd.DataFrame:
    """
    Core function — callable from other modules (backtesting, live strategy).

    If symbol is provided, scans only that symbol.
    If symbol is None, scans all Scenario B candidates from momentum history.

    Returns DataFrame of scan results.
    """
    if symbol:
        symbols = [symbol]
    else:
        symbols = get_scenario_b_symbols(momentum_log)
        if not symbols:
            print("[INFO] No Scenario B candidates found. Nothing to scan.")
            return pd.DataFrame()

    return scan_candidates(
        symbols,
        data_dir        = data_dir,
        log_dir         = log_dir,
        lookback_days   = lookback_days,
        fractal_n       = fractal_n,
        zone_tolerance  = zone_tolerance,
        min_touches     = min_touches,
        min_age_days    = min_age_days,
        vol_multiplier  = vol_multiplier,
        vol_period      = vol_period,
        trend_days      = trend_days,
        trend_threshold = trend_threshold,
        atr_period      = atr_period,
        atr_multiplier  = atr_multiplier,
    )


# ─── CLI ENTRY POINT ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Strategy 2 S/R Detection Module\n"
            "Identifies significant support/resistance zones for Scenario B candidates.\n"
            "Scans all Scenario B candidates by default, or a specific symbol."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol",          type=str,   default=None,
                        help="Scan a specific symbol (e.g. BHARATFORG.NS). Default: all Scenario B candidates.")
    parser.add_argument("--lookback_days",   type=int,   default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Trading days to look back for S/R zones (default: {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--fractal_n",       type=int,   default=DEFAULT_FRACTAL_N,
                        help=f"Bars each side for fractal detection (default: {DEFAULT_FRACTAL_N})")
    parser.add_argument("--zone_tolerance",  type=float, default=DEFAULT_ZONE_TOLERANCE,
                        help=f"Zone clustering tolerance as decimal (default: {DEFAULT_ZONE_TOLERANCE} = 1%%)")
    parser.add_argument("--min_touches",     type=int,   default=DEFAULT_MIN_TOUCHES,
                        help=f"Minimum touch count for zone significance (default: {DEFAULT_MIN_TOUCHES})")
    parser.add_argument("--min_age_days",    type=int,   default=DEFAULT_MIN_AGE_DAYS,
                        help=f"Minimum age in trading days (default: {DEFAULT_MIN_AGE_DAYS})")
    parser.add_argument("--vol_multiplier",  type=float, default=DEFAULT_VOL_MULTIPLIER,
                        help=f"Volume threshold multiplier (default: {DEFAULT_VOL_MULTIPLIER} = 40%% above avg)")
    parser.add_argument("--vol_period",      type=int,   default=DEFAULT_VOL_PERIOD,
                        help=f"Volume reference period in days (default: {DEFAULT_VOL_PERIOD})")
    parser.add_argument("--atr_period",      type=int,   default=DEFAULT_ATR_PERIOD,
                        help=f"ATR lookback period (default: {DEFAULT_ATR_PERIOD})")
    parser.add_argument("--atr_multiplier",  type=float, default=DEFAULT_ATR_MULTIPLIER,
                        help=f"ATR multiplier for proximity thresholds (default: {DEFAULT_ATR_MULTIPLIER})")
    parser.add_argument("--data_dir",        type=str,   default=DATA_DIR)
    parser.add_argument("--log_dir",         type=str,   default=LOG_DIR)
    parser.add_argument("--momentum_log",    type=str,   default=MOMENTUM_LOG)

    args = parser.parse_args()

    run(
        symbol          = args.symbol,
        data_dir        = args.data_dir,
        log_dir         = args.log_dir,
        momentum_log    = args.momentum_log,
        lookback_days   = args.lookback_days,
        fractal_n       = args.fractal_n,
        zone_tolerance  = args.zone_tolerance,
        min_touches     = args.min_touches,
        min_age_days    = args.min_age_days,
        vol_multiplier  = args.vol_multiplier,
        vol_period      = args.vol_period,
        atr_period      = args.atr_period,
        atr_multiplier  = args.atr_multiplier,
    )


if __name__ == "__main__":
    main()


# ─── DIAGNOSTIC MODE ─────────────────────────────────────────────────────────

def diagnose_symbol(
    symbol: str,
    data_dir: str           = DATA_DIR,
    lookback_days: int      = DEFAULT_LOOKBACK_DAYS,
    fractal_n: int          = DEFAULT_FRACTAL_N,
    zone_tolerance: float   = DEFAULT_ZONE_TOLERANCE,
    min_touches: int        = DEFAULT_MIN_TOUCHES,
    min_age_days: int       = DEFAULT_MIN_AGE_DAYS,
    vol_multiplier: float   = DEFAULT_VOL_MULTIPLIER,
    vol_period: int         = DEFAULT_VOL_PERIOD,
    trend_days: int         = DEFAULT_TREND_DAYS,
    trend_threshold: float  = DEFAULT_TREND_THRESHOLD,
    atr_period: int         = DEFAULT_ATR_PERIOD,
    atr_multiplier: float   = DEFAULT_ATR_MULTIPLIER,
) -> None:
    """
    Diagnostic mode — prints step-by-step pipeline output for one symbol.
    Use this to understand why signals are or are not firing.
    """
    print(f"\n{'=' * 72}")
    print(f"DIAGNOSTIC — {symbol}")
    print(f"{'=' * 72}")

    # Load data
    csv_path = find_price_csv(symbol, data_dir)
    if csv_path is None:
        print(f"[FAIL] No CSV found for {symbol}")
        return

    df_full = load_ohlcv(csv_path)
    if df_full is None or df_full.empty:
        print(f"[FAIL] OHLCV load failed")
        return

    print(f"[OK] Data loaded: {len(df_full)} trading days total")
    print(f"     Date range: {df_full.index[0].date()} to {df_full.index[-1].date()}")

    df_lookback = df_full.iloc[-lookback_days:].copy() if len(df_full) >= lookback_days else df_full.copy()
    print(f"     Lookback window: {len(df_lookback)} trading days")

    current_price = float(df_full[COL_CLOSE].iloc[-1])
    print(f"     Current price: {current_price:.2f}")

    # Step 1: Fractals
    fractals = detect_fractals(df_lookback, n=fractal_n)
    print(f"\n[STEP 1] Fractal Detection (N={fractal_n})")
    print(f"         Fractals found: {len(fractals)}")
    if not fractals.empty:
        highs = fractals[fractals["type"] == "high"]
        lows  = fractals[fractals["type"] == "low"]
        print(f"         Swing highs: {len(highs)}  |  Swing lows: {len(lows)}")
        print(f"         Price range of fractals: {fractals['price'].min():.2f} — {fractals['price'].max():.2f}")

    if fractals.empty:
        print(f"[STOP] No fractals detected. Lookback too short or price too smooth.")
        return

    # Step 2: Zones
    zones = cluster_into_zones(fractals, tolerance=zone_tolerance)
    print(f"\n[STEP 2] Zone Clustering (tolerance={zone_tolerance*100:.1f}%)")
    print(f"         Zones formed: {len(zones)}")
    for i, z in enumerate(zones, 1):
        print(f"         Zone {i:2d}: center={z['zone_center']:.2f}  "
              f"touches={z['touch_count']}  "
              f"range=[{z['zone_low']:.2f}, {z['zone_high']:.2f}]")

    if not zones:
        print(f"[STOP] No zones formed.")
        return

    # Step 3: Significance filter — show each zone's gate results
    print(f"\n[STEP 3] Significance Filter")
    print(f"         Gates: touches>={min_touches}, age>={min_age_days} days, vol>={vol_multiplier}x {vol_period}d avg")

    vol_avg = df_lookback[COL_VOLUME].rolling(vol_period, min_periods=vol_period).mean()
    passed  = 0

    for i, zone in enumerate(zones, 1):
        # Gate 1
        g1 = zone["touch_count"] >= min_touches

        # Gate 2
        first = pd.Timestamp(zone["first_touch"]) if zone["first_touch"] else None
        last  = pd.Timestamp(zone["last_touch"])  if zone["last_touch"]  else None
        if first and last and first != last:
            idx_first = df_lookback.index.get_indexer([first], method="nearest")[0]
            idx_last  = df_lookback.index.get_indexer([last],  method="nearest")[0]
            age = abs(idx_last - idx_first)
        else:
            age = 0
        g2 = age >= min_age_days

        # Gate 3
        vol_ok = False
        for touch in zone["touches"]:
            td = pd.Timestamp(touch["date"])
            if td in vol_avg.index and td in df_lookback.index:
                avg_v = vol_avg.loc[td]
                act_v = df_lookback.loc[td, COL_VOLUME]
                if not pd.isna(avg_v) and act_v >= vol_multiplier * avg_v:
                    vol_ok = True
                    break
        g3 = vol_ok

        status = "PASS" if (g1 and g2 and g3) else "FAIL"
        if g1 and g2 and g3:
            passed += 1

        print(f"         Zone {i:2d} [{status}]: center={zone['zone_center']:.2f}  "
              f"Gate1(touches {zone['touch_count']}>={min_touches})={'OK' if g1 else 'FAIL'}  "
              f"Gate2(age {age}>={min_age_days})={'OK' if g2 else 'FAIL'}  "
              f"Gate3(vol)={'OK' if g3 else 'FAIL'}")

    print(f"         Zones passing all gates: {passed} of {len(zones)}")

    # Step 4: Trend
    trend = detect_trend(df_full, trend_days=trend_days, trend_threshold=trend_threshold)
    past_price = df_full[COL_CLOSE].iloc[-(trend_days + 1)]
    pct = (current_price - past_price) / past_price * 100
    print(f"\n[STEP 4] Trend Direction")
    print(f"         20-day price change: {pct:+.2f}%  →  Trend: {trend.upper()}")

    # Step 5: ATR
    atr = compute_atr(df_full, period=atr_period)
    print(f"\n[STEP 5] ATR({atr_period})")
    if atr:
        base = atr * atr_multiplier
        print(f"         ATR={atr:.4f}  |  ATR×{atr_multiplier}={base:.4f}  "
              f"|  Testing threshold={base*DEFAULT_TEST_ATR_MULT:.4f}  "
              f"|  Approaching threshold={base*DEFAULT_APPROACH_ATR_MULT:.4f}")
    else:
        print(f"         ATR unavailable — using fixed % fallback")

    # Step 6: Significant zones vs trend direction
    significant_zones = apply_significance_filter(
        zones, df_lookback,
        min_touches=min_touches, min_age_days=min_age_days,
        vol_multiplier=vol_multiplier, vol_period=vol_period,
    )

    if trend == "down":
        candidates = [z for z in significant_zones if z["zone_center"] < current_price]
    elif trend == "up":
        candidates = [z for z in significant_zones if z["zone_center"] > current_price]
    else:
        candidates = significant_zones

    print(f"\n[STEP 6] Candidate Zones in Trend Direction ({trend.upper()})")
    print(f"         Significant zones: {len(significant_zones)}  |  "
          f"In trend direction: {len(candidates)}")

    if candidates:
        for z in candidates:
            prox = classify_proximity(current_price, z, atr, atr_multiplier=atr_multiplier)
            dist = abs(current_price - z["zone_center"])
            print(f"         Zone center={z['zone_center']:.2f}  "
                  f"distance={dist:.2f}  proximity={prox.upper()}")
    else:
        if significant_zones:
            print(f"         Significant zones exist but none in {trend} direction.")
            print(f"         Significant zone centers: "
                  f"{[round(z['zone_center'],2) for z in significant_zones]}")
            print(f"         Current price: {current_price:.2f}")
        else:
            print(f"         No zones passed significance filter.")

    print(f"\n{'=' * 72}\n")
