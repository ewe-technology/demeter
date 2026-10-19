# EXP-182: keep50 / f2low / rvol stacks on ETH-cbBTC MGL v2, significant bar, `0x4585` + Arbitrum `0x2f5e`

- Jira: QUAN-1176 (subtask of QUAN-1107)
- Status: fail on the significant bar (none significant IS); `k75_f2low_rvol` beats v2 on IS, OOS and Arbitrum
  (CAGR +7.1 / +4.1 / +1.5 pts, max DD 1.2 / 7.2 / 7.6 pts shallower), significant OOS
- Pre-registration commit: a6207ac · Result commit: see registry

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

Run 2026-10-19, `v2_goal.py is|oos|arb v2,k50_rvol,..,keep100 3` (Rust engine; `result/v2_goal/{is,oos,arb}-*`). In ETH.

| variant | `0x4585` IS CAGR / max DD | OOS CAGR / max DD | Arbitrum CAGR / max DD |
|---|---|---|---|
| v2 | 57.33% / −26.4% | 20.90% / −37.2% | 15.42% / −39.9% |
| `k50_rvol` | 58.67% / −24.9% | 22.99% / −33.8% | 16.00% / −36.3% |
| `k50_f2low` | 62.38% / −25.7% | 22.87% / −33.6% | 15.53% / −36.2% |
| `k50_f2low_rvol` | 63.61% / −25.7% | 23.49% / −33.8% | 17.19% / −36.3% |
| `keep75` | 58.79% / −23.3% | 23.70% / −29.7% | 15.07% / −32.2% |
| `k75_rvol` | 59.27% / −23.3% | 24.35% / −30.0% | 15.75% / −32.3% |
| **`k75_f2low_rvol`** | **64.45% / −25.2%** | **25.02% / −30.0%** | **16.95% / −32.2%** |
| `keep100` | 59.26% / −23.0% | 24.89% / −28.1% | 14.78% / −29.1% |

Gain vs v2 (CAGR pts / max DD pts shallower), significant marked *:

| variant | IS | OOS | Arbitrum | beats v2 on all three |
|---|---|---|---|---|
| `k50_rvol` | +1.34 / +1.56 | *+2.09 / +3.35 | +0.59 / +3.54 | yes |
| `k50_f2low` | +5.05 / +0.76 | +1.96 / +3.62 | +0.11 / +3.67 | yes |
| `k50_f2low_rvol` | +6.28 / +0.76 | *+2.59 / +3.35 | +1.77 / +3.58 | yes |
| `keep75` | +1.46 / +3.11 | *+2.80 / +7.53 | −0.35 / +7.67 | no (Arbitrum CAGR) |
| `k75_rvol` | +1.94 / +3.12 | *+3.44 / +7.24 | +0.33 / +7.57 | yes |
| **`k75_f2low_rvol`** | +7.12 / +1.23 | *+4.12 / +7.24 | +1.53 / +7.64 | **yes** |
| `keep100` | +1.93 / +3.46 | *+3.99 / +9.13 | −0.64 / +10.72 | no (Arbitrum CAGR) |

Calmar is above v2 for every variant on every segment. USD max DD is within ±5 pts of v2 everywhere (e.g.
`k75_f2low_rvol` IS −48.8% vs −53.7%, OOS −55.2% vs −53.9%, Arbitrum −48.0% vs −48.2%). Rebuilds: `k75_f2low_rvol`
124 / 71 / 121 vs v2 137 / 76 / 125.

Verdict: **fail on the pre-registered significant bar** — no variant is significant in-sample; the nearest miss on
both margins is `k75_rvol` (IS +1.94 pts CAGR, 0.06 short; DD +3.12) and `keep100` (+1.93; it also loses CAGR on
Arbitrum). Six of seven are significant out of sample.

- **Best overall: `k75_f2low_rvol`** (keep 75% of F as ETH while strong + F from the second-lowest account + rvol). It
  beats v2 on all three segments on CAGR (+7.1 / +4.1 / +1.5 pts), max DD (1.2 / 7.2 / 7.6 pts shallower) and Calmar,
  is significant OOS, and trades less. Its in-sample DD gain is small because the IS max DD episode (2022-08..11)
  comes from the USDC / BTC give-back, which more kept ETH does not touch.
- The ETH-kept share is the main drawdown lever (25% -> 50% -> 75% -> 100%: OOS DD −37.2 -> −33.8 -> −30.0 -> −28.1%;
  Arbitrum −39.9 -> −36.3 -> −32.2 -> −29.1%); f2low and rvol add return. Past 75% the Arbitrum CAGR turns negative
  (`keep100` −0.64): 75% is the last step that helps everywhere.
- Caveats: the components were picked on `0x4585` OOS (EXP-178 / 179), so `0x4585` OOS is not clean; Arbitrum is a
  different pool on the same market path. Next: the forward window after 2026-09-17, and Base cbBTC/WETH once the runner
  handles token0 = WETH.

## Deviations

- The components (keep50, f2low, rvol) were picked after their `0x4585` OOS results (EXP-178 / 179), so the `0x4585` OOS
  half is not a clean test for these stacks. Arbitrum `0x2f5e` was not used anywhere in EXP-178..181; it checks a
  different pool (fees, liquidity), not a different market path: the signal is the same Binance series.
- Before this file, v2 alone ran 2024-03-01..10 on Arbitrum and mainnet to check the pool switch (rewards 0.00462 vs
  0.00471 ETH).
