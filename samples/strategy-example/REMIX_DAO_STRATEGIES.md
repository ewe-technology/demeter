# Remix DAO backtests

Every `remix_dao_*` script in this directory: what range rule it runs, what pair and pool it
is pointed at, and how the families relate. Each file is a standalone copy of the same
scaffold, so the differences live in a handful of lines.

29 backtest scripts · 7 range rules · 8 pools · 6 generations.

## How every file is built

They all share one skeleton. Once you can read one, you can read all of them.

Each script holds a `Strategy` subclass, a `run_test()` that wires one `Actuator` +
`UniLpMarket` and returns ~30 metrics, a `process_for_date()` that builds the parameter
sweep, and a `__main__` that fans the date ranges out over `multiprocessing.Process` — one
process per date range.

Shared code lives in `remix_dao_utils.py` (tick maths, `RemixDAOParams`, weekly/monthly
triggers), `base_strategy.py`, `market_v2.py`, `rm_types.py` and `export_file.py`.
`remix_dao_utils.py` is a library, not a backtest — it is the only `remix_dao_*` file you
cannot run.

Results land in `result/<folder_prefix>-<capital>-<start>-<end>/` as one
`result_<report_name>.csv` per run plus an `apr_remix_*_results.csv` summary.

**Configuration is done by commenting.** Pairs, pools, date ranges and sweeps are stacks of
commented alternatives; whatever is uncommented is what runs. Everything in the sheet below
is the *currently active* line, not the full menu of what the file can do.

## The seven range rules

Where the LP range comes from — the one real difference between the strategies. The sheet
references these letters.

| | Rule | How the range is chosen | Files |
|---|---|---|---|
| **A** | Indicator band | `openTick ± spread × tick_spacing`, recentred on every rescale. Optional std or ATR width via `RangeStrategy`. The original rule. | 16 |
| **B** | Centred band | Rounded current tick ± `tick_spread_lower/upper`. Same as A but anchored on the live tick rather than the bar's open. | tick_C, tick_gap |
| **C** | Fixed tick grid | The tick line is cut into fixed buckets from `starting_tick`: `floor((now − start) / spread)`. The grid never moves; price moves between buckets. | tick_B_stable ×2 |
| **D** | Fixed % grid | Rule C in price space. Multiplicative buckets stepping out from `starting_mark_price` by `init_tick_spread/100` percent. | percentage_B ×2 |
| **E** | Symmetric % band | Current price ± half of a percentage width, converted to ticks. Recentres on the price each time. | percentage_D ×2 |
| **F** | Mark % band + fill | A percentage band around a mark price, plus a *second* position placed next to the main one to absorb whichever token is left over. | mark_perc ×2 |
| **G** | Multi-band shape | Not one position but a row of contiguous bands with a weight profile — liquidity is shaped across the range instead of flat. | valley ×2, gamma |

## The sheet

Ordered oldest to newest. Capital is `init_quote`, denominated in the quote token.
"Boundary check" is `utils.verify_and_get_new_rescale_tick_boundary()` — the rescale-boundary
offset gated on `was_in_range`. The 24 h lock only applies when `_aggressive = False`.

