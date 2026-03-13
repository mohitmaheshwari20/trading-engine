# S/R Detection Module — One-Page Spec
**Strategy 2: S/R Retest Pullback**
*Version 1.0 | March 2026*

---

## Hypothesis

Price levels where significant historical buying or selling activity occurred act as memory points in the market. When price returns to these levels, institutional participants who previously traded there will trade again — creating predictable support or resistance. This is the foundational principle of Wyckoff's price cycle theory (1930s), validated empirically by Edwards and Magee (1948) and confirmed in modern market microstructure research by Lo, Mamaysky and Wang (2000) who found statistically significant patterns at technical price levels in US equity markets.

A resistance level becomes support after a confirmed breakout because participants who were selling at resistance become buyers when price returns to that level — their reference point has not changed, only their direction.

---

## Candidate Identification — Two Scenarios

The module operates on two candidate populations identified through daily momentum ranking:

- **Scenario A** — Stock currently in top 10% momentum universe. Trending. Monitor for consolidation to begin. Do not act yet.
- **Scenario B** — Stock that was in top 10% until recently but has since dropped out. Now consolidating. Active trading candidate once entry signal fires.

The entry signal — confirmed S/R retest — is the mechanism that filters valid consolidation from trend reversal across both populations. The reason a stock dropped out of the ranking is irrelevant. The price structure either confirms a valid retest or it does not. Backtesting validates whether the combined system produces an edge.

---

## What Constitutes a Significant S/R Level

Calibrated for a **15-45 day holding period on a daily chart**, based on Bulkowski's Encyclopedia of Chart Patterns (2005) and Carter's Mastering the Trade (2005).

A level is significant when all three criteria are met — binary gates, not weighted scores:

| Criterion | Threshold | Research Basis |
|---|---|---|
| Test frequency | Minimum 2 tests of the level on the daily chart | Bulkowski (2005): two-touch levels on daily charts have statistically significant continuation rates. Three touches — the positional trading standard — is appropriate for weekly charts. On daily charts for swing trading, waiting for three touches means the setup is too mature and the best entry has passed. |
| Consolidation duration | Minimum 5 trading days of price activity at the level | Bulkowski (2005) and Carter (2005): 5 trading days is the minimum meaningful consolidation on a daily chart for swing trading timeframes. The positional trading standard of 10 days applies to weekly chart setups, not daily chart swing trades. |
| Volume | At least one test on volume 40% above the 20-day average | O'Neil's How to Make Money in Stocks: 40-50% above average is the minimum threshold for institutional participation. 20-day reference period used rather than 50-day — the 50-day period is too slow for our holding period and smooths out the volume spikes we are identifying. |

A level must meet all three criteria to qualify. Any level that does not meet all three is noise and is excluded.

---

## Lookback Window

S/R levels form during consolidation phases that precede momentum moves — not during the momentum phase itself. The lookback window is determined by two constraints specific to our strategy:

**Lower bound:** Our momentum filter selects stocks that have been above their 60-day MA. The consolidation that preceded the current momentum phase ended at least 60 trading days ago. The lookback must extend beyond this 60-day window to reach the consolidation zone where significant levels formed. A lookback shorter than 60 days looks inside the trend itself — where price is moving, not building zones — and will find no meaningful levels.

**Upper bound:** Carter's Mastering the Trade (2005) and Brooks' Trading Price Action (2011), both written specifically for daily chart swing trading, establish that beyond 6 months — approximately 120 trading days — institutional memory at a price level weakens meaningfully for swing trading timeframes. Participants who traded at that level have rotated, changed positions, or their reference price is no longer the dominant factor in their decision making. This is consistent with Jegadeesh and Titman's finding that momentum reverses beyond 12 months — the same underlying mechanism of fading institutional memory.

**Lookback window: 60 to 120 trading days** — calibrated specifically to our 60-day momentum filter and 15-45 day holding period on a daily chart. Starting parameter, subject to backtest validation.

---

## Expected Outcome

Trades taken at levels identified by this module should show statistically higher win rates than random entries on the same stocks over the same period — validated using a binomial significance test at p-value ≤ 0.05. This is the sole measurable validation criterion. The module's value is proven or disproven entirely through backtesting. A win rate improvement that does not pass the significance test is not sufficient evidence that the detection logic works.

---

## Exit Criteria

| Condition | Action |
|---|---|
| Identified levels show no statistically significant improvement in win rate over a random entry baseline (p > 0.05) | Detection logic is invalid — redesign required |
| Identified levels are consistently breached on first retest rather than held | Significance criteria are too loose — tighten test frequency or volume threshold |
| No levels identified on stocks with clear prior consolidation visible on the chart | Lookback window or significance threshold is too strict — widen parameters |

---

---

## Configurable Parameters

All thresholds are starting values derived from research. Every parameter must be configurable so backtest results can drive the final values. No parameter is hardcoded.

| Parameter | Default | Research Basis | Backtest Range to Test |
|---|---|---|---|
| Minimum test frequency | 2 | Bulkowski (2005) daily chart | 2, 3 |
| Minimum consolidation duration | 5 trading days | Bulkowski (2005), Carter (2005) | 3, 5, 7, 10 |
| Volume threshold | 40% above 20-day average | O'Neil institutional participation | 20%, 40%, 60% |
| Volume reference period | 20-day average | Calibrated to 15-45 day holding period | 20-day, 50-day |
| Lookback window | 60-120 trading days | Carter (2005), Brooks (2011) | 60, 90, 120 |

*All thresholds are calibrated for a 15-45 day holding period on a daily chart. They are starting parameters subject to backtest validation. Any deviation from these defaults during design must be justified against the same research sources cited above.*
