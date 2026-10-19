# EXP-179: added elements on ETH-cbBTC MGL v2 (v2 untouched), WBTC/WETH `0x4585`, IS to 2024 / OOS 2025-26

- Jira: QUAN-1173 (subtask of QUAN-1107)
- Status: pass (1 of 8 added elements counts: `rvol` realized-vol filter, IS +0.57 / OOS +0.60 pt CAGR in ETH)
- Pre-registration commit: 9da3d3c · Result commit: e7abc44

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

Run 2026-10-19, `v2_goal.py is v2,fundhot,..,cooldown7 3` then `oos v2,rvol 2` (Rust engine; raw runs in the main
checkout's `result/v2_goal/{is,oos}-*`). In ETH, rewards included.

| variant | IS ETH x / CAGR / max DD / Calmar | beats v2 IS | OOS ETH x / CAGR / max DD / Calmar | beats v2 OOS |
|---|---|---|---|---|
| v2 | 4.197 / 57.33% / −26.4% / 2.170 | – | 1.384 / 20.90% / −37.2% / 0.562 | – |
| **`rvol`** | 4.245 / 57.90% / −26.4% / 2.191 | yes (+0.57 pt) | 1.396 / 21.50% / −37.4% / 0.574 | **yes (+0.60 pt)** |
| `fundhot` | 4.167 / 56.98% / −26.4% / 2.156 | no | – | – |
| `sma200` | 3.986 / 54.79% / −37.6% / 1.458 | no | – | – |
| `stableflow` | 3.834 / 52.90% / −36.3% / 1.457 | no | – | – |
| `dvolhi` | 3.682 / 50.95% / −29.3% / 1.740 | no | – | – |
| `weekly` | 3.587 / 49.72% / −37.6% / 1.322 | no | – | – |
| `cooldown7` | 3.367 / 46.76% / −34.9% / 1.341 | no | – | – |
| `ethmom` | 3.269 / 45.39% / −31.7% / 1.433 | no | – | – |

USD (not judged): `rvol` IS x3.270 / USD max DD −53.7%, OOS x1.025 / −53.7% (v2 x3.233 / −53.7%, x1.016 / −53.9%).
Rebuilds IS / OOS: v2 137 / 76, `rvol` 145 / 79.

`rvol` flag (30-day realized vol of G > 1.5 x its 365-day median): on 61 of 1156 IS days and 48 of 625 OOS days, in
spells 2022-06-24..27, 2024-03-19..04-19, 2024-05-20..30, 2024-08-08..09-04, 2025-03-10..30, 2026-02-06..03-07. ETH ratio
by year, v2 -> `rvol`: 2021-2023 identical (1.009 / 2.726 / 1.295; the 2022 spell came while F was already low),
2024 1.190 -> 1.203, 2025 1.139 -> 1.144, 2026 1.212 -> 1.217. No year lost.

Verdict: **pass** — one added element counts with v2 untouched: `rvol`, +0.57 pt CAGR in-sample and +0.60 pt
out-of-sample, same max DD (OOS 0.2 pt deeper), Calmar up on both halves.

- Mechanism: in a volatility spike the filter moves half of the LP allocation to v2's own retreat asset (USDC while ETH
  is strong, BTC while weak) for a few weeks. It sidesteps the LP's loss to sharp two-way moves (and, while strong, part
  of an ETH drawdown), then hands back to v2 when vol normalises.
- Read it as small and event-driven: about six independent spells over five years, gains of 0.005-0.013 ETH ratio per
  year. It is the only added element out of 11 tried (EXP-178 `rconfirm3` / `divG` / `btctrend` and the 8 here) that
  wins in-sample, so chance cannot be ruled out. Next: confirm on another BTC/ETH pool (Base `0x7aea`, Arbitrum `0x2f5e`)
  before use.
- Everything that cuts F on a slower or broader signal (SMA200, weekly, stablecoin flow, DVOL percentile) loses: in ETH
  terms v2 already exits crashes through its own EMAs, and an extra cut mostly keeps it in USDC while ETH recovers
  (max DD in ETH deepens to −36..−38%). Adding ETH exposure on USD momentum (`ethmom`) and trading less (`cooldown7`) also
  lose clearly; funding overheat barely fires on this window (−0.35 pt).

## Deviations

- Two choices are shared by all six filters and fixed before any run: the action (F x 0.5) and the judging lag (D close
  -> D+1). Thresholds (0.03% / 8h, 80th percentile, 30 days, 1.5 x, SMA200, 20 weeks, EMA20 / 50, 7 days) are common
  textbook values, set once here, not tuned.
