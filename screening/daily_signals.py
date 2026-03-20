import os
import sys
import json
import pandas as pd
from datetime import datetime

SCREENING_DIR   = r"C:\Projects\trading_engine\logs"
SIGNALS_DIR     = os.path.join(SCREENING_DIR, "trend_signals")
UNIVERSE_FILE   = r"C:\Projects\Backtesting System\nifty200_symbols.txt"
POSITIONS_FILE  = os.path.join(SCREENING_DIR, "open_positions.csv")
DATA_DIR        = r"C:\Projects\trading_engine\data\Historical Daily Data"
INDICATORS_DIR  = r"C:\Projects\trading_engine\data"
SECTOR_MAP_FILE = r"C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json"
NIFTY_FILE      = r"C:\Projects\trading_engine\data\Historical Daily Data\NIFTY_NS.csv"

sys.path.insert(0, INDICATORS_DIR)
from indicators import TechnicalIndicators

TOTAL_CAPITAL            = 100000
POSITION_SIZE_RS         = 10000
MAX_POSITIONS            = 10
STOP_LOSS_PCT            = 0.15
EMA_FAST                 = 20
EMA_SLOW                 = 50
EMA_LONG                 = 200
ADX_PERIOD               = 14
ADX_THRESHOLD            = 20
STRATEGY_NAME            = "EMA20_50_ADX20_EMA200"
MIN_ROWS                 = EMA_LONG + ADX_PERIOD + 10
MAX_POSITIONS_PER_SECTOR = 2


def symbol_to_filename(symbol):
    return symbol.replace(".", "_") + ".csv"


def load_universe(filepath):
    """Load universe from txt file (one symbol per line) or csv."""
    if filepath.endswith(".txt"):
        with open(filepath, "r") as f:
            return [line.strip() for line in f if line.strip()]
    df = pd.read_csv(filepath)
    return df["Symbol"].tolist()


def load_open_positions(filepath):
    if not os.path.exists(filepath):
        return pd.DataFrame(columns=["Symbol", "Entry_Date", "Entry_Price", "SL_Price", "Shares", "Sector"])
    return pd.read_csv(filepath)


def load_price_data(symbol, data_dir):
    filepath = os.path.join(data_dir, symbol_to_filename(symbol))
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath)
        if len(df) < MIN_ROWS:
            return None
        return df
    except Exception:
        return None


def compute_indicators(df):
    df = df.copy()
    df["EMA_Fast"] = TechnicalIndicators.calculate_ema(df, period=EMA_FAST)
    df["EMA_Slow"] = TechnicalIndicators.calculate_ema(df, period=EMA_SLOW)
    df["EMA_Long"] = TechnicalIndicators.calculate_ema(df, period=EMA_LONG)
    df["ADX"]      = TechnicalIndicators.calculate_adx(df, period=ADX_PERIOD)
    return df


def load_sector_map(filepath):
    """Load sector map JSON, converting RELIANCE.NS keys to RELIANCE_NS format."""
    with open(filepath, "r") as f:
        raw = json.load(f)
    return {k.replace(".", "_"): v for k, v in raw.items()}


def check_macro_filter(nifty_filepath):
    """Load Nifty data, calculate EMA200, return macro filter status."""
    df = pd.read_csv(nifty_filepath)
    close_col = "Adj_Close" if "Adj_Close" in df.columns else "Adj Close"
    df["EMA200"] = df[close_col].ewm(span=200, adjust=False).mean()
    latest      = df.iloc[-1]
    nifty_close = round(float(latest[close_col]), 2)
    ema200      = round(float(latest["EMA200"]), 2)
    return {
        "is_on":       nifty_close > ema200,
        "nifty_close": nifty_close,
        "ema200":      ema200,
    }


def count_sector_positions(open_positions, sector, sector_map):
    """Count how many open positions belong to the given sector."""
    count = 0
    for sym in open_positions["Symbol"].values:
        if sector_map.get(sym.replace(".", "_")) == sector:
            count += 1
    return count


