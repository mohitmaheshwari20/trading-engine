Module module_a_regime
======================
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

Functions
---------

`build_regime_series(nifty_df, vix_series, start_date, end_date, verbose=True)`
:   Build a daily regime label Series for the full backtest window.
    
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

`classify_regime(nifty_close, ema200, vix)`
:   Classify a single day's market regime.
    
    Args:
        nifty_close : float — Nifty 50 closing price
        ema200      : float — EMA200 value for that day
        vix         : float — India VIX closing value for that day
    
    Returns:
        str — REGIME_ON, REGIME_CAUTION, or REGIME_OFF

`load_nifty50(data_dir, filename='NIFTY_NS.csv', verbose=True)`
:   Load Nifty 50 index data from CSV and compute EMA200.
    
    Args:
        data_dir : str or Path — directory containing NIFTY_NS.csv
        filename : str — index file name (default: NIFTY_NS.csv)
        verbose  : bool
    
    Returns:
        pandas DataFrame with columns: Date, Close, EMA200

`print_spot_checks(classifier)`
:   Print regime labels for key historical dates.

`validate_regime_classifier(classifier, verbose=True)`
:   Validate regime labels using data-driven checks — no hardcoded dates.
    
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

Classes
-------

`RegimeClassifier(data_dir, vix_series, start_date, end_date, verbose=True)`
:   Module A: Market Regime Classifier.
    
    Loads all data at initialisation and exposes fast O(1) lookups
    via get_regime(date) and get_size_multiplier(date).
    
    Usage:
        classifier = RegimeClassifier(data_dir, start_date, end_date)
        regime     = classifier.get_regime('2020-03-23')
        multiplier = classifier.get_size_multiplier('2020-03-23')
    
    Args:
        data_dir   : str — path to data directory containing NIFTY_NS.csv
        vix_series : pandas Series — from vix_loader.load_vix()['vix']
        start_date : str — backtest start
        end_date   : str — backtest end
        verbose    : bool

    ### Methods

    `get_regime(self, date)`
    :   Get market regime for a given date.
        
        If date is not a trading day, returns the most recent
        prior trading day's regime (no look-ahead bias).
        
        Args:
            date : str or datetime
        
        Returns:
            str — REGIME_ON, REGIME_CAUTION, or REGIME_OFF
            None if date is before the series start

    `get_regime_df(self)`
    :   Return full regime DataFrame for analysis and reporting.

    `get_regime_stats(self)`
    :   Return regime distribution statistics.

    `get_size_multiplier(self, date)`
    :   Get position size multiplier for a given date.
        
        Returns:
            float — 1.0 (ON), 0.5 (CAUTION), 0.0 (OFF)
            None if date is before the series start