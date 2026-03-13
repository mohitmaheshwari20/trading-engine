# NIFTY 200 ALL-WEATHER QUANT — BUILD PROGRESS TRACKER
**Strategy:** Regime-Switching Modular Backtesting System  
**Universe:** NIFTY 200 (NSE India)  
**Backtest Period:** 2017–2025  
**Starting Capital:** ₹1,00,000  
**Spec Version:** 1.0 | March 2026  
**Last Updated:** March 2026

---

## LEGEND
- `[ ]` Not started  
- `[~]` In progress  
- `[x]` Complete  
- `[!]` Blocked / needs decision  

---

## PHASE 0 — CODEBASE RECONNAISSANCE ✅ COMPLETE

> **Goal:** Understand existing architecture before writing a single line. Identify reuse vs. rebuild.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 0.1 | Read `engine.py` — understand main backtest loop and trade execution flow | `[x]` | `Position`, `Portfolio` reusable. `check_exits()` and `execute_entries()` must be fully rewritten for All-Weather. Main loop structure (exits → confirmations → entries → equity) is sound. |
| 0.2 | Read `base_strategy.py` — identify base class structure, filter interface, signal interface | `[x]` | `validate_data()`, `format_signal_output()`, `apply_filters()` reusable. `calculate_position_size()` and `calculate_stop_loss()` are % based — incompatible with ATR sizing, must be overridden. |
| 0.3 | Read `trend_following.py` — understand how previous EMA/ADX strategy was implemented | `[x]` | Reference only. 2-stage WATCH→confirm flow not needed for All-Weather. Useful as structural template. |
| 0.4 | Read `loader.py` — understand data loading interface, what symbols/indices are supported | `[x]` | CSV loader is clean and reusable. Explicitly filters out NIFTY* files — must extend for VIX and index data in Phase 1. |
| 0.5 | Identify reusable components vs. components requiring fresh build | `[x]` | See integration map below. |
| 0.6 | Confirm Nifty 50 EOD data availability in existing pipeline | `[!]` | Cannot confirm without access to local data directory. To be verified in Phase 1 when data fetching is built and tested. |

### Phase 0 — Integration Map (Locked)

| Component | Approach | Reason |
|-----------|----------|--------|
| `indicators.py` | Add `calculate_atr()` only — all else reused as-is | ATR computed internally in `calculate_adx()` but never exposed. Needed everywhere in All-Weather. Pure addition, no existing code touched. |
| `metrics.py` | Untouched — reuse `win_rate`, `profit_factor`, `max_drawdown` | Sufficient for standard metrics. 3 new All-Weather metrics go in separate file. |
| `all_weather_metrics.py` | **New file** — 3 new metrics + R-multiple expectancy | `stale_trade_ratio`, `recovery_factor`, `slippage_adjusted_return` do not exist in current codebase. |
| `all_weather_strategy.py` | **New file** — inherits `BaseStrategy`, overrides sizing and stops | ATR-based sizing and 4-layer stop system incompatible with base class implementations. |
| `all_weather_engine.py` | **New file** — own `Position`, `Portfolio`, main loop | `Position` carries insufficient state (needs regime, ATR at entry, breakeven flag, highest close, trade age, sector, sector_bucket). `check_exits()` must handle 4-layer stops, time-stop, circuit breaker, deferred exits. |
| `base_strategy.py` | **Untouched** | |
| `engine.py` | **Untouched** | Modifying would break existing trend-following strategy. |
| `trend_following.py` | **Untouched** | |

---

## PHASE 1 — DATA INFRASTRUCTURE

> **Goal:** Ensure all required data streams are available and validated before any module is built.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Build VIX data fetcher — `^INDIAVIX` via yfinance | `[ ]` | Fallback: 20-day Realized Vol of Nifty 50 × √252 if unavailable |
| 1.2 | Integrate VIX fetcher into existing loader | `[ ]` | |
| 1.3 | Verify Nifty 50 EOD data — confirm EMA200 can be computed cleanly from it | `[ ]` | |
| 1.4 | Load `final_nifty200_sector_mapping.json` — confirm all 200 symbols present | `[ ]` | |
| 1.5 | Validate sector distribution — confirm 17 named sectors + Others bucket (~55–60 stocks) | `[ ]` | |
| 1.6 | Confirm all 200 `.NS` symbols return valid yfinance data for full 2017–2025 window | `[ ]` | Survivorship bias is a known open gap — note but do not block |

