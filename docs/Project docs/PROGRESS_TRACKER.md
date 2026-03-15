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

## PHASE 1 — DATA INFRASTRUCTURE ✅ COMPLETE

> **Goal:** Ensure all required data streams are available and validated before any module is built.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Build VIX data fetcher — `^INDIAVIX` via yfinance | `[x]` | `vix_loader.py` built. Primary + fallback logic. All 5 validation checks pass on real data. Max single-day jump threshold set to 80% (real VIX spiked 65.6% in COVID crash — valid market behavior). |
| 1.2 | Integrate VIX fetcher into existing loader | `[x]` | Built as standalone `vix_loader.py` — separate from `loader.py` by design. Exposes `load_vix()`, `get_vix_on_date()`, `validate_vix()`. Multi-level yfinance column handling confirmed. |
| 1.3 | Verify Nifty 50 EOD data — confirm EMA200 can be computed cleanly from it | `[x]` | File: `NIFTY_NS.csv` at `C:\Projects\Backtesting System\data`. 2220 rows, 0 missing, 2017-01-02 to 2025-12-31. EMA200 computes cleanly. COVID period: 58/58 days below EMA200 ✓. Volume = 0 throughout — confirmed no impact (index file, volume never used). |
| 1.4 | Load `final_nifty200_sector_mapping.json` — confirm all 200 symbols present | `[x]` | Flat `{symbol: sector}` dict. All 200 `.NS` symbols present. Loaded and read in Phase 0 reconnaissance. Will be consumed directly in Phase 3 (Module B). |
| 1.5 | Validate sector distribution — confirm 17 named sectors + Others bucket (~55–60 stocks) | `[x]` | 18 sectors confirmed: IT, Auto, FMCG, Healthcare, Financial Services, Capital Goods, Metals & Mining, Energy, Power, Telecom, Chemicals, Construction, Construction Materials, Consumer Durables, Consumer Services, Realty, Logistics, Others. Others bucket size to be counted in Phase 3. |
| 1.6 | Confirm all 200 `.NS` symbols return valid yfinance data for full 2017–2025 window | `[!]` | **Known open gap — survivorship bias.** JSON reflects current Nifty 200 composition. Stocks delisted/dropped between 2017–2025 are absent. Backtest results will be mildly optimistic. Accepted limitation — does not block build. |

### Phase 1 — File Outputs
| File | Description |
|------|-------------|
| `vix_loader.py` | India VIX fetcher — primary `^INDIAVIX` + realized vol fallback |
| `indicators.py` | Updated — `calculate_atr()` added, `ATR` column in `add_all_indicators()` |

### Phase 1 — Data Sources Confirmed
| Data | File / Source | Rows | Window | Status |
|------|--------------|------|--------|--------|
| India VIX | `^INDIAVIX` via yfinance | 2205 | 2017-01-02 to 2025-12-30 | ✅ |
| Nifty 50 | `NIFTY_NS.csv` | 2220 | 2017-01-02 to 2025-12-31 | ✅ |
| Nifty 200 stocks | Individual CSVs, existing pipeline | — | 2017–2025 | ✅ |
| Sector mapping | `final_nifty200_sector_mapping.json` | 200 symbols | Static | ✅ |

---

## PHASE 2 — MODULE A: MARKET REGIME CLASSIFIER ✅ COMPLETE

