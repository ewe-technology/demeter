# Engine fix: fee denominator counts in-range liquidity only (2026-10-29)

Jira QUAN-1213 (stage 2b of QUAN-1209). Defect 1 of the audit in `REPRO-2026-10-29-remix-v3_2-v2_1.md` section 4.

## Change

Both engines add our own liquidity to the pool's `currentLiquidity`, the denominator of every position's fee share
(`demeter/uniswap/market.py` `set_market_status`, then `core.py` `update_fee`). They added all of it, so a ladder's
out-of-range bands diluted the fees of the band in range.

New flag `market.fee_in_range_liquidity` (python `UniLpMarket`, Rust `UniLpMarket`, default `False` = old numbers).
On, the denominator adds only the positions that earn a fee in that minute: `V3CoreLib.earns_fee` / Rust `earns_fee`,
the same rule as `update_fee` (in range at both ticks, or the minute's tick path overlaps the range by more than zero).

Checks:

- `tests/uni_lp_fee_in_range_test.py`: 5 cases (default off; off counts all; on counts in range; a range crossed this
  minute counts; a range only touched at its edge does not). Passes on both engines.
- `experiments/engine_check.py`: `engine_probe.py` now runs every pool with the flag off and on; engines equal
  (20,244 values; the flag changes 3,167 of the 3,373 `0x88e6` probe lines, fees up), v6_validate cases equal.
- `cargo test` passes.

`gamma_maker_defense_ethusdc_v3_2.py`: `FEE_IN_RANGE_LIQUIDITY=1` turns the flag on and adds `-feeinrange` to the
result folder; default off (the numbers so far, reproduced: $295,613.75 reinvest on / $222,864.46 off).

## v3.2 result ($100k, `0x88e6`, 2021-05-06..2026-08-31, Rust engine)

Raw: `result/quan1213/` in the main checkout (four run folders, logs, `compare_v32.py`).

**1. Flag on, script unchanged.** v3.2's depth slippage model reads the same `currentLiquidity`
(`gamma_maker_defense_ethusdc_v3_2.py`, `execute_swap`), so the flag also makes the rebuild swaps pay more:

| | reinvest off: flag off | on | reinvest on: flag off | on |
|---|---|---|---|---|
| fees (USD) | 96,244 | 96,546 (+0.31%) | 149,103 | 155,111 (+4.03%) |
| swap cost in quote | 3,189 | 5,179 | 6,629 | 9,023 |
| end value | 222,864 | 220,393 (−1.11%) | 295,614 | 298,873 (+1.10%) |
| max DD, UTC-0 daily % | −17.82% | −19.35% | −24.16% | −24.10% |

**2. Fee effect alone: depth fixed at the pool's own liquidity** (scratch copy, depth = data `currentLiquidity`
without ours, in both arms; same swap costs, so only the fee changes):

| | reinvest off: flag off | on | reinvest on: flag off | on |
|---|---|---|---|---|
| fees (USD) | 93,204 | 95,481 (**+2.44%**) | 144,551 | 153,412 (**+6.13%**) |
| LP value | 122,479 | 122,479 | 284,858 | 294,316 |
| end value | 215,684 | 217,961 (+1.06%) | 286,019 | 295,603 (+3.35%) |
| max DD, UTC-0 daily % | −20.48% | −20.24% | −24.15% | −24.10% |

Fees by year, reinvest off: 2021 +2.4%, 2022 +1.1%, 2023 +1.0%, 2024 +2.0%, 2025 +6.5%, 2026 +2.4%; reinvest on
+2.8 / +2.1 / +2.4 / +4.8 / +15.9 / +8.6%. The +2.44% (reinvest off) matches the audit's estimate (+2.49%). Reinvest
gains more: compounding puts more capital in the ladder, and 2025 (many out-of-range bands) gains most.

## Open

- **Depth model counts our own liquidity.** With our liquidity removed from the depth, v3.2's swap cost (reinvest off)
  is $6,150, not $3,189: the old model treated our own ladder (being taken down at the rebuild) as depth. The flag
  halves the problem (out-of-range bands leave the depth). Decide whether the validation run's depth uses the pool's
  liquidity only; it is a v3.2 cost-model choice, not part of this engine fix.
- JIT liquidity (end-of-minute pool liquidity hides it): the fee share stays overstated by an unknown amount.
