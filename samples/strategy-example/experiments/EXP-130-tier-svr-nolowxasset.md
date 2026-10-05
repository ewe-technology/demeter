# EXP-130: fee tier: EXP-124's WBTC half, v6.75 + cross-asset refill on 0.05% (v6.116)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

v6.75 plus EXP-086's rule that an ETH refill stage needs BTC to have rebounded too.

## Change

fee >= 0.3%: `INTRADAY_STOP`, `REFILL_VOL_CONFIRM`, `SWAP_ROUTE = pool` (EXP-124's WBTC half); below 0.3%: `REFILL_NO_NEW_LOW`, `REFILL_GATE = xasset`. Variant `DR`.

## Pre-registration

Pre-registered together with EXP-129..132 (same commit), run with `A` (v6) in `A,DQ,DR,DS,DT` per window. EXP-128 belongs to another session.

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

- Designed after EXP-123..127's results. Every fee-tier pass so far uses v6.75 alone as its ETH half, so the ETH side has one out-of-time finding. These pairs fix the WBTC half to EXP-124's (H4 +9.6%, known) and add to v6.75 one rule that raised ETH CAGR at dev but failed the ETH yearly-wins test alone (EXP-091 breadth cap, EXP-086 cross-asset refill, EXP-085 funding cap, EXP-100 strong-close refill). The ETH combination is new on H5 in every pair; a pass is new ETH evidence, a fail says that rule does not add to v6.75 out of time. Four, not five: the remaining ETH candidates either cannot act on H5 (crowding rules need 90 days of pool liquidity history, H5 starts on the pool's first day) or lost ETH return at dev.