> **Goal:** Produce a reliable daily ON / CAUTION / OFF label for the entire backtest window.
> **Validation Gate:** All 8 data-driven checks passed against real data.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Build regime labelling function using exact OR/AND logic from spec | `[x]` | `classify_regime()` — pure function, no state. Tested all 8 boundary conditions including VIX=22, VIX=25, VIX=25.01 exactly. |
| 2.2 | Implement CAUTION zone: Nifty50 > EMA200 AND VIX 22–25 → 50% size | `[x]` | `Size_Multiplier = 0.5` for CAUTION. Verified: 111/111 CAUTION days correct. |
| 2.3 | Implement OFF zone: Nifty50 < EMA200 OR VIX > 25 → no entries, tighten stops to 1.5×ATR | `[x]` | OR logic confirmed. 338 days price < EMA200 all OFF. 30 days VIX > 40 all OFF. Stop tightening consumed by engine at trade management layer. |
| 2.4 | **VALIDATION:** Spot-check labels against known events | `[x]` | COVID crash (Feb 2020) already OFF before crash bottom — VIX spiked first ✓. Jun 2020 still OFF — price not yet above EMA200 ✓. Jan 2021 CAUTION — price recovered but VIX elevated ✓. Dec 2023 ON ✓. |
| 2.5 | **VALIDATION:** Confirm CAUTION and OFF are mutually exclusive and exhaustive with ON | `[x]` | 0 conflicting days. All three regimes present. Longest OFF run: 89 consecutive days. |

### Phase 2 — Validation Results (Real Data)
| Check | Result |
|-------|--------|
| VIX > 40 days all OFF | 30/30 ✅ |
| VIX < 18 + price > EMA200 all ON | 1465/1465 ✅ |
| Price < EMA200 all OFF | 338/338 ✅ |
| VIX 22–25 + price > EMA200 all CAUTION | 111/111 ✅ |
| No day simultaneously ON and OFF | 0 conflicts ✅ |
| Size multipliers correct for all regimes | 0 errors ✅ |
| Sustained OFF period ≥ 10 consecutive days | 89 days ✅ |
| All three regimes present | ON/CAUTION/OFF ✅ |

### Phase 2 — Regime Distribution (2017–2025)
| Regime | Days | % |
|--------|------|---|
| ON | 1,737 | 78.2% |
| CAUTION | 111 | 5.0% |
| OFF | 372 | 16.8% |

### Phase 2 — File Outputs
| File | Location |
|------|----------|
| `module_a_regime.py` | `strategies/all_weather/` |

---

## PHASE 3 — MODULE B: SECTOR ALPHA FILTER ✅ COMPLETE

> **Goal:** Filter universe to stocks demonstrating relative strength vs. sector peers.
> **Validation Gate:** 40–60% pass rate on at least 3 sample dates — PASSED.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Build 15-day return calculator for all 200 stocks | `[x]` | `compute_15d_return()` — uses actual trading day index, not calendar days. Uses Adj Close for corporate action accuracy. Returns None gracefully for insufficient data. |
| 3.2 | Build sector median logic — group by sector, compute median 15d return per group | `[x]` | `get_eligible_symbols()` — computes sector medians dynamically per date. Pre-computes sector membership lists at init for efficiency. |
| 3.3 | Build Others bucket fallback — compare against Nifty 200 index median | `[x]` | Others stocks compared against median of all available 200 stocks' 15d returns on that date. Confirmed working — 40 stocks in Others bucket. |
| 3.4 | Integrate sector mapping JSON into filter pipeline | `[x]` | `load_sector_mapping()` loads JSON cleanly. 200 symbols, 17 named sectors + Others. 199/200 matched to price data (1 symbol missing CSV — not a blocker). |
| 3.5 | **VALIDATION:** Confirm 40–60% pass rate on at least 3 sample dates | `[x]` | 2018-06-15: 46.0% ✓, 2021-03-15: 46.6% ✓, 2024-06-14: 47.3% ✓. Stable convergence to ~50% as expected by construction. |
| 3.6 | Add `sector_bucket` field to output (Named Sector vs. Others) for post-backtest analysis | `[x]` | `sector_bucket` field present in every eligible stock dict. Required for Observation 2 validation in Phase 7. |

### Phase 3 — Validation Results (Real Data)
| Date | Universe | Passing | Pass Rate |
|------|----------|---------|-----------|
| 2018-06-15 | 161 | 74 | 46.0% ✅ |
| 2021-03-15 | 174 | 81 | 46.6% ✅ |
| 2024-06-14 | 188 | 89 | 47.3% ✅ |

