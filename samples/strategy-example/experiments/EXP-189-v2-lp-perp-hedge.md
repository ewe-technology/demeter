# EXP-189: the MGL v2 best's LP delta-hedged with a synthetic BTC/ETH perp, `0x4585` IS / OOS

- Jira: QUAN-1188 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: (this commit) · Result commit: (pending)

Dino (2026-10-22): "做1,2,5", item 5 = LP + perpetual hedge. This uses perps, outside the pure-LP scope set on
2026-10-01; Dino asked for it explicitly, so it is run as his exception to that rule.

## Hypothesis

A delta hedge removes the LP's directional drift but not its convexity loss: hedged daily, the LP earns fees minus
LVR (at daily sampling) minus funding minus hedge costs. On this pool fees were about 0.8-0.9 x LVR (research note
2026-10-21), so the hedged LP should lose a little against the spot version. Unhedged, the LP's loss depends on the
path: small when R mean-reverts (IS, IL only 0.34 of the variance-implied loss), large in trends (OOS). So the hedge
should lose IS and may help OOS.

## Change

`experiments/v2_goal.py`, base `k100_f2low_rvol_reupE` (LP version):

| variant | change |
|---|---|
| `k100_reupE_hedge` | each day the weak-side LP's BTC drift since its build is hedged with a synthetic BTC/ETH perp (long BTCUSDT + short ETHUSDT), h = BTC at build − BTC now; P&L in ETH = h x ΔBTC/ETH − h x price x (BTC − ETH daily funding, Binance) − 0.1% of each hedge change (two taker legs); closed at every rebuild; 10% of the LP's money kept as ETH margin |
| `k100_reupE_margin` | control: the same 10% ETH margin, no hedge |

## Pre-registration

- Pool `0x4585`, 1 ETH start, in ETH incl. rewards; hedge P&L, USD ratio and USD DD reported.
- IS 2021-11-02..2024-12-31 and OOS 2025-01-01..2026-09-30, both run for both variants (a plain comparison like
  EXP-187, not the IS-gated search: the hypothesis itself says IS and OOS should differ).
- Report `better()` per segment of `hedge` against the LP version, the margin control and the spot version
  (`k100_reupE_spot`). The hedge **works** when it beats the LP version on both segments.

## Result

(pending)

## Deviations

- Perp hedge outside the pure-LP scope (Dino's explicit request). Funding = daily sum of Binance 8h prints of the day
  before the hedge step; no liquidation or margin call is modelled (10% margin vs a hedge of at most about half the LP).
