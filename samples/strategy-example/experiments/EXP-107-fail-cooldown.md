# EXP-107: longer stage-1 wait after a refill that failed fast (v6.94)

- Jira: QUAN-991
- Status: dropped-at-dev
- Pre-registration commit: 26a4143 · Result commit: ______
- Scope: /goal round 2 (Dino, 2026-10-05: "再繼續找30個"): beat v6 at the improvement level on ETH and WBTC, pure LP, time-split
  out-of-time holdout; idle-capital yield and swap routing excluded (rulings / assumption of 2026-10-05).

## Hypothesis

A refill that is stopped out or exits on the EMA within days was a false rebound; the next one in the same decline is more likely false too. Doubling the stage-1 confirmation (3 -> 6 closes) after an account exits within 10 days of its last refill stage makes the strategy learn from its own failed refills, on both pools, without any new signal; a successful stage 1 resets it.

## Change

`FAIL_COOLDOWN = True` (variant `CT`): if an account exits (EMA exit or lower stop) within 10 days of its last refill stage, its next stage 1 needs 6 consecutive qualifying closes instead of 3; reset when that stage 1 fires. Constants: 10 days, 2x.

## Pre-registration

Pre-registered together with EXP-107..111 (same commit), run with `A` (v6) in `A,CT,CU,CV,CW,CX` per window.

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

Development (`A` and the variant in each invocation, tag `ACTCUCVCWCX`):

| test | v6 | this | gain |
|---|---|---|---|
| 2022 | +7.6% | -0.6% | -8.2 |
| 2023 | +32.2% | +33.3% | +1.1 |
| 2024 | +36.4% | +30.3% | -6.1 |
| 2025 | +16.3% | +15.9% | -0.4 |
| 2026-01..09-17 | +18.7% | +18.4% | -0.3 |

Wins 1/5, median -0.36 pts.

| continuous | total | CAGR | max DD | Sharpe | Calmar | LP fees | impact | rebuilds |
|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | -22.8% | 0.73 | 0.61 | $86.5k | $0.29k | 147 |
| ETH this | +65.5% | 11.3% | -25.0% | 0.62 | 0.45 | $77.2k | $0.24k | 149 |
| WBTC v6 | +85.6% | 17.3% | -17.8% | 1.01 | 0.97 | $61.7k | $0.72k | 106 |
| WBTC this | +75.9% | 15.7% | -18.2% | 0.91 | 0.86 | $55.7k | $0.67k | 110 |

Verdict: **dropped-at-dev** — both worse: ETH CAGR 11.3% vs 14.0%, Calmar 0.45; WBTC 15.7% vs 17.3%; wins 1/5. Holdout not run. Reading (interpretation, not measured): the refill after a fast failure is not more likely to fail; doubling its wait misses the rebound that follows a washout. The smoke-test coincidence (CT = CU = CV over 2023-09..10) is resolved: the three differ over the dev period.

## Deviations

- Designed after EXP-102..106's dev and holdout results (EXP-103 / 104 passed the time-split holdout as fee-tier rules; EXP-105's crowding cap cut risk on both pools but lost WBTC return through extra rebuilds). EXP-110 / 111 are fee-tier rules built from rules whose dev results are known (only the holdout judges them; their WBTC halves, EXP-098 and EXP-087, and EXP-106's ETH half have not been run on H4 / H5 before, except EXP-087 inside EXP-104). Whether fee-tier rules count is Dino's call. Band shape (uniform / gaussian / exponential) was considered and not registered: classified as tuning in `RESEARCH-2026-09-30-lp-literature.md`. Smoke test WBTC 2023-09-01..10-31 (`A,CT,CU,CV,CW,CX`): all execute; CT, CU and CV end identical there (0.0581 vs v6 0.0952; CU rerun alone gives the same value), read as the window's one refill being delayed past the window end by each gate; to be checked on the dev run (they must differ over 4 years).