| File | Gen | Rule | Rebalance trigger | Base / Quote | Pool | Capital | Rescale sweep | Spread `l` | DCA | Added |
|---|---|---|---|---|---|---|---|---|---|---|
| `remix_dao.py` | G0 | A | Boundary check + 24 h lock | ETH / USDC | 0xc473 · 0.03 arb | 5,000 | hourly | — | — | 2024-09 |
| `remix_dao_chaos.py` | G1 | A | Boundary check, std/ATR width | ETH / USDC | 0xC696 · 0.05% arb | 1,000,000 | hourly | — | — | 2024-09 |
| `remix_dao_new_strat.py` | G1 | A | Boundary check + bull/bear flip | ETH / USDC | 0xC696 · 0.05% arb | 1,000,000 | hourly | — | — | 2024-11 |
| `remix_dao_dca.py` | G2 | A | Boundary check + 24 h lock | ETH / USDC | 0x88e6 · 0.05% | 30,000 | hourly | — | **always** | 2024-11 |
| `remix_dao_dca_weekly.py` | G2 | A | Boundary check + 24 h lock | ETH / USDC | 0x88e6 · 0.05% | 1,000 | hourly | — | off | 2024-11 |
| `remix_dao_dca_weekly_double_sep.py` | G2 | A | Boundary check + 24 h lock | ETH / USDC | 0x88e6 · 0.05% | 10,000 | hourly | — | off (split add) | 2024-11 |
| `remix_dao_dca_weekly_btceth_in_usdc.py` | G2 | A | Boundary check + 24 h lock | **cbBTC / BTC** ⚠️ | 0xe8f7 · 0.01% | 1 | hourly | 3 – 10 | off | 2024-11 |
| `remix_dao_dca_weekly_btceth_in_usdc_double_sep.py` | G2 | A | Boundary check + 24 h lock | BTC / ETH | 0x4585 · 0.05% | 1 | hourly | 10 – 300 | **always** (base only) | 2024-11 |
| `remix_dao_dca_weekly_btceth_in_usdc_just_buy.py` | G2 | A | Buy-and-hold reference variant | BTC / ETH | 0x4585 · 0.05% | 1 | hourly | 10 | off | 2025-05 |
| `remix_dao_with_short.py` | G2 | A | Boundary check + short stop-loss | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2025-05 |
| `remix_dao_with_short_continue.py` | G2 | A | As above, short carries across rescales | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2025-05 |
| `remix_dao_refill.py` | G2 | A | Boundary check + refill of drained side | ETH / USDC | 0x88e6 · 0.05% | 1,000 | hourly | — | off | 2025-11 |
| `remix_dao_dca_weekly_btccbbtc_in_usdc.py` | G2 | A | Boundary check, conservative mode | **USDT / USDC** ⚠️ | 0x3416 · 0.01% | 2,000 | 15 min | 1 | off | 2025-11 |
| `remix_dao_current_impl_in_usdc.py` | G3 | A | Boundary check + 24 h lock | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2026-02 |
| `remix_dao_dca_weekly_non_stable_in_usdc.py` | G3 | A | Boundary check + 24 h lock | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2026-02 |
| `remix_dao_50p_non_stable_in_usdc.py` | G3 | A | Boundary check, 50% wrap range | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1 min | — | off | 2026-02 |
| `remix_dao_mark_perc_in_usdc.py` | G3 | F | Price outside mark band (±10%) | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2026-02 |
| `remix_dao_mark_perc_in_usdc_v2.py` | G3 | F | Price outside mark band (±20%) | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2026-02 |
| `remix_dao_isao_percentage_B.py` | G4 | D | Position went one-sided | BTC / ETH | 0x4585 · 0.05% | 1 | 1h 4h 8h 12h 1d | — | off | 2026-02 |
| `remix_dao_isao_percentage_B_v2.py` | G4 | D | One-sided + 20% overshoot buffer | BTC / ETH | 0x4585 · 0.05% | 1 | 1h 4h 8h 12h 1d | — | off | 2026-02 |
| `remix_dao_isao_percentage_D.py` | G4 | E | Price left the stored range | ETH / USDC | 0x88e6 · 0.05% | 100,000 | hourly | — | off | 2026-02 |
| `remix_dao_isao_percentage_D_v2.py` | G4 | E | Price left the stored range | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1h 4h 8h … | — | off | 2026-02 |
| `remix_dao_isao_tick_B_stable.py` | G4 | C | One-sided, or tick left the bucket | DAI / USDT | 0x48DA · 0.01% | 100,000 | 1h 4h 8h 12h 1d | 1 – 10 | off | 2026-02 |
| `remix_dao_isao_tick_B_stable_dontuse.py` | G4 | C | One-sided, or tick left the bucket | wstETH / ETH | 0x1098 · 0.01% | 100 | 1h 4h 8h 12h 1d | 1 – 10 | off | 2026-02 |
| `remix_dao_isao_tick_C.py` | G4 | B | One-sided, or tick left the range | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1h 4h 8h 12h 1d | 58 | off | 2026-02 |
| `remix_dao_isao_tick_B_stable_tick_gap.py` | G4 | B | Tick left range ± `tick_gap` | USDT / USDC | 0x3416 · 0.01% | 1,000,000 | 1h 4h 8h 12h 1d | 1 – 5 | off | 2026-06 |
| `remix_dao_valley_shape.py` | G5 | G | Tick left the full 7-band span | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1h 4h 8h 12h 1d | 140 | off | 2026-03 |
| `remix_dao_valley_shape_single_side.py` | G5 | G | Rebuilds bands single-sided from the breach | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1h 4h 8h 12h 1d | 140 | off | 2026-03 |
| `remix_dao_gamma.py` | **G5** | G | Tick left the full 17-band span | ETH / USDC | 0x88e6 · 0.05% | 100,000 | 1h 4h 8h 12h 1d | 140 | off | 2026-08 |

