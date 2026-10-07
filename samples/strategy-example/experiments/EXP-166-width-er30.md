# EXP-166: ladder half-width from the 30-day efficiency ratio (trend -> wide, chop -> narrow) instead of fixed ±20% (v6.151)

- Jira: QUAN-1072
- Status: fail
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: 4edc502 · Result commit: f867495
- Scope: as EXP-165 (Dino, 2026-10-07: make the ±20% dynamic, single pools ETH/USDC and WBTC/ETH).

## Hypothesis

A fixed ±20% ladder is too narrow in a trend (the price leaves it, v6 rebuilds and realises the loss) and too wide in a chop
(fees spread over unused range). Kaufman's efficiency ratio (net 30-day move / sum of daily moves) measures exactly that:
near 1 in a trend, near 0 in a chop. Unlike vol (EXP-030) it does not widen the ladder in a volatile range, where a narrow
ladder earns the most.

## Change

Variant `GJ`: `WIDTH_SIGNAL = "er30"`. At each ladder build the half-width (up and down) is `0.10 + 0.40 x ER30`, ER30 from the
last 30 completed daily closes of the engine's close series (Binance under spec v1; pool closes for `0x4585`), clamped to
[10%, 30%] and rounded to 5% (EXP-030's clamp and grid). Everything else is the baseline's. Constants fixed here: 30 days
(EXP-054's ER window is also 30), 0.10 + 0.40 x ER maps ER 0..0.5 onto the clamp.

## Pre-registration

- Pools, full history, one continuous run each, baseline in the same invocation:
  - ETH/USDC mainnet 0.05% `0x88e6` 2021-05-06..2026-09-17, `SPEC=v1`, `opt:A,GI,GJ`.
  - WBTC/ETH mainnet 0.05% `0x4585` 2021-11-02..2026-09-17, values in BTC, `opt:A,GJ` without `SPEC` (spec v1 runs on
    USD-quoted pools only; `A` is v6).
- Success rule: per pool, win if CAGR > baseline, Calmar >= baseline and max DD no more than 3 pts deeper. Win on both pools ->
  candidate for the seven-pool judge, status `dev-done`; otherwise `fail`. Both pools reported.
- Gas is reported, not charged.

## Result

Runs `opt-AGIGJ` on `0x88e6` with `SPEC=v1` and `opt-AGJ` on `0x4585` (values in BTC), 2 workers (2026-10-07; raw runs in
the main checkout's `result/v6_validate/0x88e6-opt-AGIGJ-specv1-*`, `0x4585-opt-AGJ-*`). `A` reproduces spec v1 (+97.7%) and
v6 on `0x4585` (-1.40%).

| pool | baseline total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH/USDC mainnet 0.05% `0x88e6` 2021-05-06..2026-09-17 (spec v1) | +97.7% / 13.55% / -22.9% / 0.591 | +63.4% / 9.58% / -31.8% / 0.301 | 179 → 187 | lose |
| WBTC/ETH mainnet 0.05% `0x4585` 2021-11-02..2026-09-17 (v6, BTC) | -1.40% / -0.29% / -32.7% / <0 | -6.74% / -1.42% / -34.9% / <0 | 100 → 105 | lose |

Widths built on `0x88e6`: 10% x29, 15% x74, 20% x44, 25% x23, 30% x17 (mean ~17%, narrower than v6).

Verdict: **fail** — loses both pools (ETH CAGR -3.97 pt with max DD 8.9 pts deeper; WBTC/ETH CAGR -1.13 pt).

Reading (a likely mechanism, not tested): in v6 the ladder is built after a range exit, i.e. right after a move; ER is then high in a trend but the next 30 days
are often a chop, so the width is chosen for the past regime. Narrower average ladders also leave range more often (+8 rebuilds).

## Deviations

- Picked after the fast screen described in EXP-165's Deviations. There ER30 gave `0x88e6` CAGR -6.1% vs -5.9% (fixed 20%) and
  `0x4585` -2.6% vs -4.2%; fixed 40% on `0x4585` gave -2.5%, so the gain there may be width, not the signal.
