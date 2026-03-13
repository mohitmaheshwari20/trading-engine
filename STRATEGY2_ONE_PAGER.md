# Strategy 2 — One-Page Spec
**S/R Retest Pullback Strategy**
*Version 1.1 | March 2026*

---

## Hypothesis

There is a population of stocks with genuine momentum that Strategy 1 misses because they are temporarily consolidating rather than trending. A pullback strategy targeting S/R retests will identify these stocks and enter when structural confirmation — broken resistance holding as support — distinguishes healthy consolidation from trend reversal.

A stock in genuine consolidation shows three things: price stays within a defined range, volume drops during consolidation indicating sellers are not in control, and the broader trend structure — higher highs, higher lows — remains intact above key moving averages. The S/R retest is the systematic confirmation of this condition.

---

## Expected Outcome

| Metric | Threshold | What it confirms |
|---|---|---|
| Win rate | > 55% | Retest logic is correctly identifying consolidation vs reversal |
| Win/loss ratio | > 1.5 | Tight S/R-defined stops are producing asymmetric risk/reward |
| Signal frequency | Higher than Strategy 1 in sideways markets | Strategy is filling the identified gap |
| Signal overlap with Strategy 1 | < 30% | Strategy is capturing a distinct stock population |

---

## Exit Criteria

| Condition | Threshold | Action |
|---|---|---|
| Win rate | < 55% in both in-sample and out-of-sample | Abandon strategy design |
| Max drawdown | > 12% | Stop placement logic is broken — redesign before proceeding |
| Signal frequency in sideways markets | No increase vs Strategy 1 | Hypothesis is invalid — revisit |
| Profit factor | < 2.0 | Revisit exit logic before proceeding |

---

## Relationship to Strategy 1

Strategy 1 and Strategy 2 are complementary, not competing. Strategy 1 captures multi-month trends from crossover points. Strategy 2 enters existing trends at higher-probability pullback levels during consolidation phases that Strategy 1 misses. The two strategies operate on separate universes and separate capital allocations.

---

## Universe Construction — Layer 1

Nifty 200 membership provides the outer quality floor — NSE's inclusion criteria screens for market cap, liquidity, and trading activity. No additional fundamental filter is applied.

From the Nifty 200, all stocks are ranked by price / 60-day moving average ratio. The top 10% — approximately 20 stocks — form the tradeable universe for that quarter. Universe is refreshed quarterly aligned with NSE Nifty 200 rebalancing.

**Rationale:** Momentum ranking on a quality-floored universe is sufficient. Nifty 200 membership already eliminates speculative and illiquid stocks. Adding a fundamental filter built on unreliable data introduces false precision without improving signal quality.

---

## Entry Logic — Layer 2

1. Stock is in the current quarter's top 10% momentum ranked universe
2. A valid breakout above a significant S/R level is detected
3. Price pulls back to retest the broken resistance level
4. Confirmation that the retest is holding and price is resuming upward — BUY signal

No manual fundamental review at entry. Universe construction handles stock eligibility.

---

*This spec is the foundation for all module design decisions in Strategy 2. Any module whose design cannot be justified against this hypothesis, expected outcome, or exit criteria should be reconsidered before building.*
