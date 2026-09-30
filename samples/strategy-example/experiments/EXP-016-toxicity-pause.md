# EXP-016: toxicity pause — pull the ladder for 30 minutes after a 1% five-minute move (v6.13)

- Version: v6.13
- Jira: QUAN-___
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______
- Literature: `RESEARCH-2026-09-30-lp-literature.md` §5.

## Hypothesis

LVR is paid to arbitrageurs in the minutes after the CEX price moves and before the pool catches up; a passive v3
LP cannot raise its fee like a Uniswap v4 dynamic-fee hook, but it can decline to quote. The empirical dynamic-fee
study on USDC-WETH 5 bps mainnet (Apr–Oct 2023, 1-second Binance data, https://hackmd.io/@anteroe/BkIbSfwmJx)
found that a fee raised on 2-minute momentum cut LVR by 20% at constant average fee; the same information used as
an on/off switch should cut the same toxic flow. v6's rebuilds are daily; this is the first change that acts at
minute scale. Expected: less IL per fast move (the ladder is not the counterparty during the move), a small loss of
fees during pauses (fast moves are also fee-rich minutes), and many burn/mint cycles — the gas is the real cost,
reported at mainnet prices per policy, and the count of pauses shows what the same idea would cost on Base.

## Change

`PAUSE_RET = 0.01`, `PAUSE_WINDOW = 5` minutes, `PAUSE_MINUTES = 30` (v6: no pause). All fixed here.

- Every minute, `r5 = ln(P_t / P_{t-5})` from the pool's minute close. If `|r5| ≥ PAUSE_RET` and the ladder is
  placed and not paused: remove every band (fees collected as in a rebuild), keep the tick ranges, and set
  `paused_until = t + 30 min`. Tokens sit in the wallet.
- At `paused_until` (or the first minute after it): re-add the same tick ranges with the same band shares from the
  wallet balances at the current price (`band_amounts` → `add_liquidity_by_tick`); whatever does not fit a band
  stays idle until the next rebuild, as v6's leftovers do. No new range, no swap, no F change.
- While paused the daily follow / rescale checks skip; the first daily check after resumption runs as v6. A pause
  that would start in the last 30 minutes of the data does not start.
- A move that leaves the (unplaced) ladder's span during a pause is handled by the next daily range check, as v6
  would after the same move.
- Gas: 8 burns + 8 mints per pause (16 positions per v6 ladder rebuild, so half each way here) reported in the gas
  column; nothing charged (policy). Pool fee / price impact: none (no swaps).
- Everything else identical to v6.

## Pre-registration

- Development data (in-sample): ETH/USDC 0.05% yearly segments 2022, 2023, 2024, 2025, 2026-01-01..09-17 (yearly
  reset, 100,000 USDC); continuous ETH 2022-01-01..2026-09-17 and WBTC/USDC 0.3% 2022-11-01..2026-09-17 reported.
  v6 (A) and this (L) in the same invocation.
- Holdout (run once, v6 + this only): Base USDC/WETH 0.05% (`0xd0b53d9277642d899df5c87a3966a349a798f224`), yearly
  segments 2024, 2025, 2026-01-01..09-17 plus the continuous 2024-01-01..2026-09-17 run. v6's numbers on this pool
  are known from EXP-004; no run of this variant has touched it.
- Success rule (EXP-009's Calmar family): dev return wins in ≥ 3 of 5 ETH segments, median gain > 0 pts, **and**
  continuous ETH Calmar ≥ v6's 0.61, else `dropped-at-dev`; holdout wins in ≥ 2 of 3 Base segments **and**
  continuous Base Calmar ≥ v6's → `holdout-pass`, else `holdout-fail`. Pauses per year and mainnet gas per pause
  are reported next to the verdict; a pass with prohibitive gas is a "Base-only" pass.

## Result

| test | v6 | this | gain | max DD v6 → this | pauses |
|---|---|---|---|---|---|

Continuous run: total / CAGR / max DD / Sharpe / Calmar / pauses / gas.

Verdict:

## Deviations

None yet.