### Phase 3 — Key Observations
| Observation | Detail |
|-------------|--------|
| Others bucket size | 40 stocks (spec estimated 55–60 — actual is lower, not a blocker) |
| Pass rate stability | Converges to ~50% across all dates — mathematically expected (median split) |
| Metals & Mining Jun 2024 | Sector median negative (-1.72%) — filter still correctly passes relative outperformers |
| Others bucket pass rate | 40% on Jun 2024 — slightly lower than named sectors (~50%) |
| Observation 2 deferred | Others vs Named Sector win rate / expectancy comparison deferred to Phase 7 trade log analysis |
| 1 missing symbol | 199/200 symbols matched to price data — 1 CSV missing, not a blocker |

### Phase 3 — File Outputs
| File | Location |
|------|----------|
| `module_b_sector.py` | `strategies/all_weather/` |

---

## PHASE 4 — MODULE C: REGIME 1 (TRENDING) — ISOLATED BACKTEST ✅ COMPLETE (with findings)

> **Goal:** Validate Regime 1 execution logic in isolation.
> **Outcome:** FAILED validation gate — but produced critical structural insights.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Build Donchian Channel breakout entry | `[x]` | Built and tested |
| 4.2 | Build Layer 1 (Initial Stop) | `[x]` | Entry − 3×ATR |
| 4.3 | Build Layer 2 (Breakeven Trigger) | `[x]` | Entry + 1×ATR |
| 4.4 | Build Layer 3 (Chandelier Trailing Stop) | `[x]` | Ratchets UP only |
| 4.5 | Build Layer 4 (Time-Stop) | `[x]` | Multiple iterations — see findings |
| 4.6 | Build ADTV filter | `[x]` | 60-day avg turnover > ₹10 Cr |
| 4.7 | Build circuit breaker logic | `[x]` | Close==Low + Vol<5% avg |
| 4.8 | Build position sizing | `[x]` | Qty = Equity × 0.01 / (3 × ATR) |
| 4.9 | Apply CAUTION zone sizing | `[x]` | 50% multiplier |
| 4.10 | Run Regime 1 isolated backtest | `[x]` | 3 runs across Phase 4.0 and 4.1 |
| 4.11–4.14 | **VALIDATION GATE** | `[✗]` | Gate failed — see findings below |

### Phase 4 — Key Findings
| Run | Time-Stop | Win Rate | W/L | Total Return | Verdict |
|-----|-----------|----------|-----|-------------|---------|
| Phase 4.0 | Day 5 / 0.5×ATR | 24.4% | 3.22× | −57.1% | Stale-Trade Ratio 58% — killing winners |
| Phase 4.1 | Day 8 / price≤entry | 17.2% | 3.94× | −71.8% | Initial Stop exits doubled — entry quality problem |

**Root cause:** Donchian 20-day breakout is a negative expectancy entry for Nifty 200. The "Breakout Trap" — by the time ADX > 25 and price hits a 20-day high, the move is often exhausted. 82% of trades failed. Strategic decision: **disable pure R1 entries permanently. R1 only accessible via R2→R1 upgrade path.**

---

## PHASE 5 — MODULE C: REGIME 2 (MEAN REVERSION) — ISOLATED BACKTEST ✅ COMPLETE (with findings)

> **Goal:** Validate Regime 2 execution logic in isolation.
> **Outcome:** FAILED validation gate — but produced critical structural insights.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Build RSI(2) calculator | `[x]` | Reused from indicators.py |
| 5.2 | Build Regime 2 entry: RSI(2) < 10 AND Close > EMA200 AND ADX < 20 | `[x]` | All 4 filters tested |
| 5.3 | Build primary exit: Daily Close > 10-day SMA (next day open) | `[x]` | No look-ahead bias confirmed |
| 5.4 | Build secondary exit: RSI(2) > 70 (next day open) | `[x]` | First trigger wins |
| 5.5 | Run Regime 2 isolated backtest | `[x]` | 1 run |
| 5.6–5.8 | **VALIDATION GATE** | `[✗]` | Gate failed — see findings below |

