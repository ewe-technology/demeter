# EXP-188: LP-only levers on the MGL v2 best — range-order rebuilds and an LP on/off gate, `0x4585` IS before 2025 / OOS after

- Jira: QUAN-1187 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

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

(pending)

## Deviations

(none yet)
