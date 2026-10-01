# EXP-023: recentre the ladder at +10% from the build price instead of waiting for the +20% edge (v6.18)

- Version: v6.18
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
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

Pending.

## Deviations

- The IL decomposition that motivates the rule was computed on the dev data (ETH continuous v6 run) before this
  file; no run of the rule itself was made before this commit. 0.10 is the only value that will be run.
