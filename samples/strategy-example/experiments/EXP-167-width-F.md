# EXP-167: ladder half-width from v6's own deployed fraction F (0.10 + 0.20 x F) instead of fixed ±20% (v6.152)

- Jira: QUAN-___
- Status: pre-registered
- Level: improvement (over spec v1 on ETH/USDC, over v6 on WBTC/ETH)
- Pre-registration commit: ______ · Result commit: ______
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

## Deviations

- Smoke test 2022-06-01..07-31 on `0x88e6` (code check: widths 10..30% built, `A` unchanged); not evidence.