---

## PHASE 2 — MODULE A: MARKET REGIME CLASSIFIER

> **Goal:** Produce a reliable daily ON / CAUTION / OFF label for the entire backtest window.  
> **Validation Gate:** Labels must match known market events before proceeding.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Build regime labelling function using exact OR/AND logic from spec | `[ ]` | ON: Nifty50 > 200EMA AND VIX < 22 |
| 2.2 | Implement CAUTION zone: Nifty50 > 200EMA AND VIX 22–25 → 50% size | `[ ]` | |
| 2.3 | Implement OFF zone: Nifty50 < 200EMA OR VIX > 25 → no entries, tighten stops to 1.5×ATR | `[ ]` | |
| 2.4 | **VALIDATION:** Spot-check labels against known events | `[ ]` | COVID crash (Mar 2020) must show OFF; 2022 correction must show OFF or CAUTION |
| 2.5 | **VALIDATION:** Confirm CAUTION and OFF are mutually exclusive and exhaustive with ON | `[ ]` | |

---

## PHASE 3 — MODULE B: SECTOR ALPHA FILTER

> **Goal:** Filter universe to stocks demonstrating relative strength vs. sector peers.  
> **Validation Gate:** 40–60% pass rate on a sample date.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Build 15-day return calculator for all 200 stocks | `[ ]` | Rolling, computed daily |
| 3.2 | Build sector median logic — group by sector, compute median 15d return per group | `[ ]` | |
| 3.3 | Build Others bucket fallback — compare against Nifty 200 index median | `[ ]` | ~55–60 stocks |
| 3.4 | Integrate sector mapping JSON into filter pipeline | `[ ]` | |
| 3.5 | **VALIDATION:** Confirm 40–60% pass rate on at least 3 sample dates across the backtest window | `[ ]` | If pass rate > 70%, filter is too loose; if < 30%, too restrictive |
| 3.6 | Add `sector_bucket` field to output (Named Sector vs. Others) for post-backtest analysis | `[ ]` | Required for Observation 2 validation |

---

## PHASE 4 — MODULE C: REGIME 1 (TRENDING) — ISOLATED BACKTEST

> **Goal:** Validate Regime 1 execution logic in isolation before combining with Regime 2.  
> **Validation Gate:** Win rate 35–40%, W/L ratio > 2.5×, Stale-Trade Ratio 30–50%, Avg loser days 4–6.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Build Donchian Channel breakout entry — price closes above 20-day high | `[ ]` | ADX(14) > 25 required on entry day |
| 4.2 | Build Layer 1 (Initial Stop): Entry Price − (3 × ATR14) | `[ ]` | Maximum loss anchor |
| 4.3 | Build Layer 2 (Breakeven Trigger): if Price > Entry + 1×ATR → move stop to Entry Price | `[ ]` | |
| 4.4 | Build Layer 3 (Chandelier Trailing Stop): Highest Close Since Entry − (3 × ATR14), ratchet UP only | `[ ]` | Activates once Breakeven is hit; replaces Initial Stop if Chandelier level is higher |
| 4.5 | Build Layer 4 (Time-Stop): if Trade_Age == 5 AND Profit < 0.5×ATR → exit at market open | `[ ]` | Does NOT apply to upgraded R2→R1 trades |
| 4.6 | Build ADTV filter: 60-day Avg Daily Turnover > ₹10 Crores | `[ ]` | ADTV = Avg(Volume × Close) over 60 days |
| 4.7 | Build circuit breaker logic: if Close == Low AND Volume < 5% of 20d Avg Vol → defer exit, 5% slippage on next open | `[ ]` | |
| 4.8 | Build position sizing: Qty = (Equity × 0.01) / (3 × ATR14) | `[ ]` | 3×ATR denominator matches Initial Stop distance — hard 1% risk |
| 4.9 | Apply CAUTION zone sizing: multiply Qty by 0.5 when regime is CAUTION | `[ ]` | |
| 4.10 | Run Regime 1 isolated backtest — 2017–2025 | `[ ]` | Module A and B active; Module C Regime 2 disabled |
| 4.11 | **VALIDATION:** Win rate 35–40% | `[ ]` | |
| 4.12 | **VALIDATION:** W/L ratio > 2.5× | `[ ]` | |
| 4.13 | **VALIDATION:** Stale-Trade Ratio 30–50% of R1 losing trades exited at Day 5 | `[ ]` | If < 15%, Time-Stop not executing |
| 4.14 | **VALIDATION:** Avg loser holding days 4–6 | `[ ]` | If >> 5 days, Time-Stop broken |

