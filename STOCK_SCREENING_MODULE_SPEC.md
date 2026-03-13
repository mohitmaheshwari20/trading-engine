# Stock Screening Module - Specification
**Version:** 2.0
**Date:** March 2026
**Status:** Approved - Phase 1 Complete, Proceeding to Phase 2

---

## Purpose

The Stock Screening Module provides a repeatable, forward-looking process to identify stocks with trending characteristics suitable for the trend following trading engine. It replaces the static curated 30-stock universe (selected with hindsight) with a systematic, periodically refreshed candidate list.

Universe robustness testing proved the strategy completely fails on random stock selection (0/30 random Nifty 200 samples beat benchmark). This module closes that critical gap before real capital deployment.

---

## Problem Statement

The current curated 30-stock universe was identified with full knowledge of 2017-2025 outcomes (survivorship bias). It cannot be used as-is in live trading because:
1. No principled method to decide which stocks to add/remove in future
2. Stocks that drove performance may stop trending
3. New trending opportunities will be missed

---

## Design Principles

- Forward-looking only: all screening criteria use data observable at the time of the screen
- Configurable universe: input stock universe is file-driven, not hardcoded. Default is Nifty 200
- Tool-assisted, not tool-dependent: Chartink for signals, Python for intersection/ranking/validation
- Periodic refresh: Nifty 200 list refreshed quarterly, aligned with NSE rebalancing
- Phased delivery: go/no-go gates at each phase before proceeding

---

## Screening Criteria (3 Active Components)

### Component 1 - Trend Quality (Chartink, free tier)

| Condition | Parameter | Rationale |
|---|---|---|
| ADX > 20 | 14-day period | Confirms trend is strong enough to trade |
| EMA 20 > EMA 50 | Daily close | Short-term momentum above medium-term |
| Close > EMA 200 | Daily close | Confirms long-term uptrend alignment |

Phase 1 Validation Result: 369 stocks pass on NSE cash segment. CSV export confirmed working on free tier.

### Component 2 - Liquidity (Nifty 200 membership)
Nifty 200 membership implicitly guarantees minimum liquidity and market cap. No separate volume threshold required. The universe file acts as the liquidity gate.

### Component 3 - Price History (Nifty 200 membership)
Nifty 200 stocks have sufficient listing history for EMA and ADX to be statistically reliable. No separate minimum-days filter required.

### Component 4 - Fundamental Quality - REMOVED in v2.0
See Decision Record section below.

---

## Decision Record - Removal of Component 4 (Fundamental Quality)

### Decision
Component 4 (Fundamental Quality screening) has been removed from the active screening pipeline effective Version 2.0.

### Context
The original design required fundamental filters (revenue growth, operating cash flow, debt levels, ROE, interest coverage) sourced from a third-party tool. During Phase 1 validation, the following tools were evaluated:

| Tool | Outcome |
|---|---|
| Screener.in | Data visible on free tier. CSV export requires premium (Rs 4,999/year) |
| Tijori Finance | Paid subscription required |
| Tickertape | EMA 20 filter absent - cannot replicate strategy parameters. Export moot |
| Trendlyne | Paid subscription required for meaningful fundamental access |

All tools with adequate fundamental data quality require paid subscriptions.

### Rationale for Removal
1. Strategy is unvalidated - still in experimental/validation phase. Paying for tooling before Phase 3 confirms the strategy works is not justified
2. Cost principle - tooling investment is only justified after proof of concept. Validation must precede infrastructure spend
3. Partial mitigation exists - Nifty 200 membership provides a meaningful quality baseline. NSE index inclusion criteria require minimum market cap, liquidity, and listing history. Severely distressed companies tend to exit the index before complete collapse
4. Hybrid approach available - manual fundamental sanity check is feasible at quarterly refresh and addresses the highest-risk scenarios without automation

### What Changes
- Component 4 removed from active pipeline
- Screener.in removed from automated tool stack
- Phase 2 Python script intersects Chartink output with Nifty 200 only - no fundamental CSV required
- Manual hybrid sanity check introduced for Phase 4 live deployment

### Hybrid Mitigation (Phase 4 onwards)
Before each quarterly deployment, manually review top 5-10 most distressed-looking stocks from the final intersection list using Screener.in free tier. Data (revenue, cash flow, debt, ROE, interest coverage) is visible on free tier - only CSV export is paywalled. This catches obvious blow-up candidates without requiring a paid subscription.

