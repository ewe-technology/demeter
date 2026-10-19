# EXP-177: ETH-cbBTC spec elements on v3, WBTC/WETH `0x4585`, in-sample to 2024 / out-of-sample 2025-26

- Jira: QUAN-1165 (subtask of QUAN-1107)
- Status: fail (0 of 4 new elements beat v3 on IS and OOS; `sigG` won IS by +6.05 pts, lost OOS on Calmar)
- Pre-registration commit: bac5e12 · Result commit: 7febf00

Task (Dino, 2026-10-19): continue the BTC/ETH AMM strategy; look for new filters or signals in Isao's two ETH-cbBTC
specs, "ETH-cbBTC MGL 規格書 v2（標準模式／複利模式）" (2026-09-30) and "ETH-cbBTC 防禦邏輯 規格書（WB＋ETH強勢25%）"
(2026-09-27).

## Hypothesis

v3 on `0x4585` (EXP-176) runs its whole engine on one series, ETHBTC: the same close drives the exit, the refill and the
70 / 50 share switch, and the retreat always lands in BTC. Isao's ETH-cbBTC design separates two questions: whether
the whole crypto market is falling (G = sqrt(ETH/USD x BTC/USD) drives the four virtual accounts), and which coin is
stronger (R = ETHBTC vs EMA100(R) decides where the retreat goes, how much ETH stays outside the LP and how wide the LP
is). If either part adds information, a one-element change to v3 that imports it beats v3 on `0x4585` in-sample and
again out-of-sample.

## Candidate list: every element of the two specs vs v3

The two specs share one signal logic (MGL v2 section 0: "邏輯不變"); MGL v2 adds reward handling and implementation
definitions only.

