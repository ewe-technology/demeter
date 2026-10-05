# EXP-151: fee tier: EXP-124's WBTC half, EXP-140's ETH half + account tranches (v6.137)

- Jira: QUAN-1036
- Status: pre-registered
- Pre-registration commit: 8428450 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-063's four real sub-ladders (each rebuilt only when its own account changes) on the cheap pool, under EXP-140's refill filters: fewer, smaller rebuilds of the part that changed.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool`; below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`, `MACRO_EVENTS = csv`, `MACRO_RESTORE` (EXP-140's ETH half), `ACCOUNT_TRANCHES`. Variant `EM`.

## Pre-registration

Pre-registered together with EXP-149..152 (same commit), run with `A` (v6) in `A,EK,EL,EM,EN` per window. The last four of the 30-experiment round EXP-123..152.

- Development (in-sample): ETH/USDC 0.05% mainnet yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 and continuous
  2022-01-01..2026-09-17; WBTC/USDC 0.3% mainnet continuous 2022-11-01..2026-09-17.
- Holdout (run once, `A` and the variant, only if dev passes): **time-split out-of-time**, both windows before the dev windows,
  warm-up from Binance daily closes (`BINANCE_WARM=1`): H5 ETH/USDC 0.05% 2021-05-06..2021-12-31; H4 WBTC/USDC 0.3%
  2022-01-01..2022-10-31. v6's numbers there are known (EXP-040..081) and both windows have been used for other variants; this
  variant never ran there.
- Success rule (improvement level only; `judge.py dev` and `judge.py oot`):
  - Dev: continuous ETH and WBTC each CAGR above v6's, Calmar ≥ v6's, max DD no more than 3 pts deeper; ETH yearly wins ≥ 3
    of 5. Fails → `dropped-at-dev`.
  - Holdout: on H5 and on H4 each, CAGR above v6's, Calmar ≥ v6's (if v6's CAGR is negative: CAGR above only) and max DD no
    more than 3 pts deeper → `holdout-pass`; otherwise `holdout-fail`.

## Result

(pending)

## Deviations

- Designed after EXP-144..148's dev results and before their holdout results were read. EXP-140's ETH half (v6.75 + cross-asset refill + macro restore) has the best H5 so far (+16.4%); the cross-asset refill hurts the 0.3% WBTC pool (EXP-144 / 145 / 148: WBTC dev CAGR 16.8-17.0% < v6 17.3%; EXP-146: 18.0% vs EXP-124's 21.0%), so it stays on the cheap pool. EXP-149 / 150 pair EXP-140's ETH half with WBTC halves new on H4 (EXP-124's half + macro restore; + v6.75's no-new-low refill); EXP-151 adds EXP-063's account tranches to EXP-140's ETH half (new on H5); EXP-152 is a one-rule candidate: EXP-126 plus the volume-confirmed refill on every pool. Account tranches (EXP-115 / 118 / 121) were checked as a WBTC addition and skipped: with routing it would repeat EXP-121's H4 run.