Specific items to check manually:
- Interest coverage < 1.5 (cannot service debt from operations)
- Negative operating cash flow for 2+ consecutive years
- Revenue declining for 2+ consecutive years
- Promoter pledge > 20%

### Reversibility
This decision is reversible. If Phase 3 shows unacceptable results (high distressed-stock failures, poor Sharpe), Component 4 can be reintroduced. Phase 3 evidence will justify the tooling cost at that point.

---

## Tool Stack

| Role | Tool | Cost |
|---|---|---|
| Technical screen (C1) | Chartink | Free |
| Universe file (C2, C3) | Nifty 200 CSV from NSE | Free |
| Intersection + ranking + validation | Python | Free |
| Manual fundamental sanity check (live deployment only) | Screener.in free tier | Free |

---

## Python Module Responsibilities

Python does NOT replace Chartink. It handles:

1. Intersection - takes Chartink CSV output and filters against Nifty 200 universe file
2. Ranking - ranks surviving stocks by trend quality score (ADX value, percentage above EMA 200, or composite score - exact formula agreed before build)
3. Output - produces clean ranked candidate list (format agreed before build)
4. Universe file refresh utility - helper script to update Nifty 200 symbols file from NSE index constituent CSV
5. Historical validation - replays screening logic quarterly from 2017-2025

Expected outcome: A ranked list of 30-40 stocks passing all 3 active components, ready for trading engine consumption.

---

## Delivery Phases

### Phase 1 - Manual Screening Workflow Validation COMPLETE
- Chartink scan built and validated: ADX > 20, EMA20 > EMA50, Close > EMA200
- Result: 369 stocks pass on NSE cash segment
- CSV export confirmed working on Chartink free tier
- Nifty 200 symbols file created: nifty200_symbols.txt
- Fundamental screening tools evaluated - all paid. Component 4 removed.

### Phase 2 - Python Intersection and Ranking Script
Goal: Build Python module that takes Chartink CSV and intersects with Nifty 200 universe.

Inputs:
- Chartink CSV export: Stock_Screener.csv
- Nifty 200 universe file: nifty200_symbols.txt

Deliverables:
- Script to load Chartink CSV + universe file
- Intersection logic
- Ranking logic (trend quality score - formula agreed before build)
- Clean output CSV (format agreed before build begins)
- Universe file refresh utility

Go/No-Go: Ranked output contains at least 20 stocks and includes recognisable names from curated 30.

### Phase 3 - Historical Validation (MANDATORY before real capital)
Goal: Validate screening methodology would have produced a good universe historically.

Method:
- Replay screening logic quarterly from 2017-2025 using historical price data
- For each quarterly snapshot, identify which stocks would have passed all 3 components
- Run trading engine on each quarterly-refreshed universe
- Compare to: (a) static curated 30 baseline, (b) Nifty 50 benchmark

Go/No-Go Thresholds:
| Metric | Threshold | Action if not met |
|--------|-----------|-------------------|
| Annual return | > 15% | Revisit screening criteria |
| Sharpe ratio | > 0.8 | Revisit screening criteria |
| Max drawdown | < 30% | Flag for review - not a hard stop |

If threshold not met: revisit criteria. One iteration cycle budgeted.
If second revision also fails: pause and reassess entire strategy. No capital deployment.

### Phase 4 - Quarterly Refresh Workflow
Goal: Establish the repeatable process for running the screen every quarter.

Deliverables:
- Step-by-step quarterly refresh procedure
- Decision rules for universe transitions (open positions in stocks exiting screen)
- Universe change log format
- Manual fundamental sanity check on top 5-10 flagged stocks before deployment
- Sector concentration check: if > 40% of selected stocks from single sector, apply manual cap

Fallback rule: If intersection returns < 20 stocks, do not deploy that quarter.

### Phase 5 - Integration with Trading Engine
Goal: Connect Stock Screening Module output to trading engine.

Deliverables:
- Trading engine reads universe from screening module output file (not hardcoded list)
- Universe update mechanism - engine handles mid-quarter additions/removals gracefully
- Integration test passes. Paper trading begins using screened universe.

---

## Risk Register

### Risk 1 - Financially Distressed Stock Passing Technical Screen
Rank: HIGH

Description: A technically trending stock may be in financial distress. A bad earnings announcement can cause a 20-40% gap down that stop losses cannot protect against.

Impact: One such event on a Rs 75,000 portfolio can wipe 2-3 years of accumulated gains. Stop losses do not protect against overnight gap downs triggered by earnings shocks.

