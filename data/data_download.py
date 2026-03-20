import os
import datetime as dt
from typing import List, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
import requests
import time
import csv
import urllib.parse

# ------------- CONFIG -------------

DATA_DIR = r"C:\Projects\trading_engine\data\Historical Daily Data"

# Maps our sector index symbol -> NSE index name used in the API
NSE_SECTOR_INDEX_NAME = {
    "NIFTY_BANK_NS": "NIFTY BANK",
    "NIFTY_IT_NS": "NIFTY IT",
    "NIFTY_PHARMA_NS": "NIFTY PHARMA",
    "NIFTY_AUTO_NS": "NIFTY AUTO",
    "NIFTY_FMCG_NS": "NIFTY FMCG",
    "NIFTY_FIN_SERVICE_NS": "NIFTY FINANCIAL SERVICES",
    "NIFTY_ENERGY_NS": "NIFTY ENERGY",
    "NIFTY_METAL_NS": "NIFTY METAL",
    "NIFTY_REALTY_NS": "NIFTY REALTY",
    "NIFTY_INFRASTRUCTURE_NS": "NIFTY INFRASTRUCTURE",
    "NIFTY_MEDIA_NS": "NIFTY MEDIA",
}

def _init_nse_session_for_indices() -> requests.Session:
    """
    Session with headers + homepage hit so NSE sets cookies.
    Re-use this session for all index downloads.
    """
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json,text/html",
            "Connection": "keep-alive",
        }
    )
    # prime cookies
    s.get("https://www.nseindia.com", timeout=10)
    return s