### Phase 5 — Key Findings
| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Win Rate | 48.8% | ~60% | ✗ |
| W/L Ratio | 0.99× | ~1.2× | ✗ |
| Avg Days Winners | 1.6 days | ≤15 | ✓ |
| Total Return | −38.3% | Positive | ✗ |

**Root cause:** 77% of trades (957/1233) exited via SMA in median 1 day. RSI(2) < 10 stocks were already sitting just below their SMA10 at entry — any small bounce crossed the exit trigger immediately. Wins of +0.48% avg were smaller than transaction costs. **Fix: Deep Dip filter — Close < SMA10 − 0.75×ATR required at entry.**

---

## PHASE 6 — REGIME UPGRADE TRANSITION (R2 → R1) ✅ COMPLETE

> **Goal:** Validate mid-trade regime upgrade logic.
> **Outcome:** PASSED Phase 6 gate on Phase 6.3. Architecture locked.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 6.1 | Build upgrade trigger: ADX > 20 AND 20-day high (Double-Lock) | `[x]` | Stricter than original spec — requires both conditions simultaneously. ADX lowered from 25 to 20 after diagnostic confirmed 4 additional upgrade candidates. |
| 6.2 | On upgrade: deactivate R2 exits (SMA20, RSI > 70) | `[x]` | Upgrade takes priority over same-day SMA/RSI signals — tested. |
| 6.3 | On upgrade: activate Chandelier anchored to Highest Close Since Entry | `[x]` | Chandelier gated strictly to Upgraded regime — not R2. Bug fixed in Phase 6.1. |
| 6.4 | On upgrade: evaluate Breakeven Trigger immediately | `[x]` | Tested. |
| 6.5 | Confirm Time-Stop excluded from upgraded trades | `[x]` | Day 5 filter skips Upgraded regime. |
| 6.6 | **VALIDATION:** Spot-check upgrade events | `[x]` | Phase 6.3: 1 upgrade, 100% win rate, +14.34% avg P&L. Sample too small for statistical confidence — upgrade frequency to be re-evaluated in Phase 7. |

### Phase 6 — Iteration History
| Version | Key Change | Outcome |
|---------|-----------|---------|
| Phase 6.0 | Deep Dip (SMA10−0.75×ATR) + R2 entry + Chandelier bug | 0 upgrades — Time-Stop killed all trades at Day 5 |
| Phase 6.1 | Day 5 Survival Filter + Day 20 Limbo Cap + Chandelier fix | 3 upgrades (+27.91% avg), gate failed (−0.44% return) |
| Phase 6.2 | SMA20 exit + ADX>20 upgrade + Day 30 Limbo | 4 upgrades — SMA exits faster (1.9 days), pipeline not improved |
| Phase 6.3 | Anchor alignment: SMA20−1.0×ATR entry + SMA20 exit | **GATE PASSED** +6.70%, 6% MDD, positive expectancy |

### Phase 6.3 — Final Architecture (Locked)
| Component | Specification |
|-----------|--------------|
| Entry | RSI(2)<10, Close>EMA200, ADX<20, Close<SMA20−1.0×ATR |
| Entry execution | Next day open |
| Initial Stop | Entry − 3×ATR (intraday) |
| Day 5 filter | PnL<0 → kill; PnL≥0 → Limbo |
| Limbo | Days 6–30, Initial Stop only |
| Day 30 cap | Exit at next open |
| Upgrade trigger | ADX>20 AND Close≥20-day high |
| Post-upgrade | Chandelier from Highest Close Since Entry |
| SMA exit | Close > SMA20 (next open) |
| RSI exit | RSI(2) > 70 (next open) |