Mitigation:
1. Nifty 200 membership as quality gate - severely distressed companies tend to exit the index before complete collapse
2. Manual fundamental sanity check before each quarterly deployment (Phase 4 onwards) - check interest coverage, operating cash flow, and promoter pledge on Screener.in free tier for top 5-10 suspicious-looking stocks
3. Position sizing cap - no single stock to exceed 5-10% of total portfolio
4. Accept residual risk as a known limitation of technical-only approach

---

### Risk 2 - Speculative / Operator-Driven Momentum Passing Screen
Rank: HIGH (mitigated to MEDIUM by Nifty 200 membership)

Description: A stock trends on manipulation or speculative momentum rather than business fundamentals. Technical indicators cannot distinguish genuine trend from operator-driven price action. Reversal is sharp and without warning.

Impact: Sharp reversal with no technical warning. Stop losses are the only protection and may be bypassed by gap-down opens.

Mitigation:
1. Nifty 200 membership significantly reduces this risk - institutional participation required for index inclusion, pure operator-driven stocks unlikely to qualify
2. Stop losses in trading engine provide damage control
3. Residual risk accepted - cannot be fully eliminated with technical-only approach

---

### Risk 3 - Business Deterioration Preceding Technical Breakdown
Rank: MEDIUM

Description: Fundamental problems surface in financial statements 1-2 quarters before price reacts. Technical indicators lag business reality. Strategy may hold a deteriorating stock for a full quarter before technical signal turns negative.

Impact: Larger-than-expected losses on individual positions during the lag window. Particularly damaging for high-debt companies in earnings downturns.

Mitigation:
1. Quarterly refresh - stocks underperforming technically likely to fail screen at next quarterly review
2. Stop losses in trading engine limit damage during the lag window
3. Manual fundamental check before each quarterly deployment catches deteriorating companies before re-entry after a stop-out

---

### Risk 4 - Sector Concentration
Rank: MEDIUM

Description: Entire sector trends on macro tailwind - multiple stocks from same sector pass technical screen simultaneously. Sector-level reversal hits all positions at once, creating correlated drawdown that individual stop losses cannot contain.

Impact: Portfolio drawdown far exceeds what single-stock stop losses would suggest. Recovery is slow because multiple positions exit simultaneously.

Mitigation:
1. At each quarterly refresh, check sector distribution of intersection output
2. If > 40% of selected stocks from a single sector, exclude lowest-ranked stocks in that sector until below 40%
3. Document sector distribution in quarterly refresh log for audit trail
4. Codify as a mandatory Phase 4 quarterly refresh step

---

### Risk 5 - Regime Change Between Backtest and Live Deployment
Rank: MEDIUM

Description: Strategy performs well in historical backtests (2017-2025) but underperforms live due to market regime change. Backtests cannot fully anticipate future regimes. Technical-only screened universe may be more sensitive to regime shifts than a fundamentally filtered universe.

Impact: Difficult to detect until real capital is at risk.

Mitigation:
1. Phase 3 historical validation across 2017-2025 covers multiple regime types - 2017-2018 bull market, 2020 COVID crash, 2022 correction, 2023-2024 recovery
2. Deploy minimum capital first (Rs 50,000 not Rs 75,000) for first live quarter
3. Run one full quarter paper trading vs live before increasing capital
4. Phase 3 go/no-go gate is the primary safeguard against this risk

---

### Risk 6 - High-Debt Companies Amplifying Losses in Bear Markets
Rank: LOW (standalone) -> HIGH (in prolonged bear market)

Description: Low-ROE, high-debt companies can trend strongly in bull markets and pass all technical filters. In a prolonged bear market or credit crunch, these companies amplify losses significantly beyond what technical stop losses can protect.

Impact: Manageable in normal market conditions. Severe in sustained bear markets or black swan credit events.

Mitigation:
1. Nifty 200 membership as proxy quality gate - highly leveraged companies with weak business models tend to underperform index inclusion criteria over time
2. Position sizing caps limit the absolute loss from any single position
3. Stop losses in trading engine provide the exit mechanism
4. Manual fundamental check at quarterly deployment - debt-to-equity and interest coverage visible on Screener.in free tier without paid subscription
5. Accept as a known, documented limitation of the technical-only approach

---

## Alternatives Considered

### Alternative 1 - Pay for Screener.in Premium (Rs 4,999/year)
Description: Subscribe to Screener.in premium to unlock CSV export. Reintroduce Component 4 with full fundamental filter automation.

Pros:
- Closes Risks 1 and 6 completely
- Fully automated quarterly workflow
- Screener.in has deepest fundamental data for Indian equities
- Rs 415/month small relative to Rs 50,000-75,000 capital deployment

