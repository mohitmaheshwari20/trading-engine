Module module_b_sector
======================
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

Functions
---------

`compute_15d_return(price_data, symbol, date)`
:   Compute 15-trading-day return for a single stock on a given date.
    
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

`load_sector_mapping(mapping_file, verbose=True)`
:   Load sector mapping from JSON file.
    
    Args:
        mapping_file : str or Path — path to final_nifty200_sector_mapping.json
        verbose      : bool
    
    Returns:
        dict — {symbol: sector} e.g. {'RELIANCE.NS': 'Energy'}

`validate_sector_filter(filter_obj, test_dates, verbose=True)`
:   Validate Module B against the spec gate: 40–60% pass rate.
    
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

Classes
-------

`SectorAlphaFilter(mapping_file, price_data, verbose=True)`
:   Module B: Peer-Group Alpha Filter.
    
    Filters the Nifty 200 universe daily to stocks outperforming
    their sector peers on a 15-day return basis.
    
    Usage:
        filter = SectorAlphaFilter(mapping_file, price_data)
        eligible = filter.get_eligible_symbols(date)
    
    Args:
        mapping_file : str — path to final_nifty200_sector_mapping.json
        price_data   : dict — {symbol: DataFrame} pre-loaded price data
                       (same dict used by AllWeatherEngine)
        verbose      : bool

    ### Methods

    `get_eligible_symbols(self, date, verbose=False)`
    :   Return all stocks passing the Module B filter on a given date.
        
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

    `get_pass_rate(self, date)`
    :   Return pass rate (0.0 to 1.0) for a given date.
        Useful for validation without fetching full eligible list.

    `get_sector_breakdown(self, date)`
    :   Return per-sector pass/fail counts for a given date.
        Used for diagnostic analysis and Observation 2 validation.
        
        Returns:
            pandas DataFrame with columns:
                sector, total, passing, pass_rate, median_15d_return