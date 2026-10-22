# EXP-189: the MGL v2 best's LP delta-hedged with a synthetic BTC/ETH perp, `0x4585` IS / OOS

- Jira: QUAN-1188 (subtask of QUAN-1107)
- Status: fail — the perp-hedged LP loses IS (58.04% vs 65.68%), wins OOS (31.40% vs 25.80%) and loses to spot on both
- Pre-registration commit: 021d266 · Result commit: b588371

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

In ETH (CAGR / max DD / Calmar; LP fees / IL / edge):

| variant | IS 2021-11..2024 | OOS 2025..2026-09-30 |
|---|---|---|
| LP version (base) | **65.68% / −24.8% / 2.643**; 0.610 / −0.287 / +0.324 | 25.80% / −28.7% / 0.898; 0.114 / −0.232 / −0.118 |
| `margin` (10% ETH margin, no hedge) | 65.34% / −24.8% / 2.632; 0.555 / −0.263 / +0.292 | 29.56% / −24.5% / 1.204; 0.105 / −0.172 / −0.067 |
| `hedge` | 58.04% / −24.9% / 2.334; 0.516 / −0.473 / +0.043; hedge P&L **−0.312 ETH** | 31.40% / −25.0% / 1.257; 0.108 / −0.168 / −0.059; hedge P&L **+0.022 ETH** |
| spot version (EXP-187) | 61.08% / −25.3% / 2.419 | **33.05% / −25.6% / 1.291** |

`better()` for `hedge`: vs the LP version loses IS, beats OOS; vs the margin control loses IS (−7.3 pts), beats OOS
(+1.8 pts); vs spot loses both (−3.0 / −1.7 pts).

**Verdict: fail — the hedge does not beat the LP version on both segments, and it loses to plain spot on both.**

- As expected from theory: the hedge pays away the mean reversion the unhedged LP lived on in-sample (hedge −0.312
  ETH; the LP's IL alone was −0.287) and only recovers a little in the trending OOS (+0.022 ETH). Hedged, the LP earns
  fees minus convexity loss minus funding and trading costs, which is below zero on this pool.
- The margin control moves OOS by +3.8 pts with only 10% less LP money: the OOS result of the LP version is path
  sensitive (rebuild timing; EXP-184's ±0.2 ETH noise), so OOS gaps of a few pts between LP variants are weak evidence.
- Of everything tried on the LP leg (EXP-184..189), spot remains the best way to hold the weak-side money out of sample.

## Deviations

- Perp hedge outside the pure-LP scope (Dino's explicit request). Funding = daily sum of Binance 8h prints of the day
  before the hedge step; no liquidation or margin call is modelled (10% margin vs a hedge of at most about half the LP).