Cons:
- Strategy is unvalidated. Spending on tooling before Phase 3 confirmation is premature
- If Phase 3 fails, the subscription is wasted

Decision: DEFERRED. Revisit after Phase 3 if strategy is confirmed viable.

---

### Alternative 2 - Build Fundamental Filter in Python using yfinance
Description: Use yfinance Python library (free) to pull fundamental data for Nifty 200 stocks directly in the screening script.

Pros:
- Fully free, no subscription required
- Automated, no manual tool steps
- Integrates directly into Python screening pipeline

Cons:
- yfinance pulls from Yahoo Finance which has known data quality issues for Indian stocks - missing values, stale data, inconsistent formatting
- Data reliability for NSE-listed companies unverified - requires validation before trusting in production
- Additional development effort to build, validate, and maintain
- Yahoo Finance has changed its API before without notice

Decision: VIABLE option worth a one-day spike to assess data quality. Not pursued in Phase 1 due to unverified reliability.

---

### Alternative 3 - Use Nifty 200 Membership as Full Quality Proxy (ADOPTED)
Description: Drop Component 4 entirely. Rely on Nifty 200 membership as the quality gate. Screen only on technical indicators.

Pros:
- Fully free, no subscription, no data quality risk
- Simple and repeatable
- Nifty 200 membership provides meaningful quality baseline
- Fastest path to Phase 3 historical validation

Cons:
- Does not filter out distressed stocks still in the index
- Increases exposure to Risks 1, 3, and 6

Decision: ADOPTED for Phase 1-3. Manual hybrid sanity check introduced as partial mitigation for live deployment.

---

### Alternative 4 - Manual Fundamental Check on Full Intersection
Description: After generating Chartink + Nifty 200 intersection, manually check fundamentals for every stock using Screener.in free tier before finalising universe.

Pros:
- Free - Screener.in free tier shows all fundamental data
- Fully addresses Risks 1, 3, and 6

Cons:
- If intersection returns 40-60 stocks, checking each manually takes 3-4 hours per quarter
- Introduces human judgment as a variable - makes strategy harder to replicate and backtest
- Selection bias: manually rejecting stocks introduces a non-systematic variable that cannot be backtested

Decision: NOT adopted as primary approach. Lighter version (checking only top 5-10 most distressed-looking stocks) adopted as hybrid mitigation in Phase 4.

---

## Known Gaps

| Gap | Severity | Notes |
|---|---|---|
| Survivorship bias in Nifty 200 list | High | Current list excludes stocks that dropped out historically. Phase 3 replay affected. Document in backtest results. |
| Point-in-time screening for Phase 3 | High | Chartink shows today's screen, not historical. Phase 3 approximates by applying current criteria to historical price data. |
| Position sizing not defined | Medium | Equal weight vs momentum-ranked not yet decided. Must define before Phase 3. |
| Intra-quarter breakdown rules | Medium | If stock breaks down mid-quarter, exit rule currently undefined. |
| Sector concentration rule | Medium | Defined as 40% cap but not yet codified in Python. Phase 4 task. |
| Execution slippage | Low | Backtests assume clean entry/exit. Quantify during Phase 4 live vs paper comparison. |

---

## Overall Risk Assessment

Technical-only screening is acceptable for validation phase (Phase 1-3):
- Nifty 200 membership provides a meaningful quality baseline
- Stop losses in the trading engine provide damage control
- Capital deployment is small - absolute loss exposure is limited
- Phase 3 go/no-go gate prevents capital deployment if strategy does not hold up

Technical-only screening requires hybrid mitigation for live deployment (Phase 4-5):
- Manual fundamental sanity check before each quarterly deployment
- Sector concentration monitoring and capping at 40%
- Position sizing limits: no single stock > 5-10% of portfolio

---

## Periodic Universe Refresh (Nifty 200 List)

Refresh frequency: Quarterly (aligned with NSE rebalancing - typically March/June/September/December)

Process:
1. Download latest Nifty 200 constituent list from NSE website (publicly available CSV)
2. Run universe refresh utility script to update nifty200_symbols.txt
3. Note any additions/removals and assess impact on current holdings

---

## Out of Scope

- Shorting / short-side screening
- Intraday or weekly screening (quarterly only)
- Options or derivatives universe
- US or global equities
- Automated execution of trades based on screen output

---

## Working Model

- For every step: agree on output format before locking in
- For every Python build: agree on specs before writing code
- No surprises mid-build
