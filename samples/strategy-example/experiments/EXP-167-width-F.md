# EXP-167: ladder half-width from v6's own deployed fraction F (0.10 + 0.20 x F) instead of fixed ±20% (v6.152)

- Jira: QUAN-1073
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: 4621cb7 · Result commit: ______
- Scope: Dino, 2026-10-07: "好，試試看跟著 refill 階段或 F 變寬度" (try a width that follows the refill stage or F), after
  EXP-165 / 166 (market-indicator widths) failed. Same single pools as EXP-166.

## Hypothesis

EXP-030 / 165 / 166 sized the ladder from market indicators and lost: the width was chosen for the regime just passed. v6's F
already summarises the regime it acts on. F = 1 means all four accounts are armed and fully deployed (an uptrend): a wider
ladder exits less often and keeps the coin through the trend (EXP-154's wide top raised ETH CAGR). 0 < F < 1 means the
accounts are refilling after an exit (a base is forming): a narrower ladder concentrates the refilled capital where the price
chops and earns more fees per dollar.

## Change

Variant `GK`: `WIDTH_SIGNAL = "F"`. At each ladder build the half-width (up and down) is `0.10 + 0.20 x F`, F judged on the last
completed day (the same F that sizes the build), clamped to [10%, 30%] and rounded to 5% (EXP-030's clamp and grid): F = 1 ->
30%, 0.75 -> 25%, 0.5 -> 20%, 0.25 -> 15%. Valley shape, F engine, refill, exits: the baseline's. Constants fixed here: the map
puts F = 0.5 at v6's 20% and spans EXP-030's clamp.

## Pre-registration

- Pools, full history, one continuous run each, baseline in the same invocation (`opt:A,GK,GL`; EXP-168 is `GL`):
  - ETH/USDC mainnet 0.05% `0x88e6` 2021-05-06..2026-09-17, `SPEC=v1`.
  - WBTC/ETH mainnet 0.05% `0x4585` 2021-11-02..2026-09-17, values in BTC, v6 baseline, `BINANCE_WARM=1`.
- Success rule: per pool, win if CAGR > baseline, Calmar >= baseline and max DD no more than 3 pts deeper. Win on both pools ->
  candidate for the seven-pool judge (`judge_full.py`), status `dev-done`; otherwise `fail`. Both pools reported.
- Gas is reported, not charged.

## Result

Run `opt-AGKGL` on `0x88e6` with `SPEC=v1` and on `0x4585` with `BINANCE_WARM=1` (values in BTC), 2 workers (2026-10-07; raw
runs in the main checkout's `result/v6_validate/0x88e6-opt-AGKGL-specv1-*`, `0x4585-opt-AGKGL-*`). `A` reproduces spec v1
(+97.7%) and v6 on `0x4585` (-1.40%).

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | LP fees | win |
|---|---|---|---|---|---|
| ETH/USDC `0x88e6` 2021-05-06..2026-09-17 (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +69.5% / 10.33% / -24.5% / 0.422 | 179 → 176 | $101.5k → $69.3k | lose |
| WBTC/ETH `0x4585` 2021-11-02..2026-09-17 (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | +2.80% / 0.57% / -33.1% / 0.017 | 100 → 101 | 0.262 → 0.272 BTC | **win** |

Widths built on `0x88e6`: 10% x34, 15% x36, 20% x40, 25% x30, 30% x36.

Verdict: **fail** — wins 1/2 (WBTC/ETH +0.86 pt CAGR; ETH/USDC -3.22 pt CAGR, Calmar 0.422 vs 0.591).

Reading (a likely mechanism, not tested): on ETH/USDC, F = 1 covers the uptrends where v6 earns most of its fees; widening the ladder there to 30% cuts LP fees
by a third ($32k), more than fewer exits give back. The WBTC/ETH win is +0.9 pt on one pool with a baseline near zero; one pool is not evidence of an edge.

## Deviations

- Smoke test 2022-06-01..07-31 on `0x88e6` (code check: widths 10..30% built, `A` unchanged); not evidence.
