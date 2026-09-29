# demeter in Rust

A Rust port of the demeter backtesting engine (Uniswap v3 only), with Python bindings. The
bindings are a drop-in replacement for the python `demeter` package.

```
rust/
  demeter-core/        pure Rust engine (no python): math, data loading (polars), UniLpMarket,
                       broker, triggers, actuator loop, Strategy trait
    examples/gamma.rs  remix_dao_gamma.py written as a Rust strategy
    tests/             golden tests against outputs of the original python engine
  demeter-py/          PyO3 bindings -> extension module `demeter._rs`
  python/demeter/      the `demeter` python package: original public API, heavy parts in Rust
  golden/              scripts that produce / compare python vs rust outputs
  pyproject.toml       maturin build of the python package
```

## Build and use

```bash
cd rust
python3 -m venv .venv && .venv/bin/pip install maturin "pandas>=2.2,<3" pyarrow orjson python-dateutil
.venv/bin/maturin develop --release      # installs `demeter` (Rust backed) into the venv
cargo test -p demeter-core               # Rust tests (golden files in golden/out)
```

After this `import demeter` resolves to the Rust-backed package. Existing strategies run
unchanged:

```bash
cd samples/strategy-example
../../rust/.venv/bin/python remix_dao_gamma.py
```

Do not put the repository root on `PYTHONPATH` (and do not run python *from* the repo root). If
you do, the original pure-python `demeter/` folder shadows the installed package.

## Does `remix_dao_gamma.py` run after the port?

**Yes, without modification.** That includes its helpers `market_v2.UniLpMarketV2`,
`base_strategy`, `remix_dao_utils`, `export_file` and `rm_types`. Verified with
`golden/make_golden.py` + `golden/compare.py`:

| check | result |
|---|---|
| one week × 5 rescale frequencies (`process_for_date`) | every per-minute `account_status_df` value, action and result CSV row identical |
| 2 weeks, narrow ranges, 13 rescales, 869 actions | identical |
| strategy metrics (`run_test` result dict) | worst relative difference 2e-34 |
| comparison tolerance | all 25 files match at 1e-28 relative |
| existing unit tests (`tests/uni_lp_*`, `actuator_test`, `strategy_*`, `metric_test`, `indicator_test`) | 102 / 102 pass on the Rust package |

