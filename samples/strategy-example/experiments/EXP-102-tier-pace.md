# EXP-102: refill pace by fee tier: wick-anchored on 0.3%, up-day on 0.05% (v6.89)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

Each rebuild swap pays the pool fee, six times more on a 0.3% pool than on a 0.05% pool, so the right refill pace depends on the fee tier: an expensive pool should refill later and less often, a cheap pool can refill early but should skip fading days. One rule keyed on the fee tier: on pools with fee >= 0.3% the refill is measured from the intraday low (EXP-098, slower); on cheaper pools a refill day must close above its open (EXP-099, cleaner).

## Change

Variant `CO`: pools with fee >= 0.3% run `LOW_FROM_WICK = True`; pools below 0.3% run `UP_DAY_REFILL = True`. Constant: the 0.3% tier boundary (Uniswap's fee tiers).

## Pre-registration

Pre-registered together with EXP-102..106 (same commit), run with `A` (v6) in `A,CO,CP,CQ,CR,CS` per window.

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

- Designed after EXP-097..101's dev results. **EXP-102..104 are fee-tier rules built from rules whose dev results are known**: each switch set was seen to help one pool at dev (WBTC 0.3%: EXP-087 / 098 / 101; ETH 0.05%: EXP-088 / 099). Their dev pass is therefore expected and carries no evidence; only the time-split holdout (H5 ETH 0.05%, H4 WBTC 0.3%, never used by any of the component rules except EXP-088's ETH half) judges them. Whether a fee-tier rule counts as one strategy or as two single-asset versions is Dino's call; it is reported either way. Liquidity crowding (EXP-105) trigger rate checked before registration, outcomes not looked at: 7-day mean above 1.5x the 90-day median on 13% of ETH days, 22% of WBTC days (2022-2026). Execution at the deepest UTC hour (literature pass) was considered and not registered: active liquidity varies only ±4% by hour and price impact is $0.3k of ETH's 4-year cost. Smoke test WBTC 2023-09-01..10-31 (`A,CO,CP,CQ,CR,CS`): all execute; on WBTC the tier rules reproduce their 'hi' components (CO = EXP-098's CK, CP = CN).
