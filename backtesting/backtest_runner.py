"""
backtest_runner.py
==================
Strategy 2 Backtesting Framework — Component 2: Master Runner

Orchestrates the full backtesting pipeline across 2017–2025.

ARCHITECTURE:
    Weekly loop:
        1. Slice all data to week end date            (no lookahead)
        2. Run Momentum Ranker on sliced data         (weekly)
        3. Identify Scenario B candidates             (compare to prior week)
        4. Run S/R Detection on each candidate        (weekly, zones held for week)
        Daily loop within week:
        5. Run Entry Signal scan on each candidate    (daily)
        6. If signal fires → Trade Simulator

HOW LIVE MODULES ARE CALLED IN THE BACKTEST:
    momentum_ranker : compute_momentum_ratio(series, ma_days, offset_days)
                      called directly with a sliced pd.Series — bypasses run()
                      which uses datetime.date.today() and is not backtest-safe.

    sr_detection    : analyse_symbol(symbol, data_dir=temp_dir, ...)
                      Sliced CSV written to temp dir before each call.
                      Result returns primary_zone as a nested dict — _extract_sr_zones()
                      unwraps it into (zone_center, zone_low, zone_high, secondary_center).

    entry_signal    : analyse_symbol(symbol, zone_center, zone_low, zone_high,
                      all_zone_centers, data_dir=temp_dir, ...)
                      Function name is analyse_symbol (not run). Sliced CSV +
                      sliced Nifty CSV written to temp dir before each call.

Usage:
    python backtest_runner.py                          # full 2017-2025 run
    python backtest_runner.py --start 2022-01-01       # custom start date
    python backtest_runner.py --pass2                  # also run Pass 2
    python backtest_runner.py --symbol TCS.NS          # single symbol test
    python backtest_runner.py --mock                   # smoke test, no real data

Output:
    C:\\Projects\\trading_engine\\test_results\\
        s2_backtest_trades_pass1.csv
        s2_backtest_trades_pass2.csv    (if --pass2)
        s2_backtest_equity_pass1.csv
        s2_backtest_yearly_pass1.csv
        s2_backtest_report_pass1.txt
        s2_backtest_comparison.txt      (if --pass2)
"""

import os
import sys
import shutil
import argparse
import datetime
import pandas as pd
from typing import Optional

