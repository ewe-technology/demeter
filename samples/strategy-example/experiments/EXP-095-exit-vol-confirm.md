# EXP-095: EMA exit only on pool volume above normal (v6.82)

- Jira: QUAN-979
- Status: dropped-at-dev
- Pre-registration commit: 893063f · Result commit: 7fe7966
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

v6's exits are its main cost: each exit and refill pays swap fees, price impact and the rebound it misses. A close below the EMA on thin volume is drift, not distribution; a real breakdown trades. Requiring the pool's 3-day volume to be at least its 30-day median before the EMA exit fires keeps the exits that matter. The lower stop (0.8 x centre) is not gated, so the crash protection is unchanged. Exit-side counterpart of EXP-087.

## Change

`EXIT_VOL_CONFIRM = True` (variant `CH`): an armed account below its EMA exits only on days whose pool 3-day quote volume is >= the median of that 3-day sum over the last 30 days; otherwise it stays armed and is checked again the next day. Constants: as EXP-087 (3 days, 30-day median).

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

Development (`A` and the variant in each invocation, tag `ACECFCGCHCI`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | +7.6% | -0.0 |
| 2023 | +32.2% | +25.6% | -6.7 |
| 2024 | +36.4% | +29.5% | -6.8 |
| 2025 | +16.3% | +13.6% | -2.6 |
| 2026-01..09-17 | +18.7% | +17.2% | -1.5 |

Wins 0/5, median -2.63 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +64.7% | 11.2% | -23.1% | 0.61 | 0.48 | $83.6k | $0.26k | 139 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +79.9% | 16.4% | -18.5% | 0.94 | 0.88 | $59.0k | $0.47k | 101 |

Verdict: **dropped-at-dev** — ETH CAGR 11.2% vs 14.0%, Calmar 0.48, wins 0/5; WBTC 16.4% vs 17.3%. Holdout not run. Reading: slow, quiet declines below the EMA are exactly the ones v6 should leave; delaying those exits until volume rises keeps the ladder in for more of the drop. The EMA exit is v6's protection (as EXP-054).

## Deviations

- Designed while EXP-087..091's dev run was in progress (their results not seen), first drafted then and withdrawn uncommitted when v6.75 passed (round-2 stop rule); re-registered unchanged after EXP-087..091's results were known, for Dino's new goal of 2026-10-05 (continue until 10 improvement-level passes). Smoke test WBTC 2023-09-01..10-31 (`CE,CF,CG,CH,CI`, no v6 run): all execute; CE and CI identical there (gates not triggered in that window). Trigger rates checked before registration, outcomes not looked at (2022-01..2026-09): gas spike day 1.4% of days; stablecoin 7-day change < 0 on 40% (2022 56%, 2023 62%, 2024 17%, 2025 20%); pool 3-day net selling 54% (ETH pool) / 47% (WBTC pool). A Coinbase-premium refill gate was considered and not registered: the premium's median is 0.2 bp with 7 bp std and is negative on 83% of 2026 days (USDT/USD basis, not US demand). New data: `samples/flow_daily.csv` (`samples/fetch_flow_daily.py`: DefiLlama stablecoin market cap, Coinbase closes).
