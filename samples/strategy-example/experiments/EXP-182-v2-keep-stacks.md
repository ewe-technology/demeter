# EXP-182: keep50 / f2low / rvol stacks on ETH-cbBTC MGL v2, significant bar, `0x4585` + Arbitrum `0x2f5e`

- Jira: QUAN-1176 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

Dino (2026-10-19), after EXP-180 / 181 found no added element with a significant gain: option 1 — v2's own elements may
change too; build on `keep50` and stack the other components. The significant bar of EXP-180 stays.

## Hypothesis

`keep50` (keep 50% of F as ETH outside the LP while ETH is strong, v2: 25%) raised CAGR and cut max DD on both halves
(EXP-178: OOS +1.47 pts, DD −33.6% vs −37.2%). Holding more ETH while strong avoids the LP selling ETH into rallies,
which is where v2's ETH drawdowns come from. Pushing the share further (75%, 100%) and stacking `f2low` (EXP-178) and
`rvol` (EXP-179), which also held out of sample, may add up to a significant gain.

## Change

`experiments/v2_goal.py` (Maker's btceth v1 = MGL v2 standard mode, Rust engine). Variants:

| variant | change vs v2 |
|---|---|
| `k50_rvol` | ETH_KEEP 0.50 + rvol filter |
| `k50_f2low` | ETH_KEEP 0.50 + F = second-lowest account |
| `k50_f2low_rvol` | all three |
| `keep75` | ETH_KEEP 0.75 |
| `k75_rvol` | ETH_KEEP 0.75 + rvol |
| `k75_f2low_rvol` | ETH_KEEP 0.75 + f2low + rvol |
| `keep100` | ETH_KEEP 1.0 (no LP while ETH is strong; boundary case) |

## Pre-registration

- Runs: `0x4585` IS 2021-11-02..2024-12-31 and OOS 2025-01-01..2026-09-17; Arbitrum WBTC/WETH 0.05% `0x2f5e`
  2023-01-01..2026-01-13 (all its minute data; same token order and tick spacing, USD price from mainnet `0x88e6`).
  All variants and v2 run on all three; net value in ETH incl. rewards.
- Significant on a segment: CAGR >= v2 + 2.0 pts AND max DD at least 3.0 pts shallower AND Calmar >= v2.
- **Goal reached** when a variant is significant on `0x4585` IS and OOS and beats v2 on Arbitrum (CAGR above, Calmar >=,
  DD no more than 3 pts deeper). Significance on Arbitrum is reported too.
- One batch; every run reported.

## Result

(pending)

## Deviations

- The components (keep50, f2low, rvol) were picked after their `0x4585` OOS results (EXP-178 / 179), so the `0x4585` OOS
  half is not a clean test for these stacks. Arbitrum `0x2f5e` was not used anywhere in EXP-178..181; it checks a
  different pool (fees, liquidity), not a different market path: the signal is the same Binance series.
- Before this file, v2 alone ran 2024-03-01..10 on Arbitrum and mainnet to check the pool switch (rewards 0.00462 vs
  0.00471 ETH).
