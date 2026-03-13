"""
backtest_data_slicer.py
=======================
Strategy 2 Backtesting Framework — Component 1: Data Slicer

Single responsibility: cut any price DataFrame to a cutoff date so that
every module call in the backtest only sees data that existed at that
point in time. This is the sole mechanism for preventing lookahead.

CRITICAL RULE:
    Every module call in the backtest MUST receive a sliced DataFrame.
    Passing the full DataFrame is a lookahead violation.

Usage:
    from backtest_data_slicer import slice_to_date, load_and_slice, get_trading_weeks

    # Slice an already-loaded DataFrame
    df_sliced = slice_to_date(df, cutoff_date)

    # Load a price CSV and slice in one call
    df_sliced = load_and_slice(filepath, cutoff_date)

    # Get all weekly cutoff dates between two dates
    weeks = get_trading_weeks(start_date, end_date)
"""

import os
import datetime
import pandas as pd
from typing import Optional


# ─── CONSTANTS ────────────────────────────────────────────────────────────────

DATE_COLUMN = "Date"        # expected date column name in price CSVs


# ─── CORE SLICER ──────────────────────────────────────────────────────────────

def slice_to_date(
    df: pd.DataFrame,
    cutoff_date: datetime.date,
    date_col: str = DATE_COLUMN,
) -> pd.DataFrame:
    """
    Return a copy of df containing only rows on or before cutoff_date.

    The cutoff is inclusive — data from cutoff_date itself is included.
    This matches how the live system works: on any given date, you have
    access to that day's closing data.

    Args:
        df:           Price DataFrame with a date column
        cutoff_date:  Cutoff date — all rows after this date are removed
        date_col:     Name of the date column (default: 'Date')

    Returns:
        Sliced DataFrame. Empty DataFrame if no rows on or before cutoff.

    Raises:
        ValueError: If date_col is not found in df
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if date_col not in df.columns:
        raise ValueError(
            f"Date column '{date_col}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # Ensure date column is datetime type for comparison
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    cutoff_dt = pd.Timestamp(cutoff_date)
    sliced = df[df[date_col] <= cutoff_dt].copy()
    return sliced.reset_index(drop=True)


def slice_to_date_range(
    df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
    date_col: str = DATE_COLUMN,
) -> pd.DataFrame:
    """
    Return rows between start_date and end_date (both inclusive).
    Used by the trade simulator to walk forward through exit data.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' not found in DataFrame.")

    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    start_dt = pd.Timestamp(start_date)
    end_dt   = pd.Timestamp(end_date)
    mask     = (df[date_col] >= start_dt) & (df[date_col] <= end_dt)
    return df[mask].copy().reset_index(drop=True)


# ─── FILE LOADER ──────────────────────────────────────────────────────────────

def load_price_csv(filepath: str, date_col: str = DATE_COLUMN) -> pd.DataFrame:
    """
    Load a price CSV file and parse the date column.
    Returns empty DataFrame if file does not exist.
    """
    if not os.path.exists(filepath):
        return pd.DataFrame()

    try:
        df = pd.read_csv(filepath)
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])
            df = df.sort_values(date_col).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[WARNING] Could not load {filepath}: {e}")
        return pd.DataFrame()


def load_and_slice(
    filepath: str,
    cutoff_date: datetime.date,
    date_col: str = DATE_COLUMN,
) -> pd.DataFrame:
    """
    Load a price CSV and slice to cutoff_date in one call.
    Returns empty DataFrame if file does not exist or has no data.
    """
    df = load_price_csv(filepath, date_col)
    if df.empty:
        return df
    return slice_to_date(df, cutoff_date, date_col)


# ─── TRADING CALENDAR UTILITIES ───────────────────────────────────────────────

def get_trading_weeks(
    start_date: datetime.date,
    end_date: datetime.date,
) -> list:
    """
    Return a list of Friday dates (week end dates) between start and end.

    The backtest runs weekly — S/R Detection and Momentum Ranker fire
    once per week. Friday is used as the week-end cutoff because:
    - Indian markets are open Mon–Fri
    - Using Friday data means full-week information is available
    - Consistent with how the live weekly ranker runs

    If start_date falls mid-week, the first cutoff is the Friday of
    that week (or start_date itself if it is a Friday).

    Args:
        start_date: First week start
        end_date:   Last date to include

    Returns:
        List of datetime.date objects (all Fridays)
    """
    weeks = []
    current = start_date

    # Advance to first Friday
    days_to_friday = (4 - current.weekday()) % 7  # Friday = weekday 4
    current = current + datetime.timedelta(days=days_to_friday)

    while current <= end_date:
        weeks.append(current)
        current = current + datetime.timedelta(weeks=1)

    return weeks


def get_trading_days_in_week(
    week_end_date: datetime.date,
    all_dates: list,
) -> list:
    """
    Return all trading days in the week ending on week_end_date.

    Args:
        week_end_date: Friday date (inclusive upper bound)
        all_dates:     Sorted list of all trading dates in the backtest

    Returns:
        List of datetime.date objects for trading days in that week
    """
    week_start = week_end_date - datetime.timedelta(days=6)
    return [
        d for d in all_dates
        if week_start <= d <= week_end_date
    ]


def get_all_trading_dates(data_dir: str, symbols: list) -> list:
    """
    Derive all trading dates from the price CSVs of a symbol list.
    Uses the union of all dates across all symbols.

    Args:
        data_dir: Directory containing price CSVs
        symbols:  List of symbol strings (e.g. ['TCS_NS', 'INFY_NS'])

    Returns:
        Sorted list of datetime.date objects
    """
    all_dates = set()

    for sym in symbols:
        fname = f"{sym.replace('.', '_')}.csv"
        fpath = os.path.join(data_dir, fname)
        df = load_price_csv(fpath)
        if not df.empty and DATE_COLUMN in df.columns:
            dates = df[DATE_COLUMN].dt.date.tolist()
            all_dates.update(dates)

    return sorted(all_dates)


# ─── NIFTY 200 SYMBOL LOADER ──────────────────────────────────────────────────

def load_symbols(symbols_file: str) -> list:
    """
    Load symbol list from a text file (one symbol per line).
    Returns list of symbol strings.
    """
    if not os.path.exists(symbols_file):
        print(f"[WARNING] Symbols file not found: {symbols_file}")
        return []

    with open(symbols_file, "r", encoding="utf-8") as f:
        symbols = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]
    return symbols


# ─── VALIDATION ───────────────────────────────────────────────────────────────

def validate_no_lookahead(
    df: pd.DataFrame,
    cutoff_date: datetime.date,
    date_col: str = DATE_COLUMN,
) -> bool:
    """
    Assert that a DataFrame contains no data after cutoff_date.
    Used in testing to verify slicing is working correctly.

    Returns True if clean, raises AssertionError if lookahead detected.
    """
    if df.empty:
        return True

    if date_col not in df.columns:
        return True

    max_date = df[date_col].max()
    if pd.isnull(max_date):
        return True

    max_date_val = max_date.date() if hasattr(max_date, "date") else max_date
    cutoff_val   = cutoff_date if isinstance(cutoff_date, datetime.date) else cutoff_date.date()

    if max_date_val > cutoff_val:
        raise AssertionError(
            f"LOOKAHEAD VIOLATION: DataFrame contains data up to {max_date_val} "
            f"but cutoff is {cutoff_val}"
        )
    return True