def detect_signal(df, symbol, open_positions, open_position_count, sector_map):
    df = compute_indicators(df)
    df = df.dropna(subset=["EMA_Fast", "EMA_Slow", "EMA_Long", "ADX"]).reset_index(drop=True)
    if len(df) < 2:
        return None

    today       = df.iloc[-1]
    prev        = df.iloc[-2]
    price       = today["Adj Close"]
    in_position = symbol in open_positions["Symbol"].values

    # SELL — bearish crossover
    if in_position:
        bearish_cross = (today["EMA_Fast"] < today["EMA_Slow"]) and (prev["EMA_Fast"] >= prev["EMA_Slow"])
        if bearish_cross:
            return {"Signal": "SELL", "Symbol": symbol, "Entry_Price": round(price, 2),
                    "SL_Price": "-", "Position_Size_Rs": "-", "Shares": "-",
                    "Reason": "EMA Crossover Down"}

    # STOP LOSS
    if in_position:
        pos_row  = open_positions[open_positions["Symbol"] == symbol].iloc[0]
        sl_price = float(pos_row["SL_Price"])
        if today["Low"] <= sl_price:
            return {"Signal": "STOP LOSS", "Symbol": symbol, "Entry_Price": round(sl_price, 2),
                    "SL_Price": round(sl_price, 2), "Position_Size_Rs": "-", "Shares": "-",
                    "Reason": "SL Hit"}

    # BUY — bullish crossover + ADX + EMA200
    if not in_position and open_position_count < MAX_POSITIONS:
        # Gate — Sector cap
        sym_key = symbol.replace(".", "_")
        sector  = sector_map.get(sym_key)
        if sector is not None:
            if count_sector_positions(open_positions, sector, sector_map) >= MAX_POSITIONS_PER_SECTOR:
                return None
        bullish_cross = (today["EMA_Fast"] > today["EMA_Slow"]) and (prev["EMA_Fast"] <= prev["EMA_Slow"])
        adx_ok        = today["ADX"] >= ADX_THRESHOLD
        above_ema200  = today["Adj Close"] > today["EMA_Long"]
        if bullish_cross and adx_ok and above_ema200:
            sl_price = round(price * (1 - STOP_LOSS_PCT), 2)
            shares   = int(POSITION_SIZE_RS / price)
            if shares < 1:
                return None
            return {"Signal": "BUY", "Symbol": symbol, "Entry_Price": round(price, 2),
                    "SL_Price": sl_price, "Position_Size_Rs": POSITION_SIZE_RS,
                    "Shares": shares, "Reason": "EMA Crossover Up + ADX OK + Above EMA200"}
    return None


