# Rust demeter: setup, running strategies, and writing strategies in Rust

This guide covers:

1. [Setup](#1-setup)
2. [Running existing python strategies](#2-running-existing-python-strategies)
3. [What changes for existing strategies](#3-what-changes-for-existing-strategies)
4. [Writing a strategy in Rust](#4-writing-a-strategy-in-rust)
5. [Troubleshooting](#5-troubleshooting)

For architecture, verification results, performance numbers and the list of python engine quirks,
see [README.md](README.md).

---

## 1. Setup

### 1.1 Prerequisites

| tool | version | check |
|---|---|---|
| Rust toolchain | ≥ 1.94 (fastnum requires it) | `rustc --version` → install/update with `rustup update` |
| Python | ≥ 3.11 (the remix_dao strategies use 3.12 f-string syntax, so **3.12+**) | `python3 --version` |
| maturin | ≥ 1.7 | installed into the venv below |

### 1.2 Create the virtual environment

The repo's old `.venv` points to a Homebrew Python that no longer exists, so use a fresh one.
The commands below put it in `rust/.venv`; any location works.

```bash
cd demeter/rust
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install maturin "pandas>=2.2,<3" "numpy>=1.26.4" pyarrow orjson python-dateutil pytz
# extra packages some sample strategies import:
.venv/bin/pip install matplotlib ta-lib
```

pandas 3.x is not supported. Keep `pandas<3`, as the original demeter did.

### 1.3 Build and install

```bash
cd demeter/rust
.venv/bin/maturin develop --release
```

- The first build compiles polars and takes ~5–6 minutes. Later builds are incremental.
- This installs the package **`demeter`** (distribution name `zelos-demeter-rs`) in *editable*
  mode:
  - edits to python files under `rust/python/demeter/` take effect immediately;
  - edits to Rust code (`demeter-core/`, `demeter-py/`) need `maturin develop --release` again.
- Always build with `--release`. A debug build is about 10–20× slower.

Check that the Rust version is the one being imported:

```bash
.venv/bin/python -c "import demeter; print(demeter.__file__, demeter._rs.__version__)"
# -> .../demeter/rust/python/demeter/__init__.py 0.1.0
```

If the path points to `.../demeter/demeter/__init__.py`, you are importing the **old** python
package; see [Troubleshooting](#5-troubleshooting).

### 1.4 Installing into another environment (wheel)

```bash
cd demeter/rust
.venv/bin/maturin build --release            # -> target/wheels/zelos_demeter_rs-*.whl
/path/to/other/python -m pip uninstall -y zelos-demeter   # remove the old python package first
/path/to/other/python -m pip install target/wheels/zelos_demeter_rs-*.whl
```

The wheel is built for the Python version and platform it was built on (e.g. cp313, macOS arm64).
Build one per target, or on each machine.

### 1.5 Run the tests (optional)

```bash
cd demeter/rust
cargo test -p demeter-core            # Rust unit + golden tests
cargo clippy --workspace --all-targets -- -D warnings
```

The original python unit tests can run against the Rust package. Run them from a directory
where the repo root is **not** on `sys.path`:

```bash
mkdir -p /tmp/rs_tests && cd /tmp/rs_tests
ln -sfn /path/to/demeter/tests tests && ln -sfn /path/to/demeter/tests/data data
/path/to/demeter/rust/.venv/bin/python -m pytest -q --import-mode=importlib -p no:cacheprovider \
  tests/uni_lp_market_test.py tests/uni_lp_market_test_token1_is_quote.py tests/uni_lp_add_liq_by_val.py \
  tests/uni_lp_add_liq_by_val_token1_is_quote.py tests/uni_lp_core_test.py tests/uni_lp_helper_test.py \
  tests/uni_lp_test_calc_liq.py tests/uni_lp_data_test.py tests/strategy_trigger_test.py \
  tests/actuator_test.py tests/strategy_data_access_test.py tests/metric_test.py tests/indicator_test.py
# 102 passed
```

---

## 2. Running existing python strategies

Run them exactly as before, with the new venv's python:

```bash
cd demeter/samples/strategy-example
../../rust/.venv/bin/python remix_dao_gamma.py
```

Rules:

- **Do not** set `PYTHONPATH` to the repo root, and do not run scripts *from* the repo root.
  Either one makes python pick up the old `demeter/` source folder instead of the installed Rust
  package. Running from `samples/strategy-example` (as you do today) is fine.
- `multiprocessing.Process` / `Pool` work as before (e.g. the `__main__` block of
  `remix_dao_gamma.py`, `62_multiprocess.py`, `BacktestManager`). Each process builds its own
  engine objects.
- Results match the old engine: every value matches to at least 1e-18 relative (see README).
- The `~/.demeter` feather cache is not used. Loading a year of minute CSVs takes ~0.7 s.

### Choosing quirk-compatible or corrected behaviour

By default the engine reproduces the python engine's quirks, so results are identical to past
runs. To use the corrected behaviour (listed in README, "python engine quirks"):

```python
actuator = Actuator()
actuator.legacy_quirks = False   # default True
```

In the full-year gamma benchmark this changes the final net value by about +0.05%. Pick one mode
per study and don't compare numbers across modes.

---

## 3. What changes for existing strategies

**Short answer: nothing for the strategies in `samples/strategy-example` that work today.**

Every sample was run on both the old python engine and the Rust engine (one-day tutorials; the
`remix_dao_*` strategies through `process_for_date` over 2022-01-01…07):

| result | strategies |
|---|---|
| run on both engines, **all 229 result CSVs identical** | 01, 02, 04, 05, 06, 07, 12, 13, 14, 15, 61, 62, remix_dao_gamma, _gamma_single_side, _gamma_single_side_half_shape, _current_impl_in_usdc, _dca_weekly, _dca_weekly_btccbbtc_in_usdc, _dca_weekly_non_stable_in_usdc, _isao_percentage_B, _B_v2, _D, _D_v2, _isao_tick_B_stable_tick_gap, _isao_tick_C, _mark_perc_in_usdc, _mark_perc_in_usdc_v2, _refill, _valley_shape, _valley_shape_single_side, _with_short |
| fail on the **old engine too**, same error; not caused by the port | `03_proprieties_access`, `11_deposit_by_SMA` (import `demeter.metrics`, which no longer exists → use `demeter.result`); `remix_dao`, `_chaos`, `_dca`, `_dca_weekly_btceth_*`, `_dca_weekly_double_sep`, `_new_strat` (import `RowData`, removed from demeter → use `Snapshot`); `_50p_non_stable_in_usdc` (`INIT_PRICE` not imported); `_with_short_continue` (a `KeyError` in the strategy's own logic); `_isao_tick_B_stable`, `_isao_tick_B_stable_dontuse` (pool data missing in `samples/real-data`) |
| not supported (markets not ported) | `21_aave_*`, `22_aave_*`, `23_delta_hedging`, `24_delta_hedging_gmx_uni`, `31_deribit_*`, `51/52/53_gmx_*`, `gmx_v2_short_eth*` |

### 3.1 Behaviour differences to know when writing *new* python strategies

The public API is the same. A few objects are now light views over the Rust engine instead of
pandas objects. Normal usage (attribute and item access, the calls demeter documents) works. Some
pandas-specific tricks behave differently:

| object | before | now | works | differs |
|---|---|---|---|---|
| `snapshot.market_status[key]`, `market.market_status.data` | `pd.Series` row | `BarView` | `row.price`, `row.closeTick`, `row["price"]`, user columns (`row.sma`), `.get()`, `.to_dict()`, `.keys()`, `.index` | other Series methods (`.values`, `.iloc`, arithmetic on the whole row) → use `.to_dict()` first |
| `snapshot.prices` | `pd.Series` | `PriceRow` | `prices["ETH"]`, `prices.ETH`, `.get()`, `.to_dict()`, `.items()`, `in` | Series methods → `.to_dict()` |
| `market.data`, `strategy.data[key]`, `load_uni_v3_data(...)` | `pd.DataFrame` | `MarketData` proxy | `data["price"]` / `data.price` (a pandas Series), `data.loc[...]`, `data.iloc[...]`, `len()`, `copy.deepcopy`, `data["x"] = series`, `market.data = df` | `isinstance(data, pd.DataFrame)` is False; any pandas method builds the full DataFrame once (~1–2 s per year of data); use `data.to_pandas()` if you need a real DataFrame |
| writes to market data | `market.data.loc[ts, "x"] = v` changed the data | same call only changes a pandas copy | `market.data["x"] = series`, `market.data = frame`, `strategy.add_column(...)` | assignments into the frame returned by pandas calls (`.loc[...] =`, `.iloc[...] =`) are not seen by the engine |
| `market.positions` | `dict` | live `Mapping` view | `len`, `in`, iteration, `[pos].liquidity`, `.items()`, `.copy()` | `del positions[k]` and `positions.pop(k[, default])` remove the entry like the python dict does: its liquidity and fees are dropped, not returned to the broker. `pop` returns a detached `Position` copy. Other dict writes (`positions[k] = ...`, `clear`, `update`) are not supported. |
| `strategy.account_status_df` in `finalize` | DataFrame | built lazily on first use | all DataFrame access | — |
| Decimals returned by the engine | 35-digit python `Decimal` | same, rounded to 35 digits | — | internal math uses 38 digits; values can differ from the old engine in the last 1–2 digits (≤1e-30 relative) |
| `actuator.account_status`, `actuator.actions` | lists | list-like views | indexing, `len`, iteration | not `list` instances (`list(...)` if needed) |

**Market subclasses** (like `UniLpMarketV2`) work when they add methods, or override methods that
your own strategy code calls. The engine does not see python overrides of the methods it calls
itself:

- from the loop: `update`, `set_market_status`, `get_market_balance`, `check_market`;
- from other engine methods: `swap`, `buy`, `sell`, `collect_fee`, `add_liquidity_by_tick`.
  For example `even_rebalance` calls the native `buy`/`sell`, and `remove_liquidity(collect=True)`
  calls the native `collect_fee`.

`Actuator.run` prints a warning if a market subclass overrides any of these. None of the sample
strategies do.

**Pickling / processes:** markets and `market.data` can be pickled (`BacktestManager(threads=N)`,
`Pool`), but only data and settings travel: open positions and the current market status do not.
The same holds for normal use, where markets are pickled before a run.

When not to use this port: aave / deribit / gmx / squeeth markets are not ported. Keep the old
python package (separate venv) for those strategies.

### 3.2 Making python strategies faster (optional, no Rust needed)

On the Rust engine most of the remaining time per minute is calls back into python. Things that
help:

- **Don't override `on_bar` / `after_bar` if the body does nothing useful.** The engine skips
  hooks that aren't overridden. `remix_dao_gamma.py`'s `on_bar` returns immediately because
  `utils.current_position_info` is never set; removing it saves ~1–2 s per simulated year.
- **Use the built-in triggers** (`AtTimeTrigger`, `PeriodTrigger`, `TimeRangeTrigger`, ...). The
  engine evaluates them natively. A custom `Trigger` subclass with a python `when()` (e.g.
  `WeeklyTrigger` in remix_dao_utils) is called every minute.
- Don't call `actuator.account_status_df` inside the loop; use `actuator.account_status`.

---

## 4. Writing a strategy in Rust

A strategy written in Rust runs with no python in the loop: about 2.4× faster than the same
strategy in python on the Rust engine (full-year gamma: 3.3 s vs 8.0 s; the old engine takes
139 s). Worth it for large parameter sweeps; see README, "Performance".

`demeter-core/examples/simple.rs` is the minimal example from 4.5 (`cargo run --release -p demeter-core --example simple`).
`demeter-core/examples/gamma.rs` is a complete port of `remix_dao_gamma.py`: bands, shapes, first
LP, hourly rescale, final result. It reproduces the python results. Start from it.

```bash
cd demeter/rust
cargo run --release -p demeter-core --example gamma -- 2022-01-01 2022-12-31 triangle 0.05 3600
#                                               start      end      shape  ratio rescale(seconds)
```

### 4.1 Where to put your strategy

Either:

- **As an example** in this workspace: add `demeter-core/examples/my_strategy.rs`, run with
  `cargo run --release -p demeter-core --example my_strategy`; or
- **As your own crate** (recommended for real work):

  ```toml
  # my-strategies/Cargo.toml
  [package]
  name = "my-strategies"
  version = "0.1.0"
  edition = "2021"

  [dependencies]
  demeter-core = { path = "../demeter/rust/demeter-core" }
  chrono = "0.4"

  [profile.release]
  lto = "thin"
  codegen-units = 1
  ```

### 4.2 The pieces

| python | Rust (`demeter_core::...`) |
|---|---|
| `Actuator()` | `actuator::Actuator::new(allow_negative_balance)` |
| `UniV3Pool(token0, token1, 0.05, quote)` | `types::UniV3Pool::new(token0, token1, dec("0.05"), quote, None /* tick spacing */)` |
| `UniLpMarket(MarketInfo("lp"), pool)` | `uniswap::UniLpMarket::new(MarketInfo::new("lp"), pool)` → wrap with `broker::shared(...)` |
| `market.load_data(chain, addr, start, end)` | `market.load_data("ethereum", addr, start_date, end_date)` (set `market.data_path` first) |
| `broker.add_market(market)` | `actuator.add_market(market_handle.clone())` |
| `broker.set_balance(token, x)` | `actuator.broker.borrow().wallet.borrow_mut().set(&token, x)` |
| `actuator.set_price(market.get_price_from_data())` | `data::price_from_data(...)` + `PriceTable::new(...)` + `actuator.set_price(table, quote)` (see below) |
| `class S(Strategy)` | `struct S; impl actuator::Strategy for S { ... }` |
| `self.triggers.append(AtTimeTrigger(t, do=self.f))` | `self.triggers.push(TriggerCond::at_time(ts), S::f)` with a `trigger::Triggers<S>` field |
| `actuator.run()` | `actuator.run(&mut strategy)?` |
| `actuator.account_status_df` | `actuator.account_status.borrow()` (`Vec<AccountRow>`) or `actuator.account_status_frame()?` (polars DataFrame) |
| `actuator.actions` | `actuator.log.borrow().actions` |
| `actuator.legacy_quirks = False` | `actuator.compat.legacy_quirks = false` (set before `add_market`) |
| `actuator.interval = "1h"` | `actuator.interval_secs = 3600` |

Numbers are `dec::Dec` (a 38 digit decimal, `fastnum::D128`). Create them with
`dec::parse_lossy("0.05")?`, `dec::from_i64(100)`, `dec::zero()`, `dec::one()`. Print them with
`dec::to_plain_string(&x)`.

Timestamps (`types::Ts`) are seconds since the epoch, naive UTC like pandas:
`types::naive_to_ts(&NaiveDate::from_ymd_opt(2022,1,1)?.and_hms_opt(0,0,0)?)`.

### 4.3 Strategy trait

All methods are optional:

```rust
pub trait Strategy {
    fn initialize(&mut self, ctx: &Ctx) -> Result<()>;                       // before the loop
    fn before_bar(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()>;
    fn run_triggers(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()>;       // evaluate your triggers
    fn on_bar(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()>;             // before fees of this minute accrue
    fn after_bar(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()>;          // after fees accrued
    fn notify(&mut self, ctx: &Ctx, actions: &[Action]) -> Result<()>;       // actions of this minute
    fn finalize(&mut self, ctx: &Ctx) -> Result<()>;                         // after the loop
    fn on_error(&mut self, ctx: &Ctx, s: &Snapshot, e: DemeterError) -> Result<()>; // default: re-raise
}
```

Per minute the engine does, in this order:

1. set market status;
2. `before_bar`;
3. `run_triggers`;
4. `on_bar`;
5. refresh markets that changed;
6. fee update;
7. `after_bar`;
8. `notify`;
9. record account status.

This is the same order as the python engine.

- `Snapshot { ts, row_id, price_row }`: `ctx.price(&s, "ETH")?` gives the token price in the quote
  token.
- `ctx.market("lp")?` gives the market handle; use `.borrow()` to read and `.borrow_mut()` to
  trade. Don't keep a borrow alive while calling another method that borrows the same market.
- Token balances: `m.wallet()?.borrow().balance(&token)?`, or through `ctx.broker`.
- Current bar: `m.status()?.bar` has `price`, `close_tick`, `current_liquidity`, `in_amount0/1`,
  `lowest_tick`, `highest_tick`, ...

### 4.4 Market operations (`UniLpMarket`)

The same functions as python. `Option` replaces python's `None` / `-1` defaults.

| call | returns |
|---|---|
| `add_liquidity(lower_price, upper_price, quote_max: Option, base_max: Option)` | `(PositionInfo, base_used, quote_used, liquidity)` |
| `add_liquidity_by_tick(lower_tick, upper_tick, base_max, quote_max, sqrt_price_x96: Option<U256>, tick: Option<i32>, trim_tick: bool)` | same |
| `add_liquidity_by_value(lower_tick, upper_tick, value: Option, trim_tick)` | same |
| `remove_liquidity(&pos, liquidity: Option<u128>, collect: bool, sqrt: Option, remove_dry_pool: bool)` | `(base, quote)` |
| `collect_fee(&pos, max0: Option, max1: Option, remove_dry_pool: bool, collect_to_user: bool)` | `(base_fee, quote_fee)` |
| `buy(base_amount, price: Option)` / `sell(base_amount, price: Option)` | `(fee, spent, got)` |
| `swap(amount, &from_token, &to_token, price: Option, throw_action: bool)` | `(fee, to_amount)` |
| `even_rebalance(price: Option)` | `()` |
| `get_market_balance()` | `UniLpBalance { net_value, liquidity_value, base_uncollected, ... }` |
| `get_position_status(&pos)` / `get_position_amount(&pos)` | status / `(amount0, amount1)` |
| `price()`, `price_to_tick(&p)`, `price_to_raw_tick(&p)`, `tick_to_price(t)` | |
| `positions` | `Vec<(PositionInfo, Position)>` in insertion order |

Math helpers (`demeter_core::math`): `get_sqrt_ratio_at_tick`, `get_liquidity`, `get_amounts`,
`nearest_usable_tick`, `base_unit_price_to_tick`, `tick_to_base_unit_price`, `amounts_relation`,
`estimate_ratio`, ...

### 4.5 Minimal complete example

```rust
use chrono::NaiveDate;
use demeter_core::actuator::{Actuator, Ctx, PriceTable, Snapshot, Strategy};
use demeter_core::broker::shared;
use demeter_core::data;
use demeter_core::dec::{self, parse_lossy};
use demeter_core::trigger::{TriggerCond, Triggers};
use demeter_core::types::{naive_to_ts, MarketInfo, TokenInfo, UniV3Pool};
use demeter_core::uniswap::UniLpMarket;
use demeter_core::Result;

/// Put all funds in a ±10% range at the start, collect fees every day.
struct Simple {
    triggers: Triggers<Simple>,
    start: i64,
}

impl Simple {
    fn open(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.market("lp")?;
        let mut m = m.borrow_mut();
        m.even_rebalance(None)?;
        let p = m.price()?;
        let lower = p * parse_lossy("0.9").unwrap();
        let upper = p * parse_lossy("1.1").unwrap();
        m.add_liquidity(lower, upper, None, None)?;
        Ok(())
    }

    fn collect(&mut self, ctx: &Ctx, _s: &Snapshot) -> Result<()> {
        let m = ctx.market("lp")?;
        let mut m = m.borrow_mut();
        let keys: Vec<_> = m.positions.iter().map(|(k, _)| *k).collect();
        for k in keys {
            m.collect_fee(&k, None, None, false, true)?;
        }
        Ok(())
    }
}

impl Strategy for Simple {
    fn initialize(&mut self, _ctx: &Ctx) -> Result<()> {
        self.triggers.push(TriggerCond::at_time(self.start), Simple::open);
        self.triggers.push(TriggerCond::period(86_400, false, 0).unwrap(), Simple::collect);
        Ok(())
    }
    fn run_triggers(&mut self, ctx: &Ctx, s: &Snapshot) -> Result<()> {
        let mut t = std::mem::take(&mut self.triggers);
        let r = t.run(self, ctx, s);
        self.triggers = t;
        r
    }
}

fn main() -> Result<()> {
    let usdc = TokenInfo::new("usdc", 6);
    let eth = TokenInfo::new("eth", 18);
    let pool = UniV3Pool::new(usdc.clone(), eth.clone(), parse_lossy("0.05").unwrap(), usdc.clone(), None);
    let (start, end) = (NaiveDate::from_ymd_opt(2022, 1, 1).unwrap(), NaiveDate::from_ymd_opt(2022, 1, 31).unwrap());

    let mut market = UniLpMarket::new(MarketInfo::new("lp"), pool);
    market.data_path = "../samples/real-data/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640".into();
    market.load_data("ethereum", "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", start, end)?;
    let market = shared(market);

    let mut actuator = Actuator::new(false);
    actuator.add_market(market.clone())?;
    actuator.broker.borrow().wallet.borrow_mut().set(&usdc, dec::from_i64(10_000));
    actuator.broker.borrow().wallet.borrow_mut().set(&eth, dec::zero());

    // price table from the pool (python: actuator.set_price(market.get_price_from_data()))
    let table = {
        let m = market.borrow();
        let d = m.data()?;
        let (tokens, cols) = data::price_from_data(d, &m.pool);
        PriceTable::new(d.ts.clone(), tokens, cols)?
    };
    actuator.set_price(table, usdc)?;

    let mut strategy = Simple { triggers: Triggers::default(), start: naive_to_ts(&start.and_hms_opt(0, 0, 0).unwrap()) };
    actuator.run(&mut strategy)?;

    let last = actuator.account_status.borrow().last().cloned().unwrap();
    println!("final net value: {} USDC", dec::to_plain_string(&last.net_value));
    // full per-minute history as a polars DataFrame (columns like "net_value|", "lp|net_value", "price|ETH")
    let df = actuator.account_status_frame()?;
    println!("{}", df.head(Some(3)));
    Ok(())
}
```

### 4.6 Parameter sweeps

Engine objects use `Rc`/`RefCell`, so they are **not `Send`**: create the market, actuator and
strategy *inside* each thread or process, never share them. For a sweep:

- run one process per configuration or date range (like the python `__main__` blocks); or
- use `std::thread::scope` with each thread loading its own data and building its own `Actuator`.
  Market data loading is cheap (≈0.7 s per year).

### 4.7 Checking a Rust port against its python original

Run the python strategy once on the Rust engine (it gives the same results as the old engine) and
compare the key outputs (final net value, fees, rescale count) with your Rust version. For gamma:

```bash
cd samples/strategy-example
../../rust/.venv/bin/python ../../rust/golden/bench_gamma.py 2022-01-01 2022-12-31    # python strategy
cd ../../rust && ./target/release/examples/gamma 2022-01-01 2022-12-31                # rust strategy
```

Both print `total_net_value=47547.06833353898…`. Differences in the last digits come from
python's 35-digit vs Rust's 38-digit decimals inside the strategy's own arithmetic.

---

## 5. Troubleshooting

| symptom | cause / fix |
|---|---|
| `demeter.__file__` points to `demeter/demeter/__init__.py` | The old package is shadowing the Rust one. Don't run from the repo root, unset `PYTHONPATH`, and `pip uninstall zelos-demeter` if it was installed in develop mode (`zelos_demeter.egg-info`). |
| `ModuleNotFoundError: demeter._rs` | Not built in this venv: run `maturin develop --release` with this venv's maturin. |
| `ImportError: cannot import name 'RowData'` / `demeter.metrics` | Old API names, broken in the python version too: use `Snapshot` / `demeter.result`. |
| `OSError: resource file ... not found` | Minute CSV missing for that pool/day. Download with demeter-fetch into `samples/real-data/<pool address>/`. |
| Backtest much slower than expected | Built without `--release`; or a python strategy overrides `on_bar`/`after_bar` with heavy code, or uses custom python triggers (see 3.2). |
| `RuntimeError: backtest is already running` | `actuator.run()` called from inside a strategy callback. |
| `UserWarning: ... overrides update ...` | A market subclass overrides a method the engine calls natively; see 3.1. |
| Results differ slightly from an old run | Check `actuator.legacy_quirks` (default `True` = same as the old engine). Otherwise differences are ≤1e-30 relative, from the precision difference. |
| pandas 3.x installed | `pip install "pandas>=2.2,<3"`. |
