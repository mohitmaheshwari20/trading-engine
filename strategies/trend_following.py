import pandas as pd
import numpy as np
import sys
sys.path.append('..')

from strategies.base_strategy import BaseStrategy
from data.indicators import TechnicalIndicators

class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following Strategy - Version 3 (Direct Entry)

    ENTRY LOGIC:
    BUY signal generated when ALL conditions met on crossover day:
        1. EMA20 crosses above EMA50 (bullish crossover)
        2. ADX > threshold (default 20)
        3. Price above EMA200 (long-term uptrend filter)

    EXIT LOGIC:
    Sell when ANY condition met:
        1. EMA20 crosses below EMA50 (bearish crossover)
        2. Stop loss hit (15% below entry price)
    """

    def __init__(self, config):
        self.ema_fast_period   = config.get('ema_fast_period', 20)
        self.ema_slow_period   = config.get('ema_slow_period', 50)
        self.ema_long_period   = config.get('ema_long_period', 200)
        self.adx_period        = config.get('adx_period', 14)
        self.adx_threshold     = config.get('adx_threshold', 20)
        self.trailing_stop_pct = config.get('trailing_stop_pct', 0.15)

        # Required for engine indicator pre-calculation compatibility
        self.rsi_period = config.get('rsi_period', 14)
        self.bb_period  = config.get('bb_period', 20)
        self.bb_std_dev = config.get('bb_std_dev', 2)

        super().__init__(config)

    def get_strategy_name(self):
        return f"Trend Following v3 - EMA({self.ema_fast_period}/{self.ema_slow_period}) + ADX + EMA200"

    def generate_signals(self, df, debug=False):
        """
        Generate BUY or SELL signals for the latest day.

        BUY:  EMA20 crosses above EMA50 + ADX > threshold + Price above EMA200
        SELL: EMA20 crosses below EMA50

        Returns DataFrame with Signal, Signal_Strength, Signal_Reason columns.
        """
        is_valid, error = self.validate_data(df)
        if not is_valid:
            raise ValueError(f"Invalid data: {error}")

        df = df.copy()

        # Add indicators if not already present
        if 'EMA_Fast' not in df.columns or 'ADX' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(
                df,
                ema_fast=self.ema_fast_period,
                ema_slow=self.ema_slow_period,
                adx_period=self.adx_period
            )

        # Add EMA200 if not present
        if 'EMA_200' not in df.columns:
            df['EMA_200'] = df['Adj Close'].ewm(span=self.ema_long_period, adjust=False).mean()

        # Initialise signal columns
        df['Signal']          = self.SIGNAL_HOLD
        df['Signal_Strength'] = 0.0
        df['Signal_Reason']   = ''

        # EMA difference for crossover detection
        df['EMA_Diff']      = df['EMA_Fast'] - df['EMA_Slow']
        df['Prev_EMA_Diff'] = df['EMA_Diff'].shift(1)

        latest_idx = df.index[-1]
        latest     = df.loc[latest_idx]

        # Skip if indicators not ready
        if pd.isna(latest['EMA_Fast']) or pd.isna(latest['EMA_Slow']) or \
           pd.isna(latest['ADX'])      or pd.isna(latest['EMA_200']):
            return df

        bullish_crossover = (latest['EMA_Diff'] > 0) and (latest['Prev_EMA_Diff'] <= 0)
        bearish_crossover = (latest['EMA_Diff'] < 0) and (latest['Prev_EMA_Diff'] >= 0)

        # ── BUY signal ────────────────────────────────────────────────────────
        if bullish_crossover:
            buy, strength, reason = self._check_buy_conditions(latest, debug)
            if buy:
                df.loc[latest_idx, 'Signal']          = self.SIGNAL_BUY
                df.loc[latest_idx, 'Signal_Strength'] = strength
                df.loc[latest_idx, 'Signal_Reason']   = reason
                if debug:
                    print(f"  [{latest['Date']}] BUY signal → {reason}")

        # ── SELL signal ───────────────────────────────────────────────────────
        elif bearish_crossover:
            sell, strength, reason = self._check_sell_conditions(latest, debug)
            if sell:
                df.loc[latest_idx, 'Signal']          = self.SIGNAL_SELL
                df.loc[latest_idx, 'Signal_Strength'] = strength
                df.loc[latest_idx, 'Signal_Reason']   = reason
                if debug:
                    print(f"  [{latest['Date']}] SELL signal → {reason}")

        return df

    def _check_buy_conditions(self, row, debug=False):
        """
        Check BUY conditions.

        Conditions:
            1. EMA20 crossed above EMA50 — confirmed by caller
            2. ADX > threshold
            3. Price above EMA200

        Returns:
            tuple: (buy, strength, reason)
        """
        # Condition 2: ADX strength
        if row['ADX'] < self.adx_threshold:
            if debug:
                print(f"    BUY rejected: ADX {row['ADX']:.1f} < {self.adx_threshold}")
            return False, 0.0, ""

        # Condition 3: Price above EMA200
        if row['Adj Close'] < row['EMA_200']:
            if debug:
                print(f"    BUY rejected: Price {row['Adj Close']:.2f} below EMA200 {row['EMA_200']:.2f}")
            return False, 0.0, ""

        # Signal strength
        adx_strength = min((row['ADX'] - self.adx_threshold) / 50, 1.0)
        gap_pct      = abs(row['EMA_Diff']) / row['Adj Close']
        gap_strength = min(gap_pct * 100, 1.0)
        strength     = max(0.1, min((adx_strength + gap_strength) / 2, 1.0))

        reason = (f"BUY: EMA bullish crossover — "
                  f"EMA{self.ema_fast_period}={row['EMA_Fast']:.2f} crossed above "
                  f"EMA{self.ema_slow_period}={row['EMA_Slow']:.2f}, "
                  f"ADX={row['ADX']:.1f}, Price above EMA200")

        return True, strength, reason

    def _check_sell_conditions(self, row, debug=False):
        """
        Check SELL conditions — bearish EMA crossover.

        Returns:
            tuple: (sell, strength, reason)
        """
        crossover_gap_pct = abs(row['EMA_Diff']) / row['Adj Close']
        gap_strength      = min(crossover_gap_pct * 100, 1.0)
        strength          = max(gap_strength, 0.5)

        reason = (f"SELL: EMA bearish crossover — "
                  f"EMA{self.ema_fast_period}={row['EMA_Fast']:.2f} crossed below "
                  f"EMA{self.ema_slow_period}={row['EMA_Slow']:.2f}")

        return True, strength, reason
