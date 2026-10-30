# Look-ahead and live audit: ETH-USDC v3.2 / ETH-cbBTC v2.2 (2026-10-29)

Jira QUAN-1214 (stage 2c of QUAN-1209). Two questions: does any rule read data it would not have live, and can every
rule run live as written? Scripts: `gamma_maker_defense_ethusdc_v3_2.py` (mainnet USDC/WETH 0.05% `0x88e6`) and
`gamma_ig_gap_bands_defense_btceth_v2_2.py` (mainnet WBTC/WETH `0x4585`, Base WETH/cbBTC `0x7aea`).

**Verdict: no look-ahead in either strategy; every rule can run live, but one does not run as modelled.** The v3.2
daily claim needs an estimated gas cost of $0.2 or less (spec section 6). The backtest does not model that condition.
On mainnet `0x88e6`, a full-ladder claim fails it on every day of 2021-26 (section 3). So, live on mainnet, v3.2's
rewards and monthly reinvest differ from the backtest. On Base the rule holds as modelled.

## 1. Input checklist

Both strategies act once a day at 00:00 UTC (D+1 00:00 = the judgement on day D's close), in this order: v3.2
range check / follow-F rebuild, claim, reinvest on the 1st; v2.2 claim, rebuild, reinvest on the 1st. The end-of-run
settlement at the last day's 23:59 is a backtest artefact (a final claim), not a rule.

| input | strategy | available | used | live source | look-ahead? |
|---|---|---|---|---|---|
| Binance daily close (ETHUSDT; v2.2 also BTCUSDT, ETHBTC) | both | day D's K-line closes at D+1 00:00:00 | D+1 00:00 (rows read by `timestamp - 1 day`) | Binance `GET /api/v3/klines?interval=1d`, final seconds after 00:00 | no |
| EMA90-120, EMA100(R), F, divergence flag (v3.2), strength (v2.2) | both | with D's close; `ewm(adjust=False)` seeded 2017-08-17, causal | D+1 00:00 | recomputed from the full Binance history since 2017-08-17 (the seed must match) | no |
| pool price (range centre, out-of-range check, LP share, swap price) | both | `price` of the 00:00 row = close tick of the 23:59 minute (`_add_statistic_column`: `close.shift(1)`) | 00:00 | pool `slot0` at the execution block | no |
| pool liquidity (`currentLiquidity`) | v3.2 depth slippage; engine fee share | end of the 00:00 minute (last swap's liquidity) | 00:00 swap cost; every minute's fee | pool `liquidity()` | cost model only, <= 1 minute ahead, no decision reads it |
| ETH/USD (USDC valued in ETH, the $5 claim / reinvest floors) | v2.2 | `0x88e6` price, same `shift(1)` convention; `ffill` + leading `bfill` only | 00:00 | `0x88e6` `slot0` or Chainlink ETH/USD | no |
| unclaimed fees, reward balance | both | own position state | 00:00 claim (> $5) and reinvest | position `tokensOwed` / static `collect` call | no |
| month-start reinvest | both | the 1st 00:00, after judgement and claim, at F' (v3.2) / target allocation (v2.2) of the last day of the month | the 1st 00:00 | own state + the D signal above | no |
| Chainlink price (anti-manipulation check, pool vs oracle) | both (spec) | not modelled: the backtest pool price is the fill price | - | Chainlink ETH/USD (v3.2, mainnet `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`); ETH/USD + BTC/USD or cbBTC feeds (v2.2, feed and tolerance from the spec, not checked here) | n/a: live can only skip trades the backtest makes |
| gas estimate (v3.2: claim only if <= $0.2; v2.2: congestion) | both (spec) | not modelled | - | `eth_estimateGas` x base fee x ETH/USD | n/a, see section 3 |

Execution time: the backtest fills at the 00:00 minute; live, Binance publishes the close a few seconds after 00:00
and the transaction lands a block or more later. Same information, a slightly later price.

## 2. Truncation test

Method (`experiments/lookahead_audit.py`): for each test date D both runs start at S = D - 120 days.

* **short**: Binance closes up to D-1 and pool minutes up to the D 00:00 row: what a live bot has at D 00:00;
* **long**: the scripts' own inputs to D+30 (Binance to D+30, minutes to D+30 23:59).

Both runs call the scripts' own `run_test` with the token, pool and parameter settings of their `process_for_date`.
Two settings are fixed for the audit:

* Both strategies run with auto reinvest on, the spec default.
* v3.2 also runs with the fee-in-range engine fix on (QUAN-1213). This is the validation setting; the script's own
  default is off.

The reinvest-off modes are not tested. They use the same paths without the month-start step. Pass = every logged action with execution time <= D 00:00 (v3.2 rebuilds,
reinvest checks, daily fee log; v2.2 daily judgements, rebuilds, reinvest checks), every per-minute net value up to
D 00:00 and every signal row up to D-1 identical. Dates are days with a rebuild in the full runs, one per year.

| strategy | pool | D | rebuilds compared (on D) | reinvests (on D) | daily rows | minutes | result |
|---|---|---|---|---|---|---|---|
| v3.2 | `0x88e6` | 2022-08-01 | 7 (1) | 4 (1) | 120 | 172,801 | PASS |
| v3.2 | `0x88e6` | 2023-03-16 | 6 (1) | 4 (0) | 120 | 172,801 | PASS |
| v3.2 | `0x88e6` | 2024-05-01 | 9 (1) | 4 (1) | 120 | 172,801 | PASS |
| v3.2 | `0x88e6` | 2025-10-07 | 13 (2) | 4 (0) | 120 | 172,801 | PASS |
| v3.2 | `0x88e6` | 2026-07-15 | 7 (1) | 4 (0) | 120 | 172,801 | PASS |
| v2.2 | `0x4585` | 2022-07-28 | 14 (1) | 4 (0) | 120 | 172,801 | PASS |
| v2.2 | `0x4585` | 2023-10-02 | 13 (1) | 4 (0) | 120 | 172,801 | PASS |
| v2.2 | `0x4585` | 2024-10-01 | 26 (1) | 4 (1) | 120 | 172,801 | PASS |
| v2.2 | `0x4585` | 2025-05-11 | 12 (1) | 4 (0) | 120 | 172,801 | PASS |
| v2.2 | Base `0x7aea` | 2026-04-02 | 23 (1) | 4 (0) | 120 | 172,801 | PASS |

Zero mismatches in all 10. Positive control (`--leak`: the signal shifted one day early, so D's decision sees D's
close): **10 of 10 FAIL**, all at the signal row of D-1; on v2.2 2023-10-02 and 2026-04-02 the leak also changes the
action (a rebuild at D 00:00 only in the leaky long run) and the net value from D 00:00. The test detects a one-day
leak, mostly through the signal-row comparison: a one-day shift often leaves F and the actions unchanged.

What it does not cover: a leak inside the same minute (the engine's own convention, section 1) and inputs the scripts
never read (Chainlink, gas).

## 3. Live gaps (not look-ahead)

1. **v3.2 gas <= $0.2 claim condition (spec section 6), mainnet.** At 00:00 UTC with the hourly gas price and ETH/USD
   (`samples/gas_ethereum_hourly.csv`, `eth_usd_hourly.csv`; `lookahead_audit.py gas`), the share of days a claim costs
   <= $0.2:

   | year | one collect (75k gas) | 16 collects + swap (1.32M gas) |
   |---|---|---|
   | 2021 | 0.4% | 0.4% |
   | 2022-2024 | 0% | 0% |
   | 2025 | 9.0% | 0% |
   | 2026 (to 09-17) | 76.5% | 0% |

   Gas units are assumptions (no contract to measure). On `0x88e6` the full-ladder claim never passes: live, rewards
   would be claimed only at rebuilds, so the reward balance and the monthly reinvest are smaller than the backtest's.
   On Base (the contract's LP pool WETH/USDC 0.3% `0x6c56`) gas is cents or less, so the rule holds as modelled. Not
   sized here. Decision 2026-10-30 (Dino): judge v3.2 on `0x88e6` with this condition modelled; `0x6c56` is the
   contract check.
2. **Anti-manipulation check (both).** Not modelled. Live it can only skip or delay a trade the backtest makes, on days
   the pool and Chainlink disagree beyond the spec's tolerance.
3. **Execution delay (both).** Live fills seconds to minutes after 00:00 at that moment's pool price; the backtest uses
   the 23:59 close. Unsized; no rule depends on the exact minute.
4. **End-of-minute liquidity (v3.2 slippage, engine fee share).** Up to one minute ahead in a cost estimate, the same
   convention as `REPRO-2026-10-29-remix-v3_2-v2_1.md` section 4 item 3.

## 4. Reproduce

    cd samples/strategy-example          # Rust engine, $PY = ../../.venv-rs/bin/python, no PYTHONPATH
    $PY experiments/lookahead_audit.py v32           # 5 dates, ~1 min
    $PY experiments/lookahead_audit.py v22           # 5 dates, ~1 min (Base needs base-*.minute.csv names)
    $PY experiments/lookahead_audit.py v32 --leak    # positive control, must FAIL
    $PY experiments/lookahead_audit.py gas

Raw runs and `summary_*.csv`: `result/quan1214_lookahead/` in the main checkout.