## Pools and pairs

Eight pools are live across the suite; two more sit commented in every file. Minute data is
read from `samples/real-data/<address>/`.

| Pool | Pair | Fee | Chain | Data from | Used by |
|---|---|---|---|---|---|
| `0x88e6a0c2…f5640` | USDC / WETH | 0.05% | Ethereum | 2021-05 | The default. 17 files, all ETH/USDC work |
| `0x4585FE77…5a20c0` | WBTC / WETH | 0.05% | Ethereum | 2021-05 | btceth double_sep, just_buy, percentage_B ×2 |
| `0x3416cF6C…3527C6` | USDC / USDT | 0.01% | Ethereum | 2021-11 | tick_gap, btccbbtc |
| `0xe8f7c89C…8f7e124` | WBTC / cbBTC | 0.01% | Ethereum | 2021-09 | btceth_in_usdc |
| `0x48DA0965…5B1406` | DAI / USDT | 0.01% | Ethereum | 2022-07 | tick_B_stable |
| `0x109830a1…FB7dAa` | wstETH / ETH | 0.01% | Ethereum | 2022-08 | tick_B_stable_dontuse |
| `0xC6962004…09E8D0` | WETH / USDC | 0.05% | Arbitrum | — | chaos, new_strat |
| `0xc473e2aE…9A3B57c` | ETH / USDC | 0.03 | Arbitrum | 2024-01 | remix_dao (prototype), reads `../real_data` |
| `0x56534741…9A83b2` | BTC / USDC | — | Ethereum | — | USD price feed only, for BTC-quoted runs |

## How the families grew

Dates are when the file first entered git. Each generation forked from the last rather than
replacing it.

**2024-09 · G0 — the prototype.** `remix_dao.py`: one strategy, one run, no sweep. 323 lines;
every later file is 1,000+ because the sweep harness got bolted on.

**2024-09 → 2024-11 · G1 — indicator and regime experiments.** `chaos` adds std/ATR range
widths; `new_strat` adds bull/bear parameter flipping driven by consecutive price moves. Both
run on Arbitrum.

**2024-11 → 2025-11 · G2 — the DCA line.** The big fan-out: weekly and always-on DCA, split
adds, BTC/ETH and stable pairs, short hedging with stop-loss, and refill.
`RemixDaoDcaWeekStratStrategy` becomes the class name every later file inherits — mostly by
copy, not by import.

**2026-02 · G3 — USDC-denominated rework.** Everything restated in USDC with 100,000 capital:
`current_impl` as the production baseline, plus the mark-price percentage band with its
leftover-absorbing second position.

**2026-02 → 2026-06 · G4 — ISAO, fixed grids.** The shift from "recentre on price" to "price
moves between fixed buckets", in tick space (`tick_B`) and price space (`percentage_B`), with
`C`, `D` and the tick-gap tolerance as variants.

**2026-03 → 2026-08 · G5 — shaped liquidity.** One position becomes many. `valley_shape`
places 7 percentage bands, `single_side` rebuilds them from the breached edge, and `gamma`
generalises to 17 tick bands with selectable weight profiles.

## Watch out

Things that will mislead you if you read these files quickly.

**Two filenames no longer match their pair.** `dca_weekly_btceth_in_usdc.py` is currently
pointed at the **BTC/cbBTC** pool, and `dca_weekly_btccbbtc_in_usdc.py` at **USDC/USDT**. The
names record what they were forked for, not what they run.

**The active config is invisible in a filename or folder.** Pair, capital, sweep and date
ranges are all comment-toggled. Two runs of the same file weeks apart can differ in every
input, and only `git diff` records it. The result folder name carries the pair and capital, so
keep old result folders rather than re-deriving.

**In-range statistics read 0 in the G5 files.** `on_bar()` gates on
`utils.current_position_info`, which the multi-position strategies never set — so it returns
immediately every minute. `in_range_pct`, `lock_pct` and `total_minutes` come out as 0 in the
APR CSV. Returns and fees are unaffected.

**Fixes do not propagate.** Each file carries its own ~1,100-line copy. The rescale-logging
fixes made in `gamma` (per-band fees and amounts summed rather than last-band-only) still need
applying to `valley_shape` and `valley_shape_single_side`, which were byte-identical before
that change.

**One file is marked unusable.** `isao_tick_B_stable_dontuse.py` — kept for its wstETH/ETH
configuration, not for its results.

---

Compiled from the active (uncommented) configuration of each file. Verify against the source
before relying on any row — these scripts are edited in place between runs.