---

## PHASE 5 — MODULE C: REGIME 2 (MEAN REVERSION) — ISOLATED BACKTEST

> **Goal:** Validate Regime 2 execution logic in isolation.  
> **Validation Gate:** Win rate ~60%, W/L ratio ~1.2×, no look-ahead bias in SMA exit.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Build RSI(2) calculator | `[ ]` | |
| 5.2 | Build Regime 2 entry: RSI(2) < 10 AND Daily Close > EMA200 AND ADX(14) < 20 | `[ ]` | All three conditions required |
| 5.3 | Build primary exit: Daily Close crosses above 10-day SMA (closing price only, not intraday) | `[ ]` | Exit executed at next day's open |
| 5.4 | Build secondary exit: RSI(2) > 70 → snap-back rally exit | `[ ]` | First trigger wins |
| 5.5 | Run Regime 2 isolated backtest — 2017–2025 | `[ ]` | Module A and B active; Module C Regime 1 disabled |
| 5.6 | **VALIDATION:** Win rate ~60% | `[ ]` | |
| 5.7 | **VALIDATION:** W/L ratio ~1.2× | `[ ]` | |
| 5.8 | **VALIDATION:** No look-ahead bias — SMA exit uses only data available at close of exit day | `[ ]` | |

---

## PHASE 6 — REGIME UPGRADE TRANSITION (R2 → R1)

> **Goal:** Validate mid-trade regime upgrade logic — a R2 trade becoming a R1 trend trade.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 6.1 | Build upgrade trigger: live R2 trade ADX(14) rises above 25 on any daily close | `[ ]` | |
| 6.2 | On upgrade: immediately deactivate R2 exits (10-day SMA, RSI > 70) | `[ ]` | |
| 6.3 | On upgrade: activate Chandelier Stop anchored to Highest Close Since Entry (not upgrade-moment price) | `[ ]` | Critical — must protect profit accrued in R2 phase |
| 6.4 | On upgrade: evaluate Breakeven Trigger immediately at upgrade moment | `[ ]` | |
| 6.5 | Confirm Time-Stop (Layer 4) is excluded from upgraded trades | `[ ]` | |
| 6.6 | **VALIDATION:** Spot-check 3–5 upgrade events — confirm Chandelier anchors to highest close since original entry | `[ ]` | |

---

## PHASE 7 — COMBINED SYSTEM BACKTEST

> **Goal:** Full system backtest with all modules active. Compute all 5 reporting metrics. Validate all 8 success criteria.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 7.1 | Run combined backtest — all modules active — 2017–2025 | `[ ]` | |
| 7.2 | Compute Metric 1: Expectancy per trade — E = (Win% × Avg Win) − (Loss% × Avg Loss). Target > 0.25 | `[ ]` | |
| 7.3 | Compute Metric 2: Profit Factor separately for R1 and R2. Target > 1.5 globally | `[ ]` | Must be computed independently per regime |
| 7.4 | Compute Metric 3: Stale-Trade Ratio — % of R1 losers exited at Day 5. Target 30–50% | `[ ]` | |
| 7.5 | Compute Metric 4: Recovery Factor — Net Profit / Max Drawdown. Target > 3.0 | `[ ]` | |
| 7.6 | Compute Metric 5: Slippage-Adjusted Return vs. ideal execution. Target difference > 15% | `[ ]` | If difference < 15%, circuit logic may not be functioning |
| 7.7 | **VALIDATION:** All 8 success criteria from spec Section 7.6 met | `[ ]` | See table below |
| 7.8 | **Observation 1:** Compute actual failure rate of R1 breakouts at Day 5 mark | `[ ]` | Validate 65% failure claim; adjust Time-Stop threshold if data disagrees |
| 7.9 | **Observation 2:** Compare win rate and expectancy — Others bucket vs. Named Sector trades | `[ ]` | Requires `sector_bucket` field in trade log (Phase 3.6) |

