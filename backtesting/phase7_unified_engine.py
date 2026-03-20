"""
phase7_unified_engine.py — Phase 7 Unified Backtesting Engine
All-Weather Quant Strategy | NIFTY 200

TWO STRATEGY MODES:
    S1  — EMA20/EMA50 crossover trend-following
    R2  — RSI(2) mean reversion (unchanged from Phase 6.3)

TWO RANKING VERSIONS:
    Version A — S1 signals ranked first (by alpha), then R2 signals (by alpha)
                 An R2 signal with alpha=0.99 will always lose to an S1 with alpha=0.01
    Version B — Pure alpha ranking across all signals regardless of strategy type

ADX NEUTRAL ZONE (20–25): no new entries for either strategy.
Macro filter: Module A VIX + EMA200 gate (unchanged).

OPPORTUNITY COST TRACKING:
    Logs every S1 signal rejected due to full portfolio while R2 positions are open.
    Fields: date, rejected_symbol, rejected_strategy, reason,
            r2_symbol_occupying_slot, r2_entry_date, r2_current_pnl

OUTPUTS (both versions):
    logs/phase7_versionA_trade_log.csv
    logs/phase7_versionA_opportunity_cost.csv
    logs/phase7_versionB_trade_log.csv
    logs/phase7_versionB_opportunity_cost.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.indicators import TechnicalIndicators
from backtesting.all_weather_engine import (
    AWPosition, AWPortfolio,
    compute_adtv, compute_donchian_high, is_circuit_breaker,
    REGIME_ON, REGIME_CAUTION, REGIME_OFF,
    MAX_POSITIONS, MAX_PER_SECTOR,
    EQUITY_RISK_PCT, SIZING_ATR_MULT,
    ADTV_LOOKBACK, ADTV_MIN_VALUE,
    ATR_PERIOD, ADX_PERIOD,
    ATR_INITIAL_STOP_MULT, ATR_OFF_STOP_MULT,
    ATR_CHANDELIER_MULT, ATR_BREAKEVEN_MULT,
    TIME_STOP_DAYS, LIMBO_MAX_DAYS,
    TRANSACTION_COST_PCT, CIRCUIT_SLIPPAGE,
    EXIT_TIME_STOP, EXIT_LIMBO_CAP, EXIT_CIRCUIT,
    EXIT_INITIAL_STOP, EXIT_CHANDELIER,
    EXIT_SMA, EXIT_RSI_OB, EXIT_BACKTEST_END,
)


# ─────────────────────────────────────────────────────────────────────────────
# S1 constants
# ─────────────────────────────────────────────────────────────────────────────

EMA_FAST_PERIOD    = 20
EMA_SLOW_PERIOD    = 50
EMA_LONG_PERIOD    = 200

# ADX gating
ADX_NEUTRAL_LOW    = 20      # inclusive — neutral zone lower bound
ADX_NEUTRAL_HIGH   = 25      # inclusive — neutral zone upper bound
ADX_S1_ENTRY_MIN   = 25      # S1 needs ADX > 25 (strictly above neutral zone)
ADX_R2_ENTRY_MAX   = 20      # R2 needs ADX < 20 (strictly below neutral zone)

# S1 trailing stop
S1_TRAIL_MULT      = 0.85    # exit if close < highest_close × 0.85

# R2 deep dip threshold (Phase 7 spec: 1.0×ATR)
R2_DIP_ATR_MULT    = 1.0
RSI_ENTRY_THRESHOLD = 10
RSI_EXIT_THRESHOLD  = 70
SMA_EXIT_PERIOD     = 20

# S1 exit reasons
EXIT_S1_EMA_CROSS  = 'S1 EMA Bearish Cross'
EXIT_S1_FIXED_STOP = 'S1 Fixed Stop (15%)'
EXIT_S1_MACRO      = 'Macro Exit (OFF)'


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 Unified Engine
# ─────────────────────────────────────────────────────────────────────────────

class Phase7UnifiedEngine:
    """
    Phase 7 Unified Engine.
    Supports Version A (S1 priority) and Version B (pure alpha).
    Each call to run() creates a fresh portfolio and returns independent results.
    """

    def __init__(self, config):
        self.initial_capital = config.get('initial_capital', 100000)
        self.start_date      = pd.to_datetime(config.get('start_date', '2017-01-01'))
        self.end_date        = pd.to_datetime(config.get('end_date',   '2025-12-31'))
        self.debug           = config.get('debug', False)
        self.log_dir         = config.get('log_dir', 'logs')

        self.price_data      = {}
        self._trading_dates  = []

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_price_data(self, loader, symbols, verbose=True):
        """
        Load price data and pre-calculate all required indicators.

        Indicators computed:
            ATR, ADX, EMA200, SMA10, SMA20, RSI2   — existing (R2 pipeline)
            EMA20, EMA50                             — new (S1 pipeline)
        """
        if verbose:
            print(f"Loading price data for {len(symbols)} symbols...")

        loaded = 0
        for symbol in symbols:
            filename = symbol.replace('.', '_')
            try:
                df = loader.load_stock(filename)
                if len(df) >= 200:
                    df['ATR']   = TechnicalIndicators.calculate_atr(df, ATR_PERIOD)
                    df['ADX']   = TechnicalIndicators.calculate_adx(df, ADX_PERIOD)
                    df['EMA200']= TechnicalIndicators.calculate_ema(df, 200)
                    df['SMA10'] = TechnicalIndicators.calculate_sma(df, 10)
                    df['SMA20'] = TechnicalIndicators.calculate_sma(df, 20)
                    df['RSI2']  = TechnicalIndicators.calculate_rsi(df, 2)
                    df['EMA20'] = TechnicalIndicators.calculate_ema(df, EMA_FAST_PERIOD)
                    df['EMA50'] = TechnicalIndicators.calculate_ema(df, EMA_SLOW_PERIOD)
                    self.price_data[symbol] = df
                    loaded += 1
            except Exception:
                continue

        if verbose:
            print(f"  Loaded {loaded}/{len(symbols)} symbols\n")

        return self.price_data

    def get_trading_dates(self):
        """Return sorted list of all trading dates within the backtest window."""
        all_dates = set()
        for df in self.price_data.values():
            dates = df[
                (df['Date'] >= self.start_date) &
                (df['Date'] <= self.end_date)
            ]['Date'].tolist()
            all_dates.update(dates)
        return sorted(all_dates)

    # ── Entry scanning ────────────────────────────────────────────────────────

    def scan_s1_entries(self, date, eligible_symbols, portfolio):
        """
        Scan for S1 (EMA crossover) entry signals.

        Entry conditions (all required):
            1. EMA20 crosses above EMA50 on today (bullish crossover)
            2. ADX > 25 (strictly above neutral zone 20–25)
            3. Close > EMA200
            4. ADTV > ₹10 Cr
            5. Not already in portfolio

        Entry execution: at today's close (same-day, same as original R1).
        Returns signals sorted by alpha descending.
        """
        signals = []

        for e in eligible_symbols:
            symbol = e['symbol']

            if symbol not in self.price_data:
                continue
            if symbol in portfolio.positions:
                continue

            df   = self.price_data[symbol]
            rows = df[df['Date'] <= date]

            if len(rows) < max(EMA_SLOW_PERIOD + 2, EMA_LONG_PERIOD, ADTV_LOOKBACK, ADX_PERIOD * 2):
                continue

            today    = rows.iloc[-1]
            yesterday= rows.iloc[-2]

            close  = float(today['Close'])
            adx    = float(today['ADX'])    if not pd.isna(today['ADX'])    else None
            atr    = float(today['ATR'])    if not pd.isna(today['ATR'])    else None
            ema200 = float(today['EMA200']) if not pd.isna(today['EMA200']) else None
            ema20  = float(today['EMA20'])  if not pd.isna(today['EMA20'])  else None
            ema50  = float(today['EMA50'])  if not pd.isna(today['EMA50'])  else None
            prev_ema20 = float(yesterday['EMA20']) if not pd.isna(yesterday['EMA20']) else None
            prev_ema50 = float(yesterday['EMA50']) if not pd.isna(yesterday['EMA50']) else None

            if any(v is None for v in [adx, atr, ema200, ema20, ema50, prev_ema20, prev_ema50]):
                continue
            if atr == 0:
                continue

            # Condition 1: Bullish EMA crossover today
            bullish_cross = (ema20 > ema50) and (prev_ema20 <= prev_ema50)
            if not bullish_cross:
                continue

            # Condition 2: ADX > 25 (strictly above neutral zone)
            if adx <= ADX_S1_ENTRY_MIN:
                continue

            # Condition 3: Close > EMA200
            if close <= ema200:
                continue

            # Condition 4: ADTV filter
            adtv = compute_adtv(df, date, ADTV_LOOKBACK)
            if adtv is None or adtv < ADTV_MIN_VALUE:
                continue

            signals.append({
                'symbol'       : symbol,
                'sector'       : e['sector'],
                'sector_bucket': e['sector_bucket'],
                'close'        : close,
                'atr'          : atr,
                'adx'          : adx,
                'ema20'        : ema20,
                'ema50'        : ema50,
                'alpha'        : e['alpha'],
                'strategy'     : 'S1',
            })

        signals.sort(key=lambda x: x['alpha'], reverse=True)
        return signals

    def scan_r2_entries(self, date, eligible_symbols, portfolio, pending_r2_exits):
        """
        Scan for R2 (mean reversion) entry signals.

        Entry conditions (all required):
            1. ADX < 20 (strictly below neutral zone)
            2. RSI(2) < 10
            3. Close > EMA200
            4. Close < SMA20 - 1.0×ATR  (Phase 7 spec: deep dip threshold)
            5. ADTV > ₹10 Cr
            6. Not already in portfolio or pending exit

        Entry execution: at next day's open.
        Returns signals sorted by alpha descending.
        """
        signals = []

        for e in eligible_symbols:
            symbol = e['symbol']

            if symbol not in self.price_data:
                continue
            if symbol in portfolio.positions:
                continue
            if symbol in pending_r2_exits:
                continue

            df   = self.price_data[symbol]
            rows = df[df['Date'] <= date]

            min_rows = max(200, ADTV_LOOKBACK, ADX_PERIOD * 2)
            if len(rows) < min_rows:
                continue

            today  = rows.iloc[-1]
            close  = float(today['Close'])
            rsi2   = float(today['RSI2'])   if not pd.isna(today['RSI2'])   else None
            adx    = float(today['ADX'])    if not pd.isna(today['ADX'])    else None
            ema200 = float(today['EMA200']) if not pd.isna(today['EMA200']) else None
            atr    = float(today['ATR'])    if not pd.isna(today['ATR'])    else None
            sma20  = float(today['SMA20'])  if 'SMA20' in today.index and not pd.isna(today['SMA20']) else None

            if any(v is None for v in [rsi2, adx, ema200, atr, sma20]):
                continue
            if atr == 0:
                continue

            # Condition 1: ADX < 20 (strictly below neutral zone)
            if adx >= ADX_R2_ENTRY_MAX:
                continue

            # Condition 2: RSI(2) < 10
            if rsi2 >= RSI_ENTRY_THRESHOLD:
                continue

            # Condition 3: Close > EMA200
            if close <= ema200:
                continue

            # Condition 4: Deep dip — Close < SMA20 - 1.0×ATR
            deep_dip_threshold = sma20 - R2_DIP_ATR_MULT * atr
            if close >= deep_dip_threshold:
                continue

            # Condition 5: ADTV filter
            adtv = compute_adtv(df, date, ADTV_LOOKBACK)
            if adtv is None or adtv < ADTV_MIN_VALUE:
                continue

            signals.append({
                'symbol'       : symbol,
                'sector'       : e['sector'],
                'sector_bucket': e['sector_bucket'],
                'close'        : close,
                'atr'          : atr,
                'rsi2'         : rsi2,
                'adx'          : adx,
                'alpha'        : e['alpha'],
                'strategy'     : 'R2',
            })

        signals.sort(key=lambda x: x['alpha'], reverse=True)
        return signals

    # ── Exit checking ─────────────────────────────────────────────────────────

    def check_exits(self, date, regime, portfolio, deferred_exits,
                    pending_s1_exits, pending_r2_exits):
        """
        Check all open positions for exit conditions.

        Execution order:
            1a. Pending S1 signal exits (flagged yesterday) → execute at today's open
            1b. Pending R2 signal exits (flagged yesterday) → execute at today's open
            2.  Circuit breaker deferred exits → execute at today's open
            3.  Initial Stop → intraday, R2/Upgraded ONLY (S1 explicitly excluded)
            4a. S1 exits — EMA bearish cross OR Low < entry×0.85 → next open
                S1 daily update: highest_close + trade_age only. No stop mechanics.
            4b. R2 exits (SMA20, RSI2>70, Day5, Limbo) → flag, execute next open
            4c. R2 upgrade to Upgraded → activates Chandelier, removes R2 exits
        """
        to_close     = []
        to_flag_exit = []   # (symbol, reason, exit_type) — 'S1' or 'R2'

        executed_pending = set()

        # ── Step 1a: Execute pending S1 signal exits at today's open ─────────
        for symbol, info in list(pending_s1_exits.items()):
            if symbol not in portfolio.positions:
                del pending_s1_exits[symbol]
                continue
            df   = self.price_data.get(symbol)
            rows = df[df['Date'] <= date] if df is not None else pd.DataFrame()
            if len(rows) == 0:
                continue
            exit_price = float(rows.iloc[-1]['Open']) if 'Open' in rows.columns \
                         else float(rows.iloc[-1]['Close'])
            to_close.append((symbol, exit_price, info['reason'], False, False))
            executed_pending.add(symbol)
        for sym in list(executed_pending):
            if sym in pending_s1_exits:
                del pending_s1_exits[sym]

        # ── Step 1b: Execute pending R2 signal exits at today's open ─────────
        for symbol, info in list(pending_r2_exits.items()):
            if symbol in executed_pending:
                continue
            if symbol not in portfolio.positions:
                del pending_r2_exits[symbol]
                continue
            df   = self.price_data.get(symbol)
            rows = df[df['Date'] <= date] if df is not None else pd.DataFrame()
            if len(rows) == 0:
                continue
            exit_price = float(rows.iloc[-1]['Open']) if 'Open' in rows.columns \
                         else float(rows.iloc[-1]['Close'])
            to_close.append((symbol, exit_price, info['reason'], False, False))
            executed_pending.add(symbol)
        for sym in list(executed_pending):
            if sym in pending_r2_exits:
                del pending_r2_exits[sym]

        # ── Step 2: Execute circuit breaker deferred exits ───────────────────
        for symbol, info in list(deferred_exits.items()):
            if symbol in executed_pending:
                continue
            if symbol in portfolio.positions:
                to_close.append((symbol, info['price'], EXIT_CIRCUIT, True, True))
        deferred_exits.clear()

        # ── Steps 3–4: Check each open position ──────────────────────────────
        for symbol, pos in list(portfolio.positions.items()):
            if symbol in executed_pending:
                continue
            if symbol in [t[0] for t in to_close]:
                continue
            if symbol not in self.price_data:
                continue

            df   = self.price_data[symbol]
            rows = df[df['Date'] <= date]
            if len(rows) < 2:
                continue

            today     = rows.iloc[-1]
            yesterday = rows.iloc[-2]
            close  = float(today['Close'])
            low    = float(today['Low'])
            atr    = float(today['ATR'])    if not pd.isna(today['ATR'])    else pos.atr_at_entry

            # ── Daily state update ────────────────────────────────────────────
            if pos.regime == 'S1':
                # S1: track highest close and trade_age ONLY.
                # No stop mechanics: no OFF tightening, no Chandelier, no Breakeven.
                # S1 exits are purely signal-based (EMA cross + 0.85 trailing).
                pos.trade_age += 1
                if close > pos.highest_close_since_entry:
                    pos.highest_close_since_entry = close
            else:
                pos.update_daily(close, atr, regime)

            # ── R2 Upgrade Check ──────────────────────────────────────────────
            if pos.regime == 'R2':
                adx = float(today['ADX']) if not pd.isna(today['ADX']) else 0
                dc_high = compute_donchian_high(df, date)
                if adx > ADX_R2_ENTRY_MAX and dc_high is not None and close >= dc_high:
                    pos.regime = 'Upgraded'
                    chandelier  = pos.highest_close_since_entry - ATR_CHANDELIER_MULT * atr
                    pos.chandelier_stop = chandelier
                    pos.stop_loss       = max(pos.stop_loss, chandelier)
                    bp_trigger = pos.entry_price + ATR_BREAKEVEN_MULT * pos.atr_at_entry
                    if close >= bp_trigger and not pos.breakeven_hit:
                        pos.breakeven_hit = True
                        pos.stop_loss     = max(pos.stop_loss, pos.entry_price)
                    if symbol in pending_r2_exits:
                        del pending_r2_exits[symbol]
                    if self.debug:
                        print(f"  UPGRADE {date.date()} | {symbol:20} | "
                              f"ADX={adx:.1f} Close={close:.2f} >= 20dHigh={dc_high:.2f}")
                    continue

            # ── Circuit breaker ───────────────────────────────────────────────
            if is_circuit_breaker(df, date):
                df_future = df[df['Date'] > date]
                if len(df_future) > 0:
                    next_row = df_future.iloc[0]
                    slippage_price = float(next_row['Open']) * (1 - CIRCUIT_SLIPPAGE)
                    deferred_exits[symbol] = {
                        'price' : slippage_price,
                        'date'  : next_row['Date'],
                        'reason': EXIT_CIRCUIT,
                    }
                continue

            # ── Step 3: Initial Stop — INTRADAY (R2/Upgraded only) ───────────
            # S1 positions are explicitly excluded from intraday stop execution.
            # S1 fixed stop (Low < entry×0.85) is checked in Step 4a → next open.
            if pos.regime != 'S1':
                hit, exit_price, reason = pos.check_stop_hit(low, close)
                if hit:
                    to_close.append((symbol, exit_price, reason, False, False))
                    continue

            # ── Step 4a: S1 exit conditions ───────────────────────────────────
            if pos.regime == 'S1':
                ema20      = float(today['EMA20'])     if not pd.isna(today['EMA20'])     else None
                ema50      = float(today['EMA50'])     if not pd.isna(today['EMA50'])     else None
                prev_ema20 = float(yesterday['EMA20']) if not pd.isna(yesterday['EMA20']) else None
                prev_ema50 = float(yesterday['EMA50']) if not pd.isna(yesterday['EMA50']) else None

                # Primary: EMA20 crosses below EMA50 (bearish crossover)
                if all(v is not None for v in [ema20, ema50, prev_ema20, prev_ema50]):
                    bearish_cross = (ema20 < ema50) and (prev_ema20 >= prev_ema50)
                    if bearish_cross:
                        to_flag_exit.append((symbol, EXIT_S1_EMA_CROSS, 'S1'))
                        if self.debug:
                            print(f"  FLAG S1 EXIT {date.date()} | {symbol} | "
                                  f"EMA bearish cross → next open")
                        continue

                # Secondary: Fixed stop — intraday Low < entry_price × 0.85
                fixed_stop = pos.entry_price * 0.85
                if low < fixed_stop:
                    to_flag_exit.append((symbol, EXIT_S1_FIXED_STOP, 'S1'))
                    if self.debug:
                        print(f"  FLAG S1 EXIT {date.date()} | {symbol} | "
                              f"Fixed stop (Low={low:.2f} < {fixed_stop:.2f}) → next open")
                    continue

            # ── Step 4b: R2 exits (only for R2, not Upgraded) ─────────────────
            elif pos.regime == 'R2':

                # Day 5 survival filter
                action, result = pos.check_day5_filter(close)
                if action is True and result == 'kill':
                    to_flag_exit.append((symbol, EXIT_TIME_STOP, 'R2'))
                    continue
                elif action is False and result == 'survive':
                    pos.in_limbo = True
                    if symbol in pending_r2_exits:
                        del pending_r2_exits[symbol]
                    if self.debug:
                        print(f"  LIMBO {date.date()} | {symbol:20} | "
                              f"Day 5 profit ✓ → SMA/RSI exits deactivated")
                    continue

                # Day 20 hard cap (Limbo)
                if pos.in_limbo and pos.check_limbo_cap():
                    to_flag_exit.append((symbol, EXIT_LIMBO_CAP, 'R2'))
                    continue

                # R2 signal exits — only if not in Limbo
                if not pos.in_limbo:
                    sma20 = float(today['SMA20']) if 'SMA20' in today.index and \
                            not pd.isna(today['SMA20']) else None
                    rsi2  = float(today['RSI2'])  if not pd.isna(today['RSI2']) else None

                    if sma20 is not None and close > sma20:
                        to_flag_exit.append((symbol, EXIT_SMA, 'R2'))
                        continue
                    if rsi2 is not None and rsi2 > RSI_EXIT_THRESHOLD:
                        to_flag_exit.append((symbol, EXIT_RSI_OB, 'R2'))
                        continue

        # Execute same-day closes
        for symbol, price, reason, deferred, slippage in to_close:
            portfolio.close_position(
                symbol, price, date, reason,
                deferred=deferred, slippage_applied=slippage
            )

        # Flag next-open exits
        for symbol, reason, exit_type in to_flag_exit:
            if exit_type == 'S1':
                pending_s1_exits[symbol] = {'reason': reason, 'flag_date': date}
            else:
                pending_r2_exits[symbol] = {'reason': reason, 'flag_date': date}
            if self.debug:
                print(f"  FLAG EXIT {date.date()} | {symbol} | "
                      f"[{exit_type}] {reason} → next open")

    # ── Entry execution ───────────────────────────────────────────────────────

    def execute_combined_entries(self, s1_signals, r2_signals, date,
                                 size_multiplier, portfolio, version,
                                 opportunity_cost_log, allocation_log=None):
        """
        Execute combined S1 + R2 entries.

        Version A: S1 signals first (by alpha), then R2 signals (by alpha)
                   — S1 always wins any slot over R2 regardless of alpha
        Version B: Pure alpha ranking across all signals

        S1 entries: today's close (immediate).
        R2 entries: next day's open.

        Logs opportunity cost when an S1 signal is rejected while R2
        positions are open.

        allocation_log: if provided (Version B only), records per-signal
        outcomes for the diagnostic (who competed, who won, why).
        """
        if version == 'A':
            # S1 first (sorted by alpha), then R2 (sorted by alpha)
            # Never interleave — all S1 before any R2
            merged = [('S1', s) for s in s1_signals] + \
                     [('R2', s) for s in r2_signals]
        else:
            # Version B: pure alpha — all signals mixed and sorted by alpha
            all_signals = [('S1', s) for s in s1_signals] + \
                          [('R2', s) for s in r2_signals]
            merged = sorted(all_signals, key=lambda x: x[1]['alpha'], reverse=True)

        # For Version B diagnostic: only log days where BOTH strategies fired
        log_this_day = (allocation_log is not None and
                        bool(s1_signals) and bool(r2_signals))
        slots_before = MAX_POSITIONS - len(portfolio.positions)

        for strategy_tag, sig in merged:
            symbol        = sig['symbol']
            sector        = sig['sector']
            sector_bucket = sig['sector_bucket']
            atr           = sig['atr']

            if symbol in portfolio.positions:
                if log_this_day:
                    allocation_log.append({
                        'date': date.date(), 'strategy': strategy_tag,
                        'symbol': symbol, 'alpha': round(sig['alpha'], 5),
                        'slots_available': slots_before,
                        'outcome': 'SKIP', 'reason': 'Already in portfolio',
                    })
                continue

            can_open, reason = portfolio.can_open_position(sector, sector_bucket)

            if not can_open:
                if log_this_day:
                    allocation_log.append({
                        'date': date.date(), 'strategy': strategy_tag,
                        'symbol': symbol, 'alpha': round(sig['alpha'], 5),
                        'slots_available': slots_before,
                        'outcome': 'REJECTED', 'reason': reason,
                    })
                # Opportunity cost: S1 rejected while R2 positions are open
                if strategy_tag == 'S1':
                    r2_positions = [
                        (sym, pos) for sym, pos in portfolio.positions.items()
                        if pos.regime == 'R2'
                    ]
                    if r2_positions:
                        # Pick the R2 position with the worst current P&L
                        def r2_pnl(item):
                            sym, pos = item
                            df = self.price_data.get(sym)
                            if df is None:
                                return 0.0
                            rows = df[df['Date'] <= date]
                            if len(rows) == 0:
                                return 0.0
                            curr_price = float(rows.iloc[-1]['Close'])
                            return pos.get_profit_pct(curr_price)

                        r2_positions.sort(key=r2_pnl)
                        worst_sym, worst_pos = r2_positions[0]

                        df_r2 = self.price_data.get(worst_sym)
                        rows_r2 = df_r2[df_r2['Date'] <= date] if df_r2 is not None \
                                  else pd.DataFrame()
                        r2_curr_price = float(rows_r2.iloc[-1]['Close']) \
                                        if len(rows_r2) > 0 else worst_pos.entry_price
                        r2_pnl_val = worst_pos.get_profit(r2_curr_price)

                        opportunity_cost_log.append({
                            'date'                  : date.date(),
                            'rejected_symbol'       : symbol,
                            'rejected_strategy'     : 'S1',
                            'reason'                : reason,
                            'r2_symbol_occupying_slot': worst_sym,
                            'r2_entry_date'         : worst_pos.entry_date.date()
                                                       if hasattr(worst_pos.entry_date, 'date')
                                                       else worst_pos.entry_date,
                            'r2_current_pnl'        : round(r2_pnl_val, 2),
                        })

                if self.debug:
                    print(f"  SKIP {symbol} [{strategy_tag}] — {reason}")
                continue

            if strategy_tag == 'S1':
                # S1: enter at today's close
                close  = sig['close']
                equity = portfolio.cash + sum(
                    p.get_current_value(close)
                    for p in portfolio.positions.values()
                )
                # Flat 10% of portfolio equity per position
                qty = int(equity * 0.10 / close)
                if qty <= 0:
                    continue
                total_cost = qty * close * (1 + TRANSACTION_COST_PCT)
                if total_cost > portfolio.cash:
                    continue
                # S1 has no initial stop — exits are signal-based only.
                # Set to 0 so AWPosition.check_stop_hit() can never fire.
                initial_stop = 0.0
                pos = AWPosition(
                    symbol          = symbol,
                    shares          = qty,
                    entry_price     = close,
                    entry_date      = date,
                    atr_at_entry    = atr,
                    initial_stop    = initial_stop,
                    sector          = sector,
                    sector_bucket   = sector_bucket,
                    size_multiplier = size_multiplier,
                    regime          = 'S1',
                )
                portfolio.open_position(pos, date)
                if log_this_day:
                    allocation_log.append({
                        'date': date.date(), 'strategy': 'S1',
                        'symbol': symbol, 'alpha': round(sig['alpha'], 5),
                        'slots_available': slots_before,
                        'outcome': 'ALLOCATED', 'reason': 'S1 at today close',
                    })
                if self.debug:
                    print(f"  S1 ENTRY {date.date()} | {symbol:20} | "
                          f"Close: ₹{close:.2f} | ADX: {sig['adx']:.1f} | "
                          f"EMA20={sig['ema20']:.2f} EMA50={sig['ema50']:.2f}")

            else:
                # R2: enter at next day's open
                df        = self.price_data[symbol]
                df_future = df[df['Date'] > date]
                if len(df_future) == 0:
                    continue
                next_row    = df_future.iloc[0]
                entry_price = float(next_row['Open'])
                entry_date  = next_row['Date']
                equity = portfolio.cash + sum(
                    p.get_current_value(entry_price)
                    for p in portfolio.positions.values()
                )
                risk_budget  = equity * EQUITY_RISK_PCT * size_multiplier
                qty          = int(risk_budget / (SIZING_ATR_MULT * atr))
                if qty <= 0:
                    continue
                total_cost = qty * entry_price * (1 + TRANSACTION_COST_PCT)
                if total_cost > portfolio.cash:
                    continue
                initial_stop = entry_price - ATR_INITIAL_STOP_MULT * atr
                pos = AWPosition(
                    symbol          = symbol,
                    shares          = qty,
                    entry_price     = entry_price,
                    entry_date      = entry_date,
                    atr_at_entry    = atr,
                    initial_stop    = initial_stop,
                    sector          = sector,
                    sector_bucket   = sector_bucket,
                    size_multiplier = size_multiplier,
                    regime          = 'R2',
                )
                portfolio.open_position(pos, entry_date)
                if log_this_day:
                    allocation_log.append({
                        'date': date.date(), 'strategy': 'R2',
                        'symbol': symbol, 'alpha': round(sig['alpha'], 5),
                        'slots_available': slots_before,
                        'outcome': 'ALLOCATED', 'reason': 'R2 at next open',
                    })
                if self.debug:
                    print(f"  R2 ENTRY {entry_date.date()} | {symbol:20} | "
                          f"Open: ₹{entry_price:.2f} | RSI2: {sig['rsi2']:.1f} | "
                          f"ATR: {atr:.2f}")

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self, regime_classifier, sector_filter, version='A', verbose=True):
        """
        Run the full backtest for the specified version.

        Version A: S1 signals ranked first (all S1 before any R2)
        Version B: Pure alpha ranking across all signals

        Returns dict with results, trade log, opportunity cost log.
        """
        assert version in ('A', 'B'), "version must be 'A' or 'B'"

        # Fresh state for each run
        portfolio         = AWPortfolio(self.initial_capital, debug=self.debug)
        deferred_exits    = {}
        pending_s1_exits  = {}
        pending_r2_exits  = {}
        opportunity_cost  = []
        allocation_log    = [] if version == 'B' else None

        print("=" * 70)
        print(f"PHASE 7 UNIFIED ENGINE — VERSION {version}")
        if version == 'A':
            print("  Ranking: S1 priority over R2 (all S1 before any R2)")
        else:
            print("  Ranking: Pure alpha across all signals")
        print("=" * 70)
        print(f"Period   : {self.start_date.date()} to {self.end_date.date()}")
        print(f"Capital  : ₹{self.initial_capital:,.0f}")
        print(f"Universe : {len(self.price_data)} stocks loaded\n")

        trading_dates = self.get_trading_dates()
        print(f"Trading days : {len(trading_dates)}")
        print(f"Processing...\n")

        progress_interval = max(len(trading_dates) // 10, 1)
        prev_regime = None

        for i, date in enumerate(trading_dates, 1):

            # Module A: market regime
            regime    = regime_classifier.get_regime(date)
            size_mult = regime_classifier.get_size_multiplier(date)

            if regime is None:
                portfolio.record_equity(date, self.price_data)
                continue

            # Check exits first
            self.check_exits(
                date, regime, portfolio,
                deferred_exits, pending_s1_exits, pending_r2_exits
            )

            # Macro exit: regime just switched to OFF — flag all open S1 positions
            if regime == REGIME_OFF and prev_regime != REGIME_OFF:
                for symbol, pos in list(portfolio.positions.items()):
                    if pos.regime == 'S1' and symbol not in pending_s1_exits:
                        pending_s1_exits[symbol] = {
                            'reason'   : EXIT_S1_MACRO,
                            'flag_date': date,
                        }
                        if self.debug:
                            print(f"  MACRO EXIT {date.date()} | {symbol} | "
                                  f"Regime→OFF → next open")

            prev_regime = regime

            # New entries only in ON or CAUTION
            if regime in (REGIME_ON, REGIME_CAUTION):
                eligible = sector_filter.get_eligible_symbols(date)

                s1_signals = self.scan_s1_entries(date, eligible, portfolio)
                r2_signals = self.scan_r2_entries(
                    date, eligible, portfolio, pending_r2_exits
                )

                if s1_signals or r2_signals:
                    self.execute_combined_entries(
                        s1_signals, r2_signals, date, size_mult,
                        portfolio, version, opportunity_cost,
                        allocation_log=allocation_log
                    )

            portfolio.record_equity(date, self.price_data)

            if verbose and i % progress_interval == 0:
                pct   = i / len(trading_dates) * 100
                total = portfolio.equity_curve[-1]
                n_s1  = sum(1 for p in portfolio.positions.values() if p.regime == 'S1')
                n_r2  = sum(1 for p in portfolio.positions.values() if p.regime in ('R2', 'Upgraded'))
                print(f"  {pct:.0f}% | {date.date()} | "
                      f"Equity: ₹{total:,.0f} | "
                      f"Pos: {len(portfolio.positions)} (S1={n_s1} R2={n_r2}) | "
                      f"Regime: {regime}")

        # Close remaining positions at end
        print("\nClosing remaining open positions...")
        for symbol in list(portfolio.positions.keys()):
            if symbol in self.price_data:
                df    = self.price_data[symbol]
                rows  = df[df['Date'] <= self.end_date]
                price = float(rows.iloc[-1]['Close']) if len(rows) > 0 else \
                        portfolio.positions[symbol].entry_price
            else:
                price = portfolio.positions[symbol].entry_price
            portfolio.close_position(
                symbol, price, self.end_date, EXIT_BACKTEST_END
            )

        end_count = sum(1 for t in portfolio.closed_trades
                        if t['exit_reason'] == EXIT_BACKTEST_END)
        print(f"Closed {end_count} positions at end\n")

        results = self._calculate_results(portfolio, opportunity_cost, version)
        results['allocation_log'] = allocation_log or []
        return results

    # ── Results ───────────────────────────────────────────────────────────────

    def _compute_max_drawdown(self, equity_curve):
        if not equity_curve:
            return 0
        peak   = equity_curve[0]
        max_dd = 0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _compute_sharpe(self, equity_curve):
        if len(equity_curve) < 2:
            return 0
        returns = pd.Series(equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0
        return float((returns.mean() / returns.std()) * np.sqrt(252))

    def _compute_strategy_metrics(self, trades):
        """Compute win rate and profit factor for a subset of trades."""
        if not trades:
            return {'count': 0, 'win_rate': 0, 'profit_factor': 0,
                    'avg_pnl_pct': 0}
        winners    = [t for t in trades if t['profit'] > 0]
        losers     = [t for t in trades if t['profit'] <= 0]
        win_rate   = len(winners) / len(trades) * 100
        gross_win  = sum(t['profit'] for t in winners)
        gross_loss = abs(sum(t['profit'] for t in losers))
        pf         = gross_win / gross_loss if gross_loss > 0 else 0
        avg_pnl    = np.mean([t['profit_pct'] for t in trades]) if trades else 0
        return {
            'count'        : len(trades),
            'win_rate'     : round(win_rate, 2),
            'profit_factor': round(pf, 2),
            'avg_pnl_pct'  : round(avg_pnl, 2),
        }

    def _calculate_results(self, portfolio, opportunity_cost_log, version):
        trades  = portfolio.closed_trades
        initial = self.initial_capital
        final   = portfolio.equity_curve[-1] if portfolio.equity_curve else initial

        total_ret  = ((final - initial) / initial) * 100
        years      = (self.end_date - self.start_date).days / 365.25
        annual_ret = ((1 + total_ret / 100) ** (1 / years) - 1) * 100 if years > 0 else 0

        winners    = [t for t in trades if t['profit'] > 0]
        losers     = [t for t in trades if t['profit'] <= 0]
        win_rate   = len(winners) / len(trades) * 100 if trades else 0
        gross_win  = sum(t['profit'] for t in winners)
        gross_loss = abs(sum(t['profit'] for t in losers))
        pf         = gross_win / gross_loss if gross_loss > 0 else 0
        max_dd     = self._compute_max_drawdown(portfolio.equity_curve)
        sharpe     = self._compute_sharpe(portfolio.equity_curve)

        s1_trades  = [t for t in trades if t['regime'] == 'S1']
        r2_trades  = [t for t in trades if t['regime'] in ('R2', 'Upgraded')]
        s1_metrics = self._compute_strategy_metrics(s1_trades)
        r2_metrics = self._compute_strategy_metrics(r2_trades)

        n_blocked  = len(opportunity_cost_log)
        blocked_pnl_avg = 0  # forward P&L of blocked S1 signals

        return {
            'version'         : version,
            'summary': {
                'initial_capital'   : initial,
                'final_capital'     : final,
                'total_return_pct'  : round(total_ret, 2),
                'annual_return_pct' : round(annual_ret, 2),
                'max_drawdown_pct'  : round(max_dd, 2),
                'sharpe_ratio'      : round(sharpe, 3),
                'total_trades'      : len(trades),
                'win_rate_pct'      : round(win_rate, 2),
                'profit_factor'     : round(pf, 2),
                'transaction_costs' : round(portfolio.total_costs, 2),
            },
            's1_metrics'      : s1_metrics,
            'r2_metrics'      : r2_metrics,
            'opportunity_cost': {
                'n_blocked'         : n_blocked,
                'blocked_pnl_avg'   : round(blocked_pnl_avg, 2),
                'log'               : opportunity_cost_log,
            },
            'equity_curve'    : portfolio.equity_curve,
            'equity_dates'    : portfolio.equity_dates,
            'closed_trades'   : trades,
        }

    # ── Results printing ──────────────────────────────────────────────────────

    def print_results(self, results):
        v  = results['version']
        s  = results['summary']
        s1 = results['s1_metrics']
        r2 = results['r2_metrics']
        oc = results['opportunity_cost']

        print("\n" + "=" * 70)
        print(f"PHASE 7 UNIFIED ENGINE — VERSION {v} RESULTS")
        if v == 'A':
            print("  Ranking: S1 priority over R2")
        else:
            print("  Ranking: Pure alpha (all signals mixed)")
        print("=" * 70)

        print("\nRETURNS")
        print("-" * 70)
        print(f"Initial Capital      : ₹{s['initial_capital']:>12,.0f}")
        print(f"Final Capital        : ₹{s['final_capital']:>12,.0f}")
        print(f"Total Return         : {s['total_return_pct']:>+8.2f}%")
        print(f"Annual Return        : {s['annual_return_pct']:>+8.2f}%")
        print(f"Max Drawdown         : {s['max_drawdown_pct']:>8.2f}%")
        print(f"Sharpe Ratio         : {s['sharpe_ratio']:>8.3f}  (primary comparison)")
        print(f"Transaction Costs    : ₹{s['transaction_costs']:>12,.0f}")

        print("\nOVERALL TRADE STATISTICS")
        print("-" * 70)
        print(f"Total Trades         : {s['total_trades']:>8}")
        print(f"Win Rate             : {s['win_rate_pct']:>8.2f}%")
        print(f"Profit Factor        : {s['profit_factor']:>8.2f}")

        print("\nS1 (EMA CROSSOVER) BREAKDOWN")
        print("-" * 70)
        print(f"S1 Trades            : {s1['count']:>8}")
        print(f"S1 Win Rate          : {s1['win_rate']:>8.2f}%")
        print(f"S1 Profit Factor     : {s1['profit_factor']:>8.2f}")
        print(f"S1 Avg P&L           : {s1['avg_pnl_pct']:>+8.2f}%")

        print("\nR2 (MEAN REVERSION) BREAKDOWN")
        print("-" * 70)
        print(f"R2 Trades            : {r2['count']:>8}")
        print(f"R2 Win Rate          : {r2['win_rate']:>8.2f}%")
        print(f"R2 Profit Factor     : {r2['profit_factor']:>8.2f}")
        print(f"R2 Avg P&L           : {r2['avg_pnl_pct']:>+8.2f}%")

        print("\nOPPORTUNITY COST (S1 blocked by R2)")
        print("-" * 70)
        print(f"S1 Signals Blocked   : {oc['n_blocked']:>8}")

        trades = results['closed_trades']
        s1_exits = {}
        for t in trades:
            if t['regime'] == 'S1':
                reason = t['exit_reason']
                s1_exits[reason] = s1_exits.get(reason, 0) + 1

        if s1_exits:
            print("\nS1 EXIT REASON BREAKDOWN")
            print("-" * 70)
            for reason, count in sorted(s1_exits.items(), key=lambda x: -x[1]):
                print(f"  {reason:<35}: {count:4}")

        r2_all = [t for t in trades if t['regime'] in ('R2', 'Upgraded')]
        ts_exits  = [t for t in r2_all if t['exit_reason'] == EXIT_TIME_STOP]
        lc_exits  = [t for t in r2_all if t['exit_reason'] == EXIT_LIMBO_CAP]
        upg_trades= [t for t in trades if t['regime'] == 'Upgraded']

        print("\nR2 BREAKDOWN DETAIL")
        print("-" * 70)
        print(f"  R2 (mean reversion)    : {len([t for t in trades if t['regime']=='R2']):4} trades")
        print(f"  — Day-5 Kill           : {len(ts_exits):4} trades")
        print(f"  — Limbo Cap (Day 30)   : {len(lc_exits):4} trades")
        print(f"  Upgraded (R2→R1)       : {len(upg_trades):4} trades")

        print("\n" + "=" * 70)

    # ── Diagnostic: Version B slot-competition analysis ───────────────────────

    def run_diagnostic(self, results_b):
        """
        Task 2 diagnostic: find all days where both S1 and R2 signals
        existed simultaneously in Version B.

        For each such day prints every signal in ranked order with:
            date | strategy | symbol | alpha | outcome | reason

        Then checks if ANY R2 signal ever beat an S1 signal on alpha
        and won a slot. If yes, Version B differs from A. If no, they
        are structurally identical.
        """
        log = results_b.get('allocation_log', [])
        if not log:
            print("\nDIAGNOSTIC: No allocation log available (run Version B first).")
            return

        df = pd.DataFrame(log)

        # Group by date — find dates that have BOTH S1 and R2 signals
        dates_with_s1 = set(df[df['strategy'] == 'S1']['date'].unique())
        dates_with_r2 = set(df[df['strategy'] == 'R2']['date'].unique())
        contested_dates = sorted(dates_with_s1 & dates_with_r2)

        print("\n" + "=" * 70)
        print("DIAGNOSTIC: Version B — Days with both S1 and R2 signals")
        print("=" * 70)
        print(f"Total contested dates: {len(contested_dates)}\n")

        r2_beat_s1_count = 0
        r2_beat_s1_examples = []

        for d in contested_dates:
            day_df = df[df['date'] == d].reset_index(drop=True)

            print(f"\n{d}")
            print(f"  {'Rank':<5} {'Strat':<5} {'Symbol':<25} {'Alpha':>10} {'Outcome':<12} {'Reason'}")
            print(f"  {'-'*4} {'-'*5} {'-'*25} {'-'*10} {'-'*12} {'-'*20}")
            for rank, row in day_df.iterrows():
                print(f"  {rank+1:<5} {row['strategy']:<5} {row['symbol']:<25} "
                      f"{row['alpha']:>10.5f} {row['outcome']:<12} {row['reason']}")

            # Check if an R2 ALLOCATED signal has higher alpha than any S1 signal on this day
            s1_alphas    = day_df[day_df['strategy'] == 'S1']['alpha'].tolist()
            r2_allocated = day_df[(day_df['strategy'] == 'R2') &
                                  (day_df['outcome'] == 'ALLOCATED')]

            for _, row in r2_allocated.iterrows():
                if s1_alphas and row['alpha'] > max(s1_alphas):
                    r2_beat_s1_count += 1
                    r2_beat_s1_examples.append({
                        'date': d, 'r2_symbol': row['symbol'],
                        'r2_alpha': row['alpha'],
                        'best_s1_alpha': max(s1_alphas),
                    })

        print("\n" + "=" * 70)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 70)
        if r2_beat_s1_count > 0:
            print(f"\n  R2 beat S1 on alpha AND got the slot: {r2_beat_s1_count} case(s)")
            print("  => Version B DIFFERS from Version A (pure alpha overrode S1 priority)")
            print("\n  Examples:")
            for ex in r2_beat_s1_examples[:5]:
                print(f"    {ex['date']} | R2 {ex['r2_symbol']} alpha={ex['r2_alpha']:.5f} "
                      f"> best S1 alpha={ex['best_s1_alpha']:.5f}")
        else:
            print(f"\n  R2 never beat S1 on alpha on any contested day.")
            print("  => Version B is STRUCTURALLY IDENTICAL to Version A.")
            print("     S1 signals always carry higher sector-adjusted alpha than R2.")
        print("=" * 70)

    # ── Save outputs ──────────────────────────────────────────────────────────

    def save_outputs(self, results, version=None, output_prefix=None):
        """Save trade log and opportunity cost log for the given version."""
        v = version or results['version']
        prefix = output_prefix or f'phase7_version{v}'
        log_dir = Path(self.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Trade log
        if results['closed_trades']:
            trade_df = pd.DataFrame(results['closed_trades'])
            trade_path = log_dir / f'{prefix}_trade_log.csv'
            trade_df.to_csv(trade_path, index=False)
            print(f"Trade log saved     : {trade_path} ({len(trade_df)} trades)")

        # Monthly equity curve
        if results['equity_curve'] and results['equity_dates']:
            eq_df = pd.DataFrame({
                'date': results['equity_dates'],
                'portfolio_value': results['equity_curve'],
            })
            eq_df['date'] = pd.to_datetime(eq_df['date'])
            monthly = eq_df.resample('ME', on='date').last().reset_index()
            monthly_path = log_dir / f'{prefix}_monthly_equity.csv'
            monthly.to_csv(monthly_path, index=False)
            print(f"Monthly equity saved: {monthly_path} ({len(monthly)} rows)")

            # Daily equity curve
            daily = eq_df.copy()
            daily['date'] = daily['date'].dt.strftime('%Y-%m-%d')
            daily_path = log_dir / f'{prefix}_daily_equity.csv'
            daily.to_csv(daily_path, index=False)
            print(f"Daily equity saved  : {daily_path} ({len(daily)} rows)")

        # Opportunity cost log
        oc_log = results['opportunity_cost']['log']
        if oc_log:
            oc_df = pd.DataFrame(oc_log)
            oc_path = log_dir / f'phase7_version{v}_opportunity_cost.csv'
            oc_df.to_csv(oc_path, index=False)
            print(f"Opportunity cost    : {oc_path} ({len(oc_df)} records)")
        else:
            oc_path = log_dir / f'phase7_version{v}_opportunity_cost.csv'
            pd.DataFrame(columns=[
                'date', 'rejected_symbol', 'rejected_strategy', 'reason',
                'r2_symbol_occupying_slot', 'r2_entry_date', 'r2_current_pnl'
            ]).to_csv(oc_path, index=False)
            print(f"Opportunity cost    : {oc_path} (0 records)")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    sys.path.insert(0, r'C:\Projects\trading_engine')

    from data.loader import DataLoader
    from data.vix_loader import load_vix
    from strategies.all_weather.module_a_regime import RegimeClassifier
    from strategies.all_weather.module_b_sector import SectorAlphaFilter

    DATA_DIR     = r'C:\Projects\trading_engine\data\Historical Daily Data'
    MAPPING_FILE = r'C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json'
    LOG_DIR      = r'C:\Projects\trading_engine\logs'

    CONFIG = {
        'initial_capital': 100000,
        'start_date'     : '2017-01-01',
        'end_date'       : '2025-12-31',
        'debug'          : False,
        'log_dir'        : LOG_DIR,
    }

    # ── Load shared data (loaded once, used for both runs) ────────────────────
    print("Step 1: Loading VIX data...")
    vix_result = load_vix(CONFIG['start_date'], CONFIG['end_date'])
    vix_series = vix_result['vix']

    print("\nStep 2: Building Module A (Regime Classifier)...")
    regime_classifier = RegimeClassifier(
        DATA_DIR, vix_series,
        CONFIG['start_date'], CONFIG['end_date']
    )

    print("\nStep 3: Loading stock price data...")
    with open(MAPPING_FILE) as f:
        symbol_list = list(json.load(f).keys())

    loader = DataLoader(DATA_DIR)
    engine = Phase7UnifiedEngine(CONFIG)
    engine.load_price_data(loader, symbol_list)

    print("\nStep 4: Building Module B (Sector Alpha Filter)...")
    sector_filter = SectorAlphaFilter(MAPPING_FILE, engine.price_data)

    # ── v3: v2 logic + S1 flat 10% sizing ────────────────────────────────────
    print("\n" + "=" * 70)
    print("RUNNING v3 — S1 FLAT 10% SIZING (VERSION A RANKING)")
    print("=" * 70)
    results_v3 = engine.run(regime_classifier, sector_filter, version='A')
    engine.print_results(results_v3)
    engine.save_outputs(results_v3, 'A', output_prefix='phase7_v3')
