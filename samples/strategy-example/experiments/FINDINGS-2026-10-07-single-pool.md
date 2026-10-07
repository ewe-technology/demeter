# Single-pool scan: other strategies and a dynamic ±20% (2026-10-07)

Dino: "先針對單一pool eth/usdc and wbtc/eth 看各自有沒其他策略可以有更好的報酬", then "試著看能不能找到什麼指標或訊號讓+-20%變成動態的".

## 1. Other strategy families (fast screen, `experiments/single_pool_scan.py`)

Not demeter: daily decisions, LP fees per minute from the pool's own swaps x our share of active liquidity, flat 0.1% swap cost,
gas not charged, signals from Binance daily closes. Full history: ETH/USDC `0x88e6` 2021-05-06..2026-09-17 (USD), WBTC/ETH
`0x4585` 2021-11-02..2026-09-17 (BTC). Baselines are the demeter equity curves of earlier runs, measured with the same daily
metric (so their max DD reads deeper than demeter's minute figure). Summaries and curves: main checkout
`result/single_pool_scan/`.

| strategy (CAGR / max DD) | ETH/USDC | WBTC/ETH (in BTC) |
|---|---|---|
| baseline: spec v1 / v6 | 13.7% / -27.9% | -0.6% / -32.3% |
| best variant on record: EXP-158 (`GB`) / EXP-140 (`EB`) | 17.0% / -23.1% | +1.2% / -33.3% |
| hold quote (USD / BTC) | 0% / 0% | 0% / 0% |
| hold base (ETH) | -6.4% / -79.3% | -15.5% / -79.4% |
| 50/50 monthly rebalance | 3.2% / -49.8% | -6.2% / -52.2% |
| full-range LP | 1.7% / -49.3% | -6.5% / -51.2% |
| ±20% LP, recentre on exit | -11.2% / -62.7% | -8.5% / -56.1% |
| EMA100 trend, spot | -10.7% / -71.9% | -6.4% / -53.0% |
| SMA200 trend, spot | **10.7% / -57.4%** | -3.9% / -48.4% |
| EMA100 trend + ±20% LP | -5.9% / -50.5% | -4.2% / -27.7% |
| vol target 60% (+ EMA100) | 6.5% / -52.1% | -9.4% / -60.5% |
| Bollinger mean reversion, spot | -8.5% / -66.0% | -11.8% / -56.7% |

19 families (table shows the informative ones); none beats the baseline on either pool. On ETH/USDC the closest is SMA200
spot timing (CAGR 3 pts lower, drawdown twice as deep). On WBTC/ETH ETH lost 56% against BTC over the window; every
strategy that holds ETH loses to holding BTC, v6 included (-1.4% total), and only EXP-140 is above zero (+5.8%).
Plain EMA100 spot timing loses on ETH (-10.7% CAGR, 105 switches): v6's edge is the staged refill and the four-account F,
not the EMA crossing itself.

## 2. Dynamic ladder width

Screen (EMA100-gated LP recentred on exit, width chosen at each build, clamp 10..40%; CAGR):

| width signal | ETH/USDC | WBTC/ETH |
|---|---|---|
| fixed 20% / 30% / 40% | -5.9% / -7.9% / -6.6% | -4.2% / -5.9% / -2.5% |
| realized vol 30d x sqrt(30) (EXP-030's rule) | -3.9% | -2.5% |
| relative vol (vs own 365d median) | -6.0% | -4.8% |
| Deribit DVOL one-month move | -4.8% | n/a |
| efficiency ratio ER30 | -6.1% | -2.6% |
| pool fee/LVR 7d, volume ratio, distance to EMA100 | -8.1%, -6.2%, -11.9% | -3.8%, -6.7%, -4.4% |

Fixed widths alone move CAGR by ~2 pts with no order, so no screen gain is clearly above noise. The two signals not yet tried
in v6 went to demeter on v6 itself:

| EXP | width rule | ETH/USDC (spec v1 13.55% / -22.9% / 0.591) | WBTC/ETH (v6 -0.29% / -32.7%) | verdict |
|---|---|---|---|---|
| EXP-165 v6.150 | DVOL/100 x sqrt(30/365), 10..30% | 11.20% / -24.8% / 0.451 | not run (ETH DVOL only) | fail |
| EXP-166 v6.151 | 0.10 + 0.40 x ER30, 10..30% | 9.58% / -31.8% / 0.301 | -1.42% / -34.9% | fail |

Then two widths from v6's own state (Dino: "試試看跟著 refill 階段或 F 變寬度"):

| EXP | width rule | ETH/USDC | WBTC/ETH | verdict |
|---|---|---|---|---|
| EXP-167 v6.152 | 0.10 + 0.20 x F, 10..30% | 10.33% / -24.5% / 0.422 | **0.57%** / -33.1% (win) | fail 1/2 |
| EXP-168 v6.153 | while 0 < F < 1, lower edge at the refill low (10..30%) | 12.93% / -21.8% / 0.592 | -0.69% / -33.6% | fail 0/2 |

With EXP-030 (realized vol, fail) that is five width rules that lose inside v6, from market indicators and from v6's own state.
The closest is EXP-168 on ETH (CAGR -0.6 pt, Calmar equal, max DD 1.1 pts shallower; 7 more rebuilds on each pool). The fixed
±20% stays.

## Next

- Width is done: five rules, none wins on ETH/USDC. Not tried: an asymmetric ladder below EMA100 only (EXP-153/154/164 tried
  it above EMA100).
- WBTC/ETH: no strategy here protects BTC value while ETH falls against BTC other than staying in BTC; the open idea is
  Handoff item 4 in CLAUDE.md (USDC-pool F decides coin vs USD, the coin part LPs in BTC/ETH).