| # | spec element | v3 on `0x4585` | test |
|---|---|---|---|
| 1 | F engine price G = sqrt(ETHUSDT x BTCUSDT) | ETHBTC | **new: `sigG`** |
| 2 | EMA exit needs EMA_n below its value 20 days earlier | no slope test | already run: EXP-176 `exitslope` (BTC IS fail) |
| 3 | ETH strength R vs EMA100(R) | same test (v3's close > EMA100 on ETHBTC) drives the 70 / 50 share | no change |
| 4 | ETH strong: LP F x 75% + F x 25% held as ETH outside the LP | LP = F, share 70 / 50 inside the LP | **new: `hold25`** |
| 5 | retreat to BTC when ETH is weak, to USDC when strong | retreat always to the quote (BTC) | not testable: the book holds the pool's two tokens only (see Deviations) |
| 6 | real LP width +-10% while strong, +-20% while weak | +-20% always | **new: `width10s`** |
| 7 | real LP: one uniform band, ETH / BTC half each at the centre | 8 + 8 band inverted gaussian valley | **new: `uniform1`** |
| 8 | refill ladder x1.0 (+5 / 8.33 / 11.67 / 15%) | +7.5 / 12.5 / 17.5 / 22.5% | already run: EXP-176 `ladderv1` (BTC IS fail) |
| 9 | out-of-range rebuild recentres on both sides | lower exit goes to quote, follow re-enters | already run: EXP-176 `lowrecentre` (BTC IS = v3) |
| 10 | no divergence flag | flag at +40% / +20% | already run: EXP-176 `nodiv` (flag never fires on ETHBTC IS) |
| 11 | reward compounding (MGL v2 compound mode) | rewards paid out | already run: EXP-176 `compound` (BTC IS fail); reward handling, not a signal |
| - | four EMA90-120 accounts, virtual +-20% valley, 25 / 70 / 50 virtual share, stop x0.80, rebuild x1.20, 3-day stage-1 confirm, follow 12.5%, UTC 00:00 judging | same as v3 | no change |
| - | 25% success fee, $5 claim rule, execution fees, Base pool, tick conversion | backtest has none | not a strategy element |

## Change

Base: v3 exactly as in EXP-176 (`experiments/v3_goal.py`, Maker's `gamma_maker_defense_ethusdc_v3.py` at `maker-defense`
5cec767, ETH base / WBTC quote, 2 WBTC book, engine on Binance ETHBTC closes from 2017-08-17, pool fee + depth slippage).
Each variant changes one element; the exact text replacements are `sigG`, `hold25`, `width10s`, `uniform1` in
`v3_goal.py` (`HOLD25`, `WIDTH10S`, `UNIFORM1`). "Strong" = previous UTC close of ETHBTC > its EMA100, v3's own share
test.

- `sigG`: the four virtual accounts and F run on G = sqrt(ETHUSDT x BTCUSDT) (Maker's `binance_ethusdt_1d.csv` and
  `binance_btcusdt_1d.csv` from 2017-08-17, extended to 2026-09-17 from `samples/binance_daily_closes.csv`;
  `binance_g_ext.csv`). The 70 / 50 share switch and the divergence flag stay on ETHBTC (spec: strength on R).
- `hold25`: while strong, a follow / first build puts F x 75% in the LP and F x 25% in ETH outside the LP (weak: LP = F,
  nothing held). A range-exit rebuild keeps the LP size v3 gives it and the ETH already held. The follow check also
  rebuilds when the held ETH share is 12.5% or more off its target (spec 2.6 "any item").
- `width10s`: each (re)build uses +-10% (same valley, 8 + 8 bands of 1.25%) while strong, +-20% while weak; a strength
  flip alone does not rebuild (spec 2.2).
- `uniform1`: one uniform band from base price x 0.80 to x 1.20; the pre-placement swap goes to the band's own ETH
  value share at its centre, 45.22% (the 70 / 50 share rule cannot apply to a single band; spec: "half each").

## Pre-registration

- Pool: mainnet WBTC/WETH 0.05% `0x4585` (results in BTC). The task is the BTC/ETH strategy; the ETH/USDC pool is not run.
- In-sample (IS): 2021-11-02..2024-12-31. Out-of-sample (OOS): 2025-01-01..2026-09-17. Same as EXP-176; v3 rerun in the
  same batch on each segment.
- Beats v3 on a segment: CAGR above v3, Calmar >= v3, max DD no more than 3 pts deeper (EXP-176 bar).
- Procedure: all four run IS. Only a variant that beats v3 IS gets an OOS run. A variant counts when it beats v3 on IS
  and OOS. Every run is reported.
- Verdict: **pass** if at least one of the four counts, else **fail**. A count with a margin under 0.1 pt CAGR on
  either half is reported as noise (EXP-176 convention).
- Units: net value in BTC. Converting to ETH divides every variant's final value by the same ETHBTC move, so the CAGR
  ranking in ETH is the same; max DD in ETH is not computed.

## Result

Run 2026-10-19, `v3_goal.py is btc v3,sigG,hold25,width10s,uniform1` then `oos btc v3,sigG,uniform1` (Rust engine; raw
runs in the main checkout's `result/v3_goal/btc-{is,oos}-*`). v3 reproduces EXP-176 exactly on both halves.

| variant | IS total / CAGR / max DD / Calmar | beats v3 IS | OOS total / CAGR / max DD / Calmar | beats v3 OOS |
|---|---|---|---|---|
| v3 | −0.7% / −0.21% / −25.8% / −0.008 | – | +15.4% / 8.72% / −14.9% / 0.585 | – |
| `sigG` | +19.7% / 5.84% / −19.8% / 0.295 | yes (+6.05 pts) | +15.9% / 8.99% / −16.0% / 0.562 | **no** (CAGR +0.27 pt, Calmar lower) |
| `uniform1` | +0.2% / 0.05% / −19.5% / 0.003 | yes (+0.26 pt) | +9.3% / 5.36% / −10.7% / 0.502 | no (CAGR −3.36 pts) |
| `hold25` | −3.9% / −1.26% / −29.3% / −0.043 | no | not run | – |
| `width10s` | −4.8% / −1.55% / −24.7% / −0.063 | no | not run | – |

P&L attribution (`v3_goal.attrib`, share of the 2 BTC book: directional / timing / fees / LVR-IL / costs = total):

| run | split | avg F | rebuilds (follow / upper / lower) |
|---|---|---|---|
| v3 IS | −5.7 / +9.2 / +8.7 / −12.2 / −0.6 = −0.7% | 0.17 | 43 / 1 / 0 |
| `sigG` IS | −20.9 / +48.8 / +14.3 / −21.6 / −0.8 = +19.7% | 0.56 | 80 / 1 / 0 |
| `uniform1` IS | −3.6 / +9.1 / +10.9 / −15.8 / −0.4 = +0.2% | 0.17 | 43 / 1 / 0 |
| `hold25` IS | −6.6 / +6.0 / +6.9 / −9.6 / −0.6 = −3.9% | 0.14 | 42 / 1 / 0 |
| `width10s` IS | −5.7 / +12.0 / +12.1 / −22.6 / −0.7 = −4.8% | 0.17 | 43 / 3 / 1 |
| v3 OOS | +0.2 / +20.4 / +2.2 / −5.5 / −1.9 = +15.4% | 0.20 | 24 / 1 / 0 |
| `sigG` OOS | +0.5 / +24.0 / +6.7 / −13.1 / −2.2 = +15.9% | 0.46 | 37 / 3 / 0 |
| `uniform1` OOS | +0.2 / +13.0 / +7.2 / −9.6 / −1.4 = +9.3% | 0.19 | 24 / 1 / 0 |

Verdict: **fail** — none of the four spec elements beats v3 on both halves of `0x4585`.

- `sigG` (G engine) is the only new signal with a real effect. On G the accounts are invested about three times as
  long (avg F 0.56 vs 0.17): ETHBTC fell through 2022-24, so v3's own engine stays mostly out, while G follows the USD
  market and stays in. The IS gain is timing (+39.6 pts) bought with more ETH while ETHBTC fell (directional −15.2)
  and a larger LP loss (LP net −7.3 vs −3.5). Out of sample it keeps +0.27 pt CAGR but max DD is 1.1 pt deeper and
  Calmar 0.562 vs 0.585, so it misses the bar. It is a different engine (market trend instead of ETH-vs-BTC trend),
  not a filter on v3, and it nearly doubles the follow rebuilds (80 vs 43 IS).
- `uniform1`: one uniform band earns more fees but loses more to LVR; IS +0.26 pt, OOS −3.4 pts (less timing gain).
- `hold25` and `width10s` lose in-sample. Holding 25% of F in ETH outside the LP improves the LP leg a little (LP net
  −2.7 vs −3.5) but loses timing (+6.0 vs +9.2): ETH held outside the LP is not sold on the way down by the LP; the ±10%
  LP while strong earns +3.4 pts fees but loses +10.4 pts more to LVR, and adds range-exit rebuilds.
- Together with EXP-176's runs of the other spec elements (`exitslope`, `ladderv1`, `lowrecentre`, `nodiv`,
  `compound`: none beat v3 on BTC IS), no element of the ETH-cbBTC design improves v3 on `0x4585` as a single change.
  The design may still work as a whole (its own numbers are in ETH, with a USDC retreat this book cannot hold); that is
  a combined-strategy test, not a one-element one.
- Next if the BTC/ETH line continues: the retreat-to-USDC element (needs a third asset in the book, open decision 4 in
  CLAUDE.md), and `sigG` on another BTC/ETH pool (Base `0x7aea`, Arbitrum `0x2f5e`) before any further use.

## Deviations

- Element 5 (retreat to USDC while ETH is strong) is not run: demeter's book holds only the pool's two tokens, and a
  third (USD) asset would also change the unit the result is measured in. It needs new code (a USD reserve valued in
  BTC), so it is listed and left out, decided before any run.
