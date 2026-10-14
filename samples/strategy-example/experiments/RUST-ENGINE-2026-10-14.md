# Rust engine on feat/dino-v6-opt: equivalence with the python engine (2026-10-14)

Not an experiment (no strategy change): the backtest engine is swapped, the strategy code is not. Dino's rule
(2026-10-14, "以後這個分支跑回測都要很快且正確"): every backtest on this branch runs on the Rust engine, which must give
the python engine's results byte for byte.

## What was added

- `rust/` from Maker's `maker-defense` branch (Steven, `c7b2542` .. `12f8486`, 2026-09-29 .. 10-01): a Rust port of
  demeter's Uniswap v3 engine with python bindings. Installed into its own venv, `import demeter` resolves to the Rust
  package; `v6_validate.py` runs unchanged (setup and run lines in `CLAUDE.md`).
- Python-exact arithmetic in `rust/demeter-core` (below), so the numbers equal the python engine's to the last digit.
- Guards: `engine_guard.py` (v6_validate.py refuses the python engine unless `ENGINE=python`), `experiments/engine_probe.py`
  and `experiments/engine_check.py` (both engines, byte for byte, ~2 min), `.githooks/pre-commit` (runs the check on any
  commit touching `rust/` or `demeter/`; enable with `git config core.hooksPath .githooks`).

## Fixes

Python demeter runs `decimal` at 35 digits: every `+ - * /` rounds its exact result half-even to 35 digits and keeps an
ideal exponent. The port used fastnum's 38-digit arithmetic. A strategy that truncates amounts to token units turns a
last-digit difference into a visible one.

| what | python | port before | effect seen |
|---|---|---|---|
| tick → price | `x96 / Q96`, `** 2` (libmpdec: 38 digits, then 35), `* Decimal(10 ** k)` (a float for k < 0), `1 / p` | one 38-digit pass; last digit wrong on ~half of all ticks | v6 on WBTC/USDC `0x99ac`: initial split `29999.99…98` instead of `30000.00…02` USDC, one USDC unit lost when truncating, equity off by up to 8e-11 relative from day 1 |
| price → sqrt x96 | `1 / price`, `/ Decimal(10 ** k)`, `sqrt`, `int(sqrt * Q96)` | one 38-digit pass; at a tick's own price one unit below that tick's ratio | a position ending at the current tick kept 7.9e-29 USDC where python returns 0 (`0x88e6`, 2026-06-04) |
| every `+ - * /` (fees, values, balances, net value) | 35-digit rounding per step, python's exponents | 38 digits | last digit of net values and amounts on ~8% of minutes (probe); trailing zeros / zero exponents differ |
| partial `remove_liquidity(pos, liquidity)` | `float_param_formatter` makes the int a Decimal; the position's liquidity stays a Decimal and `liquidity * 2**96 * delta` rounds | exact int math | last digit of that position's amounts from then on (v6 resize EXP-055, tranches EXP-061/063) |
| `estimate_liquidity` out of range | fractional `amount * 10**d` into `mul_div` | whole wei first | liquidity off by many units |
| `Decimal(float)` in `add_liquidity_by_value` / `estimate_amount`, `base_unit_price_to_tick` | the float's exact binary value | 38 digits | last digit, rare |
| `lower_tick == upper_tick` | ZeroDivisionError | silent zero-liquidity position | error now |
| `account_status_df` / `market.data` export | exact Decimals | one Decimal(38, scale) per column; small values in a wide column lost digits | lossless now (text fallback); cells may print extra trailing zeros, same value |

`dec::Dec` (a D128 wrapper) now does `+ - * /` and `sqrt` like python (exact big-integer result, one rounding,
python's exponent); the special steps above are reproduced as python does them (`rust/README.md`, "Python's decimal
arithmetic"). The README's other documented quirks (`legacy_quirks`, default on) are unchanged.

## Checks (final engine)

| check | result |
|---|---|
| `Dec` vs python `decimal` (prec 35), 88,691 random cases: add/sub/mul/div/sqrt, zeros, signs, exponents -60..20, 80-place gaps | all equal in value, coefficient, exponent and sign (2,000-case subset committed: `rust/golden/out/py_decimal_ops.txt`) |
| `cargo test -p demeter-core` (golden vectors + last-digit tests), clippy `-D warnings` | 24 pass, clean |
| tick → price, every 10th tick of ±887270, six decimal pairs, both quote sides | 2.1 M equal, as text (before: ~half differed) |
| price → sqrt x96, tick-boundary and random 35-digit prices | 720 k equal |
| `engine_probe.py`: three pools (both quote sides, 6/8/18 decimals, a non-USD pair), two days each, every market operation (5 kinds of add, collect, partial/full remove, buy, sell, swap, even_rebalance, estimate_liquidity/amount, price/tick), per-minute net value, positions, balances, `account_status_df` | 10,122 lines byte-identical (before the arithmetic fix: 129 lines differed) |
| EXP-157 batch `opt:A,GA,GB,GC,GD,GE,GF,GG,GH`, `SPEC=v1`, full history on its seven pools, against the stored python runs | every `equity_*`, `fees_*`, `result_*` byte-identical; summary identical except `secs` |
| partial removals: `opt:A,AR,AX` full history on `0x88e6` and `0x99ac`, both engines run today | byte-identical (AR resizes 3x in May-June 2022 alone) |
| `0x99ac` full history `opt:A,GA` rerun on python today | byte-identical to the stored 2026-10-07 run (the stored runs are a valid reference) |
| WBTC/ETH `0x4585` full history `opt:A,GJ`, old v6 (`BINANCE_WARM=1`), against the stored python run | byte-identical |
| `engine_check.py` sensitivity | the probe flags the first-round engine (129 lines); the short v6 runs alone did not catch the price bug, hence the probe |

## Speed

| run | python | Rust |
|---|---|---|
| `0x88e6` 2022, three variants, 3 workers (quiet machine) | 97 s | 8 s (first-round engine) |
| `0x99ac` full history 2021-11 .. 2026-09, two variants, 2 workers (quiet) | 499 s | 29 s |
| `0x88e6` full history, `opt:A,AR,AX`, 3 workers, machine at load ~17 | 1295 s | 149 s |
| `0x99ac` full history, `opt:A,AR,AX`, 3 workers, load ~17 | 942 s | 102 s |

Python-exact arithmetic costs ~20% against the first-round 38-digit engine (same window side by side: 19.2 s vs 15.6 s);
the Rust engine stays ~9x faster than python. Peak memory of a full-history Rust run: ~3 GB per worker.
