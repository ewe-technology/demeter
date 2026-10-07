# EXP-166: ladder half-width from the 30-day efficiency ratio (trend -> wide, chop -> narrow) instead of fixed ±20% (v6.151)

- Jira: QUAN-___
- Status: pre-registered
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: ______ · Result commit: ______
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

## Deviations

- Picked after the fast screen described in EXP-165's Deviations. There ER30 gave `0x88e6` CAGR -6.1% vs -5.9% (fixed 20%) and
  `0x4585` -2.6% vs -4.2%; fixed 40% on `0x4585` gave -2.5%, so the gain there may be width, not the signal.
