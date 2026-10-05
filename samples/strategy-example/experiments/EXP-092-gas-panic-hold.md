# EXP-092: no refill stage for 3 days after an on-chain gas spike (v6.79)

- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

A day whose median gas price is several times its normal level is an on-chain panic: liquidations, bridge runs, depeg exits. Rebounds inside a panic are the dead-cat bounces where a refill pays LVR and then exits again. Holding the refill for three days after such a spike uses on-chain stress, which neither price nor the EMA engine sees, and applies to both pools (both on Ethereum mainnet). Rare by construction (1.4% of days).

## Change

`GAS_PANIC_HOLD = True` (variant `CE`): no refill stage fires on a spike day or the 2 days after it; spike day = daily median gas > 3 x the median of the previous 30 days (`samples/gas_ethereum_hourly.csv`; no gas data -> no hold). Constants: 3x, 30 days, 3-day hold.

## Pre-registration

Pre-registered together with EXP-092..096 (same commit), run with `A` (v6) in `A,CE,CF,CG,CH,CI` per window.

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

- Designed while EXP-087..091's dev run was in progress (their results not seen), first drafted then and withdrawn uncommitted when v6.75 passed (round-2 stop rule); re-registered unchanged after EXP-087..091's results were known, for Dino's new goal of 2026-10-05 (continue until 10 improvement-level passes). Smoke test WBTC 2023-09-01..10-31 (`CE,CF,CG,CH,CI`, no v6 run): all execute; CE and CI identical there (gates not triggered in that window). Trigger rates checked before registration, outcomes not looked at (2022-01..2026-09): gas spike day 1.4% of days; stablecoin 7-day change < 0 on 40% (2022 56%, 2023 62%, 2024 17%, 2025 20%); pool 3-day net selling 54% (ETH pool) / 47% (WBTC pool). A Coinbase-premium refill gate was considered and not registered: the premium's median is 0.2 bp with 7 bp std and is negative on 83% of 2026 days (USDT/USD basis, not US demand). New data: `samples/flow_daily.csv` (`samples/fetch_flow_daily.py`: DefiLlama stablecoin market cap, Coinbase closes).
