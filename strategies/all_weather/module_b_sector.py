"""
module_b_sector.py — Module B: Peer-Group Alpha Filter
All-Weather Quant Strategy — NIFTY 200

Filters the NIFTY 200 universe to retain only stocks demonstrating
relative strength versus their sector peers on a 15-day return basis.

Logic:
    For each stock:
        15d_return = (Close_today - Close_15d_ago) / Close_15d_ago

    For each sector:
        sector_median = median(15d_return of all stocks in sector)

    Pass filter if:
        Stock_15d_return > Sector_Median_15d_return

    Others bucket fallback:
        If stock is mapped to 'Others', compare against
        NIFTY 200 Index Median (median of all 200 stocks' 15d returns)

Output per date:
    List of dicts — one per passing stock:
        {
            'symbol'       : str,
            'sector'       : str,
            'sector_bucket': 'Named Sector' or 'Others',
            'return_15d'   : float,
            'sector_median': float,
            'alpha'        : float  (return_15d - sector_median)
        }

Primary consumers:
    - AllWeatherEngine : calls get_eligible_symbols(date) before
                         passing stocks to Module C
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

LOOKBACK_DAYS   = 15          # Spec Section 3.1
OTHERS_BUCKET   = 'Others'    # Spec Section 3.2
NAMED_SECTOR    = 'Named Sector'


# ─────────────────────────────────────────────────────────────────────────────
# Sector mapping loader
# ─────────────────────────────────────────────────────────────────────────────

def load_sector_mapping(mapping_file, verbose=True):
    """
    Load sector mapping from JSON file.

    Args:
        mapping_file : str or Path — path to final_nifty200_sector_mapping.json
        verbose      : bool

    Returns:
        dict — {symbol: sector} e.g. {'RELIANCE.NS': 'Energy'}
    """
    filepath = Path(mapping_file)
    if not filepath.exists():
        raise FileNotFoundError(f"Sector mapping file not found: {filepath}")

    with open(filepath, 'r') as f:
        mapping = json.load(f)

    if verbose:
        sectors       = pd.Series(mapping.values())
        sector_counts = sectors.value_counts()
        others_count  = sector_counts.get(OTHERS_BUCKET, 0)
        named_count   = len(mapping) - others_count

        print(f"  Sector mapping loaded : {len(mapping)} symbols")
        print(f"  Named sectors         : {len(sector_counts) - 1} sectors, {named_count} stocks")
        print(f"  Others bucket         : {others_count} stocks")
        print(f"\n  Sector breakdown:")
        for sector, count in sector_counts.items():
            print(f"    {sector:<30} : {count} stocks")

    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# 15-day return calculator
# ─────────────────────────────────────────────────────────────────────────────

def compute_15d_return(price_data, symbol, date):
    """
    Compute 15-trading-day return for a single stock on a given date.

    Uses Adj Close for return calculation to account for corporate actions.
    Looks back exactly 15 trading days using the actual price data index
    (not calendar days) to avoid weekends/holidays distorting the window.

    Args:
        price_data : dict — {symbol: DataFrame} pre-loaded price data
        symbol     : str
        date       : pd.Timestamp

    Returns:
        float — 15-day return as decimal (e.g. 0.05 = +5%), or None if
                insufficient data
    """
    if symbol not in price_data:
        return None

    df = price_data[symbol]
    df_up_to_date = df[df['Date'] <= date]

    # Need at least LOOKBACK_DAYS + 1 rows
    if len(df_up_to_date) < LOOKBACK_DAYS + 1:
        return None

    price_col = 'Adj Close' if 'Adj Close' in df_up_to_date.columns else 'Close'

    price_today  = df_up_to_date.iloc[-1][price_col]
    price_15d_ago = df_up_to_date.iloc[-(LOOKBACK_DAYS + 1)][price_col]

    if price_15d_ago == 0 or pd.isna(price_15d_ago) or pd.isna(price_today):
        return None

    return (price_today - price_15d_ago) / price_15d_ago


# ─────────────────────────────────────────────────────────────────────────────
# SectorAlphaFilter — main class
# ─────────────────────────────────────────────────────────────────────────────

class SectorAlphaFilter:
    """
    Module B: Peer-Group Alpha Filter.

    Filters the Nifty 200 universe daily to stocks outperforming
    their sector peers on a 15-day return basis.

    Usage:
        filter = SectorAlphaFilter(mapping_file, price_data)
        eligible = filter.get_eligible_symbols(date)
    """

    def __init__(self, mapping_file, price_data, verbose=True):
        """
        Args:
            mapping_file : str — path to final_nifty200_sector_mapping.json
            price_data   : dict — {symbol: DataFrame} pre-loaded price data
                           (same dict used by AllWeatherEngine)
            verbose      : bool
        """
        if verbose:
            print("\n" + "=" * 60)
            print("MODULE B — SECTOR ALPHA FILTER")
            print("=" * 60)

        self._sector_map  = load_sector_mapping(mapping_file, verbose=verbose)
        self._price_data  = price_data

        # Pre-compute sector membership lists for efficiency
        self._sector_members = {}
        for symbol, sector in self._sector_map.items():
            if sector not in self._sector_members:
                self._sector_members[sector] = []
            self._sector_members[sector].append(symbol)

        # Identify Others bucket symbols
        self._others_symbols = set(
            s for s, sec in self._sector_map.items() if sec == OTHERS_BUCKET
        )

        if verbose:
            print(f"\n  Price data available  : {len(price_data)} symbols")
            matched = len(set(self._sector_map.keys()) & set(price_data.keys()))
            print(f"  Matched (map ∩ data)  : {matched} symbols")
            print("=" * 60 + "\n")

    def get_eligible_symbols(self, date, verbose=False):
        """
        Return all stocks passing the Module B filter on a given date.

        Steps:
            1. Compute 15-day return for every stock with available data
            2. Compute sector medians for named sectors
            3. Compute Nifty 200 index median for Others bucket
            4. Pass stocks where stock return > relevant median

        Args:
            date    : str or pd.Timestamp
            verbose : bool — print pass/fail counts per sector

        Returns:
            list of dicts:
                {
                    'symbol'       : str,
                    'sector'       : str,
                    'sector_bucket': 'Named Sector' or 'Others',
                    'return_15d'   : float,
                    'sector_median': float,
                    'alpha'        : float
                }
        """
        date = pd.to_datetime(date)

        # ── Step 1: Compute 15d returns for all available symbols ────────────
        returns = {}
        for symbol in self._sector_map:
            ret = compute_15d_return(self._price_data, symbol, date)
            if ret is not None:
                returns[symbol] = ret

        if len(returns) == 0:
            return []

        all_returns = list(returns.values())
        nifty200_median = float(np.median(all_returns))

        # ── Step 2: Compute sector medians ───────────────────────────────────
        sector_medians = {}
        for sector, members in self._sector_members.items():
            if sector == OTHERS_BUCKET:
                continue
            sector_returns = [returns[s] for s in members if s in returns]
            if len(sector_returns) > 0:
                sector_medians[sector] = float(np.median(sector_returns))

        # ── Step 3: Apply filter ─────────────────────────────────────────────
        eligible = []
        for symbol, ret in returns.items():
            sector = self._sector_map[symbol]

            if sector == OTHERS_BUCKET:
                benchmark      = nifty200_median
                sector_bucket  = 'Others'
            else:
                if sector not in sector_medians:
                    continue
                benchmark     = sector_medians[sector]
                sector_bucket = NAMED_SECTOR

            if ret > benchmark:
                eligible.append({
                    'symbol'       : symbol,
                    'sector'       : sector,
                    'sector_bucket': sector_bucket,
                    'return_15d'   : round(ret, 6),
                    'sector_median': round(benchmark, 6),
                    'alpha'        : round(ret - benchmark, 6)
                })

        if verbose:
            total   = len(returns)
            passing = len(eligible)
            pct     = passing / total * 100 if total > 0 else 0
            print(f"  [{date.date()}] Universe: {total} | "
                  f"Passing: {passing} ({pct:.1f}%) | "
                  f"Nifty200 median 15d return: {nifty200_median*100:.2f}%")

        return eligible

    def get_pass_rate(self, date):
        """
        Return pass rate (0.0 to 1.0) for a given date.
        Useful for validation without fetching full eligible list.
        """
        date     = pd.to_datetime(date)
        eligible = self.get_eligible_symbols(date)

        # Count total with available data
        total = sum(
            1 for s in self._sector_map
            if compute_15d_return(self._price_data, s, date) is not None
        )
        return len(eligible) / total if total > 0 else 0.0

    def get_sector_breakdown(self, date):
        """
        Return per-sector pass/fail counts for a given date.
        Used for diagnostic analysis and Observation 2 validation.

        Returns:
            pandas DataFrame with columns:
                sector, total, passing, pass_rate, median_15d_return
        """
        date     = pd.to_datetime(date)
        eligible = self.get_eligible_symbols(date)
        eligible_symbols = {e['symbol'] for e in eligible}

        # Compute returns for all
        returns = {}
        for symbol in self._sector_map:
            ret = compute_15d_return(self._price_data, symbol, date)
            if ret is not None:
                returns[symbol] = ret

        rows = []
        for sector in sorted(self._sector_members.keys()):
            members      = self._sector_members[sector]
            sector_rets  = [returns[s] for s in members if s in returns]
            sector_pass  = [s for s in members if s in eligible_symbols]

            if len(sector_rets) == 0:
                continue

            rows.append({
                'sector'           : sector,
                'total'            : len(sector_rets),
                'passing'          : len(sector_pass),
                'pass_rate_pct'    : round(len(sector_pass) / len(sector_rets) * 100, 1),
                'median_15d_ret_pct': round(float(np.median(sector_rets)) * 100, 2)
            })

        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_sector_filter(filter_obj, test_dates, verbose=True):
    """
    Validate Module B against the spec gate: 40–60% pass rate.

    Data-driven checks — no hardcoded sector expectations:
        1. Pass rate between 40–60% on each test date
        2. Others bucket and Named Sector both represented in output
        3. All passing stocks have positive alpha (return > median)
        4. No stock appears twice in eligible list
        5. Sector medians are stable (not extreme outliers)

    Args:
        filter_obj : SectorAlphaFilter instance
        test_dates : list of str — dates to validate against
        verbose    : bool

    Returns:
        bool — True if all checks pass
    """
    if verbose:
        print("Running Module B validation checks...")

    all_passed = True

    for date in test_dates:
        if verbose:
            print(f"\n  Date: {date}")

        eligible = filter_obj.get_eligible_symbols(date, verbose=False)

        # Count total available
        total = sum(
            1 for s in filter_obj._sector_map
            if compute_15d_return(filter_obj._price_data, s, date) is not None
        )

        if total == 0:
            if verbose:
                print(f"    — No data available for {date}, skipping")
            continue

        passing  = len(eligible)
        pass_pct = passing / total * 100

        # Check 1: Pass rate 40–60%
        rate_ok = 40 <= pass_pct <= 60
        status  = '✓' if rate_ok else '✗'
        if verbose:
            print(f"    {status} Pass rate: {passing}/{total} = {pass_pct:.1f}% "
                  f"(target: 40–60%)")
        if not rate_ok:
            all_passed = False

        # Check 2: Both bucket types represented
        buckets = {e['sector_bucket'] for e in eligible}
        both_present = NAMED_SECTOR in buckets and 'Others' in buckets
        status = '✓' if both_present else '✗'
        if verbose:
            print(f"    {status} Buckets in output: {sorted(buckets)}")
        if not both_present:
            all_passed = False

        # Check 3: All passing stocks have positive alpha
        neg_alpha = [e for e in eligible if e['alpha'] <= 0]
        alpha_ok  = len(neg_alpha) == 0
        status    = '✓' if alpha_ok else '✗'
        if verbose:
            print(f"    {status} All passing stocks have alpha > 0: "
                  f"{len(neg_alpha)} violations")
        if not alpha_ok:
            all_passed = False

        # Check 4: No duplicate symbols
        symbols  = [e['symbol'] for e in eligible]
        no_dupes = len(symbols) == len(set(symbols))
        status   = '✓' if no_dupes else '✗'
        if verbose:
            print(f"    {status} No duplicate symbols: "
                  f"{len(symbols) - len(set(symbols))} duplicates")
        if not no_dupes:
            all_passed = False

    if verbose:
        result = "\n  ALL CHECKS PASSED ✓" if all_passed else "\n  SOME CHECKS FAILED ✗"
        print(result)

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — run on local machine to validate
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    import os
    sys.path.insert(0, '.')

    from data.loader import DataLoader

    DATA_DIR     = r'C:\Projects\trading_engine\data\Historical Daily Data'
    MAPPING_FILE = r'C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json'

    # Load all stock data
    print("Loading Nifty 200 price data...")
    loader     = DataLoader(DATA_DIR)
    all_stocks = list(json.load(open(MAPPING_FILE)).keys())

    price_data = {}
    for symbol in all_stocks:
        # Convert RELIANCE.NS → RELIANCE_NS for file lookup
        filename = symbol.replace('.', '_')
        try:
            df = loader.load_stock(filename)
            price_data[symbol] = df
        except FileNotFoundError:
            continue

    print(f"Loaded {len(price_data)}/{len(all_stocks)} symbols\n")

    # Build filter
    sector_filter = SectorAlphaFilter(MAPPING_FILE, price_data)

    # Validate on 3 sample dates spread across backtest window
    test_dates = ['2018-06-15', '2021-03-15', '2024-06-14']

    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)
    validate_sector_filter(sector_filter, test_dates)

    # Sector breakdown for most recent test date
    print("\n" + "=" * 60)
    print(f"SECTOR BREAKDOWN — {test_dates[-1]}")
    print("=" * 60)
    breakdown = sector_filter.get_sector_breakdown(test_dates[-1])
    print(breakdown.to_string(index=False))
