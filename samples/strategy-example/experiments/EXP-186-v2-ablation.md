# EXP-186: ablation of MGL v2 (`1ETH_signal`), one element removed at a time, `0x4585` IS / OOS + Arbitrum `0x2f5e`

- Jira: QUAN-1183 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

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

(pending)

## Deviations

(none yet)
