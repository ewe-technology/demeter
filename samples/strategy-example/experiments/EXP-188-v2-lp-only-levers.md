# EXP-188: LP-only levers on the MGL v2 best — range-order rebuilds and an LP on/off gate, `0x4585` IS before 2025 / OOS after

- Jira: QUAN-1187 (subtask of QUAN-1107)
- Status: fail — range-order rebuilds (LP / spot) and LP gates (VR / ER) all lose to their bases in-sample (no OOS run)
- Pre-registration commit: 234ae70 · Result commit: (next commit)

Dino (2026-10-22), after EXP-187 (spot only beats the LP version out of sample): "那有什麼樣的策略優化是只有lp能做的嗎"
-> "做1,2,5". 1 = rebuild by range orders, 2 = an LP on/off gate; 5 (LP + perp hedge) is EXP-189.

## Hypothesis

1. Range orders: a rebuild pays 0.1% on every leg (IS swap cost 0.162 ETH for the LP version). A single-sided range one
   tick spacing (0.1%) beyond the price fills when the price crosses it, at the band's midpoint, and earns the pool fee
   (0.05%) instead of paying a swap cost. Only an LP position can do this; a fill also waits for a small move in the
   order's favour. Cost: the old allocation is held up to a day longer when the order does not fill.
2. LP gate: the LP version's edge is +0.32 ETH IS (R mean-reverting) and negative elsewhere (EXP-187). If the regime can
   be read from R's own recent path, run the weak-side LP only while R looks range-bound and hold 50/50 spot otherwise.

## Change

`experiments/v2_goal.py`:

| variant | base | change |
|---|---|---|
| `k100_reupE_ro` | `k100_f2low_rvol_reupE` (LP version) | BTC <-> ETH rebuild legs by range order: limit 0.1% beyond the price, fill at 0.05% beyond, +0.05% fee earned; unfilled after 23h59m -> market swap. USDC legs, out-of-range rebuilds and the start swap at market. Legs under 0.5% of the book swap at market |
| `k100_reupE_spot_ro` | `k100_reupE_spot` (EXP-187) | the same range-order execution |
| `k100_reupE_gatevr` | LP version | while weak, LP only while the 5-day variance ratio of log R over the last 60 closes < 1; else 50/50 spot |
| `k100_reupE_gateer` | LP version | while weak, LP only while R's 30-day efficiency ratio is below its trailing 365-day median; else 50/50 spot |

## Pre-registration

- Pool `0x4585`, 1 ETH start, net value in ETH incl. rewards; USD ratio / USD DD, swap cost and LP edge reported.
- IS 2021-11-02..2024-12-31; OOS 2025-01-01..2026-09-30.
- Bar (`better()`) against each variant's own base (`ro` vs the LP version, `spot_ro` vs spot, gates vs the LP version;
  the gates are also shown against spot): CAGR above, Calmar >=, max DD no more than 3 pts deeper.
- OOS only for IS passes. A lever **works** when its variant beats its base on IS and OOS. One batch.

## Result

IS 2021-11-02..2024-12-31, in ETH (CAGR / max DD / Calmar; LP fees / IL / edge):

| variant | base | variant | base numbers | vs own base |
|---|---|---|---|---|
| `k100_reupE_ro` | LP version | 59.96% / −26.9% / 2.233; 0.578 / −0.626 / −0.048; 117 rebuilds, 83 legs filled by range order, 14 expired | 65.68% / −24.8% / 2.643; 0.610 / −0.287 / +0.324 | loses |
| `k100_reupE_spot_ro` | spot version | 58.49% / −27.0% / 2.165; 106 rebuilds, 75 filled, 12 expired | 61.08% / −25.3% / 2.419 | loses |
| `k100_reupE_gatevr` | LP version | 62.55% / −25.0% / 2.498; 0.333 / −0.280 / +0.053; 141 rebuilds | 65.68% / −24.8% / 2.643 | loses (beats spot: 61.08% / −25.3% / 2.419) |
| `k100_reupE_gateer` | LP version | 57.97% / −24.9% / 2.324; 0.350 / −0.511 / −0.161; 191 rebuilds | 65.68% / −24.8% / 2.643 | loses |

**Verdict: fail — no lever beats its base in-sample; no OOS run.**

- Range orders fill most legs (83 of 97 on the LP version) and turn a 0.1% cost into a 0.05% rebate, yet cost 5.7 /
  2.6 pts CAGR. A one-spacing order fills when the price moves its way (a reversal) and expires in a trend, so the trend
  legs are executed a day late at a worse price: adverse selection, larger than the fee saved. The LP built at the
  fill minute also lands on a worse path (IL −0.626 vs −0.287).
- The gates cut LP time but also add rebuilds (141 / 191 vs 118). `gatevr` keeps most of the LP's IS fees per unit of
  IL and lands between the LP and spot versions in-sample; against its pre-registered base (the LP version) it loses,
  so it was not run OOS. `gateer` gates on a noisier signal and loses to both.

## Deviations

- `gatevr` beats the spot version in-sample. The spot version was not the pre-registered base for the gates, so no
  OOS run was made; testing it against spot would be a new pre-registration.
