# EXP-186: ablation of MGL v2 (`1ETH_signal`), one element removed at a time, `0x4585` IS / OOS + Arbitrum `0x2f5e`

- Jira: QUAN-1183 (subtask of QUAN-1107)
- Status: done — 3 of 9 elements effective (F engine, strength switch, ETH keep); the LP is neutral IS and harmful OOS + Arbitrum
- Pre-registration commit: 5d5b75a · Result commit: 53174e2

Dino (2026-10-21): "1ETH_signal 如果把裡面的元素一個一個拿掉回測，是不是就可以確認該元素是不是真的是一個有效元素？" -> "做".

## Hypothesis

Each element of v2 (Maker's btceth v1 = the sheet's row 2, `1ETH_signal`) should earn its place: removing it should make
the strategy worse on in-sample, out-of-sample and an unused pool. An element whose removal does not hurt, or helps, is
dead weight (or harmful) in v2 as it stands. This measures each element's marginal value with the others in place; two
overlapping elements can each look useless when removed alone.

## Change

`experiments/v2_goal.py`; each variant = v2 with ONE element removed and replaced by the neutral choice:

| variant | element removed | replaced by |
|---|---|---|
| `abl_noexit` | F engine (EMA exits and refill) | F = 1 every day |
| `noslope` (EXP-178) | 20-day falling-EMA test on the exit | exit on close < EMA alone |
| `abl_onestage` | staged refill (4 stages of 25%) | the first stage (3 closes >= low x 1.05) deploys the account fully |
| `abl_oneacct` | four accounts (EMA 90 / 100 / 110 / 120) | one account on EMA100 |
| `abl_allweak` | strength switch (R vs EMA100(R)) | always weak: retreat BTC, LP = F at +-20%, no ETH kept |
| `abl_allstrong` | strength switch | always strong: retreat USDC, LP F x 75% at +-10%, ETH F x 25% |
| `abl_keep0` | 25% of F kept as ETH while strong | 0% (all of F is LP while strong) |
| `wide20` (EXP-178) | +-10% LP range while strong | +-20% always |
| `abl_nolp` | the LP | its share held as 50% ETH / 50% BTC tokens (no fees) |

## Pre-registration

- Segments: `0x4585` IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-30; Arbitrum WBTC/WETH 0.05% `0x2f5e`
  2023-01-01..2026-01-13 (all its data, USD price from mainnet `0x88e6`). 1 ETH start, net value in ETH incl. rewards.
  v2 and every variant on all three; existing runs reused (`is-v2`, `arb-v2`, `is-noslope`, `is-wide20`; same code).
- Per segment, removing an element **hurts** when v2's CAGR is at least 0.5 pt above the variant's OR the variant's
  max DD is at least 3 pts deeper, and the variant does not beat v2 on `better()`. It **helps** when the variant beats
  v2 on `better()`.
- Verdict per element: **effective** = hurts on all three segments; **harmful** = helps on all three; otherwise
  **unclear** (mixed or within noise). Every run reported; USD ratio and USD max DD reported, not judged.
- Not an optimization: no follow-up variant is built from these results inside this experiment.

## Result

In ETH. v2: IS 57.33% / −26.4% / Calmar 2.170; OOS 20.56% / −37.2% / 0.553; Arbitrum 15.42% / −39.9% / 0.387.
Cells: variant CAGR (gap to v2 in pts) / max DD (gap) -> what removing the element did.

| element removed (variant) | IS | OOS | Arbitrum | verdict |
|---|---|---|---|---|
| F engine (`abl_noexit`) | 10.19% (−47.14) / −19.7% -> hurt | −1.26% (−21.81) / −34.5% -> hurt | 5.37% (−10.05) / −37.2% -> hurt | **effective** |
| slope filter (`noslope`) | 60.21% (+2.88) / −26.5% -> help | 14.14% (−6.42) / −43.6% -> hurt | 14.51% (−0.91) / −44.3% -> hurt | unclear (useful OOS + Arb) |
| staged refill (`abl_onestage`) | 59.92% (+2.59) / −26.3% -> help | 18.63% (−1.93) / −35.4% -> hurt | 16.39% (+0.97) / −38.5% -> help | unclear |
| four accounts (`abl_oneacct`) | 57.57% (+0.24) / −27.9% -> noise | 20.65% (+0.09) / −37.2% -> help | 14.80% (−0.62) / −39.9% -> hurt | unclear (about neutral) |
| strength switch, always weak (`abl_allweak`) | 23.28% (−34.05) / −32.3% -> hurt | 9.96% (−10.60) / −42.1% -> hurt | 17.29% (+1.87) / −43.3% -> hurt (DD) | **effective** |
| strength switch, always strong (`abl_allstrong`) | 37.52% (−19.81) / −40.3% -> hurt | 64.78% (+44.23) / −39.7% -> help | 1.04% (−14.38) / −41.4% -> hurt | unclear (regime bet) |
| ETH keep 25% while strong (`abl_keep0`) | 56.15% (−1.18) / −30.4% -> hurt | 14.52% (−6.04) / −42.4% -> hurt | 14.91% (−0.51) / −44.1% -> hurt | **effective** |
| strong-side ±10% range (`wide20`) | 56.72% (−0.61) / −27.4% -> hurt | 19.25% (−1.30) / −38.1% -> hurt | 15.39% (−0.03) / −39.6% -> noise | unclear (mildly useful) |
| the LP (`abl_nolp`) | 56.99% (−0.34) / −26.3% -> noise | 30.71% (+10.16) / −31.3% -> help | 22.32% (+6.91) / −31.3% -> help | unclear (harmful OOS + Arb) |

**Verdict: 3 of 9 elements are effective on all three segments** — the F engine, the strength switch (vs always
weak) and keeping 25% of F as ETH while strong. None is harmful on all three. Reading the unclear ones:

- **The LP is the clearest finding.** Holding its share as 50/50 ETH/BTC tokens instead ties v2 in-sample (−0.34 pt)
  and beats it by +10.2 pts OOS and +6.9 pts on Arbitrum with a 5.9 / 8.5 pts shallower DD: after 2024 and on
  Arbitrum the LP's IL exceeds its fees (EXP-184 / 185: the base's LP edge was −0.118 ETH OOS). In v2 as it stands the
  LP adds nothing in-sample and costs a lot out of sample.
- The slope filter hurts in-sample but helps OOS and on Arbitrum (DD 6.4 / 4.4 pts shallower with it): keep it.
- Always-strong wins OOS by +44 pts and loses IS / Arbitrum by 20 / 14: the switch is a bet on regimes, and it is
  `allweak`, not `allstrong`, that shows the switch earns its place on every segment.
- Four accounts vs one EMA100 account: within ±0.6 pt everywhere, a redundant layer.
- Staged refill and the strong-side ±10% range: small, mixed effects.

## Deviations

- `noslope`, `wide20` IS and `v2` IS / Arbitrum runs are reused from EXP-178 / 182 (same code apart from logging).
