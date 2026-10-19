# EXP-179: added elements on ETH-cbBTC MGL v2 (v2 untouched), WBTC/WETH `0x4585`, IS to 2024 / OOS 2025-26

- Jira: QUAN-1173 (subtask of QUAN-1107)
- Status: pre-registered
- Pre-registration commit: ______ · Result commit: ______

Goal (Dino, 2026-10-19): "在v2上新增一些因子或濾網，找到比v2好的策略", clarified after EXP-178: "原來的元素不動的情況下，
新增其他元素" — every v2 element stays as it is; a variant may only add a new element. EXP-178's two counted variants
(`keep50`, `f2low`) changed existing elements and do not count for this goal; its three added ones (`rconfirm3`, `divG`,
`btctrend`) lost in-sample.

## Hypothesis

v2 decides everything from two price series (G, R) with EMA rules. Information it does not use — derivatives positioning
(funding), implied and realized volatility, stablecoin liquidity, the long and weekly trend, ETH's own USD momentum, and
how often it trades — may tell it when to hold less LP or more ETH. An added layer that uses one of them and leaves
v2's rules unchanged beats v2 in ETH on `0x4585` in-sample and again out-of-sample.

## Change

Base `v2` and runner as in EXP-178 (`experiments/v2_goal.py`, Maker's `gamma_maker_defense_btceth_v1.py` at
maker-defense 5cec767, Rust engine; reproduces Maker's 2023 x1.300 / 2025 x1.157). Each variant adds ONE element on top
of v2's output; v2's constants and rules are not edited (text replacements `fundhot` .. `cooldown7` in `VARIANTS`).

Six filters share one action, fixed here: F' = F x 0.5 while the filter is on. The halved part follows v2's own
allocation (USDC while ETH is strong, BTC while weak). A flag judged on day D's close acts at D+1 00:00, like v2's F.

| variant | added element | rule (all constants fixed here) | data |
|---|---|---|---|
| `fundhot` | funding overheat filter | ETHUSDT perp funding, mean of the day's prints, 7-day mean > 0.03% / 8h | `samples/binance_funding_ETHUSDT_long.csv` (2020-06..) |
| `dvolhi` | implied-volatility filter | Deribit ETH DVOL > its trailing 365-day 80th percentile (min 90 days) | `samples/deribit_dvol_daily.csv` (2021-03..) |
| `stableflow` | stablecoin liquidity factor | stablecoin market cap below its value 30 days earlier | `samples/flow_daily.csv` (2020-06..) |
| `rvol` | realized-volatility filter | 30-day stdev of G's daily log returns > 1.5 x its trailing 365-day median (min 180) | Binance closes |
| `sma200` | long-trend filter | G < SMA200(G) and SMA200 below its value 20 days earlier | Binance closes |
| `weekly` | weekly confirmation filter | G's last Sunday close < 20-week EMA of weekly closes | Binance closes |
| `ethmom` | ETH momentum override | while ETH is strong and ETH/USD > EMA20 > EMA50 (ETH/USD = G x sqrt(R)), the USDC reserve 1 − F is held as ETH outside the LP (LP, width, kept ETH unchanged) | Binance closes |
| `cooldown7` | rebuild cooldown | a drift rebuild (any share >= 12.5% off target) needs 7 days since the last rebuild; out-of-range, target LP 0 / 100% and USDC 0 rebuilds unchanged | – |

## Pre-registration

- Pool, segments, metric, bar and procedure as EXP-178: `0x4585`; IS 2021-11-02..2024-12-31, OOS 2025-01-01..2026-09-17,
  separate runs from 1 ETH; net value in ETH incl. collected rewards; beats v2 = CAGR above, Calmar >=, max DD no more than
  3 pts deeper; only IS winners run OOS; a variant counts when it beats v2 on both halves. v2 rerun in the same batch.
- Goal reached when at least one added element counts with a margin of 0.1 pt CAGR or more on both halves. If none does,
  a further batch of at most 8 added elements is written from IS results only (committed before it runs); the search
  stops after three batches and reports what it found.

## Result

(pending)

## Deviations

- Two choices are shared by all six filters and fixed before any run: the action (F x 0.5) and the judging lag (D close
  -> D+1). Thresholds (0.03% / 8h, 80th percentile, 30 days, 1.5 x, SMA200, 20 weeks, EMA20 / 50, 7 days) are common
  textbook values, set once here, not tuned.
