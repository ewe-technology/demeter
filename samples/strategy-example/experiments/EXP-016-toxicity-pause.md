# EXP-016: toxicity pause — pull the ladder for 30 minutes after a 1% five-minute move (v6.13)

- Version: v6.13
- Jira: [QUAN-862](https://ewetechnology.atlassian.net/browse/QUAN-862)
- Status: dropped-at-dev
- Pre-registration commit: 599f492 (implementation b683381, e13ddb9, b8f3c14) · Result commit: d0f2df3
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

Development, ETH/USDC 0.05%, yearly reset, 100,000 USDC (final code; gas = mainnet price of the burns/mints incl.
pauses, reported not charged):

| test | v6 | this | gain | max DD v6 → this | fees v6 → this | LP principal v6 → this | pauses | gas v6 → this |
|---|---|---|---|---|---|---|---|---|
| 2022 | +7.6% | +12.2% | +4.6 | 21.5% → 15.5% | $20.1k → $11.8k | $87.5k → $100.4k | 618 | $34k → $684k |
| 2023 | +32.2% | +25.0% | −7.2 | 13.9% → 15.6% | $23.3k → $6.5k | $108.9k → $117.3k | 182 | $8k → $171k |
| 2024 | +36.4% | +20.3% | −16.0 | 26.7% → 32.4% | $30.9k → $13.9k | $105.5k → $106.5k | 303 | $9k → $403k |
| 2025 | +16.3% | +26.0% | +9.7 | 26.9% → 24.7% | $20.8k → $10.3k | $95.1k → $115.9k | 289 | $4k → $79k |
| 2026-01..09-17 | +18.7% | +16.8% | −1.9 | 12.0% → 11.3% | $6.2k → $4.8k | $112.5k → $112.0k | 210 | $0.6k → $8.6k |

Wins 2/5, median gain −1.9 pts. Pauses: 1.0–4.6% of the minutes a year.

Continuous runs (daily equity):

| run | total | CAGR | max DD | Sharpe | Calmar | fees | LP principal | pauses | gas (mainnet) |
|---|---|---|---|---|---|---|---|---|---|
| ETH v6 | +85.4% | 14.0% | −22.8% | 0.73 | 0.61 | $86.5k | $99.2k | | $61k |
| ETH this | +120.3% | 18.3% | −28.1% | 0.79 | 0.65 | $54.5k | $166.4k | 1,602 | $1.35M |
| WBTC/USDC v6 | +85.6% | 17.3% | −17.8% | 1.01 | 0.97 | $61.7k | $123.2k | | $27k |
| WBTC/USDC this | +102.8% | 20.0% | −16.7% | 0.98 | 1.20 | $27.0k | $176.6k | 513 | $545k |

Verdict: **dropped at dev** — return wins 2/5 (rule: ≥ 3) with median −1.9 pts; the continuous Calmar condition
(0.65 ≥ 0.61) passes on its own, but the max drawdown is deeper (−28.1% vs −22.8%). The two halves of the result
pull apart, and both are mechanical:

- *Fees halve* ($86k → $54k). The paused minutes are 1–5% of the time but the valley's best-paid ones: a 1% move
  sends the price toward the dense outer bands where our pool share is highest. And the design swaps nothing when
  it puts the ladder back, so after a move the same ranges want a different ETH/USDC mix than came out — 2–10% of
  the book stays idle, v6's own follow check (< 0.98 F) rebuilds, and every such rebuild re-centres the valley on
  the price where it is thinnest (3,522 ledger events vs 147). Trend years pay for it: 2023 −7.2, 2024 −16.0.
- *Principal is protected* ($99k → $166k over 2022–26; +$13k in 2022, +$21k in 2025). Being out of the pool for the
  30 minutes after every 1% move removes the IL of exactly the moves that create it; in the bear and chop years that
  is worth more than the fees given up. That is the direction the dynamic-fee study predicts (toxic flow is
  concentrated), and here it shows up as a return-of-principal effect, not a fee effect.
- *Gas decides where it could live*: 1,602 pauses × 16 burns/mints ≈ $1.35M at mainnet prices over 4.7 years
  (v6 $61k), i.e. −$16k a year on a $100k book — impossible on mainnet; on Base (cents per transaction) the same
  count costs a few hundred dollars. If this idea is ever pursued it is Base-only.

Holdout not run. A re-registration under EXP-009's Calmar rule (the EXP-009/010 path) would judge it on the
continuous Calmar 0.65 vs 0.61 and the Base holdout; with the deeper drawdown and the halved fees that is Dino's
call, not an automatic next step.

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
  liquidity is highest, so the toxic minutes are also the valley's best-paid minutes.
- **Second dev run discarded too** (ETH yearly 2022 −4.7, 2023 −7.5, 2024 −12.4, 2025 +10.7, 2026 −2.7 pts, wins 1/5;
  continuous ETH +110.1%, WBTC +99.9%): its resume used each band's *value* share, and the build's shares are
  side-rescaled, so one-sided bands got half their tokens. The final resume runs the build loop itself at the
  build's tick (per-band liquidity within 1–2% of what was pulled, checked band by band on 2023-01) and adds a
  second top-up pass for what the first pass leaves. What still cannot be placed is real: after a 1.5% move the
  same ranges want a different ETH/USDC mix than came out of them, and the design swaps nothing, so 2–10% of the
  book sits idle until v6's own follow check ("not fully deployed" below 0.98 F) rebuilds — those rebuilds re-centre
  the valley on the price, where it is thinnest, and that is where the fee loss comes from (2023-01: fees $4.7k v6
  vs $1.5k this, two extra follow rebuilds). That is the pre-registered design's consequence, not an implementation
  error, so it stands. The dev chains were rerun in full with the final code.
- Pause / resume burns and mints are logged in the cost ledger, so the `rebuilds` column of these runs counts pause
  events too (v6's rebuild count is unchanged); the follow / range rebuild count is in the strategy log.
- The WBTC continuous run of the discarded code was killed before finishing.
