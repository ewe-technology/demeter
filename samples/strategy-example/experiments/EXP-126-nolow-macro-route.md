# EXP-126: v6.75 + macro restore + cheapest-tier routing (one rule for both pools) (v6.113)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

EXP-122 passed with one rule but doubled rebuilds (WBTC 231 vs 106); routing makes each WBTC rebuild cheaper, the main doubt about EXP-122. One rule for both pools. New evidence: the combination on H4.

## Change

Variant `DO`: `REFILL_NO_NEW_LOW`, `MACRO_EVENTS = csv`, `MACRO_RESTORE`, `SWAP_ROUTE = pool` on every pool.

## Pre-registration

Pre-registered together with EXP-123..127 (same commit), run with `A` (v6) in `A,DL,DM,DN,DO,DP` per window.

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

- Dino, 2026-10-06: fee-tier rules count; 'keep searching, 30 more' (read as 30 more experiments, EXP-123..152). Routing counts as a strategy change (ruling relayed by the EXP-117 session). The routing code is EXP-117's (`SWAP_ROUTE`, `SWAP_ROUTES`: WBTC/USDC 0.3% swaps priced on WBTC/WETH 0.05% 0x4585 then WETH/USDC 0.05% 0x88e6), with the fix that session suggested: a pool without a route entry keeps v6's own ledger, so the switch is a no-op on 0x88e6. EXP-117 found routing alone took WBTC to 18.2% CAGR at dev (Calmar 1.10); routing has not been run on H4. Smoke test WBTC 2023-09-01..10-31: v6 +9.52%, routed variants +9.54..9.84%; ETH same window: `DL` equals v6.75 exactly (no-op checked).