All other sample strategies were run on both engines too: the same 31 of 45 run on both, and
all 229 result CSVs they write are identical. The other 14 fail on the old engine as well
(outdated imports, missing data, markets that were not ported). See
[GUIDE.md](GUIDE.md#3-what-changes-for-existing-strategies).

`UniLpMarketV2` reaches into private attributes (`_market_status`, `_pool`, `_is_token0_quote`,
`_convert_pair`). The Rust-backed `UniLpMarket` keeps all of them, so the subclass works as is.
`UniLpMarket.price_to_raw_tick` is also native now.

A market subclass can add methods and override methods your strategy calls. Overrides of
methods the engine itself calls are not used by the engine: `update`, `set_market_status`,
`get_market_balance`, `check_market`, and `swap` / `buy` / `sell` / `collect_fee` /
`add_liquidity_by_tick` when another engine method calls them. The engine prints a warning when a
subclass does this. None of the sample strategies do.

Decimals handed to python are rounded to 35 significant digits: return values, snapshot rows,
and the columns of `account_status_df` / `market.data`. That is the precision python demeter runs
with (`getcontext().prec = 35`), so strategy code sees the same numbers as before. Internally the
engine keeps 38 digits.

## Performance

`golden/bench_gamma.py` runs one gamma configuration (triangle shape, ±5%, hourly rescale, ETH/USDC
0.05%) over the full year 2022 (525,600 minutes, 252 rescales). Final values are identical:
net value 47547.06833353898582663432099808192 USDC in all three runs.

| engine / strategy | data load | backtest loop | per minute | speed-up |
|---|---|---|---|---|
| original python engine + python strategy | 11.6 s | 139 s | 264 µs | 1× |
| Rust engine + **unchanged** python strategy | 0.7 s | 8.0 s | 15 µs | 17× |
| Rust engine + Rust strategy (`examples/gamma.rs`) | 0.8 s | 3.3 s | 6.3 µs | 42× |

Where the time goes:

- **python engine:** pandas row lookups (`df.loc[ts]` per minute), rebuilding every position's
  value with python big ints and Decimal, and pandas Series creation per minute.
- **Rust engine:** native bar table. The price → sqrt price conversion (a 38 digit decimal sqrt,
  by far the most expensive per-minute operation) is memoized per distinct price. Out-of-range
  positions use cached amounts, and built-in triggers are evaluated in Rust.
- **What a Rust strategy saves on top:** about 9 µs per minute. That is the python `on_bar` call,
  the snapshot object, and python-side trigger bookkeeping. Gamma's `on_bar` returns immediately
  (it only counts in-range minutes of `utils.current_position_info`, which is never set), so most
  of that cost buys nothing. Deleting the method from a python strategy recovers much of it.

**Is it worth writing strategies in Rust?** Another 2.4× on top of the 17× from the engine. That
matters for large parameter sweeps (e.g. every shape × ratio × frequency × year). For day-to-day
work the unchanged python strategy on the Rust engine is usually fast enough. A full year takes
~8 s instead of ~2.5 min. Processes still parallelize as before (`multiprocessing`,
`BacktestManager(threads=N)`); markets and market data can be pickled (open positions are not
carried over).

## Is polars a replacement for pandas?

**Yes for data handling, no for the per-minute loop. Neither was the right tool for the loop.**

What polars does here (`demeter-core/src/data.rs`, `actuator.rs`):

- reads the demeter-fetch CSVs, all as strings, because amounts exceed i64;
- exports market data, prices and the account-status table as Arrow IPC;
- builds Decimal(38, s) columns with an adaptive scale.

The python layer turns that IPC into pandas with pyarrow, so no pyo3-polars version coupling is
needed.

What polars cannot do, and how it is handled:

| pandas feature used by demeter | polars | done instead |
|---|---|---|
| `df.loc[timestamp]` per minute, `ts in df.index` | no index | data converted once to `Vec<Bar>`, rows found by arithmetic on the minute grid |
| MultiIndex columns (`account_status_df["price"]["ETH"]`) | none | flat `l1\|l2` column names, rebuilt as a MultiIndex in python |
| object columns of python `Decimal` (35+ digits) | Decimal is i128, max 38 digits | values kept as `fastnum::D128` in Rust; big integers as u128/i128/U256/U512 |
| implicit index alignment (`add_column`, `concat(axis=1)`) | explicit joins | alignment by timestamp in Rust |
| `fillna` rules, `resample(...).agg(dict)` | `forward_fill`, `group_by_dynamic` exist | implemented directly on the minute grid, with the exact pandas rules (`origin="start_day"`, left closed / labelled) |

The public python API still returns pandas objects (`account_status_df`, `market.data[...]`,
`get_price_from_data()`), so strategies and analysis code keep working. pandas is now only used at
the edges, never per minute.

## ⚠️ IMPORTANT: python engine quirks

The python engine has behaviours that look like bugs. **By default the Rust engine reproduces
them**, so results match the python engine exactly. Set `actuator.legacy_quirks = False` (python)
or `EngineCompat { legacy_quirks: false }` (Rust) to get the corrected behaviour.

On the full-year gamma benchmark the corrected mode changes the final net value by **+0.05%**
(47571.35 vs 47547.07 USDC) and fees by +24 USDC, mostly because of quirk 2. Decide deliberately
which mode your results should use, and do not compare numbers across modes.

| # | quirk (python) | where | default (legacy) | `legacy_quirks = False` |
|---|---|---|---|---|
| 1 | Fee calculation with no previous tick treats NaN as "in range"; out of range it raises `decimal.InvalidOperation`. This never happens in a normal run (the first loop iteration already has a previous tick). | `uniswap/core.py` `update_fee` | same: in range → full fee, else error | no cross-range weighting without a previous tick |
| 2 | The second status refresh in an iteration (after an action, `has_update`) sets `last_tick` to the current close tick, so the cross-range fee weighting is skipped on every minute with an action. | `uniswap/market.py` `set_market_status` | reproduced | `last_tick` advances once per minute |
| 3 | `_sqrt_price_to_tick` = `int(math.log(float(sqrt), sqrt(1.0001)))` truncates toward zero; negative ticks are off by one, and float rounding can be off near boundaries. | `uniswap/helper.py` | reproduced | exact Uniswap `getTickAtSqrtRatio` (floor) |
| 4 | `nearest_usable_tick` uses python `round()`, which rounds half to even. | `uniswap/helper.py` | always reproduced (not a bug) | same |
| 5 | `AtTimesTrigger.when` does `self._time in snapshot.timestamp` and raises `TypeError`. | `strategy/trigger.py` | **fixed** in both modes | fixed |
| 6 | `Snapshot.market_status` has a mutable default shared by all snapshots. | `broker/_typing.py` | **fixed** in both modes | fixed |
| 7 | `PeriodTrigger` fires only on an exact timestamp match; a missing minute stops it forever. | `strategy/trigger.py` | reproduced | fires on the first minute at or after the scheduled time |
| 8 | `collect_fee` checks `if self._positions[position]:`, which is always true for a dataclass, so a collect action is always recorded. | `uniswap/market.py` | reproduced | same |
| 9 | Precision: python Decimal uses 35 digits, Rust uses 38. Rust also takes some exact 512-bit products in 38 digit decimal steps (reassociated). | everywhere | Decimals handed to python are rounded to 35 digits; ≤1e-30 relative on internal values | same |

Also different, intentionally:

- `Actuator.run` sets prices automatically from the first market when `set_price` was never
  called. python meant to, but failed its own quote-token check first.
- The `~/.demeter` feather cache is not used; loading CSVs with polars is fast (0.7 s per year).
  Note for comparisons: the python engine's cache key ignores the pool definition and quote
  token. A run with a different quote token over the same pool and dates silently reuses the
  cached data of the first run. Clear `~/.demeter` (or disable the cache) before comparing the
  engines.
- `market.data` is a proxy over the engine's data. Writes through `market.data[name] = series` or
  `market.data = frame` reach the engine; writes into the pandas frame it hands out
  (`market.data.loc[...] = x`) do not.
- Dropped markets: aave, deribit, gmx, squeeth (not needed per requirements).

## Writing a strategy in Rust

See `demeter-core/examples/gamma.rs`:

- implement `demeter_core::actuator::Strategy` (`initialize`, `on_bar`, `after_bar`,
  `run_triggers`, `notify`, `finalize`, `on_error`);
- register built-in triggers with `Triggers<Self>` and `TriggerCond::{at_time, period, ...}`;
- trade through `ctx.market("name")?.borrow_mut()`: `add_liquidity_by_tick`, `remove_liquidity`,
  `collect_fee`, `buy`, `sell`, `swap`, `get_market_balance`, ...

```bash
cargo run --release -p demeter-core --example gamma -- 2022-01-01 2022-12-31 triangle 0.05 3600
```

## Regenerating the golden files

```bash
cd samples/strategy-example
PYTHONPATH=../.. ../../rust/.venv/bin/python ../../rust/golden/make_golden.py math data quick gamma   # python engine
PYTHONPATH=../.. ../../rust/.venv/bin/python ../../rust/golden/make_golden.py gamma_narrow
GOLDEN_OUT=../../rust/golden/out_rs ../../rust/.venv/bin/python ../../rust/golden/make_golden.py data quick gamma gamma_narrow  # rust
cd ../.. && rust/.venv/bin/python rust/golden/compare.py --tol 1e-28
```