### Success Criteria Reference
| Metric | Target | Red Flag |
|--------|--------|----------|
| Expectancy per Trade | > 0.25 | Negative or near zero |
| Profit Factor (Global) | > 1.5 | < 1.0 |
| Win Rate (Overall) | 40–52% | > 70% (look-ahead bias) |
| Avg Days — Winners | 15–40 days | < 10 days |
| Avg Days — Losers | 4–6 days | > 10 days |
| Max Drawdown | < 15% | > 25% |
| Recovery Factor | > 3.0 | < 2.0 |
| Stale-Trade Ratio (R1) | 30–50% of R1 losers | < 15% |

---

## PHASE 8 — REPORTING

> **Goal:** Clean, structured output that enables per-regime analysis and post-backtest decisions.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 8.1 | Build trade log with all required fields: entry date, exit date, symbol, regime, sector, sector_bucket, entry price, exit price, P&L, exit reason, trade age, ATR at entry | `[ ]` | |
| 8.2 | Build per-regime performance summary (R1 vs R2 vs Upgraded) | `[ ]` | |
| 8.3 | Build equity curve output | `[ ]` | |
| 8.4 | Build drawdown chart | `[ ]` | |
| 8.5 | Output final performance report with all 5 metrics and 8 success criteria clearly flagged PASS/FAIL | `[ ]` | |

---

## OPEN OBSERVATIONS (Post-Backtest)

| # | Observation | Action Required |
|---|-------------|-----------------|
| O1 | Time-Stop Day-5 threshold calibration | After first combined run: filter all R1 losers, compute % exited at Day 5, compute forward return of survivors. Adjust threshold if mis-calibrated. |
| O2 | Others bucket filter efficacy | Compare win rate and expectancy: Others vs. Named Sector trades. If Others systematically underperform, consider exclusion or manual reclassification. |

---

## KNOWN OPEN GAPS (Not blocking build)

| Gap | Notes |
|-----|-------|
| Survivorship bias | yfinance universe reflects current Nifty 200 composition. Stocks delisted between 2017–2025 are absent. Known limitation — do not block. |
| Point-in-time data | Sector membership and index composition treated as static. Known limitation. |
| Intra-quarter breakdown rules | Not defined in spec. Defer. |

---

## CANONICAL PARAMETER REFERENCE

| Parameter | Value | Source |
|-----------|-------|--------|
| EMA (trend filter) | 200-day | Module A |
| VIX ON threshold | < 22 | Module A |
| VIX CAUTION range | 22–25 | Module A |
| VIX OFF threshold | > 25 | Module A |
| Sector lookback | 15 trading days | Module B |
| ADX period | 14 | Module C |
| Regime 1 ADX threshold | > 25 | Module C |
| Regime 2 ADX threshold | < 20 | Module C |
| Neutral zone ADX | 20–25 (no new entries) | Module C |
| Donchian channel | 20-day high | Module C R1 |
| ATR period | 14 | Module C |
| Initial Stop | Entry − 3×ATR | Module C R1 Layer 1 |
| Breakeven trigger | Entry + 1×ATR | Module C R1 Layer 2 |
| Chandelier multiplier | 3×ATR | Module C R1 Layer 3 |
| Time-Stop age | 5 days | Module C R1 Layer 4 |
| Time-Stop profit hurdle | 0.5×ATR | Module C R1 Layer 4 |
| OFF state trailing stop | 1.5×ATR | Module A |
| RSI period (R2) | 2 | Module C R2 |
| RSI entry threshold | < 10 | Module C R2 |
| RSI exit threshold | > 70 | Module C R2 |
| SMA exit period | 10-day | Module C R2 |
| ADTV filter | > ₹10 Crores | Module D |
| ADTV lookback | 60 trading days | Module D |
| Circuit trigger Vol | < 5% of 20d Avg Vol | Module D |
| Circuit slippage | 5% on next open | Module D |
| Position risk | 1% of equity | Module D |
| Sizing denominator | 3×ATR | Module D |
| Caution size factor | 50% | Module A |
| Starting capital | ₹1,00,000 | Backtest config |
| Backtest window | 2017–2025 | Backtest config |
