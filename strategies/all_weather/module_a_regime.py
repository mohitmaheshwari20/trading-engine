"""
module_a_regime.py — Module A: Market Regime Classifier
All-Weather Quant Strategy — NIFTY 200

Classifies each trading day into one of three market states:

    ON      : Nifty50 > EMA200 AND VIX < 22
              → New entries permitted at 100% position size

    CAUTION : Nifty50 > EMA200 AND VIX 22–25
              → New entries permitted at 50% position size

    OFF     : Nifty50 < EMA200 OR VIX > 25
              → No new entries. Tighten existing Regime 1
                trailing stops to 1.5×ATR.

Logic uses strict OR for OFF — a bear market (price < EMA200)
shuts the system down regardless of VIX level.

Primary consumers:
    - AllWeatherEngine  : calls get_regime(date) on every trading day
    - Module C          : reads regime to gate entries and adjust sizing
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Constants — must match spec exactly
# ─────────────────────────────────────────────────────────────────────────────

REGIME_ON      = 'ON'
REGIME_CAUTION = 'CAUTION'
REGIME_OFF     = 'OFF'

EMA_PERIOD         = 200
VIX_ON_THRESHOLD   = 22    # VIX strictly below this → ON (if price above EMA)
VIX_CAUTION_HIGH   = 25    # VIX above this → OFF regardless of price
SIZE_CAUTION_MULT  = 0.5   # Position size multiplier in CAUTION zone


# ─────────────────────────────────────────────────────────────────────────────
# Nifty 50 loader
# ─────────────────────────────────────────────────────────────────────────────

def load_nifty50(data_dir, filename='NIFTY_NS.csv', verbose=True):
    """
    Load Nifty 50 index data from CSV and compute EMA200.

    Args:
        data_dir : str or Path — directory containing NIFTY_NS.csv
        filename : str — index file name (default: NIFTY_NS.csv)
        verbose  : bool

    Returns:
        pandas DataFrame with columns: Date, Close, EMA200
    """
    filepath = Path(data_dir) / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Nifty 50 file not found: {filepath}")

    df = pd.read_csv(filepath)

    # Normalise column names
    df.columns = df.columns.str.strip()
    if 'Adj_Close' in df.columns:
        df = df.rename(columns={'Adj_Close': 'Adj Close'})

    # Parse dates and sort
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)

    # Validate
    if 'Close' not in df.columns:
        raise ValueError(f"'Close' column not found in {filename}. "
                         f"Columns present: {df.columns.tolist()}")

    missing = df['Close'].isna().sum()
    if missing > 0:
        raise ValueError(f"{missing} missing Close values in {filename}")

    # Compute EMA200 on full history for warmup accuracy
    df['EMA200'] = df['Close'].ewm(span=EMA_PERIOD, adjust=False).mean()

    if verbose:
        valid = df.dropna(subset=['EMA200'])
        print(f"  Nifty 50 loaded  : {len(df)} rows "
              f"({df['Date'].min().date()} to {df['Date'].max().date()})")
        print(f"  EMA200 ready     : from {valid['Date'].min().date()} onwards")
        print(f"  Current Close    : {df['Close'].iloc[-1]:,.2f}")
        print(f"  Current EMA200   : {df['EMA200'].iloc[-1]:,.2f}")
        above_ema = df['Close'].iloc[-1] > df['EMA200'].iloc[-1]
        print(f"  Price vs EMA200  : {'ABOVE ✓' if above_ema else 'BELOW ✗'}")

    return df[['Date', 'Close', 'EMA200']]


# ─────────────────────────────────────────────────────────────────────────────
# Regime classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_regime(nifty_close, ema200, vix):
    """
    Classify a single day's market regime.

    Args:
        nifty_close : float — Nifty 50 closing price
        ema200      : float — EMA200 value for that day
        vix         : float — India VIX closing value for that day

    Returns:
        str — REGIME_ON, REGIME_CAUTION, or REGIME_OFF
    """
    price_above_ema = nifty_close > ema200

    # OFF: price below EMA200 OR VIX above 25 (strict OR logic)
    if not price_above_ema or vix > VIX_CAUTION_HIGH:
        return REGIME_OFF

    # CAUTION: price above EMA200 AND VIX in 22–25 range
    if VIX_ON_THRESHOLD <= vix <= VIX_CAUTION_HIGH:
        return REGIME_CAUTION

    # ON: price above EMA200 AND VIX below 22
    return REGIME_ON


def build_regime_series(nifty_df, vix_series, start_date, end_date, verbose=True):
    """
    Build a daily regime label Series for the full backtest window.

    Aligns Nifty 50 and VIX on a common date index. For dates where
    VIX is missing (e.g. market holiday mismatches), forward-fills
    the last known VIX value to avoid look-ahead bias.

    Args:
        nifty_df   : DataFrame — output of load_nifty50()
        vix_series : pandas Series — output of load_vix()['vix']
        start_date : str — backtest start (e.g. '2017-01-01')
        end_date   : str — backtest end   (e.g. '2025-12-31')
        verbose    : bool

    Returns:
        pandas DataFrame with columns:
            Date, Close, EMA200, VIX, Regime, Size_Multiplier
    """
    start = pd.to_datetime(start_date)
    end   = pd.to_datetime(end_date)

    # Filter Nifty to backtest window
    nifty = nifty_df[
        (nifty_df['Date'] >= start) & (nifty_df['Date'] <= end)
    ].copy().reset_index(drop=True)

    # Align VIX to Nifty dates (forward-fill gaps — no look-ahead bias)
    nifty = nifty.set_index('Date')
    vix_aligned = vix_series.reindex(nifty.index, method='ffill')

    nifty['VIX'] = vix_aligned.values
    nifty = nifty.reset_index()

    # Drop rows where EMA200 or VIX is still NaN (warmup period)
    n_before = len(nifty)
    nifty = nifty.dropna(subset=['EMA200', 'VIX']).reset_index(drop=True)
    n_dropped = n_before - len(nifty)

    # Classify each day
    nifty['Regime'] = nifty.apply(
        lambda row: classify_regime(row['Close'], row['EMA200'], row['VIX']),
        axis=1
    )

    # Size multiplier — consumed by position sizing in Module D
    nifty['Size_Multiplier'] = nifty['Regime'].map({
        REGIME_ON     : 1.0,
        REGIME_CAUTION: SIZE_CAUTION_MULT,
        REGIME_OFF    : 0.0
    })

    if verbose:
        total = len(nifty)
        on_days      = (nifty['Regime'] == REGIME_ON).sum()
        caution_days = (nifty['Regime'] == REGIME_CAUTION).sum()
        off_days     = (nifty['Regime'] == REGIME_OFF).sum()

        print(f"\n  Regime series built : {total} trading days")
        if n_dropped > 0:
            print(f"  Warmup rows dropped : {n_dropped}")
        print(f"  Date range          : {nifty['Date'].min().date()} "
              f"to {nifty['Date'].max().date()}")
        print(f"\n  Regime distribution:")
        print(f"    ON      : {on_days:4d} days ({on_days/total*100:.1f}%)")
        print(f"    CAUTION : {caution_days:4d} days ({caution_days/total*100:.1f}%)")
        print(f"    OFF     : {off_days:4d} days ({off_days/total*100:.1f}%)")

    return nifty


# ─────────────────────────────────────────────────────────────────────────────
# RegimeClassifier — main interface for the engine
# ─────────────────────────────────────────────────────────────────────────────

class RegimeClassifier:
    """
    Module A: Market Regime Classifier.

    Loads all data at initialisation and exposes fast O(1) lookups
    via get_regime(date) and get_size_multiplier(date).

    Usage:
        classifier = RegimeClassifier(data_dir, start_date, end_date)
        regime     = classifier.get_regime('2020-03-23')
        multiplier = classifier.get_size_multiplier('2020-03-23')
    """

    def __init__(self, data_dir, vix_series, start_date, end_date, verbose=True):
        """
        Args:
            data_dir   : str — path to data directory containing NIFTY_NS.csv
            vix_series : pandas Series — from vix_loader.load_vix()['vix']
            start_date : str — backtest start
            end_date   : str — backtest end
            verbose    : bool
        """
        if verbose:
            print("\n" + "=" * 60)
            print("MODULE A — MARKET REGIME CLASSIFIER")
            print("=" * 60)

        nifty_df      = load_nifty50(data_dir, verbose=verbose)
        self._regime_df = build_regime_series(
            nifty_df, vix_series, start_date, end_date, verbose=verbose
        )

        # Build fast date-indexed lookup dict
        self._regime_map = dict(zip(
            self._regime_df['Date'],
            self._regime_df['Regime']
        ))
        self._size_map = dict(zip(
            self._regime_df['Date'],
            self._regime_df['Size_Multiplier']
        ))

        # Sorted dates for forward-fill on non-trading days
        self._dates = sorted(self._regime_map.keys())

        if verbose:
            print("=" * 60 + "\n")

    def get_regime(self, date):
        """
        Get market regime for a given date.

        If date is not a trading day, returns the most recent
        prior trading day's regime (no look-ahead bias).

        Args:
            date : str or datetime

        Returns:
            str — REGIME_ON, REGIME_CAUTION, or REGIME_OFF
            None if date is before the series start
        """
        date = pd.to_datetime(date)

        if date in self._regime_map:
            return self._regime_map[date]

        # Forward-fill: find most recent prior trading day
        prior = [d for d in self._dates if d <= date]
        if not prior:
            return None
        return self._regime_map[prior[-1]]

    def get_size_multiplier(self, date):
        """
        Get position size multiplier for a given date.

        Returns:
            float — 1.0 (ON), 0.5 (CAUTION), 0.0 (OFF)
            None if date is before the series start
        """
        date = pd.to_datetime(date)

        if date in self._size_map:
            return self._size_map[date]

        prior = [d for d in self._dates if d <= date]
        if not prior:
            return None
        return self._size_map[prior[-1]]

    def get_regime_df(self):
        """Return full regime DataFrame for analysis and reporting."""
        return self._regime_df.copy()

    def get_regime_stats(self):
        """Return regime distribution statistics."""
        df    = self._regime_df
        total = len(df)
        return {
            'total_days'   : total,
            'on_days'      : int((df['Regime'] == REGIME_ON).sum()),
            'caution_days' : int((df['Regime'] == REGIME_CAUTION).sum()),
            'off_days'     : int((df['Regime'] == REGIME_OFF).sum()),
            'pct_on'       : round((df['Regime'] == REGIME_ON).sum() / total * 100, 1),
            'pct_caution'  : round((df['Regime'] == REGIME_CAUTION).sum() / total * 100, 1),
            'pct_off'      : round((df['Regime'] == REGIME_OFF).sum() / total * 100, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_regime_classifier(classifier, verbose=True):
    """
    Validate regime labels using data-driven checks — no hardcoded dates.

    All periods are derived from the regime series itself based on
    structural conditions (VIX levels, price vs EMA200), not calendar
    assumptions. This makes the validation portable across any backtest
    window or index.

    Checks:
        1. HIGH VIX PERIODS (VIX > 40)      → must be 100% OFF
        2. LOW VIX + PRICE ABOVE EMA periods → must be 100% ON
        3. PRICE BELOW EMA periods           → must be 100% OFF
                                               regardless of VIX level
        4. VIX 22–25 + PRICE ABOVE EMA      → must be 100% CAUTION
        5. Mutual exclusivity               → no day ON and OFF together
        6. Size multipliers                 → locked to regime labels
        7. OFF coverage                     → at least one sustained OFF
                                               period of 10+ consecutive days
        8. Regime transitions               → system switches between
                                               states (not stuck in one)

    Args:
        classifier : RegimeClassifier instance
        verbose    : bool

    Returns:
        bool — True if all checks pass
    """
    if verbose:
        print("Running Module A validation checks...")

    checks = []
    df = classifier.get_regime_df()

    # ── Check 1: High VIX periods (VIX > 40) must ALL be OFF ────────────────
    # When VIX > 40, the system must always be OFF regardless of price.
    # This is the extreme stress test — no ambiguity at these VIX levels.
    high_vix = df[df['VIX'] > 40]
    if len(high_vix) > 0:
        all_off = (high_vix['Regime'] == REGIME_OFF).all()
        checks.append((
            f'All {len(high_vix)} days with VIX > 40 are OFF',
            all_off,
            f"{(high_vix['Regime'] == REGIME_OFF).sum()}/{len(high_vix)} are OFF"
        ))
    else:
        if verbose:
            print("  — Skipping VIX > 40 check (no such days in window)")

    # ── Check 2: Low VIX + price above EMA must ALL be ON ───────────────────
    # When both ON conditions are clearly met (VIX < 18, price > EMA),
    # every single day must be labelled ON — no exceptions.
    clear_on = df[(df['VIX'] < 18) & (df['Close'] > df['EMA200'])]
    if len(clear_on) > 0:
        all_on = (clear_on['Regime'] == REGIME_ON).all()
        checks.append((
            f'All {len(clear_on)} days with VIX < 18 and price > EMA200 are ON',
            all_on,
            f"{(clear_on['Regime'] == REGIME_ON).sum()}/{len(clear_on)} are ON"
        ))

    # ── Check 3: Price below EMA200 must ALL be OFF ──────────────────────────
    # The OR logic in the spec means price < EMA200 triggers OFF
    # regardless of VIX. This is the bear market shutdown condition.
    below_ema = df[df['Close'] < df['EMA200']]
    if len(below_ema) > 0:
        all_off_ema = (below_ema['Regime'] == REGIME_OFF).all()
        checks.append((
            f'All {len(below_ema)} days with price < EMA200 are OFF',
            all_off_ema,
            f"{(below_ema['Regime'] == REGIME_OFF).sum()}/{len(below_ema)} are OFF"
        ))

    # ── Check 4: VIX 22–25 + price above EMA must ALL be CAUTION ────────────
    # When both CAUTION conditions are met, no day should be ON or OFF.
    caution_zone = df[
        (df['VIX'] >= VIX_ON_THRESHOLD) &
        (df['VIX'] <= VIX_CAUTION_HIGH) &
        (df['Close'] > df['EMA200'])
    ]
    if len(caution_zone) > 0:
        all_caution = (caution_zone['Regime'] == REGIME_CAUTION).all()
        checks.append((
            f'All {len(caution_zone)} days with VIX 22–25 and price > EMA200 are CAUTION',
            all_caution,
            f"{(caution_zone['Regime'] == REGIME_CAUTION).sum()}/{len(caution_zone)} are CAUTION"
        ))

    # ── Check 5: Mutual exclusivity — no day simultaneously ON and OFF ───────
    on_and_off = df[
        (df['Regime'] == REGIME_ON) & (df['Size_Multiplier'] == 0.0)
    ]
    checks.append((
        'No day simultaneously ON and OFF',
        len(on_and_off) == 0,
        f"{len(on_and_off)} conflicting days found"
    ))

    # ── Check 6: Size multipliers locked to regime labels ────────────────────
    on_wrong      = df[(df['Regime'] == REGIME_ON)      & (df['Size_Multiplier'] != 1.0)]
    caution_wrong = df[(df['Regime'] == REGIME_CAUTION) & (df['Size_Multiplier'] != 0.5)]
    off_wrong     = df[(df['Regime'] == REGIME_OFF)     & (df['Size_Multiplier'] != 0.0)]
    total_wrong   = len(on_wrong) + len(caution_wrong) + len(off_wrong)
    checks.append((
        'Size multipliers correct for all regimes',
        total_wrong == 0,
        f"{total_wrong} days with wrong multiplier"
    ))

    # ── Check 7: At least one sustained OFF period of 10+ consecutive days ───
    # The system must have experienced at least one real defensive period.
    # A system that never goes OFF is not functioning correctly.
    regime_list   = df['Regime'].tolist()
    max_consec_off = 0
    current_run    = 0
    for r in regime_list:
        if r == REGIME_OFF:
            current_run    += 1
            max_consec_off  = max(max_consec_off, current_run)
        else:
            current_run = 0
    checks.append((
        'At least one sustained OFF period ≥ 10 consecutive days',
        max_consec_off >= 10,
        f"Longest consecutive OFF run: {max_consec_off} days"
    ))

    # ── Check 8: All three regimes appear in the series ──────────────────────
    # The system must have experienced ON, CAUTION, and OFF at some point.
    # If any regime never appears, the thresholds are likely misconfigured.
    unique_regimes = set(df['Regime'].unique())
    all_present    = {REGIME_ON, REGIME_CAUTION, REGIME_OFF}.issubset(unique_regimes)
    checks.append((
        'All three regimes (ON/CAUTION/OFF) appear in series',
        all_present,
        f"Regimes found: {sorted(unique_regimes)}"
    ))

    # ── Report ────────────────────────────────────────────────────────────────
    all_passed = True
    for name, passed, detail in checks:
        status = '✓' if passed else '✗'
        if verbose:
            print(f"  {status} {name} — {detail}")
        if not passed:
            all_passed = False

    if verbose:
        result = "ALL CHECKS PASSED ✓" if all_passed else "SOME CHECKS FAILED ✗"
        print(f"\n  {result}")

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Spot-check printer — for manual inspection
# ─────────────────────────────────────────────────────────────────────────────

def print_spot_checks(classifier):
    """Print regime labels for key historical dates."""
    spot_dates = [
        ('2020-02-28', 'Pre-COVID peak'),
        ('2020-03-23', 'COVID crash low'),
        ('2020-04-15', 'COVID — still falling'),
        ('2020-06-01', 'Early recovery'),
        ('2021-01-15', 'Post-COVID bull'),
        ('2022-06-17', 'FII selloff'),
        ('2022-10-01', 'Recovery begins'),
        ('2023-12-15', 'Bull run'),
        ('2024-06-04', 'Election result day'),
    ]

    print("\nSpot checks — key historical dates:")
    print(f"  {'Date':<15} {'Event':<30} {'Regime':<10} {'Size Mult'}")
    print("  " + "-" * 65)
    for date, event in spot_dates:
        regime = classifier.get_regime(date)
        mult   = classifier.get_size_multiplier(date)
        if regime:
            print(f"  {date:<15} {event:<30} {regime:<10} {mult}")
        else:
            print(f"  {date:<15} {event:<30} {'N/A':<10} N/A")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — run on local machine to validate
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    from data.vix_loader import load_vix

    DATA_DIR   = r'C:\Projects\Backtesting System\data'
    START_DATE = '2017-01-01'
    END_DATE   = '2025-12-31'

    # Load VIX
    vix_result = load_vix(START_DATE, END_DATE)
    vix_series = vix_result['vix']

    # Build regime classifier
    classifier = RegimeClassifier(DATA_DIR, vix_series, START_DATE, END_DATE)

    # Validate
    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)
    validate_regime_classifier(classifier)

    # Spot checks
    print_spot_checks(classifier)