# Add / edit your symbols here (Yahoo tickers)
def load_symbol_list(filepath: str = "nifty50_symbols.txt") -> list[str]:
    """
    Load a list of Yahoo Finance symbols from a text file.
    One symbol per line.
    Blank lines and comments (# ...) are ignored.

    The filename may be passed as a simple name, in which case we first
    try the current working directory.  If that fails we also look in the
    repository root (two levels above this module) where the default symbol
    lists live.  This makes the script usable when executed from elsewhere
    without needing to `cd` into the repo root.
    """
    # first try the path verbatim
    if os.path.exists(filepath):
        actual_path = filepath
    else:
        # attempt to resolve relative to project root
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                 os.pardir,  # utils
                                                 os.pardir))  # backtesting_system
        candidate = os.path.join(repo_root, filepath)
        if os.path.exists(candidate):
            actual_path = candidate
        else:
            raise FileNotFoundError(f"Symbol list file not found: {filepath}")

    symbols = []
    with open(actual_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            symbols.append(line)

    if not symbols:
        raise ValueError("Symbol list file is empty or invalid.")

    return symbols


DEFAULT_START_DATE = dt.date(2015, 1, 1)


# ------------- HELPERS -------------

def ensure_data_dir() -> None:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def get_symbol_filename(symbol: str) -> str:
    """
    Map Yahoo symbol to a CSV filename.
    Example: HDFCBANK.NS -> HDFCBANK_NS.csv
    """
    ensure_data_dir()
    safe_symbol = symbol.replace(".", "_")
    return os.path.join(DATA_DIR, f"{safe_symbol}.csv")


def _normalize_yf_df(symbol: str, raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize yfinance output (including MultiIndex columns) into:
      Ticker, Date, Open, High, Low, Close, Adj Close, Volume

    Returns empty DataFrame if raw_df is empty or unusable.
    """
    if raw_df is None or raw_df.empty:
        print(f"  WARNING [{symbol}]: Yahoo returned empty data frame.")
        return pd.DataFrame()

    df = raw_df.copy()

    # Handle MultiIndex columns like:
    #   Price            Close        High   ...
    #   Ticker     HDFCBANK.NS HDFCBANK.NS ...
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten by taking only the first level: Close, High, Low, Open, Volume
        df.columns = df.columns.get_level_values(0)

    # Ensure index has a name and is the Date
    if df.index.name is None:
        df.index.name = "Date"

    # Move Date index to a column
    df = df.reset_index()

    if "Date" not in df.columns:
        print(f"  WARNING [{symbol}]: 'Date' column missing after reset_index.")
        print("           Columns:", list(df.columns))
        return pd.DataFrame()

    # Insert Ticker column
    df.insert(0, "Ticker", symbol)

    # Make sure Adj Close exists
    if "Adj Close" not in df.columns:
        if "Adj_Close" in df.columns:
            df.rename(columns={"Adj_Close": "Adj Close"}, inplace=True)
        else:
            if "Close" not in df.columns:
                print(f"  WARNING [{symbol}]: 'Close' missing; cannot create Adj Close.")
                return pd.DataFrame()
            df["Adj Close"] = df["Close"]

    required_cols = ["Ticker", "Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    for c in required_cols:
        if c not in df.columns:
            print(f"  WARNING [{symbol}]: Missing column '{c}' after normalization.")
            print("           Available columns:", list(df.columns))
            return pd.DataFrame()

    df = df[required_cols]

    # Final cleanup
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    return df


def validate_price_data(symbol: str, df: pd.DataFrame,
                        verbose: bool = False) -> dict:
    """
    Run data quality checks on a downloaded price DataFrame.
    Returns dict with check results.
    """
    issues = []

    # Check 1: Minimum row count
    if len(df) < 200:
        issues.append(f"Low row count: {len(df)} rows (min 200 expected)")

    # Check 2: No missing dates on trading days
    df["Date"] = pd.to_datetime(df["Date"])
    date_range = pd.date_range(df["Date"].min(), df["Date"].max(), freq="B")
    missing_days = len(date_range) - len(df)
    if missing_days > len(date_range) * 0.05:  # >5% missing
        issues.append(f"Excessive missing dates: {missing_days} gaps "
                      f"({missing_days/len(date_range)*100:.1f}% of trading days)")

    # Check 3: No zero or negative prices
    zero_prices = (df["Close"] <= 0).sum()
    if zero_prices > 0:
        issues.append(f"Zero/negative Close prices: {zero_prices} rows")

    # Check 4: No extreme single-day price jumps (>50%)
    price_changes = df["Close"].pct_change().abs()
    extreme_jumps = (price_changes > 0.5).sum()
    if extreme_jumps > 0:
        jump_dates = df.loc[price_changes > 0.5, "Date"].tolist()
        issues.append(f"Extreme price jumps >50%: {extreme_jumps} days "
                      f"(check corporate actions: {jump_dates[:3]})")

    # Check 5: No zero volume days (excluding weekends)
    zero_volume = (df["Volume"] == 0).sum()
    if zero_volume > len(df) * 0.02:  # >2% zero volume
        issues.append(f"High zero-volume days: {zero_volume} "
                      f"({zero_volume/len(df)*100:.1f}%)")

    result = {
        "symbol": symbol,
        "rows": len(df),
        "start": df["Date"].min().date(),
        "end": df["Date"].max().date(),
        "issues": issues,
        "passed": len(issues) == 0
    }

    if verbose:
        status = "\u2705" if result["passed"] else "\u26a0\ufe0f"
        print(f"  {status} {symbol}: {len(df)} rows "
              f"({result['start']} to {result['end']})")
        for issue in issues:
            print(f"      \u26a0\ufe0f  {issue}")

    return result


# ------------- PER-SYMBOL FUNCTIONS -------------

def download_full_history(
    symbol: str,
    start: dt.date = DEFAULT_START_DATE,
    end: Optional[dt.date] = None,
) -> None:
    """
    Download full daily history for `symbol` from `start` to `end` (default: today)
    and save to its CSV file:
      Ticker, Date, Open, High, Low, Close, Adj Close, Volume
    """
    if end is None:
        end = dt.date.today()

    filepath = get_symbol_filename(symbol)

    start_str = start.strftime("%Y-%m-%d")
    # yfinance 'end' is exclusive for daily data -> use tomorrow
    end_exclusive = end + dt.timedelta(days=1)
    end_str = end_exclusive.strftime("%Y-%m-%d")

    print(f"[FULL] {symbol}: {start_str} -> {end} (saving to {os.path.basename(filepath)})")

    raw = yf.download(
        symbol,
        start=start_str,
        end=end_str,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    df = _normalize_yf_df(symbol, raw)
    if df.empty:
        print(f"  ERROR [{symbol}]: No usable data from Yahoo. Skipping.")
        return

    df.to_csv(filepath, index=False)
    print(f"  Saved {len(df)} rows. Last date: {df['Date'].max().date()}")
    validate_price_data(symbol, df, verbose=True)


def update_history(symbol: str) -> None:
    """
    Incrementally update CSV for `symbol`:

    - If file doesn't exist -> full download.
    - Else:
        - load CSV,
        - find last Date,
        - fetch [last_date+1, today],
        - append & deduplicate by Date.
    """
    filepath = get_symbol_filename(symbol)

    if not os.path.exists(filepath):
        print(f"[UPDATE] {symbol}: No existing file. Doing full download instead.")
        download_full_history(symbol)
        return

    existing = pd.read_csv(filepath)

    if "Date" not in existing.columns:
        print(f"[UPDATE] {symbol}: No 'Date' column in file. Re-downloading full history.")
        download_full_history(symbol)
        return

    existing["Date"] = pd.to_datetime(existing["Date"], errors="coerce")
    existing = existing.dropna(subset=["Date"])
    existing = existing.sort_values("Date").reset_index(drop=True)

    if existing.empty:
        print(f"[UPDATE] {symbol}: File empty after cleaning. Re-downloading full history.")
        download_full_history(symbol)
        return

    last_date = existing["Date"].max().date()
    today = dt.date.today()

    if last_date >= today:
        print(f"[UPDATE] {symbol}: Already up to date. Last date: {last_date}")
        return

    start = last_date + dt.timedelta(days=1)
    end = today

    start_str = start.strftime("%Y-%m-%d")
    end_exclusive = end + dt.timedelta(days=1)
    end_str = end_exclusive.strftime("%Y-%m-%d")

    print(f"[UPDATE] {symbol}: {start} -> {end}")

    raw_new = yf.download(
        symbol,
        start=start_str,
        end=end_str,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    new_df = _normalize_yf_df(symbol, raw_new)
    if new_df.empty:
        print(f"  No new usable data for {symbol} (market closed or Yahoo delayed).")
        return

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")
    combined = combined.dropna(subset=["Date"])
    combined = combined.drop_duplicates(subset=["Date"], keep="last")
    combined = combined.sort_values("Date").reset_index(drop=True)

    combined.to_csv(filepath, index=False)
    print(
        f"  Updated {symbol}: rows = {len(combined)}, "
        f"last date = {combined['Date'].max().date()}"
    )

def download_nifty_index(data_dir: str, start: str = "2015-01-01"):
    """
    Download or incrementally update NIFTY 50 index (^NSEI) data.

    - First run: downloads full history from `start` and saves NIFTY_NS.csv
    - Subsequent runs: loads existing NIFTY_NS.csv, finds last date,
      downloads data from last_date + 1 day to today, appends & de-duplicates.
    """

    index_symbol = "^NSEI"        # Yahoo Finance index symbol
    filename = "NIFTY_NS.csv"     # Our standardized file name
    filepath = os.path.join(data_dir, filename)

    # ----------------------------------------------------------
    # 1) Decide from which date to download
    # ----------------------------------------------------------
    if os.path.exists(filepath):
        # Incremental update mode
        existing = pd.read_csv(filepath, parse_dates=["Date"])
        if existing.empty:
            print(f"[WARN] Existing NIFTY file {filepath} is empty. Redownloading from scratch.")
            download_start = start
        else:
            last_date = existing["Date"].max().date()
            download_start_date = last_date + timedelta(days=1)

            today = datetime.utcnow().date()
            if download_start_date > today:
                print(f"[INFO] NIFTY index is already up to date. Last date: {last_date}")
                return

            download_start = download_start_date.strftime("%Y-%m-%d")
            print(f"[INFO] Updating NIFTY from {download_start} (last saved date was {last_date})")
    else:
        # First time: full history
        existing = None
        download_start = start
        print(f"[INFO] NIFTY file not found. Downloading full history from {download_start}.")

    # ----------------------------------------------------------
    # 2) Download from Yahoo Finance
    # ----------------------------------------------------------
    try:
        end_exclusive = (datetime.utcnow().date() + timedelta(days=1)).strftime("%Y-%m-%d")
        df_new = yf.download(
            index_symbol,
            start=download_start,
            end=end_exclusive,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
    except Exception as e:
        print(f"[ERROR] Failed to download NIFTY from {download_start}: {e}")
        return

    if df_new is None or df_new.empty:
        print(f"[INFO] No new NIFTY data available from {download_start}.")
        return

    df_new = df_new.reset_index()
    # Flatten multi-level columns if present
    if isinstance(df_new.columns, pd.MultiIndex):
        df_new.columns = df_new.columns.get_level_values(0)

    # Standardize column names
    df_new.rename(
        columns={
            "Date": "Date",
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Adj Close": "Adj_Close",
            "Volume": "Volume",
        },
        inplace=True,
    )

    # Ensure Adj_Close exists
    if "Adj_Close" not in df_new.columns:
        if "Adj Close" in df_new.columns:
            df_new.rename(columns={"Adj Close": "Adj_Close"}, inplace=True)
        else:
            # If Yahoo does not provide adjusted close for index, simply use Close
            df_new["Adj_Close"] = df_new["Close"]

    # Now safely select columns
    df_new = df_new[["Date", "Open", "High", "Low", "Close", "Adj_Close", "Volume"]]

    # ----------------------------------------------------------
    # 3) Merge with existing (if any), de-duplicate, sort
    # ----------------------------------------------------------
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, df_new], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date"]).sort_values("Date")
    else:
        combined = df_new.sort_values("Date")

    # ----------------------------------------------------------
    # 4) Save back to CSV
    # ----------------------------------------------------------
    combined.to_csv(filepath, index=False)

    print(f"[INFO] Saved NIFTY index to {filepath}")
    print(f"[INFO] Total rows: {len(combined):,}")
    print(f"[INFO] First date: {combined['Date'].min().date()}, Last date: {combined['Date'].max().date()}\n")


# ------------- BULK HELPERS (MULTI-SYMBOL) -------------

def download_all_history(
    symbols: List[str],
    start: dt.date = DEFAULT_START_DATE,
    end: Optional[dt.date] = None,
) -> None:
    """
    Full history download for a list of symbols.
    """
    print("=== FULL HISTORY DOWNLOAD FOR ALL SYMBOLS ===")
    for sym in symbols:
        try:
            download_full_history(sym, start=start, end=end)
        except Exception as e:
            print(f"  ERROR while downloading {sym}: {e}")
        time.sleep(0.1)
    print("=== DONE FULL DOWNLOAD ===")


def update_all_history(symbols: List[str]) -> None:
    """
    Incremental update for all symbols.
    """
    print("=== INCREMENTAL UPDATE FOR ALL SYMBOLS ===")
    for sym in symbols:
        try:
            update_history(sym)
        except Exception as e:
            print(f"  ERROR while updating {sym}: {e}")
        time.sleep(0.1)
    print("=== DONE UPDATE ===")

def sync_all_history(symbols: list[str]) -> None:
    """
    For each symbol:
        - If CSV exists -> incremental update
        - If CSV doesn't exist -> full history download

    This automatically picks up newly added symbols in symbols.txt.
    """
    print("=== SYNC ALL SYMBOLS ===")
    for sym in symbols:
        try:
            update_history(sym)
        except Exception as e:
            print(f"  ERROR while syncing {sym}: {e}")
        time.sleep(0.1)
    print("=== DONE SYNC ===")


def download_vix_data(data_dir: str, start: str = "2015-01-01") -> None:
    """
    Download or incrementally update India VIX (^INDIAVIX) data.
    Primary source: ^INDIAVIX via yfinance
    Fallback: 20-day realized volatility of Nifty 50 x sqrt(252) x 100
    Output file: INDIAVIX_NS.csv
    Schema: Date, VIX
    """
    filepath = os.path.join(data_dir, "INDIAVIX_NS.csv")
    vix_ticker = "^INDIAVIX"

    # Determine start date
    if os.path.exists(filepath):
        existing = pd.read_csv(filepath, parse_dates=["Date"])
        if not existing.empty:
            last_date = existing["Date"].max().date()
            download_start = (last_date + dt.timedelta(days=1)).strftime("%Y-%m-%d")
            today = dt.date.today()
            if last_date >= today:
                print(f"[VIX] Already up to date. Last date: {last_date}")
                return
            print(f"[VIX] Updating from {download_start}")
        else:
            existing = None
            download_start = start
    else:
        existing = None
        download_start = start
        print(f"[VIX] First download from {download_start}")

    end_exclusive = (dt.date.today() + dt.timedelta(days=1)).strftime("%Y-%m-%d")

    # Try primary source
    try:
        raw = yf.download(vix_ticker, start=download_start,
                          end=end_exclusive, interval="1d",
                          auto_adjust=False, progress=False)

        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.reset_index()
            raw["Date"] = pd.to_datetime(raw["Date"])
            vix_df = raw[["Date", "Close"]].copy()
            vix_df.columns = ["Date", "VIX"]
            source = "primary"
        else:
            vix_df = None
            source = None
    except Exception as e:
        print(f"[VIX] Primary source failed: {e}")
        vix_df = None
        source = None

    # Fallback: realized volatility from Nifty 50
    if vix_df is None or vix_df.empty:
        print("[VIX] Falling back to realized volatility from ^NSEI")
        try:
            raw_nifty = yf.download("^NSEI", start=download_start,
                                    end=end_exclusive, interval="1d",
                                    auto_adjust=False, progress=False)
            if isinstance(raw_nifty.columns, pd.MultiIndex):
                raw_nifty.columns = raw_nifty.columns.get_level_values(0)
            close = raw_nifty["Close"].dropna()
            log_ret = np.log(close / close.shift(1)).dropna()
            realized_vol = (log_ret.rolling(20).std() * np.sqrt(252) * 100).dropna()
            realized_vol = realized_vol.reset_index()
            realized_vol.columns = ["Date", "VIX"]
            realized_vol["Date"] = pd.to_datetime(realized_vol["Date"])
            vix_df = realized_vol
            source = "fallback"
            print("[VIX] WARNING: Using realized vol fallback — "
                  "calibrate against actual VIX before production use")
        except Exception as e:
            print(f"[VIX] Fallback also failed: {e}")
            return

    # Merge with existing
    if existing is not None and not existing.empty:
        combined = pd.concat([existing, vix_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date"]).sort_values("Date")
    else:
        combined = vix_df.sort_values("Date")

    combined.to_csv(filepath, index=False)
    print(f"[VIX] Saved {len(combined)} rows | Source: {source}")
    print(f"[VIX] Range: {combined['Date'].min().date()} "
          f"to {combined['Date'].max().date()}")


# ─────────────────────────────────────────────────────
# SECTOR INDEX DATA — KNOWN LIMITATION
# ─────────────────────────────────────────────────────
# NSE sector index data via API is unreliable and
# frequently breaks due to NSE API changes.
#
# RECOMMENDED ALTERNATIVE (implemented in All-Weather
# strategy module_b_sector.py):
#   Use stock-level returns relative to sector median
#   as a proxy for sector alpha. This approach:
#   - Requires only individual stock OHLCV data
#   - Is not dependent on NSE API availability
#   - Has been validated on Nifty 200 (2017-2025)
#   - Pass rates: 46-47% (within 40-60% target)
#
# If sector index data is needed, use yfinance with
# these tickers: ^CNXBANK, ^CNXIT, ^CNXPHARMA etc.
# Note: yfinance coverage is incomplete pre-2015.
# ─────────────────────────────────────────────────────
def download_sector_index_from_nse_V1(
    index_code: str,
    nse_name: str,
    data_dir: str,
    start: str = "2015-01-01",
) -> None:
    """
    Download (or update) sector index data from NSE for a given index.

    - index_code: internal code, e.g. "NIFTY_INFRASTRUCTURE_NS"
    - nse_name  : display name used by NSE, e.g. "NIFTY INFRASTRUCTURE"
    - data_dir  : folder where CSV will be stored
    - start     : start date (YYYY-MM-DD) for first download

    Output CSV schema (like other index files):
        Date, Open, High, Low, Close, Adj_Close
    """
    import math
    from datetime import datetime, timedelta
    import urllib.parse

    ensure_data_dir()
    filename = f"{index_code}.csv"
    filepath = os.path.join(data_dir, filename)

    # ----------------------------------------------------------
    # Decide date range
    # ----------------------------------------------------------
    if os.path.exists(filepath):
        existing = pd.read_csv(filepath, parse_dates=["Date"])
        if not existing.empty:
            last_date = existing["Date"].max().date()
            start_date = last_date + timedelta(days=1)
            print(f"[NSE-INDEX] {index_code}: updating from {start_date}")
        else:
            existing = None
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            print(f"[NSE-INDEX] {index_code}: existing empty, redownloading from {start_date}")
    else:
        existing = None
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        print(f"[NSE-INDEX] {index_code}: downloading from {start_date}")

    today = datetime.utcnow().date()
    if start_date > today:
        print(f"[NSE-INDEX] {index_code}: already up to date (last date {start_date - timedelta(days=1)})")
        return

    # ----------------------------------------------------------
    # Prepare NSE session (same pattern as build_sector_map)
    # ----------------------------------------------------------
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/",
        "X-Requested-With": "XMLHttpRequest"
    }
    session.headers.update(headers)
    session.get("https://www.nseindia.com", timeout=10)
    time.sleep(1)  # Add delay after homepage visit

    # NSE index history endpoint (date range <= 365 days)
    base_url = "https://www.nseindia.com/api/historical/indicesHistory"

    all_rows = []
    window_days = 365

    current_start = start_date
    while current_start <= today:
        current_end = min(current_start + timedelta(days=window_days - 1), today)

        params = {
        "indexType": nse_name,  # Changed from "index" to "indexType"
        "from": current_start.strftime("%d-%m-%Y"),
        "to": current_end.strftime("%d-%m-%Y"),
        }

        # Use session.get with params directly instead of manual encoding


        print(f"  [NSE-INDEX] {index_code}: chunk {current_start} -> {current_end}")
        try:
            resp = session.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"  [ERROR] {index_code}: failed chunk {current_start}->{current_end}: {e}")
            try:
                print(f"  [ERROR] Response: {resp.status_code} - {resp.text[:200]}")
            except:
                pass
            current_start = current_end + timedelta(days=1)
            time.sleep(0.8)
            continue  # Skip to next iteration
        except Exception as e:
            print(f"  [ERROR] {index_code}: failed chunk {current_start}->{current_end}: {e}")
            current_start = current_end + timedelta(days=1)
            time.sleep(0.8)
            continue  # Skip to next iteration

        data = payload.get("data") or []

        if not data:
            print(f"  [INFO] {index_code}: no records in this chunk.")
            current_start = current_end + timedelta(days=1)
            time.sleep(0.4)
            continue

        # Parse each record in a schema-tolerant way
        for rec in data:
            # Try several possible keys for each field
            date_str = (
                rec.get("EOD_TIMESTAMP")
                or rec.get("CH_TIMESTAMP")
                or rec.get("TIMESTAMP")
            )
            open_ = (
                rec.get("EOD_OPEN_INDEX_VAL")
                or rec.get("CH_OPENING_VALUE")
                or rec.get("open")
            )
            high = (
                rec.get("EOD_HIGH_INDEX_VAL")
                or rec.get("CH_HIGH_INDEX_VAL")
                or rec.get("high")
            )
            low = (
                rec.get("EOD_LOW_INDEX_VAL")
                or rec.get("CH_LOW_INDEX_VAL")
                or rec.get("low")
            )
            close = (
                rec.get("EOD_CLOSE_INDEX_VAL")
                or rec.get("CH_CLOSING_VALUE")
                or rec.get("CH_CLOSE_VALUE")
                or rec.get("close")
            )

            if not date_str or close is None:
                # essential fields missing -> skip
                continue

            all_rows.append(
                {
                    "Date": date_str,
                    "Open": open_,
                    "High": high,
                    "Low": low,
                    "Close": close,
                }
            )

        current_start = current_end + timedelta(days=1)
        time.sleep(0.4)

    if not all_rows:
        print(f"[NSE-INDEX] {index_code}: no data collected at all.")
        return

    df = pd.DataFrame(all_rows)

    # Date parsing – NSE usually uses dd-MMM-yyyy or dd-MM-yyyy
    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
        infer_datetime_format=True,
        dayfirst=True,
    )
    df = df.dropna(subset=["Date"])

    # Ensure numeric types
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Close"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["Adj_Close"] = df["Close"]

    if existing is not None and not existing.empty:
        combined = pd.concat([existing, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date"]).sort_values("Date")
    else:
        combined = df

    out_path = os.path.join(data_dir, f"{index_code}.csv")
    combined.to_csv(out_path, index=False)

    print(f"[NSE-INDEX] {index_code}: saved {len(combined)} rows to {out_path}")
    print(
        f"[NSE-INDEX] {index_code}: first={combined['Date'].min().date()}, "
        f"last={combined['Date'].max().date()}"
    )

def download_sector_index_from_nse(
    index_code: str,
    nse_name: str,
    data_dir: str,
    start: str = "2015-01-01",
) -> None:
    """
    Download sector index data using nsepy library.
    """
    from nsepy import get_history
    from datetime import datetime
    import pandas as pd
    
    ensure_data_dir()
    filepath = os.path.join(data_dir, f"{index_code}.csv")
    
    # Determine date range
    if os.path.exists(filepath):
        existing = pd.read_csv(filepath, parse_dates=["Date"])
        if not existing.empty:
            start_date = existing["Date"].max().date() + timedelta(days=1)
        else:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
    else:
        existing = None
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
    
    end_date = datetime.now().date()
    
    if start_date > end_date:
        print(f"[NSE-INDEX] {index_code}: already up to date")
        return
    
    print(f"[NSE-INDEX] {index_code}: downloading from {start_date} to {end_date}")
    
    try:
        # nsepy handles the index name mapping automatically
        df = get_history(
            symbol=nse_name,
            start=start_date,
            end=end_date,
            index=True
        )
        
        if df.empty:
            print(f"[NSE-INDEX] {index_code}: no data received")
            return
        
        # Rename columns to match your schema
        df = df.reset_index()
        df = df.rename(columns={
            'Date': 'Date',
            'Open': 'Open',
            'High': 'High',
            'Low': 'Low',
            'Close': 'Close',
        })
        df['Adj_Close'] = df['Close']
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Adj_Close']]
        
        # Combine with existing
        if existing is not None:
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['Date']).sort_values('Date')
        else:
            combined = df
        
        combined.to_csv(filepath, index=False)
        print(f"[NSE-INDEX] {index_code}: saved {len(combined)} rows")
        
    except Exception as e:
        print(f"[NSE-INDEX] {index_code}: error - {e}")


def download_all_sector_indices_from_nse(
    data_dir: str,
    start: str = "2015-01-01",
) -> None:
    """
    Download / update all configured NIFTY sector indices from NSE.
    Uses NSE_SECTOR_INDEX_NAME mapping.
    """
    print("[NSE-INDEX] Downloading all sector indices from NSE...")
    for index_code, nse_name in NSE_SECTOR_INDEX_NAME.items():
        download_sector_index_from_nse(index_code, nse_name, data_dir, start=start)
    print("[NSE-INDEX] Done.")


# ============================================================
# NSE sector / industry fetch + sector_map regeneration
# ============================================================

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.nseindia.com/",
}

def load_existing_sector_map(path: str) -> dict:
    """
    Optional: load an existing sector_map.csv to preserve your
    manually curated 'sector' and 'sector_index_symbol' while
    refreshing raw_industry from NSE.
    Returns: {symbol: {"sector": ..., "sector_index_symbol": ...}}
    """
    if not os.path.exists(path):
        return {}

    out = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("symbol")
            if not sym:
                continue
            out[sym.strip()] = {
                "sector": row.get("sector", "").strip(),
                "sector_index_symbol": row.get("sector_index_symbol", "").strip(),
            }
    return out

# ------------- ENTRY POINT -------------

if __name__ == "__main__":
   # --- NIFTY 50 ---
    symbols = load_symbol_list("nifty200_symbols.txt")  # or nifty50_symbols.txt

    try:
        nifty50_symbols = load_symbol_list("nifty50_symbols.txt")
        print(f"[INFO] Loaded {len(nifty50_symbols)} NIFTY50 symbols.")
    except FileNotFoundError:
        nifty50_symbols = []
        print("[WARN] nifty50_symbols.txt not found. Skipping NIFTY50.")
    

    # --- NIFTY 200 ---
    try:
        nifty200_symbols = load_symbol_list("nifty200_symbols.txt")
        print(f"[INFO] Loaded {len(nifty200_symbols)} NIFTY200 symbols.")
    except FileNotFoundError:
        nifty200_symbols = []
        print("[WARN] nifty200_symbols.txt not found. Skipping NIFTY200.")

    # Merge lists (avoid duplicates if a NIFTY50 stock is also in NIFTY200)
    all_symbols = sorted(set(nifty50_symbols + nifty200_symbols))

    if not all_symbols:
        raise SystemExit("[ERROR] No symbols loaded from any list. Aborting.")

    # Sync history for all symbols (full download or incremental update)
    sync_all_history(all_symbols)

    # Keep NIFTY index updated (for regime filters etc.)
    download_nifty_index(DATA_DIR, start="2015-01-01")

    # Download VIX data
    download_vix_data(DATA_DIR, start="2015-01-01")

    # Run quality check on all downloaded files
    print("\n=== DATA QUALITY CHECK ===")
    quality_issues = []
    for sym in all_symbols:
        filepath = get_symbol_filename(sym)
        if os.path.exists(filepath):
            df = pd.read_csv(filepath)
            result = validate_price_data(sym, df, verbose=True)
            if not result["passed"]:
                quality_issues.append(result)
    print(f"\nTotal symbols with issues: {len(quality_issues)}")
    if quality_issues:
        print("Symbols needing review:")
        for r in quality_issues:
            print(f"  {r['symbol']}: {r['issues']}")
    print("=== DONE ===")

    #download_all_sector_indices_from_nse(DATA_DIR, start="2010-01-01")

    # If you ever want a full re-download instead of sync, use:
    # download_all_history(all_symbols)
    # Or for daily updates only:
    # update_all_history(all_symbols)
