# Entry Signal Module — One-Page Spec
**Strategy 2: S/R Retest Pullback**
*Version 1.0 | March 2026*

---

## Hypothesis

When price pulls back to a significant S/R zone identified by the detection module, a specific candlestick pattern at that zone confirms two things simultaneously — that the zone is holding and that momentum is resuming. This price action confirmation is the entry trigger. Without it, proximity to an S/R zone is not sufficient reason to enter a trade.

This principle is the foundation of price action trading as documented by Carter (Mastering the Trade, 2005), Brooks (Trading Price Action, 2011), and Nison (Japanese Candlestick Charting Techniques, 1991). All three establish that the confirmation candle is the mechanism that separates a genuine retest from a breakdown.

---

## What the Entry Signal Module Does

The module sits downstream of the S/R detection module. It receives stocks flagged as TESTING or APPROACHING a significant support zone and checks whether a valid price action confirmation pattern has formed at that zone. If yes, it generates an actionable entry signal with specific entry price, stop loss, and target price.

---

## Candidate Input

Stocks where sr_detection.py has generated:
- **BUY** — testing primary support in downtrend
- **ALERT** — approaching primary support in downtrend
- **MONITOR** — testing secondary support

---

## Primary Confirmation Patterns

Calibrated for a 15-45 day holding period on a daily chart. Research basis: Nison (1991), Bulkowski Encyclopedia of Candlestick Charts (2008), Brooks (2011).

Three patterns qualify as primary confirmation — all three signal that buyers stepped in at the zone and overwhelmed sellers:

| Pattern | Definition | Research Basis |
|---|---|---|
| Pin Bar (Hammer) | Candle with small body at the top, long lower wick ≥ 2× body length, closes within the upper 30% of the candle range. Body and close must be at or above the zone boundary. | Nison (1991): hammer at support = rejection of lower prices. Bulkowski (2008): hammer at S/R has 60%+ reversal rate on daily charts. |
| Bullish Engulfing | Current candle's body completely engulfs the prior candle's body. Current candle closes green. Must occur with at least one candle partially inside the zone. | Nison (1991): engulfing pattern = momentum shift. Bulkowski (2008): bullish engulfing at support has 63% reversal rate on daily charts. |
| Inside Bar Breakout | Current candle's range is inside the prior candle's range (inside bar). Entry triggers when next candle breaks above the inside bar high. Signals consolidation at zone followed by resumption. | Brooks (2011): inside bar at S/R = institutional accumulation. Breakout above signals commitment. |

---

## Secondary Confirmation — Indicators (Optional)

Applied only after a primary pattern fires. Does not generate signals independently. Used to filter out low-quality setups if backtesting shows it improves win rate.

| Indicator | Condition | Research Basis |
|---|---|---|
| RSI(14) | RSI between 30-50 at signal date — oversold to neutral zone, not already extended | Wilder (1978): RSI 30-50 = recovery from oversold, momentum not exhausted |
| MACD | MACD line crossing above signal line, or positive divergence at the zone | Appel (2005): MACD crossover at support = momentum confirmation |

Secondary filters are configurable — can be enabled or disabled independently for backtesting.

---

## Entry Price

**Pin Bar and Bullish Engulfing:**
Open of the candle immediately following the confirmation candle.

**Inside Bar Breakout:**
The inside bar forms on day 1. The breakout candle — which closes above the inside bar high — forms on day 2. Entry is on the open of day 3 — the candle immediately following the breakout confirmation candle.

This means the inside bar entry is one additional day later than the pin bar and engulfing entries. This is correct and intentional — the inside bar pattern requires two-step confirmation. Attempting to enter earlier introduces ambiguity about whether the breakout is genuine.

Rationale: Fully systematic, no intraday monitoring required. For a 15-45 day holding period, entry price slippage of 0.2-0.5% versus the confirmation candle close is immaterial relative to the expected move. Can be upgraded to intraday entry once API integration is in place.

---

## Broader Market Filter

No long entry signals are generated when the broader market is in a confirmed downtrend.

**Definition of confirmed downtrend for Nifty 50:**
Nifty 50 closing price is below its 50-day MA on the signal date.

**Rationale:** Minervini's SEPA methodology and O'Neil's CAN SLIM both require the broader market to be in an uptrend or neutral before taking individual stock long entries. When the market index is below its 50-day MA, the headwind on individual stock longs is statistically significant — even strong S/R retest setups fail at higher rates because institutional participants reduce long exposure across the board. Research basis: O'Neil How to Make Money in Stocks — "M" in CAN SLIM stands for Market Direction as the primary filter. Minervini Trade Like a Stock Market Wizard (2013) — market direction filter is the single highest-impact rule for reducing false signals.

**Implementation:**
- Load Nifty 50 daily price data (symbol: ^NSEI or NIFTY_50 depending on data source)
- Compute 50-day MA on signal date
- If Nifty 50 close < 50-day MA: suppress all long entry signals, output MARKET FILTER ACTIVE
- If Nifty 50 close ≥ 50-day MA: proceed normally

**Configurable parameters:**

| Parameter | Default | Backtest Range |
|---|---|---|
| Market index | Nifty 50 | Nifty 50, Nifty 200 |
| Market MA period | 50-day | 50-day, 200-day |
| Filter enabled | TRUE | TRUE / FALSE |

Filter can be disabled for backtesting to measure its impact on win rate independently.

---

## Stop Loss Placement

Below the confirmation candle low OR below the zone low — whichever is lower — plus one ATR(14) × 0.5 buffer.