### Phase 6.3 — Validated Results
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total Return | +6.70% | Positive | ✅ |
| Annual Return | +0.72% | Positive | ✅ |
| Max Drawdown | 6.00% | <25% | ✅ |
| Expectancy | 0.054R | >0.25R | ⚠️ Positive but below target |
| Profit Factor | 1.37 | >1.5 | ⚠️ Close |
| Win Rate | 62.4% | 40–52% | ⚠️ Above target (mean rev dominant) |
| Trade Count | 109 / 8 years | — | ⚠️ Low — overfitting risk flagged |
| Upgrades | 1 / 8 years | — | ⚠️ Insufficient for tranche split |

### Phase 6 — Strategic Decisions Locked
| Decision | Rationale |
|----------|-----------|
| No tranche split | 1 upgrade in 8 years = insufficient statistical mandate. Revisit if Phase 7 produces ≥10 upgrades. |
| R1 standalone entries were negative expectancy | Confirmed by Phase 4 data — 82% failure rate on Donchian breakouts |
| Deep Dip filter is the core discovery | SMA20−1.0×ATR produces clean geometry, low costs, positive expectancy |

### Phase 6 — File Outputs
| File | Location |
|------|----------|
| `all_weather_engine.py` (Phase 6.3) | `backtesting/` |
| `quant-decision-framework.skill` | Installed in Claude.ai user skills |

---

## PHASE 7 — COMBINED SYSTEM BACKTEST 🔄 NEXT

> **Goal:** Full combined system — R2 engine + R1 engine + Macro filter.
> **Foundation:** Phase 6.3 architecture unchanged. R1 re-enabled as parallel entry path.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 7.0 | Re-enable R1 (Donchian + ADX>25) as parallel entry alongside R2 | `[ ]` | R1 was disabled after Phase 4. Returns as secondary path, not primary. |
| 7.1 | Activate Priority 3 signal ranking — R1 prioritised over R2 in bull market | `[ ]` | Per spec Section 11.3 |
| 7.1a | Run combined backtest — all modules active — 2017–2025 | `[ ]` | Monitor R1 vs R2 contribution separately |
| 7.2 | Compute Metric 1: Expectancy per trade. Target > 0.25R | `[ ]` | |
| 7.3 | Compute Metric 2: Profit Factor separately for R1 and R2. Target > 1.5 globally | `[ ]` | Critical — R1 must not drag down R2 |
| 7.4 | Compute Metric 3: Stale-Trade Ratio. Target 30–50% | `[ ]` | |
| 7.5 | Compute Metric 4: Recovery Factor. Target > 3.0 | `[ ]` | |
| 7.6 | Compute Metric 5: Slippage-Adjusted Return | `[ ]` | |
| 7.7 | **VALIDATION:** All 8 success criteria from spec Section 7.6 | `[ ]` | See gate table above |
| 7.8 | **Observation 1:** R1 additive or dilutive to R2? | `[ ]` | If R1 reduces overall expectancy, disable permanently |
| 7.9 | **Observation 2:** Others bucket vs Named Sector trade quality | `[ ]` | Requires sector_bucket field in trade log |
| 7.10 | **Tranche mandate check:** Count upgrades in combined system | `[ ]` | If ≥10 upgrades, statistical mandate for tranche split exists |

### Phase 7 — Validation Gate (8 criteria)
| Metric | Target | Red Flag |
|--------|--------|----------|
| Expectancy | > 0.25R | Negative |
| Profit Factor (global) | > 1.5 | < 1.0 |
| Win Rate | 40–52% | > 70% |
| Avg Days Winners | 15–40 | < 10 |
| Avg Days Losers | 4–6 | > 10 |
| Max Drawdown | < 15% | > 25% |
| Recovery Factor | > 3.0 | < 2.0 |
| Stale-Trade Ratio (R1) | 30–50% | < 15% |

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
