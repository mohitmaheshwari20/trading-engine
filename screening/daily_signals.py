import os
import sys
import pandas as pd
from datetime import datetime

SCREENING_DIR   = r"C:\Projects\trading_engine\logs"
SIGNALS_DIR     = os.path.join(SCREENING_DIR, "trend_signals")
UNIVERSE_FILE   = r"C:\Projects\Backtesting System\nifty200_symbols.txt"
POSITIONS_FILE  = os.path.join(SCREENING_DIR, "open_positions.csv")
DATA_DIR        = r"C:\Projects\Backtesting System\data"
INDICATORS_DIR  = r"C:\Projects\trading_engine\data"

sys.path.insert(0, INDICATORS_DIR)
from indicators import TechnicalIndicators

TOTAL_CAPITAL    = 100000
POSITION_SIZE_RS = 5000
MAX_POSITIONS    = 5
STOP_LOSS_PCT    = 0.15
EMA_FAST         = 20
EMA_SLOW         = 50
EMA_LONG         = 200
ADX_PERIOD       = 14
ADX_THRESHOLD    = 20
STRATEGY_NAME    = "EMA20_50_ADX20_EMA200"
MIN_ROWS         = EMA_LONG + ADX_PERIOD + 10


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
        return pd.DataFrame(columns=["Symbol", "Entry_Date", "Entry_Price", "SL_Price", "Shares"])
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


def detect_signal(df, symbol, open_positions, open_position_count):
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

    universe        = load_universe(UNIVERSE_FILE)
    open_positions  = load_open_positions(POSITIONS_FILE)
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
        result = detect_signal(df, symbol, open_positions, effective_open)
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

    print("=" * 55)
    print(f"  Daily Signals - {datetime.today().strftime('%d %B %Y')}")
    print(f"  Capital: Rs {TOTAL_CAPITAL:,} | Positions: {open_count}/{MAX_POSITIONS} | Slots: {slots_available}")
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

    print(f"\n  Output saved to: {output_file}")
    print("=" * 55)

    if not os.path.exists(POSITIONS_FILE):
        print(f"\n  NOTE: open_positions.csv not found.")
        print(f"  Script assumed 0 open positions.")
        print(f"  Create this file after your first paper trade.")


if __name__ == "__main__":
    main()