Rationale: Stop must be below both the confirmation candle and the zone boundary. A stop placed only below the confirmation candle can be taken out by normal zone volatility. The ATR buffer prevents stop-hunting on normal intraday wicks. Research basis: Brooks (2011) — stop below the pattern low plus a volatility buffer is standard for daily chart swing trades.

Formula:
```
stop_loss = min(confirmation_candle_low, zone_low) - (ATR(14) × 0.5)
```

Maximum stop distance: 6% from entry price — enforced as a hard filter. If the computed stop is more than 6% from entry, the setup is rejected. Rationale: 6% per trade stop is consistent with a 12% maximum portfolio drawdown (Strategy 2 exit criterion) with two concurrent positions.

---

## Target Price

Two targets per trade — partial booking at Target 1, hold remainder to Target 2.

**Target 1 — Nearest S/R zone above entry:**
The nearest significant S/R zone above entry price as identified by the detection module. Book 50% of position at this level. Move stop to breakeven on remaining position after Target 1 is hit.

**Target 2 — Next S/R zone above Target 1:**
The next significant S/R zone above Target 1. If no second zone is identified, compute Target 2 as 1.5× risk/reward from entry:
```
target_2 = entry_price + (1.5 × (entry_price - stop_loss))
```

**If no S/R zone exists above entry at all:**
Use minimum 1.5× risk/reward as Target 1 and 2.0× as Target 2.

**No hard minimum RR enforcement at signal generation:**
The relationship between win rate and risk/reward is mathematical — a higher win rate supports a lower RR. Enforcing a hard minimum before backtesting confirms the actual win rate is premature. The 1.5× minimum applies only as a fallback when no S/R zones are available above entry. Backtesting will determine whether the natural targets produce sufficient RR given the actual win rate.

**Partial booking rationale:**
Minervini, O'Neil, and IBD all recommend scaling out of positions at logical price targets. Booking 50% at Target 1 locks in gains while keeping exposure to extended moves. Van Tharp's position sizing research confirms partial exits improve risk-adjusted returns. Moving stop to breakeven after Target 1 eliminates the possibility of a winning trade turning into a loss.

**Configurable parameters:**
- Partial booking percentage at Target 1: default 50%
- Move stop to breakeven after Target 1: default TRUE
- Fallback RR for Target 1 (no zone): default 1.5×
- Fallback RR for Target 2 (no zone): default 2.0×

---

## Signal Output

For each confirmed entry signal:

| Field | Description |
|---|---|
| symbol | NSE symbol |
| signal_date | Date of confirmation candle |
| pattern | Pin Bar / Bullish Engulfing / Inside Bar Breakout |
| entry_price | Open of next candle after confirmation |
| stop_loss | Computed per formula above |
| target_1 | Nearest S/R zone above entry or 1.5× RR fallback |
| target_2 | Next S/R zone above Target 1 or 2.0× RR fallback |
| partial_booking_pct | Percentage to book at Target 1 (default 50%) |
| risk_pct | Stop distance as % of entry price |
| reward_1_pct | Target 1 distance as % of entry price |
| reward_2_pct | Target 2 distance as % of entry price |
| rr_ratio_1 | reward_1_pct / risk_pct |
| rr_ratio_2 | reward_2_pct / risk_pct |
| zone_center | S/R zone that triggered the signal |
| market_filter | PASS / BLOCKED — Nifty 50 above/below 50-day MA |
| rsi_at_signal | RSI(14) value on signal date |
| macd_confirmed | TRUE / FALSE |

---

## Expected Outcome

- Win rate > 55% on confirmed signals — validated by binomial significance test at p ≤ 0.05 against random entry baseline
- Win/loss ratio > 1.5 — structurally enforced by minimum target formula
- Maximum stop distance ≤ 6% — structurally enforced as hard filter at signal generation

---

## Exit Criteria

| Condition | Action |
|---|---|
| Win rate < 55% on in-sample and out-of-sample | Entry pattern logic invalid — redesign required |
| Win rate improves significantly with secondary indicator filters | Enable secondary filters as default |
| Win rate does not improve with secondary filters | Keep strategy as price action only |
| Win rate improves significantly with market filter enabled | Keep market filter as default |
| Win rate does not improve meaningfully with market filter | Make market filter optional |
| RR ratio consistently below 1.5 after fills | Review target placement logic |

---

## Configurable Parameters

| Parameter | Default | Backtest Range |
|---|---|---|
| Min wick/body ratio for pin bar | 2.0× | 1.5×, 2.0×, 2.5× |
| Pin bar close position | Upper 30% of range | Upper 25%, 30%, 40% |
| Min candle size | 0.5× ATR(14) | 0.3×, 0.5×, 0.75× |
| Max stop distance | 6% | 5%, 6%, 8% |
| Partial booking at Target 1 | 50% | 33%, 50%, 75% |
| Move stop to breakeven after T1 | TRUE | TRUE / FALSE |
| Fallback RR for Target 1 | 1.5× | 1.2×, 1.5×, 2.0× |
| Fallback RR for Target 2 | 2.0× | 1.5×, 2.0×, 2.5× |
| Pattern scan lookback | 3 days | 1, 2, 3 |
| RSI period | 14 | 14 |
| RSI range for secondary filter | 30-50 | 25-50, 30-55 |
| Secondary filters enabled | FALSE | TRUE / FALSE |
| Market filter enabled | TRUE | TRUE / FALSE |
| Market MA period | 50-day | 50-day, 200-day |

---

*All thresholds calibrated for 15-45 day holding period on daily chart. Entry on next candle open — no intraday monitoring required. Starting parameters subject to backtest validation.*