def main():
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    run_date    = datetime.today().strftime("%Y%m%d")
    output_file = os.path.join(SIGNALS_DIR, f"signals_{run_date}.csv")

    universe       = load_universe(UNIVERSE_FILE)
    open_positions = load_open_positions(POSITIONS_FILE)
    sector_map     = load_sector_map(SECTOR_MAP_FILE)
    macro          = check_macro_filter(NIFTY_FILE)

    # Ensure Sector column exists; back-fill from sector_map and persist
    if "Sector" not in open_positions.columns:
        open_positions["Sector"] = open_positions["Symbol"].apply(
            lambda s: sector_map.get(s.replace(".", "_"), "Unknown")
        )
        if os.path.exists(POSITIONS_FILE):
            open_positions.to_csv(POSITIONS_FILE, index=False)

    # ── HEADER ───────────────────────────────────────────────────────
    print("=" * 55)
    print(f"  Daily Signals - {datetime.today().strftime('%d %B %Y')}")
    print("=" * 55)

    # ── OPEN POSITIONS REVIEW ────────────────────────────────────────
    print(f"\n  OPEN POSITIONS REVIEW ({len(open_positions)} positions)")
    print(f"  {'-' * 45}")
    if len(open_positions) == 0:
        print("  No open positions.")
    else:
        today_dt = datetime.today()
        for _, row in open_positions.iterrows():
            symbol     = row["Symbol"]
            entry_date = str(row["Entry_Date"])
            entry_px   = float(row["Entry_Price"])
            sl_px      = float(row["SL_Price"])
            sector     = row["Sector"] if "Sector" in open_positions.columns else \
                         sector_map.get(symbol.replace(".", "_"), "Unknown")
            try:
                days_held = (today_dt - datetime.strptime(entry_date, "%Y-%m-%d")).days
            except Exception:
                days_held = "?"

            # Determine status
            status = "\u2705 Holding"
            df_pos = load_price_data(symbol, DATA_DIR)
            if df_pos is not None and len(df_pos) >= MIN_ROWS:
                df_ind = compute_indicators(df_pos)
                df_ind = df_ind.dropna(subset=["EMA_Fast", "EMA_Slow", "EMA_Long", "ADX"]).reset_index(drop=True)
                if len(df_ind) >= 2:
                    t = df_ind.iloc[-1]
                    p = df_ind.iloc[-2]
                    bearish_cross = (t["EMA_Fast"] < t["EMA_Slow"]) and (p["EMA_Fast"] >= p["EMA_Slow"])
                    sl_hit        = t["Low"] <= sl_px
                    if bearish_cross:
                        status = "\u26a0\ufe0f  SELL SIGNAL"
                    elif sl_hit:
                        status = "\U0001f534 STOP LOSS HIT"

            print(f"  {symbol:<20} | Entry: {entry_px:>8.2f} | Date: {entry_date} | "
                  f"Days: {str(days_held):>3} | Sector: {str(sector):<22} | SL: {sl_px:>8.2f} | {status}")

    # ── SIGNAL SCANNING ──────────────────────────────────────────────
    open_count      = len(open_positions)
    slots_available = MAX_POSITIONS - open_count
    buys_this_run   = 0

    buy_signals, sell_signals, sl_signals, skipped = [], [], [], []

    for symbol in universe:
        df = load_price_data(symbol, DATA_DIR)
        if df is None:
            skipped.append(symbol)
            continue
        effective_open = open_count + buys_this_run
        result = detect_signal(df, symbol, open_positions, effective_open, sector_map)
        if result is None:
            continue
        result["Strategy"] = STRATEGY_NAME
        if result["Signal"] == "BUY":
            buy_signals.append(result)
            buys_this_run += 1
        elif result["Signal"] == "SELL":
            sell_signals.append(result)
        elif result["Signal"] == "STOP LOSS":
            sl_signals.append(result)

    all_signals = buy_signals + sell_signals + sl_signals
    cols = ["Signal", "Symbol", "Entry_Price", "SL_Price", "Position_Size_Rs", "Shares", "Strategy", "Reason"]
    if all_signals:
        pd.DataFrame(all_signals)[cols].to_csv(output_file, index=False)
    else:
        pd.DataFrame(columns=cols).to_csv(output_file, index=False)

    print(f"\n  Capital: Rs {TOTAL_CAPITAL:,} | Positions: {open_count}/{MAX_POSITIONS} | Slots: {slots_available}")
    print(f"  Universe: {len(universe)} stocks (Nifty 200)")
    print("=" * 55)

    print(f"\n  BUY SIGNALS ({len(buy_signals)})")
    print(f"  {'-' * 50}")
    if buy_signals:
        for s in buy_signals:
            print(f"  {s['Symbol']:<20} | Entry: {s['Entry_Price']:>8} | SL: {s['SL_Price']:>8} | Qty: {s['Shares']:>4} | Rs {s['Position_Size_Rs']:,}")
    else:
        print("  None")

    print(f"\n  SELL SIGNALS ({len(sell_signals)})")
    print(f"  {'-' * 50}")
    if sell_signals:
        for s in sell_signals:
            print(f"  {s['Symbol']:<20} | Exit at market open | Reason: {s['Reason']}")
    else:
        print("  None")

    print(f"\n  STOP LOSS ALERTS ({len(sl_signals)})")
    print(f"  {'-' * 50}")
    if sl_signals:
        for s in sl_signals:
            print(f"  {s['Symbol']:<20} | SL Price: {s['SL_Price']:>8} | Exit immediately")
    else:
        print("  None")

    total_signals   = len(buy_signals) + len(sell_signals) + len(sl_signals)
    no_signal_count = len(universe) - total_signals - len(skipped)
    print(f"\n  No signal : {no_signal_count} stocks")

    if skipped:
        print(f"\n  Skipped (data unavailable): {len(skipped)}")
        for s in skipped:
            print(f"    - {s}")

    # ── SECTOR SUMMARY ───────────────────────────────────────────────
    print(f"\n  SECTOR SUMMARY")
    print(f"  {'-' * 45}")
    sector_counts = {}
    for _, row in open_positions.iterrows():
        sec = row["Sector"] if "Sector" in open_positions.columns else \
              sector_map.get(row["Symbol"].replace(".", "_"), "Unknown")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    if sector_counts:
        for sec, cnt in sorted(sector_counts.items()):
            flag = "  \u26a0\ufe0f  (at cap)" if cnt >= MAX_POSITIONS_PER_SECTOR else ""
            print(f"  {str(sec):<30} : {cnt}{flag}")
    else:
        print("  No open positions.")

    print(f"\n  Output saved to: {output_file}")
    print("=" * 55)

    if not os.path.exists(POSITIONS_FILE):
        print(f"\n  NOTE: open_positions.csv not found.")
        print(f"  Script assumed 0 open positions.")
        print(f"  Create this file after your first paper trade.")


if __name__ == "__main__":
    main()
