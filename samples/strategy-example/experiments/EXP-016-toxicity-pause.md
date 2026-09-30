# EXP-016: toxicity pause — pull the ladder for 30 minutes after a 1% five-minute move (v6.13)

- Version: v6.13
- Jira: [QUAN-862](https://ewetechnology.atlassian.net/browse/QUAN-862)
- Status: pre-registered
- Pre-registration commit: 599f492 · Result commit: ______
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

- **First dev run discarded (implementation did not match the pre-registration).** The first `resume_ladder` re-added
  each band from the tokens *that band* had returned when pulled. After a move a band often needs the other token
  (a quote band the price fell through now needs base), got zero, and was dropped as dry — so every pause thinned the
  ladder and left tokens idle until the next rebuild; the idle ETH then rode rallies unhedged, the EXP-006 half-ladder
  effect. That run (ETH yearly 2022 −3.6, 2023 −1.0, 2024 −11.8, 2025 +13.6, 2026 −1.0 pts, wins 1/5; continuous ETH
  +137.2% vs +85.4% with 2024 fees $9.4k vs $30.9k for 6 days paused) is recorded here and not used. The resume now
  does what the Change section says: the same tick ranges, each taking its pre-pause value share of the wallet's free
  tokens through `band_amounts` (a first attempt with value shares under-placed one-sided bands by half, because the
  build's shares are side-rescaled; the final code re-runs the build loop itself at the build's tick, so the placed
  value is within 0–5% of what was pulled — checked with a temporary debug print on the smoke window). Smoke run of
  the corrected code, ETH 2021-11..12: v6 −4.8%, this −6.8%, 50 pauses, fees $3.26k → $2.45k. Those 1,500 paused
  minutes are 1.7% of the time and carry 7.3% of the pool's swap volume (3.5x an average minute), yet 25% of the
  ladder's fees: a 1% move pushes the price toward the valley's dense outer bands, where our share of the pool's
  liquidity is highest, so the toxic minutes are also the valley's best-paid minutes. The dev chains were rerun in
  full with the corrected code.
- Pause / resume burns and mints are logged in the cost ledger, so the `rebuilds` column of these runs counts pause
  events too (v6's rebuild count is unchanged); the follow / range rebuild count is in the strategy log.
- The WBTC continuous run of the discarded code was killed before finishing.