# ─── PATH SETUP ───────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from backtest_data_slicer import (
    slice_to_date, load_price_csv,
    get_trading_weeks, get_trading_days_in_week,
    get_all_trading_dates, load_symbols,
)
from backtest_trade_simulator import (
    simulate_trade_pass1, simulate_trade_pass2,
    TOTAL_CAPITAL, RISK_PER_TRADE,
)
from backtest_analysis import (
    run_analysis, compare_passes, should_run_pass2,
    print_comparison_report,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DATA_DIR          = r"C:\Projects\Backtesting System\data"
SCREENING_DIR     = r"C:\Projects\trading_engine\screening"
SYMBOLS_FILE      = r"C:\Projects\trading_engine\nifty200_symbols.txt"
TEST_RESULTS_DIR  = r"C:\Projects\trading_engine\test_results"
NIFTY_FILE        = "NIFTY_NS.CSV"

BACKTEST_START    = datetime.date(2017, 1, 1)
BACKTEST_END      = datetime.date(2025, 12, 31)
IN_SAMPLE_END     = datetime.date(2024, 12, 31)

MA_DAYS           = 60
TOP_PCT           = 0.10
LOOKBACK_WEEKS    = 4
SR_LOOKBACK_DAYS  = 90
MIN_TOUCHES       = 2
VOL_MULTIPLIER    = 1.2
MAX_STOP_PCT      = 0.06


# ─── MODULE LOADER ────────────────────────────────────────────────────────────

def _import_modules():
    """Load momentum_ranker, sr_detection, entry_signal from SCREENING_DIR."""
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    try:
        ranker = load("momentum_ranker", os.path.join(SCREENING_DIR, "momentum_ranker.py"))
        sr     = load("sr_detection",    os.path.join(SCREENING_DIR, "sr_detection.py"))
        entry  = load("entry_signal",    os.path.join(SCREENING_DIR, "entry_signal.py"))
        return ranker, sr, entry
    except Exception as e:
        print(f"[ERROR] Could not import screening modules: {e}")
        print(f"[ERROR] Ensure modules exist in: {SCREENING_DIR}")
        raise


# ─── TEMP DIRECTORY HELPERS ───────────────────────────────────────────────────

def _write_temp_csv(df: pd.DataFrame, symbol: str, temp_dir: str) -> None:
    """
    Write sliced DataFrame to temp_dir using the filename format that
    sr_detection and entry_signal expect: e.g. TCS_NS.csv
    """
    fname = f"{symbol.replace('.', '_')}.csv"
    df.to_csv(os.path.join(temp_dir, fname), index=False)


def _write_nifty_temp_csv(nifty_df: pd.DataFrame, temp_dir: str) -> None:
    """Write sliced Nifty CSV so entry_signal's market filter can read it."""
    if nifty_df is not None and not nifty_df.empty:
        nifty_df.to_csv(os.path.join(temp_dir, NIFTY_FILE), index=False)


def _extract_sr_zones(sr_result: dict) -> tuple:
    """
    Unwrap sr_detection.analyse_symbol() result.

    The live module returns primary_zone as a NESTED dict:
        { "zone_center": ..., "zone_high": ..., "zone_low": ..., ... }
    not flat keys like sr_result["primary_zone_center"].

    Returns: (zone_center, zone_low, zone_high, secondary_center)
             All None if no valid primary zone.
    """
    primary = sr_result.get("primary_zone")
    if not primary or not isinstance(primary, dict):
        return None, None, None, None

    zone_center = primary.get("zone_center")
    zone_low    = primary.get("zone_low")
    zone_high   = primary.get("zone_high")

    zones = sr_result.get("zones", [])
    secondary_center = zones[1].get("zone_center") if len(zones) >= 2 else None

    return zone_center, zone_low, zone_high, secondary_center


# ─── MOMENTUM RANKING ─────────────────────────────────────────────────────────

def _rank_momentum(
    ranker_mod,
    price_cache: dict,
    week_end: datetime.date,
    ma_days: int   = MA_DAYS,
    top_pct: float = TOP_PCT,
    use_mock: bool = False,
) -> set:
    """
    Rank universe by price/MA ratio and return the top top_pct symbols.

    Live path:  calls ranker_mod.compute_momentum_ratio(series, ma_days, 0)
                directly with a sliced pd.Series — no file I/O, no today's date.
    Mock path:  delegates to ranker_mod.rank_universe() for test purposes.
    """
    if use_mock:
        sliced = {
            sym: slice_to_date(df, week_end)
            for sym, df in price_cache.items()
            if not slice_to_date(df, week_end).empty
        }
        return set(ranker_mod.rank_universe(sliced, week_end, ma_days=ma_days, top_pct=top_pct))

    results = []
    for sym, df in price_cache.items():
        sliced = slice_to_date(df, week_end)
        if len(sliced) < ma_days:
            continue

        close_col = "Adj Close" if "Adj Close" in sliced.columns else "Close"
        if close_col not in sliced.columns:
            continue

        sliced_copy = sliced.copy()
        if not pd.api.types.is_datetime64_any_dtype(sliced_copy["Date"]):
            sliced_copy["Date"] = pd.to_datetime(sliced_copy["Date"])
        series = sliced_copy.set_index("Date")[close_col]

        try:
            r     = ranker_mod.compute_momentum_ratio(series, ma_days, offset_days=0)
            ratio = r.get("ratio")
            if ratio is not None and not pd.isna(ratio):
                results.append({"symbol": sym, "ratio": ratio})
        except Exception:
            continue

    results.sort(key=lambda x: x["ratio"], reverse=True)
    n_top = max(1, int(len(results) * top_pct))
    return set(r["symbol"] for r in results[:n_top])


# ─── MOCK MODULES ─────────────────────────────────────────────────────────────

def _build_mock_modules():
    """
    Lightweight mock objects for smoke testing without real data.
    Method names and return structures match the live module APIs exactly.
    """
    class MockRanker:
        def rank_universe(self, price_data_dict, cutoff_date, ma_days=60, top_pct=0.10):
            results = []
            for sym, df in price_data_dict.items():
                if len(df) < ma_days:
                    continue
                close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
                ma    = df[close_col].rolling(ma_days).mean().iloc[-1]
                price = df[close_col].iloc[-1]
                if pd.isna(ma) or ma == 0:
                    continue
                results.append({"symbol": sym, "ratio": price / ma})
            results.sort(key=lambda x: x["ratio"], reverse=True)
            n_top = max(1, int(len(results) * top_pct))
            return [r["symbol"] for r in results[:n_top]]

    class MockSR:
        def analyse_symbol(self, symbol, data_dir=None, **kwargs):
            import hashlib
            h    = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
            price = 1000.0 + (h % 500)
            atr   = price * 0.015
            zc    = round(price * 0.97, 2)
            zl    = round(zc * 0.99, 2)
            zh    = round(zc * 1.01, 2)
            prox  = abs(price - zc) / atr
            sig   = "BUY" if prox < 1.0 else "ALERT" if prox < 3.0 else "MONITOR"
            pz    = {"zone_center": zc, "zone_low": zl, "zone_high": zh,
                     "touch_count": 3, "proximity": round(prox, 2), "signal": sig}
            return {"symbol": symbol, "current_price": price, "trend": "down",
                    "atr": round(atr, 2), "top_signal": sig,
                    "primary_zone": pz, "zones": [pz], "error": None}

    class MockEntry:
        def analyse_symbol(self, symbol, zone_center, zone_low, zone_high,
                           all_zone_centers, data_dir=None, **kwargs):
            import hashlib
            h = int(hashlib.md5(f"{symbol}{zone_center}".encode()).hexdigest(), 16)
            if h % 5 != 0:
                return {"symbol": symbol, "signal": "NONE", "error": None}
            price = round(zone_center * 1.03, 2)
            stop  = round(zone_low * 0.995, 2)
            t1    = round(price * 1.04, 2)
            t2    = round(price * 1.08, 2)
            if price > 0 and (price - stop) / price > 0.06:
                return {"symbol": symbol, "signal": "NONE", "error": "stop too wide"}
            rr1 = round((t1 - price) / (price - stop), 2) if price != stop else 0
            rr2 = round((t2 - price) / (price - stop), 2) if price != stop else 0
            return {"symbol": symbol, "pattern": "Pin Bar", "signal_date": None,
                    "entry_price": round(price * 1.001, 2), "stop_loss": stop,
                    "target_1": t1, "target_2": t2, "t1_source": "zone",
                    "t2_source": "zone", "rr_ratio_1": rr1, "rr_ratio_2": rr2,
                    "signal": "ENTRY SIGNAL", "error": None}

    return MockRanker(), MockSR(), MockEntry()


# ─── MASTER BACKTEST LOOP ─────────────────────────────────────────────────────

def run_backtest(
    start_date: datetime.date    = BACKTEST_START,
    end_date: datetime.date      = BACKTEST_END,
    symbols_file: str            = SYMBOLS_FILE,
    data_dir: str                = DATA_DIR,
    test_results_dir: str        = TEST_RESULTS_DIR,
    run_pass2: bool              = False,
    symbol_filter: Optional[str] = None,
    use_mock: bool               = False,
    total_capital: float         = TOTAL_CAPITAL,
    risk_pct: float              = RISK_PER_TRADE,
    verbose: bool                = True,
) -> dict:

    os.makedirs(test_results_dir, exist_ok=True)
    temp_dir = os.path.join(test_results_dir, "temp_backtest")
    os.makedirs(temp_dir, exist_ok=True)

    print(f"\n{'=' * 72}")
    print(f"  STRATEGY 2 BACKTEST — VIABILITY TEST")
    print(f"  Period    : {start_date} to {end_date}")
    print(f"  Capital   : INR {total_capital:,.0f}")
    print(f"  Risk/Trade: {risk_pct*100:.1f}% = INR {total_capital*risk_pct:,.0f}")
    print(f"  Mode      : {'MOCK' if use_mock else 'LIVE MODULES'}")
    print(f"{'=' * 72}\n")

    # ── Load modules ─────────────────────────────────────────────────────────
    if use_mock:
        ranker_mod, sr_mod, entry_mod = _build_mock_modules()
    else:
        try:
            ranker_mod, sr_mod, entry_mod = _import_modules()
        except Exception:
            print("[WARNING] Could not load live modules — falling back to mock.")
            ranker_mod, sr_mod, entry_mod = _build_mock_modules()
            use_mock = True

    # ── Load symbols ─────────────────────────────────────────────────────────
    all_symbols = load_symbols(symbols_file)
    if symbol_filter:
        all_symbols = [s for s in all_symbols if s == symbol_filter]
    if not all_symbols:
        print(f"[ERROR] No symbols loaded from {symbols_file}")
        return {}
    if verbose:
        print(f"  Universe : {len(all_symbols)} symbols")

    # ── Pre-load price data ───────────────────────────────────────────────────
    if verbose:
        print(f"  Loading price data...")

    price_cache = {}
    for sym in all_symbols:
        fpath = os.path.join(data_dir, f"{sym.replace('.', '_')}.csv")
        df    = load_price_csv(fpath)
        if not df.empty:
            price_cache[sym] = df

    nifty_df = load_price_csv(os.path.join(data_dir, NIFTY_FILE))
    loaded   = len(price_cache)

    if verbose:
        print(f"  Loaded   : {loaded}/{len(all_symbols)} ({len(all_symbols)-loaded} missing)")

    # ── Calendar ─────────────────────────────────────────────────────────────
    all_trading_dates = get_all_trading_dates(data_dir, list(price_cache.keys()))
    all_trading_dates = [d for d in all_trading_dates if start_date <= d <= end_date]
    weekly_cutoffs    = get_trading_weeks(start_date, end_date)

    if verbose:
        print(f"  Trading days  : {len(all_trading_dates)}")
        print(f"  Weekly cycles : {len(weekly_cutoffs)}\n")

    # ── State ─────────────────────────────────────────────────────────────────
    scenario_b_hist = {}   # symbol → [week_end dates when in top 10%]
    open_trades     = {}   # symbol → exit_date
    all_trades_p1   = []
    all_trades_p2   = []

    # ── Weekly loop ───────────────────────────────────────────────────────────
    for week_idx, week_end in enumerate(weekly_cutoffs):

        if verbose and week_idx % 13 == 0:
            print(f"  [{week_end}] Week {week_idx+1}/{len(weekly_cutoffs)}  "
                  f"Open: {len(open_trades)}  Trades: {len(all_trades_p1)}")

        # Step 1: Momentum ranking
        try:
            current_top10 = _rank_momentum(
                ranker_mod, price_cache, week_end,
                ma_days=MA_DAYS, top_pct=TOP_PCT, use_mock=use_mock
            )
        except Exception as e:
            if verbose:
                print(f"  [WARNING] Ranking failed {week_end}: {e}")
            current_top10 = set()

        # Step 2: Scenario B candidates
        for sym in current_top10:
            scenario_b_hist.setdefault(sym, []).append(week_end)

        lookback_cutoff = week_end - datetime.timedelta(weeks=LOOKBACK_WEEKS)
        scenario_b = {
            sym for sym, weeks in scenario_b_hist.items()
            if sym not in current_top10
            and any(w >= lookback_cutoff for w in weeks)
        }

        if not scenario_b:
            continue

        # Step 3: S/R Detection (weekly — zones fixed for the week)
        sr_zones = {}
        for sym in scenario_b:
            if sym not in price_cache or sym in open_trades:
                continue

            sliced_df = slice_to_date(price_cache[sym], week_end)
            if len(sliced_df) < 30:
                continue

            try:
                if not use_mock:
                    _write_temp_csv(sliced_df, sym, temp_dir)

                sr_result = sr_mod.analyse_symbol(
                    sym,
                    data_dir       = temp_dir,
                    lookback_days  = SR_LOOKBACK_DAYS,
                    min_touches    = MIN_TOUCHES,
                    vol_multiplier = VOL_MULTIPLIER,
                )
                base_signal = sr_result.get("top_signal", "NONE").replace(" [FLIP RISK]", "")
                if base_signal in ("BUY", "ALERT", "MONITOR"):
                    sr_zones[sym] = sr_result
            except Exception:
                continue

        if not sr_zones:
            continue

        # Step 4: Entry signal scan (daily)
        for trade_date in get_trading_days_in_week(week_end, all_trading_dates):

            if not use_mock and not nifty_df.empty:
                _write_nifty_temp_csv(slice_to_date(nifty_df, trade_date), temp_dir)

            for sym, sr in sr_zones.items():
                if sym in open_trades:
                    continue

                daily_df = slice_to_date(price_cache.get(sym, pd.DataFrame()), trade_date)
                if len(daily_df) < 20:
                    continue

                zone_center, zone_low, zone_high, secondary_center = _extract_sr_zones(sr)
                if not zone_center:
                    continue

                all_zone_centers = [zone_center]
                if secondary_center:
                    all_zone_centers.append(secondary_center)

                try:
                    if not use_mock:
                        _write_temp_csv(daily_df, sym, temp_dir)

                    entry_result = entry_mod.analyse_symbol(
                        sym,
                        zone_center,
                        zone_low,
                        zone_high,
                        all_zone_centers,
                        data_dir     = temp_dir,
                        max_stop_pct = MAX_STOP_PCT,
                    )
                except Exception:
                    continue

                if not entry_result or entry_result.get("signal") != "ENTRY SIGNAL":
                    continue

                entry_price = entry_result.get("entry_price")
                stop_loss   = entry_result.get("stop_loss")
                target_1    = entry_result.get("target_1")
                target_2    = entry_result.get("target_2")

                if not all([entry_price, stop_loss, target_1]):
                    continue

                # Step 5: Trade Simulator
                full_df = price_cache.get(sym, pd.DataFrame())

                trade_p1 = simulate_trade_pass1(
                    symbol=sym, entry_date=trade_date,
                    entry_price=float(entry_price), stop_loss=float(stop_loss),
                    target_1=float(target_1), price_df=full_df,
                    total_capital=total_capital, risk_pct=risk_pct,
                )
                trade_p1.update({
                    "pattern":       entry_result.get("pattern"),
                    "sr_signal":     sr.get("top_signal"),
                    "zone_center":   zone_center,
                    "t1_source":     entry_result.get("t1_source"),
                    "t2_source":     entry_result.get("t2_source"),
                    "rr_ratio_1":    entry_result.get("rr_ratio_1"),
                    "rr_ratio_2":    entry_result.get("rr_ratio_2"),
                    "week_of_entry": str(week_end),
                    "period":        "in_sample" if trade_date <= IN_SAMPLE_END else "out_of_sample",
                })
                all_trades_p1.append(trade_p1)

                if trade_p1.get("exit_date"):
                    open_trades[sym] = trade_p1["exit_date"]

                if run_pass2 and target_2:
                    trade_p2 = simulate_trade_pass2(
                        symbol=sym, entry_date=trade_date,
                        entry_price=float(entry_price), stop_loss=float(stop_loss),
                        target_1=float(target_1), target_2=float(target_2),
                        price_df=full_df, total_capital=total_capital, risk_pct=risk_pct,
                    )
                    trade_p2.update({
                        "pattern":       entry_result.get("pattern"),
                        "sr_signal":     sr.get("top_signal"),
                        "zone_center":   zone_center,
                        "week_of_entry": str(week_end),
                        "period":        "in_sample" if trade_date <= IN_SAMPLE_END else "out_of_sample",
                    })
                    all_trades_p2.append(trade_p2)

        # Expire open trades so symbols can trade again
        expired = [
            sym for sym, exit_dt in open_trades.items()
            if isinstance(exit_dt, datetime.date) and exit_dt <= week_end
        ]
        for sym in expired:
            del open_trades[sym]

    # ── Cleanup temp dir ─────────────────────────────────────────────────────
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    # ── Results ──────────────────────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print(f"  Backtest complete.  Pass 1 trades: {len(all_trades_p1)}")
    if run_pass2:
        print(f"  Pass 2 trades: {len(all_trades_p2)}")

    if not all_trades_p1:
        print("  [WARNING] No trades generated. Check data and module connectivity.")
        return {}

    trades_p1_df = pd.DataFrame(all_trades_p1)
    trades_p2_df = pd.DataFrame(all_trades_p2) if all_trades_p2 else pd.DataFrame()

    p1_path = os.path.join(test_results_dir, "s2_backtest_trades_pass1.csv")
    trades_p1_df.to_csv(p1_path, index=False, encoding="utf-8")
    print(f"  Trade log (P1) : {p1_path}")

    if not trades_p2_df.empty:
        p2_path = os.path.join(test_results_dir, "s2_backtest_trades_pass2.csv")
        trades_p2_df.to_csv(p2_path, index=False, encoding="utf-8")
        print(f"  Trade log (P2) : {p2_path}")

    metrics_p1, equity_p1, yearly_p1 = run_analysis(
        trades_p1_df, pass_label="Pass 1 — T1 Only",
        output_dir=test_results_dir, total_capital=total_capital
    )

    if not run_pass2:
        gate_ok, gate_msg = should_run_pass2(trades_p1_df)
        print(f"\n  PASS 2 DECISION GATE:\n  {gate_msg}")
        if gate_ok:
            print("  → Re-run with --pass2 to compare T1-only vs T1+T2")

    if run_pass2 and not trades_p2_df.empty:
        metrics_p2, equity_p2, yearly_p2 = run_analysis(
            trades_p2_df, pass_label="Pass 2 — T1+T2",
            output_dir=test_results_dir, total_capital=total_capital
        )
        comparison = compare_passes(trades_p1_df, trades_p2_df, total_capital)
        print_comparison_report(
            comparison,
            output_file=os.path.join(test_results_dir, "s2_backtest_comparison.txt")
        )

    print(f"\n  Results: {test_results_dir}")
    print(f"{'=' * 72}\n")

    return {
        "trades_p1":  trades_p1_df,
        "trades_p2":  trades_p2_df if not trades_p2_df.empty else None,
        "metrics_p1": metrics_p1,
        "equity_p1":  equity_p1,
        "yearly_p1":  yearly_p1,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Strategy 2 Backtesting Framework — S/R Retest Pullback",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start",    type=str,   default=str(BACKTEST_START))
    parser.add_argument("--end",      type=str,   default=str(BACKTEST_END))
    parser.add_argument("--pass2",    action="store_true")
    parser.add_argument("--symbol",   type=str,   default=None)
    parser.add_argument("--mock",     action="store_true")
    parser.add_argument("--capital",  type=float, default=TOTAL_CAPITAL)
    parser.add_argument("--risk_pct", type=float, default=RISK_PER_TRADE)
    parser.add_argument("--output",   type=str,   default=TEST_RESULTS_DIR)

    args = parser.parse_args()
    run_backtest(
        start_date       = datetime.date.fromisoformat(args.start),
        end_date         = datetime.date.fromisoformat(args.end),
        test_results_dir = args.output,
        run_pass2        = args.pass2,
        symbol_filter    = args.symbol,
        use_mock         = args.mock,
        total_capital    = args.capital,
        risk_pct         = args.risk_pct,
    )


if __name__ == "__main__":
    main()
