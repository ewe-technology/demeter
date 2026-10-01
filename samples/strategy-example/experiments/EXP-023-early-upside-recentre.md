# EXP-023: recentre the ladder at +10% from the build price instead of waiting for the +20% edge (v6.18)

- Version: v6.18
- Jira: [QUAN-874](https://ewetechnology.atlassian.net/browse/QUAN-874)
- Status: dropped-at-dev
- Pre-registration commit: 5c6dfbd · Result commit: 185ee50
- Scope: the Uniswap strategy itself (Dino, 2026-10-01): LP mechanics only, no perps, no lending.

## Hypothesis

Decomposition of v6's ETH 2022-01..2026-09 run (this session, from `result_A_v6.csv`, per rebuild interval:
IL = removed value − the added tokens held to the removal price): LP fees +$86.2k, IL −$101.4k, hold/timing
+$103.3k. **86% of the IL (−$87.0k) comes from the 19 intervals that ended with the price outside the ±20% span**,
and 14 of those were upside exits: −$75.5k of IL against +$171k of hold gain. The other 103 intervals cost −$14.4k
together. At the 00:00 rebuild the price was only 2.8% past the edge on average, so the loss is not the wait for the
daily check: it is the ladder selling all its ETH across a 20% rally. A concentrated LP's impermanent loss grows with
the square of the move, so recentring halfway (two +10% legs instead of one +20% leg) gives up roughly half the IL
in a trend, at the cost of one extra rebuild (swap fee + impact) and of locking in IL that a round trip would have
returned. v6 deploys mostly in uptrends (the F engine), where the first effect should dominate.

## Change

`RECENTRE_UP = 0.10` (variant `R`): at the daily 00:00 rebuild check, also rebuild when the base price is ≥ 1.10 x
the price of the last build. 0.10 = half the ladder's ±20% span (the midpoint of the upper half), fixed by the
geometry, not searched. Downside unchanged (exits there are the F engine's job; down-exit IL was −$11.4k). The
rebuild is v6's own (burn, collect, swap to the 70/50 share, re-mint centred on the price). v6 (`A`) in the same
invocations. No cash yield, no perp, fees paid out as in v6.

## Pre-registration

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and
  continuous 2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, A and R):
  - Arbitrum WETH/USDC 0.05% `0xc6962004f452be9203591991d15f6b388e09e8d0` (never run with any variant except none:
    EXP-022 was dropped at dev, so this pool is untouched): continuous 2024-01-01..2025-07-23 and yearly segments
    2024, 2025-01-01..07-23; EMA warm-up on mainnet ETH/USD;
  - mainnet AAVE/WETH 0.3% `0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb` (untouched; 40 WETH, ETH numeraire):
    continuous 2022-01-01..2026-09-17 and yearly segments 2022..2026-09-17 (run when its minute data is complete);
  - Base USDC/WETH 0.05% continuous 2024-01-01..2026-09-17 and Base USDC/cbBTC 0.05% continuous
    2025-01-01..2026-09-17 (v6 ran on them before, this variant never).
- Success rule (`R` vs v6 `A`, daily equity, Calmar = CAGR / |max DD|):
  - Dev: continuous ETH and WBTC CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly
    wins ≥ 3 of 5. Else `dropped-at-dev`.
  - Holdout: on each of the four holdout pools continuous CAGR above v6's **and** Calmar ≥ v6's (if v6's CAGR is
    negative: `R`'s CAGR above and max DD not more than 3 pts deeper) **and** max DD no more than 3 pts deeper;
    **and** yearly wins in ≥ 4 of the 7 Arbitrum + AAVE segments → `holdout-pass`, else `holdout-fail`.

## Result

Development (A and R per invocation):

| test | v6 | this (R) | gain | max DD v6 → this |
|---|---|---|---|---|
| 2022 | +7.6% | +10.3% | +2.7 | 21.5% → 21.2% |
| 2023 | +32.2% | +32.5% | +0.3 | 13.9% → 14.7% |
| 2024 | +36.4% | +27.4% | −9.0 | 26.7% → 33.2% |
| 2025 | +16.3% | +25.6% | +9.3 | 26.9% → 27.6% |
| 2026-01..09-17 | +18.7% | +19.3% | +0.6 | 12.0% → 11.9% |

Wins 4/5, median +0.64 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds (recentres) |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +121.1% | 18.3% | −26.2% | 0.84 | 0.70 | $80.0k | $0.48k | 159 (27) |
| WBTC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +87.7% | 17.6% | −21.5% | 0.87 | 0.82 | $32.6k | $0.93k | 115 (17) |

Verdict: **dropped-at-dev** — ETH passes CAGR and Calmar (0.70 vs 0.61) but its max DD is 3.4 pts deeper (limit 3);
WBTC fails Calmar (0.82 vs 0.97) and DD (3.7 pts deeper). On ETH the rule does what the decomposition predicted
(+35.7 pts total, Sharpe 0.73 → 0.84), but it buys back ETH at +10% just before the 2024 reversal (2024 −9.0 pts,
DD 26.7% → 33.2%). On the 0.3% WBTC pool the recentred book earns about half the fees ($61.7k → $32.6k), which more
than offsets the IL saving; why the fees halve was not diagnosed (open question).
The holdout was not run.

Next (not run): the literature pass of 2026-10-01 points to a model-derived daily width (Cartea, Drissi, Monga,
SIAM J. Fin. Math. 2024: width ∝ γ / (8π − σ²), π = pool fee rate, σ² = variance) and a rolling partial rebuild
(re-mint only the far bands on the exit side) as the structural LP-layer candidates with A-grade evidence.

## Deviations

- The IL decomposition that motivates the rule was computed on the dev data (ETH continuous v6 run) before this
  file; no run of the rule itself was made before this commit. 0.10 is the only value that will be run.
