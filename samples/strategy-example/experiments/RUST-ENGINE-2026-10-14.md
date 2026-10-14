# Rust engine on feat/dino-v6-opt: equivalence check (2026-10-14)

Not an experiment (no strategy change): the backtest engine is swapped, the strategy code is not.

## What was added

- `rust/` from Maker's `maker-defense` branch (Steven, `c7b2542` .. `12f8486`, 2026-09-29 .. 10-01): a Rust port of
  demeter's Uniswap v3 engine with python bindings. Installed into its own venv, `import demeter` resolves to the Rust
  package; `v6_validate.py` runs unchanged (setup and run lines in `CLAUDE.md`).
- Two fixes in `rust/demeter-core` so the numbers equal the python engine's to the last digit (below).

## Fixes

Python demeter computes prices with `decimal` at 35 digits, rounding after every step. The port computed both price
conversions in 38 digits and rounded once, which differs in the last digit:

| conversion | python (`demeter/uniswap/helper.py`) | port before | effect in defense v6 |
|---|---|---|---|
| tick → price (`market.data` `price` / `close`) | `x96 / Q96`, `** 2` (libmpdec squares at 38 digits, then rounds to 35), `* Decimal(10 ** k)` (a float for k < 0), `1 / p` | last digit wrong on about half of all ticks, on every pool | the initial split came out `29999.99…98` instead of `30000.00…02` USDC; truncating to USDC units lost one unit, `quote_used` moved 7.4e-6 USDC, the WBTC/USDC `0x99ac` full-history equity drifted by up to 8e-11 relative from day 1 |
| price → sqrt price x96 (every amount and fee) | `1 / price`, `/ Decimal(10 ** k)`, `Decimal.sqrt`, `int(sqrt * Q96)` (product rounded to 35 digits first) | at a tick's own price, one unit below that tick's sqrt ratio | a position ending at the current tick kept 7.9e-29 USDC where python returns 0 (ETH/USDC `0x88e6`, 2026-06-04): `quote_removed` printed `0.00000000` instead of `0` |

Both now follow python's steps exactly with big-integer arithmetic (`dec::ratio_round`, `dec::sqrt_round`,
`math::sqrt_price_x96_to_base_unit_price`, `math::base_unit_price_to_sqrt_price_x96`). The README's other
documented quirks (`legacy_quirks`, default on) are unchanged.

## Checks

| check | result |
|---|---|
| tick → price, every 10th tick of ±887270, six decimal pairs, both quote sides (2.1 M) | 0 differ (before the fix: 21205 of 40000 ticks on the `0x99ac` range) |
| price → sqrt price x96, tick boundary prices and 20 k random 35-digit prices per case (720 k) | 0 differ |
| `cargo test -p demeter-core` (golden vectors from the python engine + two new last-digit tests) | 23 pass, clippy clean |
| EXP-157 batch `opt:A,GA,GB,GC,GD,GE,GF,GG,GH`, `SPEC=v1`, full history on its seven pools (`0x88e6`, `0x8ad5`, `0xd0b5`, `0xc696`, `0x6c56`, `0x99ac`, `0xfbb6`), against the stored python runs | every `equity_*`, `fees_*`, `result_*` file byte-identical; summary CSV identical except `secs` |
| `0x99ac` full history `opt:A,GA` rerun on python today | byte-identical to the stored 2026-10-07 run (so the stored runs are a valid reference) |
| `0x88e6` 2022 `opt:A,GA,GD`, `SPEC=v1`, python and Rust run today | byte-identical |
| WBTC/ETH `0x4585` full history `opt:A,GJ`, old v6 (pool-price signal, `BINANCE_WARM=1`), against the stored python run | byte-identical |

## Speed (this machine, same invocation on both engines)

| run | python | Rust |
|---|---|---|
| `0x88e6` 2022, three variants, 3 workers | 97 s | 8 s |
| `0x99ac` full history 2021-11 .. 2026-09, two variants, 2 workers | 499 s | 40 s |
| `0x88e6` full history 2021-05 .. 2026-09, nine variants, 4 workers | ~8 min per variant (2 workers, 2026-10-07) | 99 s for all nine |

Peak memory of a full-history Rust run with two workers: 5–6 GB (whole process tree).
