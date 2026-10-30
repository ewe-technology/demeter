# Validation layer fit: L0-L10 for ETH-USDC v3.2 / ETH-cbBTC v2.2 (2026-10-29)

Jira QUAN-1211 (stage 1 of QUAN-1209). For each of Maker's 11 validation layers (`GLOSSARY.md`), says whether it can
run on our two strategies, why in one line, and what method and data it needs. No backtest was run for this note.

Sources: Maker's ladder and his advice in #scrum-quant-amm, 2026-10-28 15:23
([link](https://ewetechnology.slack.com/archives/C0BQH8SBV9Q/p1793172230988799));
`RESEARCH-2026-10-13-strategy-validation.md` (methods, primary sources); `VALIDATION-2026-10-13-defense-v1-v3-demeter.md`
(the last scorecard, v1-v3); `REPRO-2026-10-29-remix-v3_2-v2_1.md` (engine and data audit); `INVENTORY.md` (pools).

## What the two strategies give the layers to work with

| | ETH-USDC MGL v3.2 | ETH-cbBTC MGL v2.2 |
|---|---|---|
| code | `gamma_maker_defense_ethusdc_v3_2.py` (Steven, remix `a042a82`) | none yet: v2.1 + target-allocation reinvest (QUAN-1212) |
| unit | USD, $100k | ETH, 1 ETH |
| target pool | mainnet USDC/WETH 0.05% `0x88e6` (spec); the Base contract LPs in WETH/USDC 0.3% `0x6c56` and swaps on 0.05% `0xd0b5` (`gamma_maker_defense_ethusdc_v3_2_p30.py` docstring) | Base WETH/cbBTC 0.05% `0x7aea` (spec calibrated on mainnet WBTC/WETH `0x4585`) |
| pool minute data | `0x88e6` 2021-05-06..2026-09-30 (5.4 y); `0x6c56` from 2024-01-01 (2.7 y); `0xd0b5` from 2023-12-01 (2.8 y) | `0x4585` 2021-11-02..2026-09-30 (4.9 y); `0x7aea` from 2024-09-13 (2.0 y) |
| signal data | Binance ETHUSDT daily closes from 2017-08 | Binance ETHUSDT, BTCUSDT, ETHBTC daily closes from 2017-08 |
| fitted per window? | no: spec constants (EMA 90-120, ±20% valley, refill ladder, +40% divergence exit) | no: spec constants (same F engine on G, strength switch on R, 25% ETH keep) |
| constants frozen | spec v3.2, 2026-10-27, after all the pool data above | spec v2.1 / v2.2, 2026-10-27, same |

Two facts drive most verdicts below. Nothing is refitted per window, so layers built around a fitting step test
nothing new. Every year of pool data was seen before the constants were frozen, so no backtest window is a clean
out-of-sample test; only data after 2026-10-27 is.

## Layer table

"can" = runs on the data and code we have, with a meaningful answer. "can, limited" = runs, but the answer is weak for
the reason given. "can't" = no meaningful answer now. "pending" = meaningful, but needs time or tooling outside
QUAN-1209. In the Maker column, "differs" marks where this note departs from his 10-28 advice.

| layer | v3.2 | v2.2 | 1-line reason | method + data it needs | Maker 10-28 |
|---|---|---|---|---|---|
| L0 backtest | can | can (after QUAN-1212) | Engine and data pass the audit (REPRO §4); two engine defects and the cost model must be fixed first | demeter on Rust, full history per pool. Engine: fee denominator in-range only (QUAN-1213, done: `FEE_IN_RANGE_LIQUIDITY=1`), % DD from daily NV. Costs (our list): reward valuation stated (fixed vs marked), gas not charged (team ruling 2026-10-30: left out at our capital; a strategy with more than ~1,000 rebuilds is discussed before gas is charged), swap cost flat 0.1% as the spec says (decided 2026-10-30, `FLAT_SWAP_COST=1`; the depth model counted our own bands as depth). JIT dilution of fees is not modelled: report it as a known optimism | do first (cost P0) |
| L1 walk-forward | can, limited | can, limited | Nothing is refitted, so walk-forward reduces to one yearly table with constants held fixed | one continuous run per pool (`0x88e6`, `0x4585`), cut per calendar year 2022 / 2023 / 2024 / 2025 / 2026-01..09, plus anchored windows 2022, 2022-23, 2022-24, 2022-25 ("the yearly table") | do (with L5) |
| L2 MCPT | can, limited | can, limited | Permuting prices needs synthetic swap data (demeter replays real swaps); permuting the strategy's own decisions on the real path does not | our substitute, not Maker's L2: keep the real pool path, shuffle the dates of F changes / exits (same count and sizes), 500-1,000 reruns, p = share of shuffles that beat the real rule. It tests timing skill on one path, not robustness to other paths. Needs a rerun harness (~1 min per run per year on Rust) | skip for now; differs: substitute test |
| L3 block bootstrap | can, limited | can, limited | Resampling the strategy's daily NV returns needs no new backtest, but cannot test a path-dependent LP rule on new price paths (resampling prices would, at high cost) | stationary bootstrap of daily log returns, mean block 20 d (mean) and 90 d (one-year paths, DD and loss probability); `method3_significance` / `method5_monte_carlo` in `strategy_validation.py` already do it | skip for now (price paths); differs: returns only |
| L4 multiple testing | can | can | The spec went through many versions and sweeps; the count of tries is the input, not a Bonferroni divisor | trial ledger: every spec version (v1, v2, v3, v3.1, v3.2 / v1..v2.2) and every parameter sweep Maker / Steven / CTO ran counts as a trial; report N beside every result. A DSR haircut by N is Sharpe-based, so like L8 it is a report, not a gate. Our `registry.csv` covers only this branch | do (ledger, not Bonferroni) |
| L5 out-of-sample | can, limited | can, limited | All pool data predates the 2026-10-27 freeze: years are pseudo-OOS; clean OOS is 2026-10 onward only | pseudo-OOS: the yearly table (L1), judged on the later years; clean OOS: refetch `0x88e6` / `0x6c56` / `0xd0b5` / `0x7aea` after 2026-10-27 each month (`fetch_uni_minute.py`) and rerun frozen code | do (with L1); differs: later years count as pseudo-OOS only |
| L6 regime split | can | can | Bull / bear / range labels split the existing runs; ~5 years give few episodes per regime | label each window bull / bear / range with our own rule (EMA200 slope + drawdown from the high), written down before any result is looked at; report return and DD per regime (v3.2 on ETH/USD, v2.2 on ETH/BTC). Robustness test: rerun one step either side of the main constants (EMA length, band width) and check that the best setting does not change with the regime; ~4 extra runs per pool | do |
| L7 CPCV | can't | can't | CPCV checks a fitting step on held-out folds; nothing is fitted, and 4-5 years of daily data give too few independent folds | would need a parameter-selection step plus purged folds | skip |
| L8 PSR | can | can | One formula on daily returns, already in `strategy_validation.py`; LP returns are fat-tailed, so it is a report, not a gate | PSR from daily log returns (skew, kurtosis), bar 0.95; for v2.2 on returns in ETH | optional, add to metrics |
| L9 reality check / SPA | can't | can't | No competing set of daily return series exists for these specs (the versions were not run side by side), and 4-5 years give little power | would need daily NV of every tried version / sweep on the same window, then `arch.bootstrap.SPA` | skip |
| L10 paper trading | pending | pending | Only a live dry-run shows fills, slippage and gas; it takes 6-12 months, past QUAN-1209's due date (2026-11-13) | a bot runs the frozen code on live Base data without funds; compare daily its intended actions, fills and costs with the backtest replay of the same days | do before deploy |

## Plan for stage 3 (QUAN-1216)

Order follows Maker's advice; stage 3 starts only when the stage-2 preconditions pass (QUAN-1212..1215).

1. L0 on both strategies with the fixed engine and stated costs.
2. L1 + L5: the yearly table; clean OOS rows added monthly.
3. L6 per-regime rows from the same runs, plus the one-step-either-side runs.
4. L4 trial count beside every number; L3 and L8 from the same daily returns (no new backtests), reported, not gating.
5. L2 decision-permutation only if steps 1-4 leave the verdict open.

Scorecard rows for L7 and L9 say "not applicable" with the reason above. L10 is recorded as "pending" and opens its
own ticket.

## Open questions

- Settled 2026-10-29: `pair_regime.py`, `BACKTEST_COST_TODO.md` and `RANGE_TUNING` in Maker's message are his local,
  unpublished files ("T16" = his to-do item 16); he called the advice reference only. Dino: do not use them. L6 uses
  our own regime rule and L0 our own cost list, both as written above.
- Settled 2026-10-30 (Dino, option 1): v3.2 is judged on mainnet `0x88e6` (spec numbers, 5.4 y), with the spec's
  gas <= $0.2 claim condition modelled there (`LOOKAHEAD-AUDIT-2026-10-29.md` section 3: on mainnet a full-ladder claim
  never passes it; modelled in QUAN-1216 as `CLAIM_GAS_CAP=1`, L0 in `VALIDATION-2026-10-29-v3_2-v2_2.md`). Base
  WETH/USDC 0.3% `0x6c56` (the contract's LP pool, 2.7 y) is scored as the contract check, not judged. An earlier version of this file named `0xd0b5`: that is the contract's 0.05% swap pool, not its LP pool.
- The trial count for L4: count the versions and sweeps from the spec sheets' version history and the `remix` /
  `maker-defense` git history; anything not recorded there stays uncounted and is reported as a lower bound.
