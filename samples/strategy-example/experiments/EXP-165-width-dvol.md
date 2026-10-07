# EXP-165: ladder half-width from ETH implied vol (Deribit DVOL one-month move) instead of fixed ±20% (v6.150)

- Jira: QUAN-1071
- Status: fail
- Level: improvement (over spec v1)
- Pre-registration commit: 4edc502 · Result commit: ______
- Scope: Dino, 2026-10-07: "先針對單一pool eth/usdc and wbtc/eth 看各自有沒其他策略可以有更好的報酬", then "試著看能不能找到什麼
  指標或訊號讓+-20%變成動態的" (find an indicator or signal that makes the ±20% dynamic). Single-pool question: judged on the
  ETH/USDC pool he named, not the seven-pool bar.

## Hypothesis

v6's ladder is a fixed ±20%. EXP-030 sized it from 30-day *realized* vol and lost (ETH CAGR 13.7% vs 14.0%, WBTC 10.9% vs
17.3%): realized vol lags, so the ladder is widest just after a move. Implied vol (DVOL) is the market's forward one-month
estimate: a ladder sized to the expected move should stay in range when a move is priced in, and concentrate (more fees per
dollar) when the market expects calm.

## Change

Variant `GI`: `WIDTH_SIGNAL = "dvol"`. At each ladder build the half-width (up and down) is
`DVOL_ETH / 100 x sqrt(30 / 365)` from the last completed daily DVOL close (`samples/deribit_dvol_daily.csv`), clamped to
[10%, 30%] and rounded to 5% (EXP-030's clamp and grid, unchanged). Valley shape, F engine, refill, exits: spec v1. No constant
is searched: sqrt(30/365) is the one-month horizon, clamp and grid are EXP-030's.

## Pre-registration

- Baseline: `A` under `SPEC=v1`, same invocation, `opt:A,GI,GJ` (EXP-166 is `GJ`).
- Pool: ETH/USDC mainnet 0.05% `0x88e6`, full history 2021-05-06..2026-09-17, one continuous run.
- Success rule: win if CAGR > spec v1, Calmar >= spec v1 and max DD no more than 3 pts deeper (the full-history per-pool test).
  A win makes it a candidate for the seven-pool judge (`judge_full.py`), status `dev-done`; a loss is `fail`.
- Gas is reported, not charged.

## Result

Run `opt-AGIGJ` with `SPEC=v1`, 2 workers (2026-10-07; raw run in the main checkout's
`result/v6_validate/0x88e6-opt-AGIGJ-specv1-2021-05-06-2026-09-17*`). `A` reproduces EXP-156's spec v1 numbers (+97.7%).

| pool | spec v1 total / CAGR / max DD / Calmar | this | rebuilds | win |
|---|---|---|---|---|
| ETH mainnet 0.05% `0x88e6` 2021-05-06..2026-09-17 | +97.7% / 13.55% / -22.9% / 0.591 | +76.8% / 11.20% / -24.8% / 0.451 | 179 → 178 | lose |

Widths built: 10% x6, 15% x29, 20% x67, 25% x20, 30% x56 (mean ~22%). LP fees $85.0k vs $101.5k; gas $121k vs $122k.

Verdict: **fail** — CAGR -2.35 pt, Calmar 0.451 vs 0.591, max DD 1.9 pts deeper.

Reading (a likely mechanism, not tested): DVOL widens the ladder after a sell-off (implied vol is highest at the lows), which is exactly when v6's staged refill
wants a tight ladder to buy back; fees fall 16% and the refill gains less. A forward-looking vol does not fix EXP-030's problem.

## Deviations

- DVOL and ER30 were picked after a fast screen on the same pools (`experiments/single_pool_scan.py`, 2026-10-07): a trend-gated
  recentring LP with the width from each of eight signals (fixed 20/30/40%, realized vol, relative vol, DVOL, ER30, fee/LVR,
  volume, EMA distance). On `0x88e6` DVOL gave CAGR -4.8% vs -5.9% for fixed 20% (realized vol -3.9%, but that rule is EXP-030's,
  already tested in v6); fixed 20/30/40% moved by about 2 pts with no order, so the screen's gains are within its noise. The
  screen is not v6 and is not evidence; it is why these two signals were chosen.
