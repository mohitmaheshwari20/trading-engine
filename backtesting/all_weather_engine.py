"""
all_weather_engine.py — All-Weather Quant Strategy Backtesting Engine
NIFTY 200 | Regime-Switching | Phase 7: R2-Only Entries (R1 Permanently Disabled)

Architecture:
    Module A (RegimeClassifier)  → daily ON/CAUTION/OFF gate
    Module B (SectorAlphaFilter) → peer-group relative strength filter
    Module C (R2 only + upgrade) → mean reversion entries; R1 logic retained for
                                   R2→R1 upgrade path only (Chandelier, Breakeven,
                                   4-layer stops, Time-Stop)
    Module D                     → ADTV filter, ATR sizing, circuit breaker

R1 standalone entries PERMANENTLY DISABLED.
Evidence from Phase 4 (isolated) and Phase 7 (combined):
    Win rate: 26.63% vs 40–52% spec target
    R1 crowded out R2 (95.6% of all slots taken by false breakouts)
    Donchian + ADX>25 entry generates too many low-quality signals
    Overall system return: -45.90% with R1 active vs positive with R2-only

R1 mechanics (Chandelier, Breakeven, Time-Stop) remain in AWPosition and
check_exits — required for the R2→R1 upgrade path.

Signal ranking (Section 11.2):
    Priority 1 — Sector cap: max 2 positions per sector (Others = 1 sector)
    Priority 2 — Alpha rank: highest (stock_15d_return - sector_median) first
    Priority 3 — Not applicable (R1 disabled; single entry regime)

Spec reference: Nifty200_AllWeather_Strategy_Spec_v2.docx
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.indicators import TechnicalIndicators


# ─────────────────────────────────────────────────────────────────────────────
# Constants — canonical parameter reference (spec Section 11 / tracker)
# ─────────────────────────────────────────────────────────────────────────────

# Regime 1 parameters
DONCHIAN_PERIOD       = 20      # 20-day high breakout
ADX_PERIOD            = 14
ADX_R1_THRESHOLD      = 25      # ADX > 25 → Regime 1
ATR_PERIOD            = 14
ATR_INITIAL_STOP_MULT = 3.0     # Initial stop = Entry - 3×ATR
ATR_BREAKEVEN_MULT    = 1.0     # Breakeven trigger = Entry + 1×ATR
ATR_CHANDELIER_MULT   = 3.0     # Chandelier = Highest Close - 3×ATR
ATR_TIMESTOP_PROFIT   = 0.5     # Time-stop profit hurdle = 0.5×ATR
ATR_OFF_STOP_MULT     = 1.5     # OFF state tightens stop to 1.5×ATR
TIME_STOP_DAYS        = 5       # Day 5: exit if profit < 0
LIMBO_MAX_DAYS        = 30      # Day 30: hard cap for Limbo trades (Phase 6.2 — was 20)

# Position management (spec Section 11)
MAX_POSITIONS         = 10
MAX_PER_SECTOR        = 2

# Risk / sizing (spec Section 6)
EQUITY_RISK_PCT       = 0.01    # 1% per trade
SIZING_ATR_MULT       = 3.0     # Qty = (Equity × 0.01) / (3 × ATR)

# Liquidity filter (spec Section 6.2)
ADTV_LOOKBACK         = 60      # trading days
ADTV_MIN_CRORES       = 10.0   # ₹10 Crores minimum
ADTV_MIN_VALUE        = ADTV_MIN_CRORES * 1e7  # in rupees

# Circuit breaker (spec Section 6.3)
CIRCUIT_VOL_THRESHOLD = 0.05    # < 5% of 20-day avg volume
CIRCUIT_VOL_LOOKBACK  = 20
CIRCUIT_SLIPPAGE      = 0.05    # 5% slippage on deferred exit

# Transaction costs
TRANSACTION_COST_PCT  = 0.001   # 0.1% per side (brokerage + STT approx)

# Regime labels
REGIME_ON      = 'ON'
REGIME_CAUTION = 'CAUTION'
REGIME_OFF     = 'OFF'

# Regime 2 parameters
ADX_R2_THRESHOLD      = 20      # ADX < 20 → Regime 2 entry gate
RSI_PERIOD            = 2       # RSI(2) for mean reversion
RSI_ENTRY_THRESHOLD   = 10      # RSI(2) < 10 → oversold entry
RSI_EXIT_THRESHOLD    = 70      # RSI(2) > 70 → snap-back exit
SMA_EXIT_PERIOD       = 20      # 20-day SMA exit (Phase 6.2 — gives room to reach upgrade)

# Exit reasons — R2 specific
EXIT_INITIAL_STOP    = 'Initial Stop'
EXIT_CHANDELIER      = 'Chandelier Stop'
EXIT_TIME_STOP       = 'Time Stop (Day 5 Loss)'
EXIT_LIMBO_CAP       = 'Limbo Cap (Day 20)'
EXIT_OFF_STOP        = 'OFF State Stop'
EXIT_BACKTEST_END    = 'Backtest End'
EXIT_CIRCUIT         = 'Circuit Breaker'
EXIT_SMA             = 'SMA Exit'
EXIT_RSI_OB          = 'RSI Overbought'


# ─────────────────────────────────────────────────────────────────────────────
# Position — extended state for All-Weather trades
# ─────────────────────────────────────────────────────────────────────────────

class AWPosition:
    """
    Extended position carrying all state required by the 4-layer stop system.
    """

    def __init__(self, symbol, shares, entry_price, entry_date, atr_at_entry,
                 initial_stop, sector, sector_bucket, size_multiplier,
                 regime='R1'):
        self.symbol               = symbol
        self.shares               = shares
        self.entry_price          = entry_price
        self.entry_date           = entry_date
        self.atr_at_entry         = atr_at_entry
        self.sector               = sector
        self.sector_bucket        = sector_bucket
        self.size_multiplier      = size_multiplier
        self.regime               = regime          # 'R1', 'R2', 'Upgraded'

        # Stop layers
        self.initial_stop         = initial_stop    # Layer 1
        self.breakeven_hit        = False           # Layer 2 flag
        self.chandelier_stop      = None            # Layer 3 (activates post-breakeven)
        self.stop_loss            = initial_stop    # Active stop (whichever is highest)

        # State tracking
        self.highest_close_since_entry = entry_price
        self.trade_age            = 0               # incremented each day
        self.deferred_exit        = False           # circuit breaker flag
        self.deferred_exit_price  = None
        self.in_limbo             = False           # True after Day 5 survival

    def update_daily(self, current_close, current_atr, market_regime):
        """
        Called every day the position is open.

        State updates differ by regime:
            R2       : Only track highest_close and trade_age.
                       No Chandelier, no Breakeven — these are R1 mechanics.
            Upgraded : Full 4-layer stop system active.

        Returns:
            None (stop updates happen in-place)
        """
        self.trade_age += 1

        # Always track highest close since entry (needed for upgrade Chandelier)
        if current_close > self.highest_close_since_entry:
            self.highest_close_since_entry = current_close

        # ── R2: only Initial Stop is active — no Chandelier, no Breakeven ─────
        if self.regime == 'R2':
            # OFF state tightening still applies to protect against crashes
            if market_regime == REGIME_OFF:
                off_stop   = self.highest_close_since_entry - (ATR_OFF_STOP_MULT * current_atr)
                self.stop_loss = max(self.stop_loss, off_stop)
            return

        # ── Upgraded: full Chandelier + Breakeven system ──────────────────────
        # Layer 2: Breakeven trigger
        if not self.breakeven_hit:
            breakeven_trigger = self.entry_price + (ATR_BREAKEVEN_MULT * self.atr_at_entry)
            if current_close >= breakeven_trigger:
                self.breakeven_hit = True
                self.stop_loss     = max(self.entry_price, self.stop_loss)

        # Layer 3: Chandelier trailing stop (ratchet up only)
        if self.breakeven_hit:
            chandelier = (self.highest_close_since_entry -
                         ATR_CHANDELIER_MULT * current_atr)
            if self.chandelier_stop is None:
                self.chandelier_stop = chandelier
            else:
                self.chandelier_stop = max(self.chandelier_stop, chandelier)
            self.stop_loss = max(self.stop_loss, self.chandelier_stop)

        # OFF state tightening for upgraded positions
        if market_regime == REGIME_OFF:
            off_stop   = self.highest_close_since_entry - (ATR_OFF_STOP_MULT * current_atr)
            self.stop_loss = max(self.stop_loss, off_stop)

    def check_stop_hit(self, day_low, day_close):
        """
        Check if stop loss was hit during the day.

        Args:
            day_low   : float — day's low price
            day_close : float — day's close price

        Returns:
            (bool, float, str) — (hit, exit_price, reason)
        """
        if day_low <= self.stop_loss:
            # Exit at stop price or day's close if gap down below stop
            exit_price  = max(self.stop_loss, day_low)
            exit_price  = min(exit_price, day_close)  # can't exit above close
            exit_reason = (EXIT_CHANDELIER if self.breakeven_hit
                          else EXIT_INITIAL_STOP)
            return True, exit_price, exit_reason
        return False, None, None

    def check_day5_filter(self, current_close):
        """
        Day 5 Survival Filter (replaces Time-Stop for R2 trades).

        At Day 5:
            profit < 0  → Exit (dip was a trap)
            profit >= 0 → Survive (dip was a success, deactivate SMA/RSI exits)

        The caller is responsible for deactivating R2 signal exits
        when this returns False (survival).

        Only applies to R2 trades. Upgraded trades have no day cap.

        Returns:
            (bool, str) — (should_exit, reason)
                'kill'    → exit at next open
                'survive' → deactivate R2 exits, enter Limbo
                None      → not Day 5, no action
        """
        if self.regime != 'R2':
            return None, None
        if self.trade_age == TIME_STOP_DAYS:
            if current_close < self.entry_price:
                return True, 'kill'
            else:
                return False, 'survive'
        return None, None

    def check_limbo_cap(self):
        """
        Day 20 hard cap for Limbo trades.
        Exits at next open regardless of profit/loss.
        Only applies to R2 trades in Limbo (SMA/RSI exits deactivated).

        Returns:
            bool — True if Limbo cap reached
        """
        return self.regime == 'R2' and self.in_limbo and self.trade_age >= LIMBO_MAX_DAYS

    def get_current_value(self, current_price):
        return self.shares * current_price

    def get_profit(self, exit_price):
        revenue  = self.shares * exit_price * (1 - TRANSACTION_COST_PCT)
        cost     = self.shares * self.entry_price * (1 + TRANSACTION_COST_PCT)
        return revenue - cost

    def get_profit_pct(self, exit_price):
        return ((exit_price - self.entry_price) / self.entry_price) * 100


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

class AWPortfolio:
    """
    Portfolio tracking cash, positions, closed trades, and equity curve.
    """

    def __init__(self, initial_capital, debug=False):
        self.initial_capital      = initial_capital
        self.cash                 = initial_capital
        self.positions            = {}       # {symbol: AWPosition}
        self.closed_trades        = []
        self.equity_curve         = []
        self.equity_dates         = []
        self.total_costs          = 0.0
        self.debug                = debug

    def can_open_position(self, sector, sector_bucket):
        """
        Check if a new position can be opened.
        Enforces: max 10 total, max 2 per sector (Others = 1 sector).
        """
        if len(self.positions) >= MAX_POSITIONS:
            return False, 'Max positions reached'

        # Count open positions in this sector
        sector_key = sector_bucket if sector_bucket == 'Others' else sector
        sector_count = sum(
            1 for p in self.positions.values()
            if (p.sector_bucket == 'Others' if sector_bucket == 'Others'
                else p.sector == sector)
        )
        if sector_count >= MAX_PER_SECTOR:
            return False, f'Sector cap reached ({sector})'

        return True, None

    def open_position(self, position, date):
        """Open a new position and deduct cash."""
        cost = (position.shares * position.entry_price *
                (1 + TRANSACTION_COST_PCT))
        self.cash        -= cost
        self.total_costs += position.shares * position.entry_price * TRANSACTION_COST_PCT
        self.positions[position.symbol] = position

        if self.debug:
            print(f"  BUY  {date.date()} | {position.symbol:20} | "
                  f"Shares: {position.shares:4} @ ₹{position.entry_price:8.2f} | "
                  f"Stop: ₹{position.stop_loss:8.2f} | "
                  f"ATR: {position.atr_at_entry:.2f} | "
                  f"Sector: {position.sector} | "
                  f"Cash: ₹{self.cash:,.0f}")

    def close_position(self, symbol, exit_price, exit_date, exit_reason,
                       deferred=False, slippage_applied=False):
        """Close a position and record the trade."""
        if symbol not in self.positions:
            return

        pos     = self.positions[symbol]
        profit  = pos.get_profit(exit_price)
        pct     = pos.get_profit_pct(exit_price)
        revenue = pos.shares * exit_price * (1 - TRANSACTION_COST_PCT)

        self.cash        += revenue
        self.total_costs += pos.shares * exit_price * TRANSACTION_COST_PCT

        self.closed_trades.append({
            'symbol'           : symbol,
            'regime'           : pos.regime,
            'sector'           : pos.sector,
            'sector_bucket'    : pos.sector_bucket,
            'entry_date'       : pos.entry_date,
            'exit_date'        : exit_date,
            'entry_price'      : pos.entry_price,
            'exit_price'       : exit_price,
            'shares'           : pos.shares,
            'atr_at_entry'     : pos.atr_at_entry,
            'initial_stop'     : pos.initial_stop,
            'breakeven_hit'    : pos.breakeven_hit,
            'profit'           : profit,
            'profit_pct'       : pct,
            'hold_days'        : pos.trade_age,
            'exit_reason'      : exit_reason,
            'size_multiplier'  : pos.size_multiplier,
            'deferred_exit'    : deferred,
            'slippage_applied' : slippage_applied,
        })

        if self.debug:
            print(f"  SELL {exit_date.date()} | {symbol:20} | "
                  f"Shares: {pos.shares:4} @ ₹{exit_price:8.2f} | "
                  f"P&L: ₹{profit:+,.0f} ({pct:+.2f}%) | "
                  f"Reason: {exit_reason} | "
                  f"Days: {pos.trade_age} | "
                  f"Cash: ₹{self.cash:,.0f}")

        del self.positions[symbol]

    def get_positions_value(self, price_data, date):
        """Mark-to-market value of all open positions."""
        total = 0.0
        for symbol, pos in self.positions.items():
            if symbol in price_data:
                df   = price_data[symbol]
                rows = df[df['Date'] <= date]
                if len(rows) > 0:
                    total += pos.get_current_value(rows.iloc[-1]['Close'])
                else:
                    total += pos.get_current_value(pos.entry_price)
            else:
                total += pos.get_current_value(pos.entry_price)
        return total

    def record_equity(self, date, price_data):
        total = self.cash + self.get_positions_value(price_data, date)
        self.equity_curve.append(total)
        self.equity_dates.append(date)
        return total


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def compute_adtv(df, date, lookback=ADTV_LOOKBACK):
    """
    Compute 60-day Average Daily Turnover (Volume × Close).
    Returns value in rupees, or None if insufficient data.
    """
    rows = df[df['Date'] <= date].tail(lookback)
    if len(rows) < lookback:
        return None
    return (rows['Volume'] * rows['Close']).mean()


def is_circuit_breaker(df, date):
    """
    Detect lower circuit: Close == Low AND Volume < 5% of 20-day avg volume.
    Returns True if circuit triggered.
    """
    rows = df[df['Date'] <= date]
    if len(rows) < CIRCUIT_VOL_LOOKBACK + 1:
        return False

    today = rows.iloc[-1]

    # Condition 1: Close == Low (price closed at day's low)
    if not np.isclose(today['Close'], today['Low'], rtol=1e-4):
        return False

    # Condition 2: Volume < 5% of 20-day avg volume
    avg_vol = rows.iloc[-CIRCUIT_VOL_LOOKBACK - 1:-1]['Volume'].mean()
    if avg_vol == 0:
        return False

    return today['Volume'] < CIRCUIT_VOL_THRESHOLD * avg_vol


def compute_donchian_high(df, date, period=DONCHIAN_PERIOD):
    """
    20-day high (excluding today — breakout = today's close > prior 20-day high).
    Returns the high or None if insufficient data.
    """
    rows = df[df['Date'] < date].tail(period)
    if len(rows) < period:
        return None
    return rows['High'].max()


# ─────────────────────────────────────────────────────────────────────────────
# AllWeatherEngine
# ─────────────────────────────────────────────────────────────────────────────

class AllWeatherEngine:
    """
    All-Weather Quant Strategy Backtesting Engine.
    Phase 7: R2-Only Entries — R1 standalone permanently disabled.

    R2 (RSI<10 + ADX<20) is the sole entry mode. R1 mechanics (Chandelier,
    Breakeven, Time-Stop, 4-layer stops) are retained exclusively for the
    R2→R1 upgrade path. No standalone R1 positions are opened.
    """

    def __init__(self, config):
        self.initial_capital = config.get('initial_capital', 100000)
        self.start_date      = pd.to_datetime(config.get('start_date', '2017-01-01'))
        self.end_date        = pd.to_datetime(config.get('end_date',   '2025-12-31'))
        self.debug           = config.get('debug', False)
        self.log_dir         = config.get('log_dir', 'logs')

        self.portfolio       = AWPortfolio(self.initial_capital, debug=self.debug)
        self.price_data      = {}
        self._trading_dates  = []

        # Deferred exits: circuit breaker — exit at next day open with slippage
        # {symbol: {'price': float, 'date': Timestamp, 'reason': str}}
        self._deferred_exits = {}

        # Pending R2 signal exits — flagged on EOD close, executed at next open
        # {symbol: {'reason': str, 'flag_date': Timestamp}}
        self._pending_r2_exits = {}

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_price_data(self, loader, symbols, verbose=True):
        """
        Load and pre-calculate indicators for all symbols.
        Stores in self.price_data — shared with Module B.
        """
        if verbose:
            print(f"Loading price data for {len(symbols)} symbols...")

        loaded = 0
        for symbol in symbols:
            filename = symbol.replace('.', '_')
            try:
                df = loader.load_stock(filename)

                # Add required indicators
                if len(df) >= 200:
                    df['ATR']     = TechnicalIndicators.calculate_atr(df, ATR_PERIOD)
                    df['ADX']     = TechnicalIndicators.calculate_adx(df, ADX_PERIOD)
                    df['EMA200']  = TechnicalIndicators.calculate_ema(df, 200)
                    df['SMA10']   = TechnicalIndicators.calculate_sma(df, 10)
                    df['SMA20']   = TechnicalIndicators.calculate_sma(df, 20)
                    df['RSI2']    = TechnicalIndicators.calculate_rsi(df, 2)
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

    # ── Exit checking ─────────────────────────────────────────────────────────

    def check_exits(self, date, regime):
        """
        Check all open positions for exit conditions.

        Execution order:
            1. Pending R2 signal exits (flagged yesterday) → execute at today's open
            2. Circuit breaker deferred exits → execute at today's open
            3. Initial Stop → intraday (Low <= stop price), same day
            4. R2 signal exits (SMA / RSI) → flagged today, execute tomorrow's open
            5. Time-Stop → flagged today, execute tomorrow's open

        R2 exit rules (SMA/RSI/Time-Stop) execute at NEXT day open.
        Initial Stop executes INTRADAY — emergency protection only.
        """
        to_close      = []
        to_flag_exit  = []   # will execute next open

        # ── Step 1: Execute pending R2 signal exits at today's open ──────────
        executed_pending = set()
        for symbol, info in list(self._pending_r2_exits.items()):
            if symbol not in self.portfolio.positions:
                del self._pending_r2_exits[symbol]
                continue
            df   = self.price_data.get(symbol)
            rows = df[df['Date'] <= date] if df is not None else pd.DataFrame()
            if len(rows) == 0:
                continue
            # Execute at today's open
            exit_price = float(rows.iloc[-1]['Open']) if 'Open' in rows.columns \
                         else float(rows.iloc[-1]['Close'])
            to_close.append((symbol, exit_price, info['reason'], False, False))
            executed_pending.add(symbol)
        for sym in executed_pending:
            if sym in self._pending_r2_exits:
                del self._pending_r2_exits[sym]

        # ── Step 2: Execute circuit breaker deferred exits ────────────────────
        for symbol, info in list(self._deferred_exits.items()):
            if symbol in executed_pending:
                continue
            if symbol in self.portfolio.positions:
                to_close.append((symbol, info['price'], EXIT_CIRCUIT, True, True))
        self._deferred_exits = {}

        # ── Steps 3–5: Check each open position ───────────────────────────────
        for symbol, pos in list(self.portfolio.positions.items()):
            if symbol in executed_pending:
                continue
            if symbol in [t[0] for t in to_close]:
                continue
            if symbol not in self.price_data:
                continue

            df   = self.price_data[symbol]
            rows = df[df['Date'] <= date]
            if len(rows) == 0:
                continue

            today = rows.iloc[-1]
            close = float(today['Close'])
            low   = float(today['Low'])
            atr   = float(today['ATR']) if not pd.isna(today['ATR']) \
                    else pos.atr_at_entry

            # Update daily state (breakeven, chandelier, OFF tightening)
            pos.update_daily(close, atr, regime)

            # ── Regime Upgrade Check (R2 → R1) ───────────────────────────────
            # Double-Lock: ADX > 25 AND Close >= 20-day high
            # Deactivates R2 exits, activates Chandelier trailing stop.
            # Initial stop stays at original R2_entry - 3×ATR.
            if pos.regime == 'R2':
                adx = float(today['ADX']) if not pd.isna(today['ADX']) else 0
                dc_high = compute_donchian_high(df, date, DONCHIAN_PERIOD)
                if adx > ADX_R2_THRESHOLD and dc_high is not None and close >= dc_high:
                    pos.regime = 'Upgraded'

                    # Activate Chandelier anchored to Highest Close Since Entry
                    chandelier = (pos.highest_close_since_entry -
                                 ATR_CHANDELIER_MULT * atr)
                    pos.chandelier_stop = chandelier
                    pos.stop_loss       = max(pos.stop_loss, chandelier)

                    # Evaluate Breakeven immediately at upgrade moment
                    breakeven_trigger = pos.entry_price + (ATR_BREAKEVEN_MULT * pos.atr_at_entry)
                    if close >= breakeven_trigger and not pos.breakeven_hit:
                        pos.breakeven_hit = True
                        pos.stop_loss     = max(pos.stop_loss, pos.entry_price)

                    # Remove from pending R2 exits if flagged
                    if symbol in self._pending_r2_exits:
                        del self._pending_r2_exits[symbol]

                    if self.debug:
                        print(f"  UPGRADE {date.date()} | {symbol:20} | "
                              f"ADX={adx:.1f} Close={close:.2f} >= "
                              f"20dHigh={dc_high:.2f} | "
                              f"Chandelier={chandelier:.2f} | "
                              f"Breakeven={'HIT' if pos.breakeven_hit else 'pending'}")
                    continue  # Skip R2 exits on upgrade day — now managed as R1

            # ── Circuit breaker check — defer to next day ─────────────────────
            if is_circuit_breaker(df, date):
                df_future = df[df['Date'] > date]
                if len(df_future) > 0:
                    next_row       = df_future.iloc[0]
                    slippage_price = float(next_row['Open']) * (1 - CIRCUIT_SLIPPAGE)
                    self._deferred_exits[symbol] = {
                        'price' : slippage_price,
                        'date'  : next_row['Date'],
                        'reason': EXIT_CIRCUIT
                    }
                    if self.debug:
                        print(f"  CIRCUIT {date.date()} | {symbol} — "
                              f"deferred to {next_row['Date'].date()}")
                continue

            # ── Step 3: Initial Stop — INTRADAY (emergency) ───────────────────
            hit, exit_price, reason = pos.check_stop_hit(low, close)
            if hit:
                to_close.append((symbol, exit_price, reason, False, False))
                continue

            # ── Step 3b: R1 Time-Stop (Layer 4) ───────────────────────────────
            # Day 5 only, profit < 0.5×ATR → flag exit at next open.
            # Applies to original R1 entries only — Upgraded trades excluded.
            if pos.regime == 'R1' and pos.trade_age == TIME_STOP_DAYS:
                profit_in_atr = (close - pos.entry_price) / pos.atr_at_entry
                if profit_in_atr < ATR_TIMESTOP_PROFIT:
                    to_flag_exit.append((symbol, EXIT_TIME_STOP))
                    continue

            # ── Step 4: Day 5 Survival Filter / Day 20 Limbo Cap ─────────────
            # Must run BEFORE SMA/RSI exits — Day 5 evaluation takes
            # priority over signal-based exits on the same day.
            if pos.regime == 'R2':

                # Day 5: Kill losers, promote survivors to Limbo
                action, result = pos.check_day5_filter(close)
                if action is True and result == 'kill':
                    to_flag_exit.append((symbol, EXIT_TIME_STOP))
                    continue
                elif action is False and result == 'survive':
                    pos.in_limbo = True
                    if symbol in self._pending_r2_exits:
                        del self._pending_r2_exits[symbol]
                    if self.debug:
                        print(f"  LIMBO {date.date()} | {symbol:20} | "
                              f"Day 5 profit ✓ → SMA/RSI exits deactivated")
                    continue

                # Day 20: Hard cap — force exit regardless of P&L
                if pos.in_limbo and pos.check_limbo_cap():
                    to_flag_exit.append((symbol, EXIT_LIMBO_CAP))
                    continue

            # ── Step 5: R2 signal exits (SMA/RSI) — only if not in Limbo ────
            # Once in_limbo=True, SMA and RSI exits are permanently deactivated
            if pos.regime == 'R2' and not pos.in_limbo:
                sma20 = float(today['SMA20']) if 'SMA20' in today.index and not pd.isna(today['SMA20']) \
                        else None
                rsi2  = float(today['RSI2'])  if not pd.isna(today['RSI2'])  \
                        else None

                # Exit A: Close > 20-day SMA (Phase 6.2 — was SMA10)
                if sma20 is not None and close > sma20:
                    to_flag_exit.append((symbol, EXIT_SMA))
                    continue

                # Exit B: RSI(2) > 70
                if rsi2 is not None and rsi2 > RSI_EXIT_THRESHOLD:
                    to_flag_exit.append((symbol, EXIT_RSI_OB))
                    continue

        # Execute same-day closes (Initial Stop, Circuit)
        for symbol, price, reason, deferred, slippage in to_close:
            self.portfolio.close_position(
                symbol, price, date, reason,
                deferred=deferred, slippage_applied=slippage
            )

        # Flag next-open exits
        for symbol, reason in to_flag_exit:
            self._pending_r2_exits[symbol] = {
                'reason'    : reason,
                'flag_date' : date
            }
            if self.debug:
                print(f"  FLAG EXIT {date.date()} | {symbol} | "
                      f"{reason} — executes next open")

    # ── Entry scanning ────────────────────────────────────────────────────────

    def scan_regime1_entries(self, date, eligible_symbols, size_multiplier):
        """
        Scan eligible symbols for Regime 1 entry signals.

        Entry conditions:
            1. Close > 20-day high (Donchian breakout)
            2. ADX(14) > 25 on entry day
            3. Passes ADTV filter (60-day avg turnover > ₹10 Cr)
            4. Sufficient ATR data available

        Returns list of signal dicts sorted by alpha (Priority 2).
        """
        signals = []
        eligible_map = {e['symbol']: e for e in eligible_symbols}

        for e in eligible_symbols:
            symbol = e['symbol']

            if symbol not in self.price_data:
                continue
            if symbol in self.portfolio.positions:
                continue

            df   = self.price_data[symbol]
            rows = df[df['Date'] <= date]

            if len(rows) < max(DONCHIAN_PERIOD + 1, ADTV_LOOKBACK, ADX_PERIOD * 2):
                continue

            today = rows.iloc[-1]
            close = float(today['Close'])
            adx   = float(today['ADX'])  if not pd.isna(today['ADX'])  else 0
            atr   = float(today['ATR'])  if not pd.isna(today['ATR'])  else 0

            if adx == 0 or atr == 0:
                continue

            # Condition 1: ADX > 25
            if adx <= ADX_R1_THRESHOLD:
                continue

            # Condition 2: Donchian breakout
            dc_high = compute_donchian_high(df, date, DONCHIAN_PERIOD)
            if dc_high is None or close <= dc_high:
                continue

            # Condition 3: ADTV filter
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
                'alpha'        : e['alpha'],     # for Priority 2 ranking
            })

        # Priority 2: rank by alpha descending
        signals.sort(key=lambda x: x['alpha'], reverse=True)
        return signals

    # ── R2 Entry scanning ─────────────────────────────────────────────────────

    def scan_regime2_entries(self, date, eligible_symbols):
        """
        Scan eligible symbols for Regime 2 (Mean Reversion) entry signals.

        Entry conditions (all required):
            1. RSI(2) < 10      — price overextended to downside
            2. Close > EMA200   — structural uptrend intact
            3. ADX(14) < 20     — range-bound, not trending
            4. Passes ADTV filter
            5. Not already in portfolio

        Entry executes at NEXT day's open (flagged here, executed in run loop).

        Returns list of signal dicts sorted by alpha (Priority 2).
        """
        signals = []

        for e in eligible_symbols:
            symbol = e['symbol']

            if symbol not in self.price_data:
                continue
            if symbol in self.portfolio.positions:
                continue
            if symbol in self._pending_r2_exits:
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

            if any(v is None for v in [rsi2, adx, ema200, atr]):
                continue
            if atr == 0:
                continue

            # Condition 1: RSI(2) < 10
            if rsi2 >= RSI_ENTRY_THRESHOLD:
                continue

            # Condition 2: Price > EMA200
            if close <= ema200:
                continue

            # Condition 3: ADX < 20
            if adx >= ADX_R2_THRESHOLD:
                continue

            # Condition 4: ADTV filter
            adtv = compute_adtv(df, date, ADTV_LOOKBACK)
            if adtv is None or adtv < ADTV_MIN_VALUE:
                continue

            # Condition 5: Deep Dip filter — Close < SMA20 - 0.5×ATR
            # Anchor alignment: entry and exit both reference SMA20.
            # 0.5×ATR gap (Phase 7 Step 1): relaxed from 1.0×ATR to widen
            # the entry window and capture more mean-reversion candidates.
            sma20_entry = float(today['SMA20']) if 'SMA20' in today.index and not pd.isna(today['SMA20']) else None
            if sma20_entry is None:
                continue
            deep_dip_threshold = sma20_entry - 0.5 * atr
            if close >= deep_dip_threshold:
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
            })

        # Priority 2: rank by alpha descending
        signals.sort(key=lambda x: x['alpha'], reverse=True)
        return signals

    def execute_r2_entries(self, signals, date, size_multiplier):
        """
        Execute R2 entry orders at next day's open.
        Stores pending entries — price and shares computed at next open.
        Respects sector cap and position limit.
        """
        for sig in signals:
            symbol        = sig['symbol']
            sector        = sig['sector']
            sector_bucket = sig['sector_bucket']

            can_open, reason = self.portfolio.can_open_position(
                sector, sector_bucket
            )
            if not can_open:
                continue

            # Get next day's open price
            df       = self.price_data[symbol]
            df_future = df[df['Date'] > date]
            if len(df_future) == 0:
                continue

            next_row    = df_future.iloc[0]
            entry_price = float(next_row['Open'])
            entry_date  = next_row['Date']
            atr         = sig['atr']  # ATR from signal day

            # Sizing
            equity      = self.portfolio.cash + sum(
                p.get_current_value(entry_price)
                for p in self.portfolio.positions.values()
            )
            risk_budget = equity * EQUITY_RISK_PCT * size_multiplier
            qty         = int(risk_budget / (SIZING_ATR_MULT * atr))

            if qty <= 0:
                continue

            total_cost = qty * entry_price * (1 + TRANSACTION_COST_PCT)
            if total_cost > self.portfolio.cash:
                continue

            initial_stop = entry_price - (ATR_INITIAL_STOP_MULT * atr)

            pos = AWPosition(
                symbol         = symbol,
                shares         = qty,
                entry_price    = entry_price,
                entry_date     = entry_date,
                atr_at_entry   = atr,
                initial_stop   = initial_stop,
                sector         = sector,
                sector_bucket  = sector_bucket,
                size_multiplier= size_multiplier,
                regime         = 'R2'
            )

            self.portfolio.open_position(pos, entry_date)

            if self.debug:
                print(f"  R2 ENTRY {entry_date.date()} | {symbol:20} | "
                      f"Open: ₹{entry_price:.2f} | RSI2: {sig['rsi2']:.1f} | "
                      f"ATR: {atr:.2f}")

    def execute_entries(self, signals, date, size_multiplier):
        """
        Execute entry orders respecting sector caps and position limit.

        Priority 1: sector cap (max 2 per sector, Others treated as one sector)
        Priority 2: alpha rank (already sorted by scan_regime1_entries)
        """
        for sig in signals:
            symbol       = sig['symbol']
            sector       = sig['sector']
            sector_bucket = sig['sector_bucket']

            # Check position limits (total + sector cap)
            can_open, reason = self.portfolio.can_open_position(
                sector, sector_bucket
            )
            if not can_open:
                if self.debug:
                    print(f"  SKIP {symbol} — {reason}")
                continue

            close = sig['close']
            atr   = sig['atr']

            # Position sizing: Qty = (Equity × 0.01) / (3 × ATR)
            equity       = self.portfolio.cash + sum(
                p.get_current_value(close)
                for p in self.portfolio.positions.values()
            )
            risk_budget  = equity * EQUITY_RISK_PCT * size_multiplier
            qty          = int(risk_budget / (SIZING_ATR_MULT * atr))

            if qty <= 0:
                continue

            total_cost = qty * close * (1 + TRANSACTION_COST_PCT)
            if total_cost > self.portfolio.cash:
                continue

            initial_stop = close - (ATR_INITIAL_STOP_MULT * atr)

            pos = AWPosition(
                symbol         = symbol,
                shares         = qty,
                entry_price    = close,
                entry_date     = date,
                atr_at_entry   = atr,
                initial_stop   = initial_stop,
                sector         = sector,
                sector_bucket  = sector_bucket,
                size_multiplier= size_multiplier,
                regime         = 'R1'
            )

            self.portfolio.open_position(pos, date)

    def execute_combined_entries(self, r1_signals, r2_signals, date, size_multiplier):
        """
        Execute combined R1 + R2 entries with Priority 3 regime preference.

        Combined list order: R1 signals (sorted by alpha) first, then R2 signals
        (sorted by alpha). Both share the same sector-cap and position-limit
        checks applied in order — R1 fills slots at today's close first;
        if all 10 positions are taken by R1, R2 signals do not execute.

        R1 entries: open at today's close (same-day).
        R2 entries: open at next day's open price.
        """
        combined = [('R1', s) for s in r1_signals] + [('R2', s) for s in r2_signals]

        for regime_tag, sig in combined:
            symbol        = sig['symbol']
            sector        = sig['sector']
            sector_bucket = sig['sector_bucket']
            atr           = sig['atr']

            # Skip if symbol was opened earlier in this loop (R1 took the slot)
            if symbol in self.portfolio.positions:
                continue

            can_open, reason = self.portfolio.can_open_position(sector, sector_bucket)
            if not can_open:
                if self.debug:
                    print(f"  SKIP {symbol} [{regime_tag}] — {reason}")
                continue

            if regime_tag == 'R1':
                close = sig['close']
                equity = self.portfolio.cash + sum(
                    p.get_current_value(close)
                    for p in self.portfolio.positions.values()
                )
                risk_budget  = equity * EQUITY_RISK_PCT * size_multiplier
                qty          = int(risk_budget / (SIZING_ATR_MULT * atr))
                if qty <= 0:
                    continue
                total_cost = qty * close * (1 + TRANSACTION_COST_PCT)
                if total_cost > self.portfolio.cash:
                    continue
                initial_stop = close - (ATR_INITIAL_STOP_MULT * atr)
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
                    regime          = 'R1'
                )
                self.portfolio.open_position(pos, date)

            else:  # R2
                df        = self.price_data[symbol]
                df_future = df[df['Date'] > date]
                if len(df_future) == 0:
                    continue
                next_row    = df_future.iloc[0]
                entry_price = float(next_row['Open'])
                entry_date  = next_row['Date']
                equity = self.portfolio.cash + sum(
                    p.get_current_value(entry_price)
                    for p in self.portfolio.positions.values()
                )
                risk_budget  = equity * EQUITY_RISK_PCT * size_multiplier
                qty          = int(risk_budget / (SIZING_ATR_MULT * atr))
                if qty <= 0:
                    continue
                total_cost = qty * entry_price * (1 + TRANSACTION_COST_PCT)
                if total_cost > self.portfolio.cash:
                    continue
                initial_stop = entry_price - (ATR_INITIAL_STOP_MULT * atr)
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
                    regime          = 'R2'
                )
                self.portfolio.open_position(pos, entry_date)

                if self.debug:
                    print(f"  R2 ENTRY {entry_date.date()} | {symbol:20} | "
                          f"Open: ₹{entry_price:.2f} | RSI2: {sig['rsi2']:.1f} | "
                          f"ATR: {atr:.2f}")

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self, regime_classifier, sector_filter, verbose=True):
        """
        Run the full backtest — R2 entries only, upgrade path active.

        Args:
            regime_classifier : RegimeClassifier — Module A
            sector_filter     : SectorAlphaFilter — Module B
            verbose           : bool

        Returns:
            dict — full results including trades, equity curve, metrics
        """
        print("=" * 70)
        print("ALL-WEATHER QUANT — PHASE 7: COMBINED SYSTEM BACKTEST")
        print("=" * 70)
        print(f"Period   : {self.start_date.date()} to {self.end_date.date()}")
        print(f"Capital  : ₹{self.initial_capital:,.0f}")
        print(f"Universe : {len(self.price_data)} stocks loaded\n")

        self._trading_dates = self.get_trading_dates()
        print(f"Trading days : {len(self._trading_dates)}")
        print(f"Processing...\n")

        progress_interval = max(len(self._trading_dates) // 10, 1)

        for i, date in enumerate(self._trading_dates, 1):

            # ── Module A: Get market regime ───────────────────────────────────
            regime     = regime_classifier.get_regime(date)
            size_mult  = regime_classifier.get_size_multiplier(date)

            if regime is None:
                self.portfolio.record_equity(date, self.price_data)
                continue

            # ── Check exits first ─────────────────────────────────────────────
            self.check_exits(date, regime)

            # ── New entries only if market is ON or CAUTION ───────────────────
            if regime in (REGIME_ON, REGIME_CAUTION):

                # Module B: Get eligible symbols
                eligible = sector_filter.get_eligible_symbols(date)

                # R1 standalone entries permanently disabled.
                # R1 mechanics (Chandelier, Breakeven, Time-Stop) remain active
                # for the R2→R1 upgrade path only.
                r2_signals = self.scan_regime2_entries(date, eligible)

                if r2_signals:
                    self.execute_r2_entries(r2_signals, date, size_mult)

            # Record equity
            self.portfolio.record_equity(date, self.price_data)

            if verbose and i % progress_interval == 0:
                pct   = i / len(self._trading_dates) * 100
                total = self.portfolio.equity_curve[-1]
                print(f"  {pct:.0f}% | {date.date()} | "
                      f"Equity: ₹{total:,.0f} | "
                      f"Positions: {len(self.portfolio.positions)} | "
                      f"Regime: {regime}")

        # ── Close remaining positions at end ──────────────────────────────────
        print("\nClosing remaining open positions...")
        for symbol in list(self.portfolio.positions.keys()):
            if symbol in self.price_data:
                df    = self.price_data[symbol]
                rows  = df[df['Date'] <= self.end_date]
                price = float(rows.iloc[-1]['Close']) if len(rows) > 0 else \
                        self.portfolio.positions[symbol].entry_price
            else:
                price = self.portfolio.positions[symbol].entry_price
            self.portfolio.close_position(
                symbol, price, self.end_date, EXIT_BACKTEST_END
            )

        print(f"Closed {len([t for t in self.portfolio.closed_trades if t['exit_reason'] == EXIT_BACKTEST_END])} positions at end\n")

        return self.calculate_results()

    # ── Results ───────────────────────────────────────────────────────────────

    def calculate_results(self):
        """
        Compute all performance metrics.
        Includes the 5 All-Weather specific metrics from spec Section 7.
        """
        trades  = self.portfolio.closed_trades
        initial = self.initial_capital
        final   = self.portfolio.equity_curve[-1] if self.portfolio.equity_curve else initial

        # Standard metrics
        total_ret  = ((final - initial) / initial) * 100
        years      = (self.end_date - self.start_date).days / 365.25
        annual_ret = ((1 + total_ret / 100) ** (1 / years) - 1) * 100 if years > 0 else 0

        winners    = [t for t in trades if t['profit'] > 0]
        losers     = [t for t in trades if t['profit'] <= 0]
        win_rate   = len(winners) / len(trades) * 100 if trades else 0

        avg_win    = np.mean([t['profit_pct'] for t in winners]) if winners else 0
        avg_loss   = abs(np.mean([t['profit_pct'] for t in losers])) if losers else 0
        wl_ratio   = avg_win / avg_loss if avg_loss > 0 else 0

        gross_profit = sum(t['profit'] for t in winners)
        gross_loss   = abs(sum(t['profit'] for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        max_dd = self._compute_max_drawdown()

        # ── All-Weather Metric 1: Expectancy ──────────────────────────────────
        # E = (Win% × Avg Win) - (Loss% × Avg Loss) — in R-multiples
        win_pct  = len(winners) / len(trades) if trades else 0
        loss_pct = len(losers)  / len(trades) if trades else 0
        avg_win_r  = np.mean([
            t['profit'] / (t['shares'] * t['atr_at_entry'] * SIZING_ATR_MULT)
            for t in winners
        ]) if winners else 0
        avg_loss_r = abs(np.mean([
            t['profit'] / (t['shares'] * t['atr_at_entry'] * SIZING_ATR_MULT)
            for t in losers
        ])) if losers else 0
        expectancy = (win_pct * avg_win_r) - (loss_pct * avg_loss_r)

        # ── All-Weather Metric 2: Profit Factor by Regime ─────────────────────
        r1_trades  = [t for t in trades if t['regime'] == 'R1']
        r1_winners = [t for t in r1_trades if t['profit'] > 0]
        r1_losers  = [t for t in r1_trades if t['profit'] <= 0]
        r1_gp      = sum(t['profit'] for t in r1_winners)
        r1_gl      = abs(sum(t['profit'] for t in r1_losers))
        r1_pf      = r1_gp / r1_gl if r1_gl > 0 else 0

        r2_all     = [t for t in trades if t['regime'] in ('R2', 'Upgraded')]
        r2_winners = [t for t in r2_all if t['profit'] > 0]
        r2_losers  = [t for t in r2_all if t['profit'] <= 0]
        r2_gp      = sum(t['profit'] for t in r2_winners)
        r2_gl      = abs(sum(t['profit'] for t in r2_losers))
        r2_pf      = r2_gp / r2_gl if r2_gl > 0 else 0

        # ── All-Weather Metric 3: Stale-Trade Ratio ───────────────────────────
        r1_losers_list   = [t for t in r1_trades if t['profit'] <= 0]
        time_stop_losers = [t for t in r1_losers_list
                           if t['exit_reason'] == EXIT_TIME_STOP]
        stale_ratio = (len(time_stop_losers) / len(r1_losers_list) * 100
                      if r1_losers_list else 0)

        # ── All-Weather Metric 4: Recovery Factor ─────────────────────────────
        recovery_factor = (total_ret / max_dd) if max_dd > 0 else 0

        # ── All-Weather Metric 5: Slippage-Adjusted Return ───────────────────
        circuit_trades    = [t for t in trades if t['slippage_applied']]
        slippage_cost_pct = (sum(abs(t['profit']) * CIRCUIT_SLIPPAGE
                               for t in circuit_trades) / initial * 100
                            if circuit_trades else 0)
        ideal_return      = total_ret + slippage_cost_pct

        # Avg holding days
        avg_days_winners = np.mean([t['hold_days'] for t in winners]) if winners else 0
        avg_days_losers  = np.mean([t['hold_days'] for t in losers])  if losers  else 0

        return {
            'summary': {
                'initial_capital'   : initial,
                'final_capital'     : final,
                'total_return_pct'  : round(total_ret, 2),
                'annual_return_pct' : round(annual_ret, 2),
                'max_drawdown_pct'  : round(max_dd, 2),
                'total_trades'      : len(trades),
                'win_rate_pct'      : round(win_rate, 2),
                'avg_win_pct'       : round(avg_win, 2),
                'avg_loss_pct'      : round(avg_loss, 2),
                'wl_ratio'          : round(wl_ratio, 2),
                'profit_factor'     : round(profit_factor, 2),
                'avg_days_winners'  : round(avg_days_winners, 1),
                'avg_days_losers'   : round(avg_days_losers, 1),
                'transaction_costs' : round(self.portfolio.total_costs, 2),
            },
            'all_weather_metrics': {
                'expectancy'              : round(expectancy, 4),
                'profit_factor_r1'        : round(r1_pf, 2),
                'profit_factor_r2'        : round(r2_pf, 2),
                'stale_trade_ratio_pct'   : round(stale_ratio, 1),
                'recovery_factor'         : round(recovery_factor, 2),
                'slippage_adjusted_return': round(total_ret, 2),
                'ideal_return'            : round(ideal_return, 2),
                'slippage_cost_pct'       : round(slippage_cost_pct, 2),
            },
            'equity_curve' : self.portfolio.equity_curve,
            'equity_dates' : self.portfolio.equity_dates,
            'closed_trades': trades,
        }

    def _compute_max_drawdown(self):
        """Compute maximum peak-to-trough drawdown from equity curve."""
        if not self.portfolio.equity_curve:
            return 0
        curve  = self.portfolio.equity_curve
        peak   = curve[0]
        max_dd = 0
        for val in curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    # ── Results printer ───────────────────────────────────────────────────────

    def print_results(self, results):
        """Print formatted backtest results with all-weather metrics."""
        s  = results['summary']
        aw = results['all_weather_metrics']

        print("\n" + "=" * 70)
        print("BACKTEST RESULTS — PHASE 7: COMBINED SYSTEM BACKTEST")
        print("=" * 70)

        print("\nRETURNS")
        print("-" * 70)
        print(f"Initial Capital      : ₹{s['initial_capital']:>12,.0f}")
        print(f"Final Capital        : ₹{s['final_capital']:>12,.0f}")
        print(f"Total Return         : {s['total_return_pct']:>+8.2f}%")
        print(f"Annual Return        : {s['annual_return_pct']:>+8.2f}%")
        print(f"Max Drawdown         : {s['max_drawdown_pct']:>8.2f}%")
        print(f"Transaction Costs    : ₹{s['transaction_costs']:>12,.0f}")

        print("\nTRADE STATISTICS")
        print("-" * 70)
        print(f"Total Trades         : {s['total_trades']:>8}")
        print(f"Win Rate             : {s['win_rate_pct']:>8.2f}%  (target: 40–52%)")
        print(f"Avg Win              : {s['avg_win_pct']:>+8.2f}%")
        print(f"Avg Loss             : {s['avg_loss_pct']:>8.2f}%")
        print(f"Win/Loss Ratio       : {s['wl_ratio']:>8.2f}x  (target: > 2.5×)")
        print(f"Profit Factor        : {s['profit_factor']:>8.2f}  (target: > 1.5)")
        print(f"Avg Days — Winners   : {s['avg_days_winners']:>8.1f}  (target: 15–40)")
        print(f"Avg Days — Losers    : {s['avg_days_losers']:>8.1f}  (target: 4–6)")

        print("\nALL-WEATHER METRICS (Spec Section 7)")
        print("-" * 70)
        exp_flag = '✓' if aw['expectancy'] > 0.25 else '✗'
        pf1_flag = '✓' if aw['profit_factor_r1'] > 1.5 else '✗'
        pf2_flag = '✓' if aw['profit_factor_r2'] > 1.5 else '✗'
        sr_flag  = '✓' if 30 <= aw['stale_trade_ratio_pct'] <= 50 else '✗'
        rf_flag  = '✓' if aw['recovery_factor'] > 3.0 else '✗'
        sl_flag  = '✓' if aw['slippage_cost_pct'] > 0 else '—'

        print(f"Expectancy (R-mult)  : {aw['expectancy']:>8.4f}  {exp_flag} (target: > 0.25)")
        print(f"Profit Factor R1     : {aw['profit_factor_r1']:>8.2f}  {pf1_flag} (target: > 1.5)")
        print(f"Profit Factor R2+Upg : {aw['profit_factor_r2']:>8.2f}  {pf2_flag} (target: > 1.5)")
        print(f"Stale-Trade Ratio    : {aw['stale_trade_ratio_pct']:>7.1f}%  {sr_flag} (target: 30–50%)")
        print(f"Recovery Factor      : {aw['recovery_factor']:>8.2f}  {rf_flag} (target: > 3.0)")
        print(f"Slippage Cost        : {aw['slippage_cost_pct']:>7.2f}%  {sl_flag}")
        print(f"Ideal Return         : {aw['ideal_return']:>+8.2f}%")
        print(f"Actual Return        : {aw['slippage_adjusted_return']:>+8.2f}%")

        # Regime breakdown
        trades        = results['closed_trades']
        r1_trades     = [t for t in trades if t['regime'] == 'R1']
        r2_trades     = [t for t in trades if t['regime'] == 'R2']
        upg_trades    = [t for t in trades if t['regime'] == 'Upgraded']
        r1_time_stops = [t for t in r1_trades if t['exit_reason'] == EXIT_TIME_STOP]
        r2_time_stops = [t for t in r2_trades if t['exit_reason'] == EXIT_TIME_STOP]
        limbo_exits   = [t for t in r2_trades if t['exit_reason'] == EXIT_LIMBO_CAP]
        print(f"\nREGIME BREAKDOWN")
        print("-" * 70)
        print(f"R1 (trend breakout)      : {len(r1_trades):4} trades")
        print(f"  — Time Stop (Day 5)    : {len(r1_time_stops):4} trades")
        print(f"R2 (mean reversion)      : {len(r2_trades):4} trades")
        print(f"  — Day-5 Kill           : {len(r2_time_stops):4} trades")
        print(f"  — Limbo Cap (Day 30)   : {len(limbo_exits):4} trades")
        print(f"Upgraded (R2 → R1)       : {len(upg_trades):4} trades")
        if upg_trades:
            upg_wr  = sum(1 for t in upg_trades if t['profit'] > 0) / len(upg_trades) * 100
            upg_avg = np.mean([t['profit_pct'] for t in upg_trades])
            print(f"  Upgraded win rate      : {upg_wr:.1f}%")
            print(f"  Upgraded avg P&L       : {upg_avg:+.2f}%")

        print("\nVALIDATION GATE — PHASE 7")
        print("-" * 70)
        pos_ret  = s['total_return_pct'] > 0
        exp_ok   = aw['expectancy'] > 0.25
        pf_ok    = s['profit_factor'] > 1.5
        wr_ok    = 40 <= s['win_rate_pct'] <= 52
        dd_ok    = s['max_drawdown_pct'] < 15
        rf_ok    = aw['recovery_factor'] > 3.0

        print(f"  {'✓' if pos_ret else '✗'} Positive total return      : {s['total_return_pct']:+.2f}%")
        print(f"  {'✓' if exp_ok  else '✗'} Expectancy > 0.25 R-mult   : {aw['expectancy']:.4f}")
        print(f"  {'✓' if pf_ok   else '✗'} Profit factor > 1.5        : {s['profit_factor']:.2f}")
        print(f"  {'✓' if wr_ok   else '✗'} Win rate 40–52%            : {s['win_rate_pct']:.2f}%")
        print(f"  {'✓' if dd_ok   else '✗'} Max drawdown < 15%         : {s['max_drawdown_pct']:.2f}%")
        print(f"  {'✓' if rf_ok   else '✗'} Recovery factor > 3.0      : {aw['recovery_factor']:.2f}")

        gate_pass = all([pos_ret, exp_ok, pf_ok, wr_ok, dd_ok, rf_ok])
        print(f"\n  {'PHASE 7 GATE: PASSED ✓' if gate_pass else 'PHASE 7 GATE: FAILED ✗ — review metrics before reporting'}")
        print("=" * 70)

    def save_trade_log(self, results, output_dir=None):
        """Save detailed trade log to CSV."""
        if not results['closed_trades']:
            print("No trades to save.")
            return

        log_dir = Path(output_dir or self.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(results['closed_trades'])
        filepath = log_dir / 'all_weather_p7_step1_trade_log.csv'
        df.to_csv(filepath, index=False)
        print(f"Trade log saved: {filepath} ({len(df)} trades)")
        return filepath


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — run on local machine
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    sys.path.insert(0, r'C:\Projects\trading_engine')

    from data.loader import DataLoader
    from data.vix_loader import load_vix
    from strategies.all_weather.module_a_regime import RegimeClassifier
    from strategies.all_weather.module_b_sector import SectorAlphaFilter

    DATA_DIR     = r'C:\Projects\Backtesting System\data'
    MAPPING_FILE = r'C:\Projects\trading_engine\strategies\all_weather\final_nifty200_sector_mapping.json'
    LOG_DIR      = r'C:\Projects\trading_engine\logs'

    CONFIG = {
        'initial_capital': 100000,
        'start_date'     : '2017-01-01',
        'end_date'       : '2025-12-31',
        'debug'          : False,
        'log_dir'        : LOG_DIR,
    }

    # ── Load data ─────────────────────────────────────────────────────────────
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
    engine = AllWeatherEngine(CONFIG)
    engine.load_price_data(loader, symbol_list)

    print("\nStep 4: Building Module B (Sector Alpha Filter)...")
    sector_filter = SectorAlphaFilter(MAPPING_FILE, engine.price_data)

    # ── Run backtest ──────────────────────────────────────────────────────────
    print("\nStep 5: Running combined R1 + R2 backtest...")
    results = engine.run(regime_classifier, sector_filter)

    # ── Print and save results ────────────────────────────────────────────────
    engine.print_results(results)
    engine.save_trade_log(results, LOG_DIR)
