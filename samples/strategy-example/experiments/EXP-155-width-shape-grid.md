# EXP-155: ladder half-width x liquidity shape grid, 3 x 3 (v6.141, diagnostic)

- Jira: QUAN-___
- Status: pre-registered
- Level: validation (a diagnostic of v6's design; no cell becomes a candidate)
- Pre-registration commit: ______ · Result commit: ______
- Scope: Dino, 2026-10-06, asked whether "fixed ±20% vs not" and "which distribution" are strongly related, then how that was
  proven. It was not: the evidence in `FINDINGS-2026-10-05.md` §2 is recentre x shape, and EXP-030 moved width alone. Dino: "跑"
  on a 3 x 3 factorial to test it.

## Hypothesis

H1: the ladder's half-width and its liquidity shape interact — which shape is best depends on the width. Mechanism: v6's
inverted-gaussian valley holds most liquidity at its edges, which sit at ±width, so changing the width moves the thick bands
toward or away from where the price spends its time; a flat ladder only becomes uniformly thinner or thicker, and a bell keeps
its thick bands next to the price at every width. If H1 holds, the split "fixed ±20% vs variable range" used to group
EXP-001..154 is incomplete (width experiments that kept the valley, EXP-030 / 154, confound width with effective shape), and
width and shape have to be designed together. If it fails, the two can be studied one at a time.

H0: the ranking of the three shapes is the same at every width (no material interaction).

## Change

Nine cells, everything except the ladder's weights and reach identical to v6 (F engine, ETH share rule, range-exit rebuild,
costs). Same 16 side bands, half_gap 0, equal tick width per side, only the per-band weights and the reach change:

| shape \ half-width | ±10% | ±20% | ±30% |
|---|---|---|---|
| valley (v6's `inverted_gaussian`) | `EQ` | `A` (v6) | `ER` |
| flat (`uniform_16`: 1/16 per side band) | `ES` | `ET` | `EU` |
| bell (`gaussian_16`: v6 sheet's `gaussian` minus its centre band) | `EV` | `EW` | `EX` |

Constants fixed here: widths 0.10 / 0.20 / 0.30 (the same reach up and down in price, as v6), the two new weight columns
above. No other value is searched. On tick-spacing-60 pools (0.3%) the band width rounds to the spacing, so the realised
reach is ±10.1/−9.2%, +21.2/−21.3%, +27.1/−28.5% (spacing 10: within 0.2 pts of nominal); reported, not corrected.

Not a strategy search: this is v6's own width / shape family (PBO 0.56). The best cell is reported but never becomes a
candidate; any use of it would need its own pre-registration on data it has not seen.

## Pre-registration

- Runs: one continuous run per pool over all of its usable data, `opt:A,EQ,ER,ES,ET,EU,EV,EW,EX`, `BINANCE_WARM=1`
  (tag `AEQERESETEUEVEWEX`):
  - ETH: mainnet WETH/USDC 0.05% `0x88e6` 2021-05-06..2026-09-17; mainnet USDC/WETH 0.3% `0x8ad5` 2021-05-06..2026-09-17;
    Base WETH/USDC 0.05% `0xd0b5` 2023-12-01..2026-09-17; Arbitrum WETH/USDC 0.05% `0xc696` 2024-01-01..2025-07-23; Base
    WETH/USDC 0.3% `0x6c56` 2025-01-01..2026-09-17.
  - BTC: mainnet WBTC/USDC 0.3% `0x99ac` 2021-11-02..2026-09-17; Base USDC/cbBTC 0.05% `0xfbb6` 2025-01-01..2026-09-17.
  - The Arbitrum and cbBTC starts are later than in EXP-153/154 because v6 alone is invalid from those pools' first weeks
    (impact ledger above equity); 2024-01-01 / 2025-01-01 are the windows the old holdout used, where v6 is valid. Chosen
    from v6's validity only, before any cell ran.
- Metrics per cell (`exp_metrics.metrics` on the daily equity): total, CAGR, max DD, Calmar, LP fees, rebuilds.
- Invalid cell: net value ≤ 0 at any point or impact ledger above the starting equity. A pool's test below uses only the
  widths whose three cells are all valid; a pool with fewer than two such widths counts as "no interaction".
- Per pool, Calmar C[w, s]; b(w) = the best shape at width w. The pool shows **material interaction** if there are two widths
  w1, w2 with b(w1) ≠ b(w2), C[w1, b(w1)] − C[w1, b(w2)] ≥ 0.05 and C[w2, b(w2)] − C[w2, b(w1)] ≥ 0.05 (the order of two shapes
  reverses by at least 0.05 Calmar both ways).
- Success rule: H1 supported (status `pass`) if at least 4 of the 7 pools show material interaction, with at least one ETH
  and one BTC pool among them. Otherwise `fail` (H0: width and shape separable on this data). Every pool is reported.
- Reported, not deciding: the same test on CAGR (margin 1 pt); per pool the interaction share of the 3 x 3 CAGR variation
  (two-way decomposition without replication, SS_interaction / (SS_width + SS_shape + SS_interaction)); the best cell per pool
  vs v6; LP fees and rebuild counts by cell.

## Result

Pending.

## Deviations

- v6's (`A`) full-history numbers on five of the seven pools are known from EXP-153/154. No other cell has run.
